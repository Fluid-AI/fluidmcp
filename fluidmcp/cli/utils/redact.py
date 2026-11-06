"""
Centralized secret redaction for logs, exception messages and subprocess output.

This module is the single source of truth for scrubbing credentials out of any
text that may end up in application logs (Railway, Docker, journald, ...),
HTTP error responses or exception tracebacks.

Redaction is the *last* line of defence. Code should first avoid putting
secrets into log messages at all - use :func:`redact_command` and
:func:`redact_mapping` when a command line or configuration has to be logged.

:func:`redact_secrets` applies two layers:

1. **Value-based redaction** - the literal values of
   - sensitive environment variables of this process (``GITHUB_TOKEN``,
     ``OPENAI_API_KEY``, ``FMCP_BEARER_TOKEN``, ``MONGODB_URI``, ...),
   - secrets registered at runtime with :func:`register_secret` /
     :func:`register_secrets_from_mapping` (e.g. API keys from MCP server
     ``env`` blocks or LLM model configs that never touch ``os.environ``),
   - secrets passed explicitly via ``extra_secrets``,
   each also in its Base64 forms (raw, and ``x-access-token:<secret>`` as used
   by HTTP Basic auth). This catches opaque keys with no recognizable format.

2. **Pattern-based redaction** - well-known credential shapes:
   - credentials embedded in URLs (``scheme://user:pass@host``) and sensitive
     URL query parameters (``?key=``, ``?access_token=``, ``&sig=``, ...)
   - ``Authorization`` / ``Proxy-Authorization`` header values, Bearer tokens
   - provider keys: GitHub, OpenAI, Anthropic, Google/Gemini, Hugging Face,
     AWS, Slack, Stripe, SendGrid, GitLab, npm, Replicate, Groq, ...
   - JWTs and Google OAuth access tokens
   - PEM private keys
   - ``key=value`` / ``"key": "value"`` pairs whose key looks sensitive
     (password, secret, token, api_key, client_secret, AccountKey, ...)
"""

from __future__ import annotations

import base64
import logging
import os
import re
import sys
import threading
from typing import Any, Iterable, List, Mapping, Optional, TextIO

REDACTED = "***REDACTED***"

# Shortest value treated as a secret for literal (value-based) redaction.
# Shorter values ("true", "8080", ...) would cause false positives.
_MIN_SECRET_LENGTH = 8

# --------------------------------------------------------------------------- #
# Sensitive names
# --------------------------------------------------------------------------- #

# Names (env vars, dict keys, header names) whose values are secrets.
_SENSITIVE_NAME = re.compile(
    r"(token|secret|passw(or)?d|[_\-]pwd$|api[_\-]?key|apikey|access[_\-]?key|private[_\-]?key|"
    r"account[_\-]?key|shared[_\-]?access|credential|auth|cookie|"
    r"connection[_\-]?string|conn[_\-]?str|dsn|signature|passphrase|"
    r"(^|[_\-])key$|^key$|_pat$|^pat$)",
    re.IGNORECASE,
)

# Names that look sensitive but are not (avoid redacting harmless config).
_NON_SENSITIVE_NAME = re.compile(
    r"(^|[_\-])(author|authority|oauth[_\-]?url|auth[_\-]?(url|uri|mode|type|method|enabled|required|provider|header[_\-]?name)|"
    r"token[_\-]?(file|path|url|uri|type|limit|count|expir\w*|ttl)|tokenizer\w*|"
    r"(max|min|num|total|prompt|completion|input|output|cached|reasoning)[_\-]?(new[_\-]?)?tokens?|"
    r"key[_\-]?(file|path|id[_\-]?name|name|rotation|config)|secret[_\-]?(file|path|name))$",
    re.IGNORECASE,
)

# URL-ish names: only treated as secret when the value embeds credentials.
_URL_NAME = re.compile(r"(url|uri|endpoint|host)$", re.IGNORECASE)

# Sections of a config whose values are always masked when logging a mapping.
_ALWAYS_MASKED_SECTIONS = {"env", "environment", "headers", "http_headers", "extra_headers"}


def is_sensitive_name(name: Any) -> bool:
    """Return True if a variable/key/header name denotes a secret value."""
    if not isinstance(name, str) or not name:
        return False
    if _NON_SENSITIVE_NAME.search(name):
        return False
    return bool(_SENSITIVE_NAME.search(name))


# Connection-string schemes whose passwords are often written unencoded.
_DB_SCHEMES = re.compile(
    r"^(mongodb(\+srv)?|postgres(ql)?(\+\w+)?|mysql(\+\w+)?|mariadb|redis|rediss|amqps?|mssql|sqlserver)$"
)


def _has_url_credentials(value: str) -> bool:
    return bool(_URL_CREDENTIALS.search(value)) or _url_password(value) is not None


# --------------------------------------------------------------------------- #
# Pattern-based redaction
# --------------------------------------------------------------------------- #

# scheme://<userinfo>@host  ->  scheme://***REDACTED***@host
# The userinfo match is greedy and may contain '@', so it extends to the LAST
# '@' before the host: an unencoded '@' in a password (mongodb://u:p@ss@host)
# is fully covered. It stops at '/', whitespace and quotes so path segments
# such as https://unpkg.com/@scope/pkg@1.0 are not mistaken for credentials.
_URL_CREDENTIALS = re.compile(
    r"(?P<scheme>\b[a-zA-Z][a-zA-Z0-9+.\-]*://)(?P<userinfo>(?![*:]+@)[^/\s'\"<>]+)@"
)

# Database connection strings: passwords are often written unencoded and may
# contain '@', ':', '/', '#', '?' or '%'. Extend to the LAST '@' that is followed
# by a host list (host[:port][,host[:port]]...) and then '/', '?', end or space.
_DB_URL_CREDENTIALS = re.compile(
    r"(?P<scheme>\b(?:mongodb(?:\+srv)?|postgres(?:ql)?(?:\+\w+)?|mysql(?:\+\w+)?|mariadb|redis|rediss|"
    r"amqps?|mssql|sqlserver)://)(?P<userinfo>(?![*:]+@)[^\s'\"<>]+)@"
    r"(?=[A-Za-z0-9.\-_\[\]:,]+(?:[/?\s'\"<>]|$))",
    re.IGNORECASE,
)

# Sensitive query-string parameters: ?key=..., &access_token=..., &sig=...
_QUERY_SECRET = re.compile(
    r"(?P<prefix>[?&](?:key|api[_\-]?key|apikey|access[_\-]?token|refresh[_\-]?token|id[_\-]?token|"
    r"token|auth|client[_\-]?secret|password|passwd|secret|sig|signature|x-amz-signature|"
    r"x-amz-security-token|x-amz-credential|code)=)(?P<value>[^&\s#'\"<>]+)",
    re.IGNORECASE,
)

# Authorization headers: the whole value (scheme + credentials) up to end of value.
_AUTH_HEADER_VALUE = re.compile(
    r"(?P<prefix>\b(?:proxy-)?authorization[\"']?\s*[:=]\s*[\"']?)"
    r"(?P<value>(?!\*\*\*REDACTED)[^\"'\r\n,}]+)",
    re.IGNORECASE,
)

# "Bearer <token>" / "Basic <credentials>" anywhere in free text.
_BEARER_BASIC = re.compile(
    r"(?P<prefix>\b(?:Bearer|Basic)\s+)(?P<value>(?!\*\*\*REDACTED)[A-Za-z0-9+/=_\-.~]{12,})",
    re.IGNORECASE,
)

# Provider / well-known token formats. Order matters: specific before generic.
_TOKEN_PATTERNS = [
    # PEM private keys (multi-line)
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----", re.DOTALL),
    # GitHub: classic, OAuth, user/server-to-server, refresh, fine-grained
    re.compile(r"\b(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{10,}"),
    # Anthropic (sk-ant-...), OpenAI (sk-..., sk-proj-..., sk-svcacct-..., sk-admin-...)
    re.compile(r"\bsk-(?:ant-|proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{16,}"),
    # Google API keys (Gemini, Maps, ...), Google OAuth access tokens, OAuth client secrets
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"\bya29\.[0-9A-Za-z_\-]{20,}"),
    re.compile(r"\bGOCSPX-[0-9A-Za-z_\-]{20,}"),
    # Hugging Face
    re.compile(r"\bhf_[A-Za-z0-9]{20,}"),
    # AWS access key IDs
    re.compile(r"\b(?:AKIA|ASIA|ABIA|ACCA|AROA|AIDA)[0-9A-Z]{16}\b"),
    # Slack
    re.compile(r"\bxox[abposr]-[A-Za-z0-9\-]{10,}"),
    # Stripe / generic prefixed keys (sk_live_, pk_test_, rk_live_, tok_, key_)
    re.compile(r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{10,}"),
    # SendGrid
    re.compile(r"\bSG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}"),
    # GitLab, npm, PyPI, Groq, Perplexity, DigitalOcean, Shopify, Twilio-style
    re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bnpm_[A-Za-z0-9]{30,}"),
    re.compile(r"\bpypi-[A-Za-z0-9_\-]{50,}"),
    re.compile(r"\bgsk_[A-Za-z0-9]{20,}"),
    re.compile(r"\bpplx-[A-Za-z0-9]{20,}"),
    re.compile(r"\bdop_v1_[a-f0-9]{40,}"),
    re.compile(r"\bshp(?:at|ss|ca|pa)_[a-fA-F0-9]{20,}"),
    # JWT (header.payload.signature) - covers OAuth access/ID tokens, Azure AD tokens, ...
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
]

# Replicate API keys keep their prefix for debuggability.
_REPLICATE_KEY = re.compile(r"\br8_[A-Za-z0-9]{20,}\b")

# Common API key prefixes (sk_, pk_, tok_, key_).
_PREFIXED_KEY = re.compile(r"\b(sk|pk|tok|key)_[A-Za-z0-9_\-]{10,}\b", re.IGNORECASE)

# key=value / key: value / "key": "value" where the key looks sensitive.
# Covers JSON payloads, Python dict reprs, env-style lines, Azure connection
# strings (AccountKey=...;) and MongoDB/ODBC style "Password=...".
_SENSITIVE_KV = re.compile(
    r"(?P<key>\b[\w\-]*(?:password|passwd|pwd|secret|token|api[_\-]?key|apikey|access[_\-]?key|"
    r"private[_\-]?key|account[_\-]?key|shared[_\-]?access[_\-]?(?:key|signature)|credential|"
    r"client[_\-]?secret|passphrase|session[_\-]?token)s?[\"']?)"
    r"(?P<sep>\s*[=:]\s*[\"']?)"
    r"(?P<value>(?!\*\*\*REDACTED)[^\s\"',;&}\]]{4,})",
    re.IGNORECASE,
)


def _apply_patterns(text: str) -> str:
    text = _DB_URL_CREDENTIALS.sub(lambda m: f"{m.group('scheme')}{REDACTED}@", text)
    text = _URL_CREDENTIALS.sub(lambda m: f"{m.group('scheme')}{REDACTED}@", text)
    text = _QUERY_SECRET.sub(lambda m: f"{m.group('prefix')}{REDACTED}", text)
    text = _AUTH_HEADER_VALUE.sub(lambda m: f"{m.group('prefix')}{REDACTED}", text)
    text = _BEARER_BASIC.sub(lambda m: f"{m.group('prefix')}{REDACTED}", text)
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub(REDACTED, text)
    text = _REPLICATE_KEY.sub(f"r8_{REDACTED}", text)
    text = _PREFIXED_KEY.sub(lambda m: f"{m.group(1)}_{REDACTED}", text)
    text = _SENSITIVE_KV.sub(_kv_replacement, text)
    return text


def _kv_replacement(match: "re.Match") -> str:
    key = match.group("key").strip("\"'")
    if _NON_SENSITIVE_NAME.search(key):  # e.g. max_tokens=1000, prompt_tokens: 12
        return match.group(0)
    return f"{match.group('key')}{match.group('sep')}{REDACTED}"


# --------------------------------------------------------------------------- #
# Value-based redaction
# --------------------------------------------------------------------------- #

_lock = threading.Lock()
_registered_secrets: set = set()
_variant_cache: dict = {}


def _secret_variants(secret: str) -> List[str]:
    """Return the secret plus its Base64-encoded forms (cached)."""
    cached = _variant_cache.get(secret)
    if cached is not None:
        return cached
    variants = {secret}
    for raw in (secret, f"x-access-token:{secret}"):
        data = raw.encode("utf-8")
        std = base64.b64encode(data).decode("ascii")
        variants.update((std, std.rstrip("="), base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")))
    result = sorted((v for v in variants if len(v) >= _MIN_SECRET_LENGTH), key=len, reverse=True)
    with _lock:
        if len(_variant_cache) > 4096:
            _variant_cache.clear()
        _variant_cache[secret] = result
    return result


def _url_password(value: str) -> Optional[str]:
    """
    Return the password component of a credential-bearing URL.

    Used for values known to be a single URL (env vars, config values), so it
    splits on the LAST '@' and tolerates unencoded '@', ':', '/', '#' and '?'
    in the password, which the free-text pattern cannot safely do.
    """
    if not isinstance(value, str) or "://" not in value:
        return None
    scheme, after = value.split("://", 1)
    scheme = scheme.rsplit(None, 1)[-1].lower() if scheme.strip() else ""
    parts = after.split()
    rest = parts[0] if parts else ""
    if not _DB_SCHEMES.match(scheme):
        # Web URLs: userinfo cannot contain '/', so the authority ends at the
        # first '/' (prevents https://unpkg.com/@scope/pkg@1.0 false positives).
        rest = rest.split("/", 1)[0]
    if "@" not in rest:
        return None
    userinfo = rest.rsplit("@", 1)[0]
    if not userinfo:
        return None
    return userinfo.split(":", 1)[1] if ":" in userinfo else userinfo


def register_secret(value: Any) -> None:
    """
    Register a secret value so it is redacted from all subsequent output,
    even if it does not match any known credential pattern. For URLs with
    embedded credentials, the password is registered on its own as well.
    """
    if isinstance(value, str) and len(value) >= _MIN_SECRET_LENGTH and value != REDACTED:
        with _lock:
            _registered_secrets.add(value)
        password = _url_password(value)
        if password and password != value:
            register_secret(password)
            from urllib.parse import unquote
            if unquote(password) != password:
                register_secret(unquote(password))


def collect_secrets_from_mapping(obj: Any, _parent_key: Optional[str] = None, _found: Optional[set] = None) -> set:
    """
    Walk a configuration (dicts/lists) and return every value stored under a
    sensitive key - e.g. ``env.OPENAI_API_KEY``, ``api_key``, ``headers.Authorization``,
    ``github_token`` - plus URL values that embed credentials and values passed as
    ``--api-key VALUE`` / ``--api-key=VALUE`` in argument lists.
    """
    found = set() if _found is None else _found
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            if isinstance(value, str):
                if is_sensitive_name(key) or _has_url_credentials(value):
                    found.add(value)
            else:
                collect_secrets_from_mapping(value, key if isinstance(key, str) else None, found)
    elif isinstance(obj, (list, tuple, set)):
        items = list(obj)
        for index, item in enumerate(items):
            if isinstance(item, str):
                if _has_url_credentials(item):
                    found.add(item)
                if item.startswith("-"):
                    flag, has_value, value = item.partition("=")
                    if _is_sensitive_flag(flag):
                        if has_value:
                            found.add(value)
                        elif index + 1 < len(items) and isinstance(items[index + 1], str):
                            found.add(items[index + 1])
            else:
                collect_secrets_from_mapping(item, _parent_key, found)
    return found


def register_secrets_from_mapping(obj: Any) -> None:
    """
    Register every secret found by :func:`collect_secrets_from_mapping`.

    Call this whenever a configuration enters the process (config file, REST API,
    database) so that secrets which never reach ``os.environ`` are still redacted.
    """
    for value in collect_secrets_from_mapping(obj):
        register_secret(value)


def _env_secrets() -> List[str]:
    secrets = []
    for name, value in os.environ.items():
        if not value or len(value) < _MIN_SECRET_LENGTH:
            continue
        if is_sensitive_name(name) or (_URL_NAME.search(name) and _has_url_credentials(value)):
            secrets.append(value)
            password = _url_password(value)
            if password:
                from urllib.parse import unquote
                secrets.extend(p for p in {password, unquote(password)} if len(p) >= _MIN_SECRET_LENGTH)
    return secrets


def _redact_known_values(text: str, extra_secrets: Iterable[Any]) -> str:
    with _lock:
        candidates = set(_registered_secrets)
    candidates.update(_env_secrets())
    candidates.update(s for s in extra_secrets if isinstance(s, str) and len(s) >= _MIN_SECRET_LENGTH)
    if not candidates:
        return text

    variants = set()
    for secret in candidates:
        variants.update(_secret_variants(secret))

    # Longest first so a value is never partially replaced by a shorter one.
    for variant in sorted(variants, key=len, reverse=True):
        if variant in text:
            text = text.replace(variant, REDACTED)
    return text


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def redact_secrets(text: Any, extra_secrets: Iterable[Any] = ()) -> str:
    """
    Redact credentials from ``text``.

    Uses known secret values plus targeted patterns (no "looks random"
    heuristics), so it is safe to apply to every log line without mangling
    UUIDs, hashes or trace IDs.

    Args:
        text: Text that may contain secrets. Non-strings are converted with ``str()``.
        extra_secrets: Additional literal secret values to redact (e.g. a token
            passed as a function argument that is not in the environment).

    Returns:
        The text with all detected secrets replaced by ``***REDACTED***``.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return text
    # Literal values first: catches tokens in any format, including Base64.
    text = _redact_known_values(text, extra_secrets)
    return _apply_patterns(text)


def sanitize_error_message(error_msg: Any) -> str:
    """
    Aggressive redaction for error messages returned to API clients.

    Applies :func:`redact_secrets` and additionally redacts any long
    alphanumeric string containing both letters and digits. That heuristic
    produces false positives (UUIDs, hashes), so it is used for error messages
    only, not for every log line.
    """
    if not isinstance(error_msg, str):
        error_msg = str(error_msg)

    error_msg = redact_secrets(error_msg)

    # Redact long alphanumeric strings that look like tokens (20+ chars, mixed letters/numbers)
    error_msg = re.sub(
        r'\b(?=.*[A-Za-z])(?=.*[0-9])[A-Za-z0-9_\-\.]{20,}\b',
        REDACTED,
        error_msg
    )
    return error_msg


def redact_jsonable(obj: Any, extra_secrets: Iterable[Any] = ()) -> Any:
    """Recursively redact every string inside JSON-like data (dicts, lists)."""
    extra = tuple(extra_secrets)
    if isinstance(obj, str):
        return redact_secrets(obj, extra_secrets=extra)
    if isinstance(obj, Mapping):
        return {k: redact_jsonable(v, extra) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact_jsonable(v, extra) for v in obj]
    return obj


_LOG_TEXT_FIELDS = ("content", "message", "msg", "stderr", "stderr_tail", "error", "detail")


def redact_log_entry(entry: Any) -> Any:
    """
    Sanitize the text fields of a stored log/crash entry in place and return it.
    Used by the persistence layer so child-process output is never stored or
    served unredacted (covers entries written before redaction existed).
    """
    if isinstance(entry, dict):
        for field in _LOG_TEXT_FIELDS:
            value = entry.get(field)
            if isinstance(value, str):
                entry[field] = redact_secrets(value)
            elif isinstance(value, (list, dict)):
                entry[field] = redact_jsonable(value)
    return entry


def redact_mapping(obj: Any, _parent_key: Optional[str] = None) -> Any:
    """
    Return a copy of a configuration that is safe to log.

    - Values under sensitive keys (``api_key``, ``password``, ``github_token``, ...) are masked.
    - ``env`` / ``headers`` sections keep their keys but *all* values are masked,
      because environment variables and headers routinely carry credentials.
    - Remaining strings are passed through :func:`redact_secrets`.
    """
    if isinstance(obj, Mapping):
        masked_section = isinstance(_parent_key, str) and _parent_key.lower() in _ALWAYS_MASKED_SECTIONS
        result = {}
        for key, value in obj.items():
            if masked_section and not isinstance(value, (Mapping, list, tuple)):
                result[key] = REDACTED
            elif is_sensitive_name(key) and isinstance(value, (str, bytes, int, float)) and value not in ("", None):
                result[key] = REDACTED
            else:
                result[key] = redact_mapping(value, key if isinstance(key, str) else None)
        return result
    if isinstance(obj, (list, tuple)):
        if _parent_key in ("args", "command_args") and all(isinstance(i, str) for i in obj):
            return redact_args(obj)
        return [redact_mapping(item, _parent_key) for item in obj]
    if isinstance(obj, str):
        return redact_secrets(obj)
    return obj


def _is_sensitive_flag(text: str) -> bool:
    """
    Check if a command-line flag name indicates that its value is sensitive.

    Uses segment-based matching to catch variants like --my-api-key or
    --prod-access-token while avoiding false positives such as --tokenizer,
    --api-key-rotation or --keyboard-layout.
    """
    flag_name = text.lstrip('-').lower()

    sensitive_flags = {
        'api-key', 'apikey', 'api_key',
        'my-api-key', 'your-api-key',
        'access-key', 'accesskey', 'access_key',
        'secret-key', 'secretkey', 'secret_key',
        'auth-key', 'authkey', 'auth_key', 'authentication',
        'auth-token', 'access-token', 'bearer-token',
        'credential', 'credentials',
    }
    if flag_name in sensitive_flags:
        return True

    segments = re.split(r'[-_]+', flag_name)

    # "pass" is intentionally excluded (--pass-through, --bypass, ...)
    sensitive_segments = {
        "token", "secret", "password", "passwd", "pwd",
        "auth", "authentication", "credential", "credentials",
    }
    if any(seg in sensitive_segments for seg in segments):
        return True

    # Only treat flags as sensitive when they *end* with a sensitive pair
    # (--prod-api-key yes, --api-key-rotation no).
    sensitive_segment_pairs = {
        ("api", "key"), ("access", "key"), ("secret", "key"), ("private", "key"),
        ("access", "token"), ("auth", "token"), ("bearer", "token"), ("api", "token"),
        ("prod", "key"), ("staging", "key"),
        ("prod", "token"), ("staging", "token"),
        ("prod", "secret"), ("staging", "secret"),
    }
    if len(segments) >= 2 and (segments[-2], segments[-1]) in sensitive_segment_pairs:
        return True

    # Three-word combinations like "access-key-id", "aws-access-key"
    if len(segments) >= 3:
        if (segments[-3], segments[-2]) in sensitive_segment_pairs and segments[-1] in {"id", "secret"}:
            return True
        if segments[-2] in ("access", "secret", "api") and segments[-1] in ("key", "token"):
            return True

    return False


def redact_command(command_parts: Iterable[Any]) -> str:
    """
    Render a command line for logging with credentials removed.

    - The value after a sensitive flag (``--api-key VALUE``) is redacted.
    - ``--flag=value`` arguments with a sensitive flag name are redacted.
    - Every other argument is passed through :func:`redact_secrets`
      (catches ``Authorization: Bearer ...`` headers, URL credentials, known keys).

    Example:
        >>> redact_command(["vllm", "--api-key", "secret123"])
        'vllm --api-key ***REDACTED***'
    """
    return ' '.join(redact_args(command_parts))


def redact_args(command_parts: Iterable[Any]) -> List[str]:
    """List form of :func:`redact_command` (keeps argument boundaries)."""
    safe_command = []
    redact_next = False

    for part in command_parts:
        part = str(part)
        if redact_next:
            safe_command.append(REDACTED)
            redact_next = False
            continue

        if '=' in part:
            key, _ = part.split('=', 1)
            if _is_sensitive_flag(key):
                safe_command.append(f"{key}={REDACTED}")
            else:
                safe_command.append(redact_secrets(part))
            continue

        if part.startswith('-') and _is_sensitive_flag(part):
            safe_command.append(part)
            redact_next = True
        else:
            safe_command.append(redact_secrets(part))

    return safe_command


# --------------------------------------------------------------------------- #
# Logging integration
# --------------------------------------------------------------------------- #

def _redact_record(record) -> None:
    """loguru patcher: scrub the message and string ``extra`` fields of a record."""
    record["message"] = redact_secrets(record["message"])
    extra = record.get("extra")
    if extra:
        for key, value in list(extra.items()):
            if isinstance(value, str):
                extra[key] = redact_secrets(value)


_stdlib_installed = False


def _install_stdlib_redaction() -> None:
    """
    Redact stdlib ``logging`` records (uvicorn, httpx, pymongo, asyncio, ...).

    A LogRecord factory is used rather than a handler filter so that every
    record is covered regardless of which logger/handler emits it. The message
    is rendered, redacted and frozen (args cleared); exception text is
    pre-formatted and redacted so handlers do not re-render the raw traceback.
    """
    global _stdlib_installed
    if _stdlib_installed:
        return
    original_factory = logging.getLogRecordFactory()
    formatter = logging.Formatter()

    def redact_arg(value):
        return redact_secrets(value) if isinstance(value, str) else value

    def factory(*args, **kwargs):
        record = original_factory(*args, **kwargs)
        try:
            # 1. Redact each argument, keeping the args shape: some formatters
            #    (e.g. uvicorn's access log) unpack record.args positionally.
            if isinstance(record.args, tuple):
                record.args = tuple(redact_arg(a) for a in record.args)
            elif isinstance(record.args, Mapping):
                record.args = {k: redact_arg(v) for k, v in record.args.items()}
            # 2. Never redact the template alone (that could remove '%s'
            #    placeholders). Render it; if the rendered text still contains a
            #    secret (i.e. in the template itself), freeze the redacted text.
            rendered = record.getMessage()
            redacted = redact_secrets(rendered)
            if redacted != rendered:
                record.msg = redacted
                record.args = None
            if record.exc_info and not record.exc_text:
                record.exc_text = redact_secrets(formatter.formatException(record.exc_info))
            if record.stack_info:
                record.stack_info = redact_secrets(record.stack_info)
        except Exception:  # never let redaction break logging
            pass
        return record

    logging.setLogRecordFactory(factory)
    _stdlib_installed = True


def install_log_redaction() -> None:
    """
    Install redaction for all application logging:

    - a loguru patcher that redacts every record before it reaches any sink
      (``logger.info/warning/error/exception/...``);
    - a stdlib ``logging`` record factory (uvicorn, httpx, third-party libraries).

    Exception tracebacks in loguru are formatted by the sink, so sinks should
    additionally write through :class:`RedactingStream` (or call
    :func:`redact_secrets` on the formatted traceback).
    """
    from loguru import logger

    logger.configure(patcher=_redact_record)
    _install_stdlib_redaction()


def install_redacting_exception_handlers(app) -> None:
    """
    Central guarantee that API error responses never carry secrets.

    Many endpoints build HTTPException details from ``str(e)`` (provider
    errors, git errors, subprocess output). These handlers redact every error
    detail before it is sent, and mask request-body echoes in 422 validation
    errors (which would otherwise reflect submitted env vars/API keys).
    Unhandled exceptions already return a generic 500 without details.
    """
    from fastapi.encoders import jsonable_encoder
    from fastapi.exception_handlers import http_exception_handler
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(StarletteHTTPException)
    async def _redacted_http_exception(request, exc: StarletteHTTPException):
        exc.detail = redact_jsonable(exc.detail)
        return await http_exception_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def _redacted_validation_error(request, exc: RequestValidationError):
        errors = jsonable_encoder(exc.errors())
        # Sensitive values submitted in this request body (e.g. a raw api_key) are
        # redacted wherever pydantic echoes them: input, msg or ctx.
        submitted = collect_secrets_from_mapping(getattr(exc, "body", None))
        for error in errors:
            if not isinstance(error, dict) or "input" not in error:
                continue
            loc = error.get("loc") or ()
            if loc and is_sensitive_name(str(loc[-1])):
                error["input"] = REDACTED  # the field itself is a credential
            else:
                error["input"] = redact_mapping(error["input"])
        return JSONResponse(status_code=422, content={"detail": redact_jsonable(errors, submitted)})


class RedactingStream:
    """
    File-like wrapper that redacts everything written to the wrapped stream.

    Used as a loguru sink (so formatted tracebacks are scrubbed) and to wrap
    ``sys.stdout``/``sys.stderr`` in long-running server processes (so
    ``print()``, uncaught-exception tracebacks and warnings are scrubbed too).
    """

    def __init__(self, stream: Optional[TextIO] = None):
        self._stream = stream

    @property
    def stream(self) -> TextIO:
        # Resolve lazily so pytest's capsys/capfd replacements are honoured.
        return self._stream if self._stream is not None else sys.stderr

    def write(self, message: str) -> int:
        return self.stream.write(redact_secrets(message))

    def writelines(self, lines: Iterable[str]) -> None:
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        flush = getattr(self.stream, "flush", None)
        if flush:
            flush()

    def isatty(self) -> bool:
        isatty = getattr(self.stream, "isatty", None)
        return bool(isatty and isatty())

    def __getattr__(self, name: str) -> Any:
        # Delegate everything else (encoding, fileno, buffer, ...) to the real stream.
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.stream, name)


def install_stream_redaction() -> None:
    """
    Wrap ``sys.stdout`` and ``sys.stderr`` in :class:`RedactingStream`.

    Intended for long-running server processes (``fmcp serve`` / ``run``), whose
    console output is the deployment log. Idempotent. Output written directly to
    the underlying file descriptors by child processes is not affected.
    """
    if not isinstance(sys.stdout, RedactingStream):
        sys.stdout = RedactingStream(sys.stdout)
    if not isinstance(sys.stderr, RedactingStream):
        sys.stderr = RedactingStream(sys.stderr)
