"""
Error handling utilities for FluidMCP.

Provides functions for sanitizing and truncating error messages
to prevent information leakage and client issues.
"""


def truncate_error_message(msg: str, max_len: int = 1000) -> str:
    """
    Truncate error messages to prevent information leakage and client issues.

    Args:
        msg: Error message to truncate
        max_len: Maximum length (default: 1000 characters)

    Returns:
        Truncated message with indicator if truncated
    """
    if len(msg) <= max_len:
        return msg
    return msg[:max_len] + "... [truncated]"


def redact_secrets(text: str) -> str:
    """Redact credential-shaped substrings from text that will be stored or pushed.

    MCP servers frequently echo their own connection strings in error messages
    ("could not connect to postgres://app:hunter2@db:5432/..."). Monitoring
    events travel further than logs — into an external monitoring store, a Slack
    channel, an incident ticket — so that text must be scrubbed before it leaves.

    **Classify before redacting.** Redaction is lossy and can remove the very
    token a failure pattern matches on, so callers should run classification
    against the raw message and store only the redacted form.

    Args:
        text: Untrusted error text, typically from an MCP server.

    Returns:
        The text with credential-shaped substrings replaced.
    """
    import re

    if not isinstance(text, str):
        return str(text)

    # URL userinfo: scheme://user:secret@host -> scheme://user:***@host
    text = re.sub(
        r'([a-zA-Z][a-zA-Z0-9+.-]*://[^:/\s@]+):[^@/\s]+@',
        r'\1:***REDACTED***@',
        text,
    )

    # key=value, key: value, and JSON "key": "value" for credential-named keys.
    # The optional quote after the key name is what makes this match JSON
    # payloads — a very common shape in MCP tool error responses. Quoting is
    # preserved so a redacted JSON error stays parseable for whoever reads it.
    def _mask_kv(match: "re.Match") -> str:
        key, key_quote, separator, value = match.groups()
        if value[:1] in ('"', "'"):
            masked = f"{value[0]}***REDACTED***{value[0]}"
        else:
            masked = "***REDACTED***"
        return f"{key}{key_quote}{separator}{masked}"

    text = re.sub(
        r'\b(password|passwd|pwd|secret|token|api[_-]?key|apikey|auth|credential'
        r'|access[_-]?key|private[_-]?key)(["\']?)(\s*[:=]\s*)'
        r'("[^"]*"|\'[^\']*\'|[^\s,;&)}\]]+)',
        _mask_kv,
        text,
        flags=re.IGNORECASE,
    )

    # Known provider key prefixes
    text = re.sub(r'\br8_[A-Za-z0-9]{16,}\b', 'r8_***REDACTED***', text)
    text = re.sub(
        r'\b(sk|pk|tok|key|ghp|gho|github_pat)[_-][A-Za-z0-9_-]{10,}\b',
        r'\1_***REDACTED***',
        text,
        flags=re.IGNORECASE,
    )

    # Bearer / Basic authorization values
    text = re.sub(
        r'\b(Bearer|Basic)\s+[A-Za-z0-9_\-.=+/]{12,}',
        r'\1 ***REDACTED***',
        text,
        flags=re.IGNORECASE,
    )

    # JWTs (three dot-separated base64url segments)
    text = re.sub(
        r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b',
        '***REDACTED_JWT***',
        text,
    )

    return text
