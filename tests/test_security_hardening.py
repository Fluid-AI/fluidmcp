"""
Security hardening tests (review round 3):

1. No part of a generated bearer token is ever logged.
2. Secure mode: every protected endpoint rejects missing/invalid bearer tokens.
3. Child-process (MCP / LLM server) output is captured, sanitized and safely
   logged, stored and served.
4. GITHUB_TOKEN stays supported for private repo cloning (config precedence).
5. MongoDB URI masking handles @ : / # ? and percent-encoded credentials.
6. No registered secrets in logs, exceptions, tracebacks or API error responses.

All credentials are dummy values.
"""

import asyncio
import io
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from loguru import logger
from pydantic import BaseModel

from fluidmcp.cli.utils.redact import (
    REDACTED,
    RedactingStream,
    install_log_redaction,
    install_redacting_exception_handlers,
    redact_secrets,
    register_secret,
    register_secrets_from_mapping,
)

X = "Qw7eRt4yUi1oPa8sDf5gHj2kLz9xCv6b"
CORRECT_TOKEN = "correct-bearer-" + X
OPAQUE_KEY = "opaque-vendor-key-" + X  # third-party key, no recognizable format
OPENAI_KEY = "sk-" + "proj-" + X + X
JWT = "ey" + "JhbGciOiJIUzI1NiJ9" + ".ey" + "JzdWIiOiIxMjM0NTY3ODkwIn0" + "." + X


@pytest.fixture
def loguru_capture():
    buf = io.StringIO()
    install_log_redaction()
    sink_id = logger.add(RedactingStream(buf), level="DEBUG", format="{message}", diagnose=False)
    yield buf
    logger.remove(sink_id)
    logger.configure(patcher=lambda record: None)


def _track_env(monkeypatch, *names):
    """Make monkeypatch restore names even if code under test sets them directly."""
    for name in names:
        monkeypatch.setenv(name, "placeholder")
        monkeypatch.delenv(name)


# --------------------------------------------------------------------------- #
# 1. Bearer token never logged, not even a prefix
# --------------------------------------------------------------------------- #

class TestNoPartialTokenLogging:
    def test_no_token_slicing_in_log_statements(self):
        """No log/print statement in the codebase interpolates a slice of a token/key/secret."""
        offenders = []
        pattern = re.compile(
            r"(logger\.\w+|print)\(.*\{[^}]*(token|secret|password|api_key|apikey)[^}]*\[[^\]]*:[^\]]*\][^}]*\}",
            re.IGNORECASE,
        )
        for path in Path("fluidmcp").rglob("*.py"):
            for lineno, line in enumerate(path.read_text().splitlines(), 1):
                if pattern.search(line):
                    offenders.append(f"{path}:{lineno}: {line.strip()}")
        assert offenders == []

    def test_server_main_logs_no_token_fragment(self, monkeypatch, tmp_path, capsys, loguru_capture):
        """Run server.py's __main__ token block: neither logs nor stdout carry the token."""
        import runpy

        _track_env(monkeypatch, "FMCP_BEARER_TOKEN", "FMCP_SECURE_MODE")
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(sys, "argv", ["server", "--secure"])
        generated = {}

        def fake_run(coro):
            coro.close()
            generated["token"] = (tmp_path / ".fmcp" / "tokens" / "current_token.txt").read_text()

        with patch("asyncio.run", side_effect=fake_run):
            runpy.run_module("fluidmcp.cli.server", run_name="__main__")

        token = generated["token"]
        output = loguru_capture.getvalue() + capsys.readouterr().out
        assert "Bearer token generated (value not logged)" in loguru_capture.getvalue()
        for fragment in (token, token[:8], token[-8:]):
            assert fragment not in output


# --------------------------------------------------------------------------- #
# 2. Secure mode authentication on every protected endpoint
# --------------------------------------------------------------------------- #

# Intentionally public: health check (Railway), SPA shell, API docs/schema.
PUBLIC_PATHS = {"/health", "/", "/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}


@pytest.fixture
def secure_app(monkeypatch):
    from fluidmcp.cli.repositories import InMemoryBackend
    from fluidmcp.cli.server import create_app
    from fluidmcp.cli.services.server_manager import ServerManager

    _track_env(monkeypatch, "FMCP_BEARER_TOKEN", "FMCP_SECURE_MODE")
    monkeypatch.setenv("FMCP_BEARER_TOKEN", CORRECT_TOKEN)
    monkeypatch.setenv("FMCP_SECURE_MODE", "true")

    async def build():
        db = InMemoryBackend()
        await db.connect()
        manager = ServerManager(db)
        await manager.db.save_server_config({"id": "srv", "name": "srv", "command": "echo", "args": []})
        manager.configs["srv"] = {"id": "srv", "name": "srv", "command": "echo", "args": []}
        return await create_app(db, manager, secure_mode=True, token=CORRECT_TOKEN)

    return asyncio.run(build())


def _http_routes(app):
    for route in app.routes:
        for method in sorted((getattr(route, "methods", None) or set()) - {"HEAD", "OPTIONS"}):
            yield method, route.path


def _call(client, method, path, headers):
    url = re.sub(r"\{[^}]+\}", "srv", path)
    body = {} if method in ("POST", "PUT", "PATCH") else None
    return client.request(method, url, headers=headers, json=body)


class TestSecureModeAuthentication:
    @pytest.mark.parametrize("path", [
        "/api/servers",
        "/api/servers/srv/status",
        "/api/servers/srv/logs",
        "/api/servers/srv/instance/env",
        "/api/servers/srv/tools",
    ])
    def test_previously_open_endpoints_now_require_token(self, secure_app, path):
        client = TestClient(secure_app, raise_server_exceptions=False)
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer wrong-" + X}).status_code == 401
        assert client.get(path, headers={"Authorization": f"Basic {CORRECT_TOKEN}"}).status_code == 401
        assert client.get(path, headers={"Authorization": f"Bearer {CORRECT_TOKEN}"}).status_code != 401

    def test_every_non_public_route_rejects_missing_and_invalid_tokens(self, secure_app):
        client = TestClient(secure_app, raise_server_exceptions=False)
        failures = []
        checked = 0
        for method, path in _http_routes(secure_app):
            if path in PUBLIC_PATHS or path.startswith("/assets"):
                continue
            checked += 1
            for headers in ({}, {"Authorization": "Bearer wrong-" + X}):
                status = _call(client, method, path, headers).status_code
                if status not in (401, 403):
                    failures.append(f"{method} {path} {headers or 'no-token'} -> {status}")
        assert checked > 50
        assert failures == []

    def test_valid_token_is_accepted(self, secure_app):
        client = TestClient(secure_app, raise_server_exceptions=False)
        resp = client.get("/api/servers", headers={"Authorization": f"Bearer {CORRECT_TOKEN}"})
        assert resp.status_code == 200

    def test_empty_configured_token_never_authenticates(self, secure_app, monkeypatch):
        monkeypatch.setenv("FMCP_BEARER_TOKEN", "")
        client = TestClient(secure_app, raise_server_exceptions=False)
        assert client.get("/api/servers", headers={"Authorization": "Bearer "}).status_code in (401, 403)

    def test_public_health_still_open(self, secure_app):
        client = TestClient(secure_app, raise_server_exceptions=False)
        assert client.get("/health").status_code == 200


# --------------------------------------------------------------------------- #
# 3. Child-process output: captured, sanitized, safely logged/stored/served
# --------------------------------------------------------------------------- #

class TestChildProcessOutput:
    def test_piped_stderr_sanitized_at_ingestion(self, tmp_path, loguru_capture):
        """package_launcher drains PIPE stderr: buffer, logs and log file are all sanitized."""
        from fluidmcp.cli.services.package_launcher import get_stderr_tail, start_stderr_drainer, clear_stderr_buffer
        register_secret(OPAQUE_KEY)
        log_file = tmp_path / "srv.log"
        proc = subprocess.Popen(
            [sys.executable, "-c",
             f"import sys; sys.stderr.write('auth failed key={OPAQUE_KEY}\\nopenai {OPENAI_KEY}\\njwt {JWT}\\n')"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        with open(log_file, "w") as fh:
            start_stderr_drainer(proc, "drain-test", log_fh=fh)
            proc.wait(timeout=10)
            deadline = time.time() + 5
            while time.time() < deadline and "jwt" not in get_stderr_tail("drain-test"):
                time.sleep(0.05)
        try:
            for text in (get_stderr_tail("drain-test"), loguru_capture.getvalue(), log_file.read_text()):
                assert "auth failed" in text
                for secret in (OPAQUE_KEY, OPENAI_KEY, JWT):
                    assert secret not in text
        finally:
            clear_stderr_buffer("drain-test")

    def test_file_written_stderr_sanitized_on_read(self, tmp_path):
        """server_manager: child writes the file directly; all readers sanitize."""
        from fluidmcp.cli.repositories import InMemoryBackend
        from fluidmcp.cli.services.server_manager import ServerManager
        register_secret(OPAQUE_KEY)
        manager = ServerManager(InMemoryBackend())
        log_path = tmp_path / "srv_stderr.log"
        log_path.write_text(f"boot\nError: bad key {OPAQUE_KEY}\nAuthorization: Bearer {X}\n")
        with patch.object(manager, "_get_stderr_log_path", return_value=str(log_path)):
            crash = manager._read_crash_stderr("srv")
            tail = "\n".join(manager.get_stderr_tail("srv")["lines"])
        for text in (crash, tail):
            assert "bad key" in text
            assert OPAQUE_KEY not in text and X not in text

    @pytest.mark.parametrize("backend_name", ["memory"])
    def test_log_store_and_crash_events_sanitized(self, backend_name):
        from fluidmcp.cli.repositories import InMemoryBackend
        register_secret(OPAQUE_KEY)

        async def run():
            db = InMemoryBackend()
            await db.connect()
            await db.save_log_entry({"server_name": "srv", "stream": "stderr", "content": f"key {OPAQUE_KEY}"})
            await db.save_crash_event({"server_id": "srv", "exit_code": 1, "stderr_tail": f"jwt {JWT}"})
            return await db.get_logs("srv"), await db.list_crash_events("srv")

        logs, crashes = asyncio.run(run())
        assert logs[0]["content"] == f"key {REDACTED}"
        assert JWT not in crashes[0]["stderr_tail"]

    def test_mongodb_log_store_sanitizes_on_save_and_read(self):
        """DatabaseManager: new entries redacted before insert; legacy entries on read."""
        from fluidmcp.cli.repositories.database import DatabaseManager
        register_secret(OPAQUE_KEY)
        inserted = []

        class FakeCursor:
            def __init__(self, docs): self.docs = docs
            def sort(self, *a, **k): return self
            def limit(self, *a, **k): return self
            async def to_list(self, length): return list(self.docs)

        class FakeCollection:
            async def insert_one(self, doc): inserted.append(dict(doc))
            def find(self, *a, **k):
                return FakeCursor([{"_id": object(), "server_name": "srv", "content": f"legacy {OPAQUE_KEY}",
                                    "timestamp": 1}])

        class FakeDB:
            fluidmcp_server_logs = FakeCollection()
            fluidmcp_crash_events = FakeCollection()

        manager = DatabaseManager.__new__(DatabaseManager)
        manager.db = FakeDB()
        from fluidmcp.cli.repositories.database import LogBuffer
        manager._log_buffer = LogBuffer()

        async def run():
            await manager.save_log_entry({"server_name": "srv", "content": f"new {OPAQUE_KEY}"})
            await manager.save_crash_event({"server_id": "srv", "stderr_tail": f"crash {OPAQUE_KEY}"})
            return await manager.get_logs("srv")

        logs = asyncio.run(run())
        assert all(OPAQUE_KEY not in str(doc) for doc in inserted) and len(inserted) == 2
        assert logs[0]["content"] == f"legacy {REDACTED}"
        assert "_id" not in logs[0], "ObjectId must be dropped (not JSON-serializable for the /logs API)"

    async def test_crashing_mcp_server_end_to_end(self, tmp_path, loguru_capture, monkeypatch):
        """A real MCP subprocess that prints its env API key and argv key, then crashes."""
        from fluidmcp.cli.repositories import InMemoryBackend
        from fluidmcp.cli.services.server_manager import ServerManager
        monkeypatch.setenv("HOME", str(tmp_path))
        script = tmp_path / "leaky.py"
        script.write_text(
            "import os, sys\n"
            "sys.stderr.write(f\"auth failed for {os.environ['VENDOR_API_KEY']} / {sys.argv[2]}\\n\")\n"
            "sys.exit(1)\n"
        )
        arg_key = "argv-key-" + X
        env_key = "env-key-" + X[::-1]
        db = InMemoryBackend()
        manager = ServerManager(db)
        config = {
            "id": "leaky", "name": "leaky", "command": sys.executable,
            "args": [str(script), "--api-key", arg_key],
            "env": {"VENDOR_API_KEY": env_key},
            "working_dir": str(tmp_path), "install_path": str(tmp_path),
        }
        result = await manager._spawn_mcp_process("leaky", config)
        assert result is None
        logs = loguru_capture.getvalue()
        assert "auth failed for" in logs
        assert arg_key not in logs and env_key not in logs
        # Crash diagnostics served via API are sanitized as well
        tail = manager.get_stderr_tail("leaky")
        assert tail["lines"] and all(arg_key not in l and env_key not in l for l in tail["lines"])

    def test_inspector_session_log_sanitized(self):
        from fluidmcp.cli.services.inspector_session import InspectorSession
        session = InspectorSession.__new__(InspectorSession)
        session.logs = []
        register_secret(OPAQUE_KEY)
        session.add_log("tool_error", f"Tool failed: 401 for {OPAQUE_KEY}")
        assert OPAQUE_KEY not in session.logs[0]["message"]

    def test_no_child_process_inherits_console_streams(self):
        """Every subprocess spawn captures or redirects stdout and stderr (no direct console output)."""
        offenders = []
        for path in Path("fluidmcp").rglob("*.py"):
            text = path.read_text()
            for match in re.finditer(r"subprocess\.(run|Popen|call|check_call)\(|create_subprocess_exec\(", text):
                line_text = text[text.rfind("\n", 0, match.start()) + 1: match.start()]
                if not re.fullmatch(r"\s*(\w+(\.\w+)*\s*=\s*)?(await\s+)?(asyncio\.)?", line_text):
                    continue  # mention in a docstring/comment, not a call
                window = text[match.end(): match.end() + 900]
                call = window[: window.find("\n)") if "\n)" in window else 900]
                has_stdout = "stdout=" in call or "capture_output=True" in call
                has_stderr = "stderr=" in call or "capture_output=True" in call
                if not (has_stdout and has_stderr):
                    line = text[: match.start()].count("\n") + 1
                    offenders.append(f"{path}:{line}")
        assert offenders == []


# --------------------------------------------------------------------------- #
# 4. GITHUB_TOKEN support and configuration compatibility
# --------------------------------------------------------------------------- #

class TestGithubTokenCompatibility:
    def _resolve(self, tmp_path, config):
        import json as _json
        from fluidmcp.cli.services import config_resolver
        path = tmp_path / "cfg.json"
        path.write_text(_json.dumps(config))
        seen = {}

        def fake_handle(server_name, server_cfg, default_github_token):
            seen[server_name] = server_cfg.get("github_token") or default_github_token

        with patch.object(config_resolver, "_handle_github_server", side_effect=fake_handle):
            try:
                config_resolver.resolve_from_file(str(path))
            except Exception:
                pass  # later stages need real repos; only token resolution matters here
        return seen

    @pytest.mark.parametrize("env,config_default,server_token,expected", [
        ({"GITHUB_TOKEN": "env-github"}, None, None, "env-github"),
        ({"FMCP_GITHUB_TOKEN": "env-fmcp"}, None, None, "env-fmcp"),
        ({"GITHUB_TOKEN": "env-github", "FMCP_GITHUB_TOKEN": "env-fmcp"}, None, None, "env-fmcp"),
        ({"GITHUB_TOKEN": "env-github"}, "cfg-default", None, "cfg-default"),
        ({"GITHUB_TOKEN": "env-github"}, "cfg-default", "per-server", "per-server"),
    ])
    def test_token_precedence_unchanged(self, tmp_path, monkeypatch, env, config_default, server_token, expected):
        for name in ("GITHUB_TOKEN", "FMCP_GITHUB_TOKEN"):
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        server = {"github_repo": "owner/repo", "branch": "main"}
        if server_token:
            server["github_token"] = server_token
        config = {"mcpServers": {"srv": server}}
        if config_default:
            config["github_token"] = config_default
        assert self._resolve(tmp_path, config) == {"srv": expected}

    def test_private_repo_without_any_token_fails_clearly(self, monkeypatch):
        from fluidmcp.cli.services.config_resolver import _handle_github_server
        for name in ("GITHUB_TOKEN", "FMCP_GITHUB_TOKEN"):
            monkeypatch.delenv(name, raising=False)
        with pytest.raises(ValueError, match="GITHUB_TOKEN"):
            _handle_github_server("srv", {"github_repo": "owner/repo"}, None)

    def test_github_token_reaches_git_via_askpass_only(self, tmp_path, monkeypatch):
        """GITHUB_TOKEN from the environment authenticates the clone (via askpass env)."""
        from fluidmcp.cli.services import github_utils
        token = "github_pat_" + "11DUMMY_" + X
        monkeypatch.setenv("GITHUB_TOKEN", token)
        seen = {}

        def fake_run(cmd, *a, **kw):
            seen["cmd"], seen["env"] = cmd, kw.get("env", {})
            Path(cmd[-1]).mkdir(parents=True)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch.object(github_utils.subprocess, "run", side_effect=fake_run):
            github_utils.clone_github_repo("owner/private-repo", os.environ["GITHUB_TOKEN"], "main", tmp_path)
        assert token not in " ".join(seen["cmd"])
        assert seen["env"]["FMCP_GIT_ASKPASS_TOKEN"] == token
        assert "GIT_ASKPASS" in seen["env"]


# --------------------------------------------------------------------------- #
# 5. MongoDB URI masking with special characters
# --------------------------------------------------------------------------- #

PASSWORDS = [
    "p@ssw0rd-Secret",           # unencoded @
    "p:a:ss-Secret99",           # colons
    "pa/ss/w0rd-Secret",         # slashes
    "pa#ss?w0rd-Secret",         # fragment / query chars
    "p%40ss%3Aw%2Fd%23-Secret",  # percent-encoded @ : / #
    "p@ss:w/o#rd%25-Secret",     # everything at once
]
HOSTS = [
    "cluster0.example.mongodb.net/fluidmcp?retryWrites=true&w=majority",
    "h1.example.com:27017,h2.example.com:27017/db?replicaSet=rs0",
    "localhost:27017",
]


class TestMongoUriMasking:
    @pytest.mark.parametrize("password", PASSWORDS)
    @pytest.mark.parametrize("host", HOSTS)
    @pytest.mark.parametrize("scheme", ["mongodb", "mongodb+srv"])
    def test_mask_mongodb_uri(self, scheme, host, password):
        from fluidmcp.cli.repositories.database import mask_mongodb_uri
        uri = f"{scheme}://fmcp_user:{password}@{host}"
        masked = mask_mongodb_uri(uri)
        assert masked == f"{scheme}://***:***@{host}"
        assert "Secret" not in masked and "fmcp_user" not in masked

    @pytest.mark.parametrize("password", PASSWORDS)
    @pytest.mark.parametrize("host", HOSTS)
    def test_free_text_redaction(self, host, password, monkeypatch):
        for name in list(os.environ):
            if "MONGO" in name or name.endswith(("_URI", "_URL")):
                monkeypatch.delenv(name, raising=False)
        uri = f"mongodb+srv://fmcp_user:{password}@{host}"
        out = redact_secrets(f"Failed to connect to {uri}: timeout")
        assert "Secret" not in out and "fmcp_user" not in out
        assert host.split("/")[0].split(",")[0] in out  # host kept for debugging

    @pytest.mark.parametrize("password", PASSWORDS)
    def test_mongodb_uri_env_password_redacted_standalone(self, password, monkeypatch):
        from urllib.parse import unquote
        monkeypatch.setenv("MONGODB_URI", f"mongodb+srv://u:{password}@cluster0.example.net/db")
        for form in {password, unquote(password)}:
            assert form not in redact_secrets(f"driver echoed password {form} in error")

    def test_unmasked_shapes_fail_closed(self):
        from fluidmcp.cli.repositories.database import mask_mongodb_uri
        assert "Secret" not in mask_mongodb_uri("user:Secret@host")
        assert mask_mongodb_uri("mongodb://host:27017/db") == "mongodb://host:27017/db"

    def test_web_urls_with_at_in_path_not_mangled(self):
        line = "fetch https://unpkg.com/@modelcontextprotocol/server@1.2.0/dist and https://github.com/a/b"
        assert redact_secrets(line) == line


# --------------------------------------------------------------------------- #
# 6. API error responses and Sentry events
# --------------------------------------------------------------------------- #

class TestApiErrorResponses:
    def _app(self):
        app = FastAPI()
        install_redacting_exception_handlers(app)

        class Body(BaseModel):
            id: str
            env: dict
            count: int

        @app.get("/provider-error")
        def provider_error():
            raise HTTPException(502, f"Upstream said: Incorrect API key provided: {OPENAI_KEY}")

        @app.get("/opaque-error")
        def opaque_error():
            raise HTTPException(400, {"error": f"bad key {OPAQUE_KEY}", "hint": "check config"})

        @app.post("/validate")
        def validate(body: Body):
            return {}

        return app

    def test_http_exception_detail_redacted(self):
        register_secret(OPAQUE_KEY)
        client = TestClient(self._app())
        r = client.get("/provider-error")
        assert r.status_code == 502 and OPENAI_KEY not in r.text and "Incorrect API key" in r.text
        r = client.get("/opaque-error")
        assert r.status_code == 400 and OPAQUE_KEY not in r.text and r.json()["detail"]["hint"] == "check config"

    def test_validation_error_does_not_echo_submitted_secrets(self):
        client = TestClient(self._app())
        r = client.post("/validate", json={"id": "x", "env": {"VENDOR_API_KEY": OPAQUE_KEY + "-unregistered"},
                                           "count": "not-a-number", "github_token": JWT})
        assert r.status_code == 422
        assert OPAQUE_KEY not in r.text and JWT not in r.text
        assert "count" in r.text  # still tells the client what is wrong

    def test_validation_error_on_sensitive_field_never_echoes_its_value(self):
        """An opaque, unregistered credential in a sensitive field must not come back in a 422."""

        class Model(BaseModel):
            name: str
            api_key: int  # wrong type on purpose: pydantic echoes the submitted value as input

        app = FastAPI()
        install_redacting_exception_handlers(app)

        @app.post("/m")
        def endpoint(body: Model):
            return {}

        opaque = "opaque-unregistered-value-" + X
        r = TestClient(app).post("/m", json={"name": 5, "api_key": opaque, "nested": {"password": opaque + "2"}})
        assert r.status_code == 422
        assert opaque not in r.text
        locs = [tuple(e["loc"]) for e in r.json()["detail"]]
        assert ("body", "api_key") in locs and ("body", "name") in locs  # still actionable

    def test_all_gateway_apps_install_handlers(self):
        for module in ("fluidmcp/cli/server.py", "fluidmcp/cli/services/run_servers.py", "fluidmcp/cli/cli.py"):
            assert "install_redacting_exception_handlers(app)" in Path(module).read_text(), module

    def test_sentry_events_redacted(self, monkeypatch):
        import sentry_sdk
        from fluidmcp.cli import server
        captured = {}
        monkeypatch.setenv("SENTRY_DSN", "https://public@o0.ingest.sentry.io/0")
        monkeypatch.setattr(sentry_sdk, "init", lambda **kw: captured.update(kw))
        server.init_sentry()
        event = {"exception": {"values": [{"value": f"auth failed {OPENAI_KEY}"}]},
                 "breadcrumbs": {"values": [{"message": f"Authorization: Bearer {X}"}]}}
        redacted = captured["before_send"](event, {})
        assert OPENAI_KEY not in str(redacted) and X not in str(redacted)
        assert captured["include_local_variables"] is False
        assert captured["before_send"]({"request": {"url": "http://x/health"}}, {}) is None


class TestRailwayStyleLogs:
    def test_every_secret_type_absent_from_json_logs(self, capsys, monkeypatch):
        """Simulate fmcp serve on Railway: JSON sink + stream redaction, all secret kinds."""
        from fluidmcp.cli import server
        mongo = "mongodb+srv://u:Mongo-Secret-" + X[:8] + "@c.example.net/db"
        monkeypatch.setenv("MONGODB_URI", mongo)
        monkeypatch.setenv("FMCP_BEARER_TOKEN", CORRECT_TOKEN)
        register_secrets_from_mapping({"env": {"VENDOR_API_KEY": OPAQUE_KEY}})
        real_out, real_err = sys.stdout, sys.stderr
        server._configure_json_logging()
        try:
            logger.info(f"conn {mongo} token {CORRECT_TOKEN}")
            logger.warning(f"provider: {OPENAI_KEY} jwt {JWT}")
            try:
                raise RuntimeError(f"vendor rejected {OPAQUE_KEY}")
            except RuntimeError:
                logger.exception("call failed")
            print(f"stray print of {OPAQUE_KEY} and {CORRECT_TOKEN}")
            import logging as std_logging
            std_logging.getLogger("uvicorn.error").error("bad header Authorization: Bearer %s", CORRECT_TOKEN)
        finally:
            logger.remove()
            logger.configure(patcher=lambda record: None)
            logger.add(real_err)
            sys.stdout, sys.stderr = real_out, real_err
        captured = capsys.readouterr()
        text = captured.out + captured.err
        assert "call failed" in text and "stray print" in text
        for secret in (CORRECT_TOKEN, OPENAI_KEY, JWT, OPAQUE_KEY, "Mongo-Secret-" + X[:8]):
            assert secret not in text
