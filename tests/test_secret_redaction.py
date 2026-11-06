"""
Secret-redaction tests for every credential category FluidMCP handles.

Covers both layers:
  * prevention - code paths that used to put secrets into log lines
    (raw configs, command lines, MongoDB URI, generated bearer tokens);
  * redaction - the central redactor applied to loguru, stdlib logging,
    tracebacks, stdout/stderr and API error messages.

All credentials are DUMMY values. Provider-shaped values are assembled from
fragments so secret scanners do not flag this file.
"""

import io
import json
import logging
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from loguru import logger

from fluidmcp.cli.utils.redact import (
    REDACTED,
    RedactingStream,
    install_log_redaction,
    install_stream_redaction,
    is_sensitive_name,
    redact_command,
    redact_mapping,
    redact_secrets,
    register_secret,
    register_secrets_from_mapping,
    sanitize_error_message,
)

# --------------------------------------------------------------------------- #
# Dummy credentials, one or more per category
# --------------------------------------------------------------------------- #
X = "Ab3dEf6hIj9kLm2nOp5qRs8tUv1wXy4z"  # 32 dummy chars

GITHUB_PAT = "github_pat_" + "11DUMMY0000000000_" + X + X[:20]
GITHUB_CLASSIC = "gh" + "p_" + X + "1234"
OPENAI_KEY = "sk-" + "proj-" + X + X
ANTHROPIC_KEY = "sk-" + "ant-api03-" + X + X + "-AA"
GEMINI_KEY = "AI" + "za" + "Sy" + X[:33]
HF_TOKEN = "hf" + "_" + X + "AbCd"
AWS_ACCESS_KEY = "AK" + "IA" + "IOSFODNN7EXAMPLE"
AWS_SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCY" + "EXAMPLEKEY"
AZURE_ACCOUNT_KEY = X + X + "Zz9+/Yy8Xx7Ww6=="
AZURE_CLIENT_SECRET = "Q~" + X[:30]
JWT = "ey" + "JhbGciOiJIUzI1NiJ9" + ".ey" + "JzdWIiOiIxMjM0NTY3ODkwIn0" + "." + X
OAUTH_ACCESS = "ya" + "29." + X + X
OAUTH_REFRESH = "1//" + "0g" + X + X
DB_PASSWORD = "Db-P4ss-" + X[:12]
MONGO_URI = f"mongodb+srv://fmcp_user:{DB_PASSWORD}@cluster0.example.mongodb.net/fluidmcp"
POSTGRES_URI = f"postgresql://admin:{DB_PASSWORD}@db.internal:5432/app"
SLACK_TOKEN = "xo" + "xb-" + "1234567890-" + X
STRIPE_KEY = "sk" + "_live_" + X
SENDGRID_KEY = "SG" + "." + X[:22] + "." + X + X[:11]
REPLICATE_KEY = "r8" + "_" + X
OPAQUE_MCP_KEY = "opaque-mcp-" + X  # third-party key with no recognizable format
PASSWORD = "Sup3r-S3cret-" + X[:10]
BEARER = "bearer-" + X
PEM = "-----BEGIN " + "PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASC\n" + X + "\n-----END " + "PRIVATE KEY-----"

# (category, text containing the secret, secret)
CASES = [
    ("github-pat", f"token {GITHUB_PAT}", GITHUB_PAT),
    ("github-classic", f"GITHUB_TOKEN={GITHUB_CLASSIC}", GITHUB_CLASSIC),
    ("github-url", f"fatal: could not read Password for 'https://{GITHUB_PAT}@github.com'", GITHUB_PAT),
    ("openai", f"openai.AuthenticationError: Incorrect API key provided: {OPENAI_KEY}", OPENAI_KEY),
    ("anthropic", f'{{"x-api-key": "{ANTHROPIC_KEY}"}}', ANTHROPIC_KEY),
    ("anthropic-free", f"using key {ANTHROPIC_KEY} for claude", ANTHROPIC_KEY),
    ("gemini-query", f"GET https://generativelanguage.googleapis.com/v1/models?key={GEMINI_KEY}&alt=json", GEMINI_KEY),
    ("gemini-free", f"GEMINI key {GEMINI_KEY}", GEMINI_KEY),
    ("huggingface", f"HF_TOKEN loaded: {HF_TOKEN}", HF_TOKEN),
    ("aws-access-key", f"AWS key id {AWS_ACCESS_KEY}", AWS_ACCESS_KEY),
    ("aws-secret-key", f"aws_secret_access_key={AWS_SECRET_KEY}", AWS_SECRET_KEY),
    ("aws-secret-json", f'{{"SecretAccessKey": "{AWS_SECRET_KEY}"}}', AWS_SECRET_KEY),
    ("azure-conn-string", f"DefaultEndpointsProtocol=https;AccountName=acct;AccountKey={AZURE_ACCOUNT_KEY};EndpointSuffix=core.windows.net", AZURE_ACCOUNT_KEY),
    ("azure-client-secret", f'{{"client_secret": "{AZURE_CLIENT_SECRET}"}}', AZURE_CLIENT_SECRET),
    ("azure-sas", f"https://acct.blob.core.windows.net/c/b?sv=2022-11-02&sig={X}%2Bx%3D", X),
    ("bearer-header", f"Authorization: Bearer {BEARER}", BEARER),
    ("bearer-free", f"sent Bearer {BEARER} upstream", BEARER),
    ("jwt", f"id_token={JWT}", JWT),
    ("jwt-free", f"decoded {JWT} ok", JWT),
    ("oauth-access", f'{{"access_token": "{OAUTH_ACCESS}", "token_type": "Bearer"}}', OAUTH_ACCESS),
    ("oauth-google", f"google token {OAUTH_ACCESS}", OAUTH_ACCESS),
    ("oauth-refresh", f"refresh_token: {OAUTH_REFRESH}", OAUTH_REFRESH),
    ("mongodb-uri", f"connecting to {MONGO_URI}", DB_PASSWORD),
    ("postgres-uri", f"DATABASE_URL={POSTGRES_URI}", DB_PASSWORD),
    ("odbc-password", f"Server=db;Database=app;User Id=sa;Password={PASSWORD};", PASSWORD),
    ("slack", f"slack token {SLACK_TOKEN}", SLACK_TOKEN),
    ("stripe", f"stripe key {STRIPE_KEY}", STRIPE_KEY),
    ("sendgrid", f"sendgrid {SENDGRID_KEY}", SENDGRID_KEY),
    ("replicate", f"replicate {REPLICATE_KEY}", REPLICATE_KEY),
    ("password-kv", f"password={PASSWORD}", PASSWORD),
    ("password-json", f'{{"user": "a", "password": "{PASSWORD}"}}', PASSWORD),
    ("client-secret-kv", f"client_secret={AZURE_CLIENT_SECRET}", AZURE_CLIENT_SECRET),
    ("authorization-basic", f"Authorization: Basic {X}", X),
    ("authorization-dict", f"{{'Authorization': 'token {X}'}}", X),
    ("pem-private-key", f"key:\n{PEM}\nend", X),
]


@pytest.fixture
def no_env_secrets(monkeypatch):
    """Pattern tests must not pass merely because the value is in os.environ."""
    for name in list(__import__("os").environ):
        if is_sensitive_name(name):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture
def loguru_capture():
    buf = io.StringIO()
    install_log_redaction()
    sink_id = logger.add(RedactingStream(buf), level="DEBUG", format="{message}", diagnose=False)
    yield buf
    logger.remove(sink_id)
    logger.configure(patcher=lambda record: None)


@pytest.fixture
def stdlib_capture():
    install_log_redaction()
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    yield buf
    root.removeHandler(handler)
    root.setLevel(old_level)
    logger.configure(patcher=lambda record: None)


# --------------------------------------------------------------------------- #
# Every category: plain text, nested exception, loguru, stdlib logging, API errors
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("category,text,secret", CASES, ids=[c[0] for c in CASES])
class TestEveryCategory:
    def test_redact_secrets(self, category, text, secret, no_env_secrets):
        out = redact_secrets(text)
        assert secret not in out
        assert REDACTED in out

    def test_loguru_with_nested_exception(self, category, text, secret, no_env_secrets, loguru_capture):
        try:
            try:
                raise ConnectionError(text)
            except ConnectionError as inner:
                raise RuntimeError(f"provider call failed: {inner}") from inner
        except RuntimeError as e:
            logger.error(f"[{category}] {e}")
            logger.exception("traceback follows")
        out = loguru_capture.getvalue()
        assert "ConnectionError" in out
        assert secret not in out

    def test_stdlib_logging(self, category, text, secret, no_env_secrets, stdlib_capture):
        lib_logger = logging.getLogger("httpx")
        lib_logger.info("HTTP Request: %s", text)
        try:
            raise ValueError(text)
        except ValueError:
            lib_logger.exception("request failed")
        out = stdlib_capture.getvalue()
        assert "HTTP Request" in out and "ValueError" in out
        assert secret not in out

    def test_api_error_message(self, category, text, secret, no_env_secrets):
        from fluidmcp.cli.api.management import sanitize_error_message as mgmt_sanitize
        assert secret not in mgmt_sanitize(text)
        assert secret not in sanitize_error_message(RuntimeError(text))


# --------------------------------------------------------------------------- #
# Value-based redaction for opaque / third-party keys
# --------------------------------------------------------------------------- #

class TestOpaqueSecrets:
    def test_env_var_values_are_redacted(self, monkeypatch, no_env_secrets):
        for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "HF_TOKEN",
                     "AWS_SECRET_ACCESS_KEY", "AZURE_CLIENT_SECRET", "AZURE_STORAGE_KEY",
                     "DB_PASSWORD", "SOME_VENDOR_APIKEY", "FMCP_BEARER_TOKEN"):
            value = f"{name.lower()}-{X}"
            monkeypatch.setenv(name, value)
            assert value not in redact_secrets(f"echo {value}"), name

    def test_url_env_var_with_credentials(self, monkeypatch, no_env_secrets):
        monkeypatch.setenv("DATABASE_URL", POSTGRES_URI)
        assert DB_PASSWORD not in redact_secrets(f"pw is {DB_PASSWORD}")

    def test_plain_url_env_var_not_treated_as_secret(self, monkeypatch, no_env_secrets):
        monkeypatch.setenv("MCP_FETCH_URL", "https://registry.fluidmcp.com/fetch-mcp-package")
        line = "fetching https://registry.fluidmcp.com/fetch-mcp-package"
        assert redact_secrets(line) == line

    def test_registered_mcp_server_env_is_redacted(self, no_env_secrets):
        register_secrets_from_mapping({
            "command": "npx",
            "args": ["-y", "@vendor/server", "--api-key", "argkey-" + X],
            "env": {"VENDOR_API_KEY": OPAQUE_MCP_KEY, "PORT": "8080", "LOG_LEVEL": "debugging"},
        })
        out = redact_secrets(f"server said: invalid key {OPAQUE_MCP_KEY} / argkey-{X} on port 8080 debugging")
        assert OPAQUE_MCP_KEY not in out and f"argkey-{X}" not in out
        assert "8080" in out and "debugging" in out  # non-secret values untouched

    def test_llm_registry_registers_api_keys(self, no_env_secrets):
        from fluidmcp.cli.services.llm_provider_registry import (
            clear_registry, get_model_config, initialize_llm_registry,
        )
        key = "llm-opaque-" + X
        try:
            initialize_llm_registry({"m": {"type": "openai", "api_key": key}})
            assert key not in redact_secrets(f"401 for key {key}")
        finally:
            clear_registry()

    def test_replicate_client_registers_key(self, no_env_secrets):
        from fluidmcp.cli.services.replicate_client import ReplicateClient
        key = "repl-opaque-" + X
        ReplicateClient("m", {"model": "owner/model", "api_key": key})
        assert key not in redact_secrets(f"key={key}"[4:])

    def test_base64_forms_redacted(self, no_env_secrets):
        import base64
        register_secret(OPAQUE_MCP_KEY)
        for raw in (OPAQUE_MCP_KEY, f"x-access-token:{OPAQUE_MCP_KEY}"):
            enc = base64.b64encode(raw.encode()).decode()
            assert enc not in redact_secrets(f"blob {enc}")
            assert enc.rstrip("=") not in redact_secrets(f"blob {enc.rstrip('=')}")


# --------------------------------------------------------------------------- #
# Prevention: secrets never put into log messages in the first place
# --------------------------------------------------------------------------- #

class TestPrevention:
    def test_redact_mapping_masks_env_headers_and_sensitive_keys(self):
        cfg = {
            "command": "npx",
            "args": ["-y", "server", "--api-key", OPENAI_KEY, f"--token={HF_TOKEN}", "--port", "8001"],
            "env": {"ANY_NAME": "plain-but-masked", "OPENAI_API_KEY": OPENAI_KEY},
            "headers": {"Authorization": f"Bearer {BEARER}", "Accept": "json"},
            "github_token": GITHUB_PAT,
            "api_key": "x" * 12,
            "max_tokens": 1000,
            "nested": {"client_secret": AZURE_CLIENT_SECRET, "author": "jane"},
        }
        safe = redact_mapping(cfg)
        dumped = json.dumps(safe)
        for secret in (OPENAI_KEY, HF_TOKEN, BEARER, GITHUB_PAT, "x" * 12, AZURE_CLIENT_SECRET, "plain-but-masked"):
            assert secret not in dumped
        assert set(safe["env"]) == {"ANY_NAME", "OPENAI_API_KEY"}  # names kept
        assert safe["args"][:3] == ["-y", "server", "--api-key"] and safe["args"][-1] == "8001"
        assert safe["max_tokens"] == 1000 and safe["nested"]["author"] == "jane"
        assert cfg["env"]["OPENAI_API_KEY"] == OPENAI_KEY  # original untouched

    def test_redact_command(self):
        out = redact_command(["server", "--api-key", OPENAI_KEY, f"--password={PASSWORD}",
                              "--header", f"Authorization: Bearer {BEARER}", f"--db={MONGO_URI}",
                              "--tokenizer", "gpt2"])
        for secret in (OPENAI_KEY, PASSWORD, BEARER, DB_PASSWORD):
            assert secret not in out
        assert "--tokenizer gpt2" in out

    async def test_mcp_spawn_debug_logs_have_no_secrets(self, tmp_path, no_env_secrets, loguru_capture):
        from fluidmcp.cli.repositories import InMemoryBackend
        from fluidmcp.cli.services.server_manager import ServerManager
        opaque = "spawn-opaque-" + X
        config = {
            "id": "s", "name": "s",
            "command": "fmcp-test-nonexistent-binary",
            "args": ["--api-key", opaque, "--header", f"Authorization: Bearer {BEARER}"],
            "env": {"VENDOR_SECRET": opaque, "OPENAI_API_KEY": OPENAI_KEY},
            "working_dir": str(tmp_path), "install_path": str(tmp_path),
        }
        await ServerManager(InMemoryBackend())._spawn_mcp_process("s", config)
        out = loguru_capture.getvalue()
        assert "Spawning process" in out
        for secret in (opaque, BEARER, OPENAI_KEY):
            assert secret not in out

    def test_mongodb_uri_masked_even_with_at_in_password(self):
        from fluidmcp.cli.repositories.database import mask_mongodb_uri
        assert DB_PASSWORD not in mask_mongodb_uri(MONGO_URI)
        weird = "mongodb://user:p@ss@word@host:27017/db"
        assert "p@ss" not in mask_mongodb_uri(weird) and "word" not in mask_mongodb_uri(weird)

    def test_server_logs_masked_mongodb_uri(self):
        source = Path("fluidmcp/cli/server.py").read_text()
        assert "{args.mongodb_uri}" not in source
        assert "mask_mongodb_uri(args.mongodb_uri)" in source

    def test_generated_token_not_printed_when_not_a_tty(self, capsys):
        from fluidmcp.cli.auth import announce_generated_token
        token = "gen-token-" + X
        with patch.object(sys.stdout, "isatty", return_value=False, create=True):
            announce_generated_token(token, Path("/tmp/token.txt"))
        out = capsys.readouterr().out
        assert token not in out
        assert "fmcp token show" in out and "FMCP_BEARER_TOKEN" in out

    def test_generated_token_printed_on_tty(self, capsys):
        from fluidmcp.cli.auth import announce_generated_token
        token = "gen-token-" + X
        with patch.object(sys.stdout, "isatty", return_value=True, create=True):
            announce_generated_token(token)
        assert token in capsys.readouterr().out

    @pytest.mark.parametrize("env_token", [True, False])
    def test_cli_secure_mode_honours_fmcp_bearer_token(self, env_token, monkeypatch, tmp_path, capsys):
        import fluidmcp.cli.server as server
        from fluidmcp.cli import cli
        configured = "configured-token-" + X
        monkeypatch.setenv("HOME", str(tmp_path))
        # cli.main() writes these into os.environ directly. setenv() first makes
        # monkeypatch record the original state (delenv alone records nothing when
        # the variable is absent), so they are restored after the test.
        for name in ("FMCP_SECURE_MODE", "FMCP_BEARER_TOKEN"):
            monkeypatch.setenv(name, "placeholder")
            monkeypatch.delenv(name)
        if env_token:
            monkeypatch.setenv("FMCP_BEARER_TOKEN", configured)
        seen = {}

        async def fake_main(args):
            seen["token"] = __import__("os").environ.get("FMCP_BEARER_TOKEN")

        monkeypatch.setattr(server, "main", fake_main)
        monkeypatch.setattr(sys, "argv", ["fmcp", "serve", "--secure", "--in-memory"])
        try:
            cli.main()
        finally:
            logger.remove()
            logger.configure(patcher=lambda record: None)
            logger.add(sys.stderr)
        out = capsys.readouterr().out
        if env_token:
            assert seen["token"] == configured
            assert "BEARER TOKEN GENERATED" not in out
        else:
            generated = seen["token"]
            assert generated and generated != configured
            assert generated not in out  # capsys stdout is not a TTY
            assert (tmp_path / ".fmcp" / "tokens" / "current_token.txt").read_text() == generated


# --------------------------------------------------------------------------- #
# Console streams (print / uncaught tracebacks) in server processes
# --------------------------------------------------------------------------- #

class TestStreamRedaction:
    def test_print_is_redacted_after_install(self, monkeypatch, no_env_secrets):
        buf_out, buf_err = io.StringIO(), io.StringIO()
        monkeypatch.setattr(sys, "stdout", buf_out)
        monkeypatch.setattr(sys, "stderr", buf_err)
        install_stream_redaction()
        install_stream_redaction()  # idempotent
        assert isinstance(sys.stdout, RedactingStream) and not isinstance(sys.stdout._stream, RedactingStream)
        print(f"debug dump OPENAI_API_KEY={OPENAI_KEY}")
        print(f"conn {MONGO_URI}", file=sys.stderr)
        assert OPENAI_KEY not in buf_out.getvalue() and "debug dump" in buf_out.getvalue()
        assert DB_PASSWORD not in buf_err.getvalue()

    def test_stream_delegates_attributes(self):
        stream = RedactingStream(io.StringIO())
        assert stream.isatty() is False
        assert hasattr(stream, "getvalue")


# --------------------------------------------------------------------------- #
# No false positives on ordinary log lines
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("line", [
    "Secure mode enabled with bearer token authentication",
    "Generated bearer token (shown on interactive terminals only)",
    "Initialized LLM registry with 2 models: {'replicate': 2}",
    "request max_tokens=1000 temperature=0.7 tokenizer=gpt2",
    "author: jane, auth_mode: none, token_type: Bearer",
    "trace_id=550e8400-e29b-41d4-a716-446655440000 commit 3f786850e387550fdab836ed7e6dc881de23001b",
    "Cloned Fluid-AI/fluid-ai-mcp-servers@gemini-image-mcp to /app/.fmcp-packages",
    "POST http://localhost:8099/api/llm/v1/chat/completions 200",
    "Using MongoDB persistence backend at mongodb+srv://***:***@cluster0.example.mongodb.net/db",
    "vllm serve facebook/opt-125m --port 8001 --api-key-rotation daily",
])
def test_no_false_positives(line, no_env_secrets):
    assert redact_secrets(line) == line
