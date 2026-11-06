"""Black-box security E2E tests for PR #967 (credential redaction and API authentication).

Every scenario drives the real source CLI (``fmcp serve`` / ``fmcp run`` /
``fmcp github``) as a subprocess, real MCP SDK subprocesses, a real MongoDB
(Docker), real git over HTTP against a local GitHub stand-in, and real HTTP
requests. Assertions are made on what an operator would actually see: the
process's console output (the Railway/Docker log), HTTP responses, records in
MongoDB, files on disk, and what crossed the wire to "GitHub".

All credentials are dummy values generated per run. See README.md
("Security redaction suite") for prerequisites and artifacts.
"""

import base64
import json
import os
import shutil
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import uuid
import gzip
import zlib
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, quote_plus, unquote

import httpx
import psutil
import pytest

from mock_github import MockGitHub

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
FAKE_ECHO = HERE / "fake_mcp_server.py"
LEAKY = HERE / "leaky_mcp_server.py"
HARNESS = HERE / "logging_harness.py"
MONGO_IMAGE = os.environ.get("FMCP_E2E_MONGO_IMAGE", "mongo:7.0")
CLI = [sys.executable, "-c", "from fluidmcp.cli.cli import main; main()"]

# ── Dummy credentials (unique per run; assembled from fragments so secret
#    scanners never mistake this file for a real credential) ─────────────────
RUN = uuid.uuid4().hex[:12]
RUN_UP = RUN.upper()


def _d(*parts):
    return "".join(parts)


BEARER = _d("e2e-bearer-", RUN, "-", "b" * 20)
GH_TOKEN = _d("github_pat_", "11E2E", RUN_UP, "_", "Gh7k" * 10)
GH_WRONG = _d("github_pat_", "11E2EWRONG", RUN_UP, "_", "Wr0n" * 10)
VENDOR_KEY = _d("vendor-opaque-", RUN, "-", "v" * 16)       # no recognizable format
SERVE_OPAQUE = _d("serve-env-opaque-", RUN, "-", "s" * 16)   # in fmcp serve's own env
ARG_KEY = _d("cli-arg-opaque-", RUN, "-", "a" * 16)          # passed as --api-key VALUE
MONGO_USER = "fmcp_e2e"
MONGO_PASSWORD = _d("E2e@Db:pa/ss#w%rd-", RUN)               # @ : / # % on purpose

# One representative credential per supported category: (leak context, secret).
# The context is how the credential typically appears in real output; the secret
# is what must never be visible. Each is detectable by pattern alone.
CATEGORY_LEAKS = {
    "github": (_d("token ", "gh", "p_", RUN, "Ab12" * 6, "x"), _d("gh", "p_", RUN, "Ab12" * 6, "x")),
    "openai": (_d("Incorrect API key provided: ", "sk-", "proj-", RUN, "Op3n" * 8),
               _d("sk-", "proj-", RUN, "Op3n" * 8)),
    "anthropic": (_d("x-api-key: ", "sk-", "ant-api03-", RUN, "Ant7" * 8, "-AA"),
                  _d("sk-", "ant-api03-", RUN, "Ant7" * 8, "-AA")),
    "gemini": (_d("GET /v1beta/models?key=", "AI", "za", "Sy", RUN, "G" * 21), _d("AI", "za", "Sy", RUN, "G" * 21)),
    "huggingface": (_d("HF hub token ", "hf", "_", RUN, "HuGg" * 5), _d("hf", "_", RUN, "HuGg" * 5)),
    "aws-access-key": (_d("AccessKeyId=", "AK", "IA", RUN_UP[:8], "E2EEXAMP"), _d("AK", "IA", RUN_UP[:8], "E2EEXAMP")),
    "aws-secret-key": (_d("aws_secret_access_key=", RUN, "/Aws+Secret/E2EKEY", "q" * 8),
                       _d(RUN, "/Aws+Secret/E2EKEY", "q" * 8)),
    "azure": (_d("DefaultEndpointsProtocol=https;AccountName=e2e;AccountKey=", RUN, "AzUrE" * 6, "==;EndpointSuffix=x"),
              _d(RUN, "AzUrE" * 6, "==")),
    "jwt": (_d("id_token=", "ey", "JhbGciOiJIUzI1NiJ9", ".ey", "JzdWIiOiJlMmUifQ", ".", RUN, "Jwt" * 6),
            _d("ey", "JhbGciOiJIUzI1NiJ9", ".ey", "JzdWIiOiJlMmUifQ", ".", RUN, "Jwt" * 6)),
    "oauth": (_d('{"access_token": "', "ya", "29.", RUN, "OaUtH" * 5, '", "refresh_token": "1//', RUN, 'rEfReSh"}'),
              _d("ya", "29.", RUN, "OaUtH" * 5)),
    "slack": (_d("slack ", "xo", "xb-", "123456789012-", RUN, "SlAcK" * 3), _d("xo", "xb-", "123456789012-", RUN, "SlAcK" * 3)),
    "stripe": (_d("stripe ", "sk", "_live_", RUN, "StRiPe" * 3), _d("sk", "_live_", RUN, "StRiPe" * 3)),
    "sendgrid": (_d("sendgrid ", "SG", ".", RUN, "SeNdGrId00", ".", RUN, "SeNdGrIdKeY" * 3),
                 _d("SG", ".", RUN, "SeNdGrId00", ".", RUN, "SeNdGrIdKeY" * 3)),
    "replicate": (_d("replicate ", "r8", "_", RUN, "RePl1cAtE" * 2), _d("r8", "_", RUN, "RePl1cAtE" * 2)),
    "database": (_d("postgresql://admin:", "Pg@pa:ss/", RUN, "@db.internal:5432/app"), _d("Pg@pa:ss/", RUN)),
    "bearer": (_d("Authorization: Bearer ", RUN, "BeArEr" * 4), _d(RUN, "BeArEr" * 4)),
    "password": (_d("password=", "Pw-", RUN, "-hunter2"), _d("Pw-", RUN, "-hunter2")),
}
CATEGORY_SECRETS = {name: secret for name, (_, secret) in CATEGORY_LEAKS.items()}
OPAQUE_SECRETS = {"vendor-env-key": VENDOR_KEY, "cli-arg-key": ARG_KEY}
ALL_SECRETS = {**CATEGORY_SECRETS, **OPAQUE_SECRETS, "bearer-token": BEARER, "github-token": GH_TOKEN,
               "serve-env-opaque": SERVE_OPAQUE, "mongo-password": MONGO_PASSWORD}


# ── Assertion helpers ────────────────────────────────────────────────────────

def secret_forms(value):
    """The secret plus encodings it could plausibly appear in."""
    forms = {value, quote_plus(value), quote(value, safe=""), unquote(value),
             base64.b64encode(value.encode()).decode(),
             base64.b64encode(f"x-access-token:{value}".encode()).decode()}
    return {form for form in forms if len(form) >= 8}


def assert_no_secrets(text, secrets, where):
    """Fail if any secret (in any form) occurs in text. Never echoes secret values."""
    leaked = sorted({label for label, value in secrets.items() for form in secret_forms(value) if form in text})
    assert not leaked, f"{where}: secrets visible for categories {leaked}"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def poll(predicate, timeout, interval=0.25, message="condition not met"):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            last = predicate()
            if last:
                return last
        except (httpx.HTTPError, OSError, ValueError, KeyError):
            pass
        time.sleep(interval)
    pytest.fail(f"Timed out after {timeout}s: {message}")


# ── Process management (mirrors conftest.gateway's launch/cleanup) ───────────

class Proc:
    """A source-CLI subprocess whose combined stdout/stderr is the 'deployment log'."""

    def __init__(self, name, command, env, cwd, artifacts):
        self.name = name
        self.log_path = artifacts / f"{name}.log"
        self._log = self.log_path.open("w")
        self.process = subprocess.Popen(command, cwd=cwd, env=env, stdout=self._log,
                                        stderr=subprocess.STDOUT, start_new_session=True)

    def log(self):
        if not self._log.closed:
            self._log.flush()
        return self.log_path.read_text(errors="replace")

    def wait_for_log(self, text, timeout=60):
        return poll(lambda: text in self.log(), timeout,
                    message=f"{self.name}: {text!r} not logged; see {self.log_path}")

    def wait_exit(self, timeout=90):
        try:
            return self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pytest.fail(f"{self.name} did not exit within {timeout}s; see {self.log_path}")

    def wait_http(self, url, ready=lambda r: r.status_code == 200, timeout=90):
        with httpx.Client(timeout=3, trust_env=False) as client:
            def check():
                if self.process.poll() is not None:
                    pytest.fail(f"{self.name} exited ({self.process.returncode}):\n{self.log()[-6000:]}")
                return ready(client.get(url))
            poll(check, timeout, interval=0.2, message=f"{self.name} not ready at {url}; see {self.log_path}")

    def stop(self):
        try:
            children = psutil.Process(self.process.pid).children(recursive=True)
        except psutil.NoSuchProcess:
            children = []
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(children, timeout=5)
        for child in alive:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        psutil.wait_procs(alive, timeout=5)
        self._log.close()


class Launcher:
    def __init__(self, artifacts):
        self.artifacts = artifacts
        self.procs = []

    def env(self, home, **extra):
        """Minimal isolated environment (no inherited credentials), like conftest.gateway."""
        home = Path(home)
        home.mkdir(parents=True, exist_ok=True)
        env = {key: os.environ[key] for key in ("PATH", "LANG", "SYSTEMROOT") if key in os.environ}
        env.update({
            # python3 for MCP server commands resolves to this interpreter (has mcp installed).
            "PATH": os.pathsep.join([str(Path(sys.executable).parent), env.get("PATH", "")]),
            "PYTHONPATH": str(ROOT), "PYTHONUNBUFFERED": "1", "HOME": str(home),
            "MCP_INSTALLATION_DIR": str(home / "packages"),
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
        })
        env.update({key: str(value) for key, value in extra.items()})
        return env

    def start(self, name, args, env, module=None):
        command = [sys.executable, "-m", module, *args] if module else [*CLI, *args]
        cwd = Path(env["HOME"])
        proc = Proc(name, command, env, cwd, self.artifacts)
        self.procs.append(proc)
        return proc

    def serve(self, name, env, port, *extra_args, in_memory=True):
        args = ["serve", "--host", "127.0.0.1", "--port", str(port), "--secure", "--allow-all-origins", *extra_args]
        if in_memory:
            args.append("--in-memory")
        return self.start(name, args, env)

    def stop_all(self):
        for proc in reversed(self.procs):
            proc.stop()


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory):
    path = tmp_path_factory.mktemp("security-e2e")
    (path / "echo-journal").mkdir()
    print(f"\nSecurity E2E artifacts: {path}")
    return path


@pytest.fixture(scope="module", autouse=True)
def _clean_checkout():
    # The CLI loads these with override=True and would silently change the fixture.
    for path in (ROOT / ".env", ROOT / "fluidmcp/cli/.env"):
        if path.exists():
            pytest.fail(f"{path} would override the isolated test environment; use a clean worktree")


@pytest.fixture(scope="module")
def module_launcher(artifacts):
    launcher = Launcher(artifacts)
    yield launcher
    launcher.stop_all()


@pytest.fixture
def launcher(artifacts):
    launcher = Launcher(artifacts)
    yield launcher
    launcher.stop_all()


def http():
    return httpx.Client(timeout=60, trust_env=False)


AUTH = {"Authorization": f"Bearer {BEARER}"}


# ── External services: MongoDB (Docker) and GitHub stand-in ──────────────────

class Mongo:
    def __init__(self, port, ca_file):
        self.port = port
        self.ca_file = ca_file

    def uri(self, password=MONGO_PASSWORD, encode=True, port=None):
        secret = quote_plus(password) if encode else password
        # FluidMCP always connects with TLS and validates certificates by default
        # (FMCP_MONGODB_ALLOW_INVALID_CERTS=false); trust the test CA explicitly.
        return (f"mongodb://{MONGO_USER}:{secret}@127.0.0.1:{port or self.port}/"
                f"?authSource=admin&tls=true&tlsCAFile={quote(str(self.ca_file))}")

    def client(self):
        import pymongo
        return pymongo.MongoClient(self.uri(), serverSelectionTimeoutMS=2000)


def _make_tls_material(directory):
    """Throwaway CA and a server certificate for 127.0.0.1/localhost."""
    directory.mkdir()
    def openssl(*args):
        subprocess.run(["openssl", *args], cwd=directory, check=True, capture_output=True)
    openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "ca.key", "-out", "ca.pem",
            "-days", "2", "-subj", "/CN=fmcp-e2e-test-ca")
    openssl("req", "-newkey", "rsa:2048", "-nodes", "-keyout", "server.key", "-out", "server.csr",
            "-subj", "/CN=localhost")
    (directory / "san.cnf").write_text("subjectAltName=IP:127.0.0.1,DNS:localhost\n")
    openssl("x509", "-req", "-in", "server.csr", "-CA", "ca.pem", "-CAkey", "ca.key", "-CAcreateserial",
            "-out", "server.crt", "-days", "2", "-extfile", "san.cnf")
    pem = directory / "server.pem"
    pem.write_text((directory / "server.crt").read_text() + (directory / "server.key").read_text())
    for path in (pem, directory / "ca.pem"):
        path.chmod(0o644)  # readable by the container's mongodb user
    return directory / "ca.pem", pem


@pytest.fixture(scope="module")
def mongo(artifacts):
    for tool in ("docker", "openssl"):
        if not shutil.which(tool):
            pytest.fail(f"{tool} is required for the MongoDB-backed security scenarios (see tests_e2e/README.md)")
    ca_file, server_pem = _make_tls_material(artifacts / "mongo-tls")
    name = f"fmcp-e2e-mongo-{RUN}"
    # preferTLS: the image's init step connects without TLS; FluidMCP always uses TLS.
    # MongoDB 7 requires a CA for TLS; clients authenticate with passwords, not certificates.
    created = subprocess.run(
        ["docker", "create", "--name", name, "-p", "127.0.0.1::27017",
         "-e", f"MONGO_INITDB_ROOT_USERNAME={MONGO_USER}", "-e", f"MONGO_INITDB_ROOT_PASSWORD={MONGO_PASSWORD}",
         MONGO_IMAGE, "--tlsMode", "preferTLS", "--tlsCertificateKeyFile", "/tmp/fmcp-e2e-server.pem",
         "--tlsCAFile", "/tmp/fmcp-e2e-ca.pem", "--tlsAllowConnectionsWithoutCertificates"],
        capture_output=True, text=True)
    if created.returncode != 0:
        pytest.fail(f"Could not create MongoDB container ({MONGO_IMAGE}): {created.stderr.strip()[:500]}")
    try:
        for source, target in ((server_pem, "/tmp/fmcp-e2e-server.pem"), (ca_file, "/tmp/fmcp-e2e-ca.pem")):
            subprocess.run(["docker", "cp", str(source), f"{name}:{target}"], check=True, capture_output=True)
        subprocess.run(["docker", "start", name], check=True, capture_output=True)
        port = int(subprocess.run(["docker", "port", name, "27017/tcp"], capture_output=True, text=True,
                                  check=True).stdout.strip().splitlines()[0].rsplit(":", 1)[1])
        db = Mongo(port, ca_file)

        def authenticated_ping():
            try:
                with db.client() as client:
                    return client.admin.command("ping")["ok"] == 1
            except Exception:  # still initialising (connection resets, auth not ready)
                return False
        poll(authenticated_ping, 90, interval=1, message="MongoDB container never accepted the test user")
        yield db
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


REPO_CONFIG_KEY = _d("repo-config-opaque-", RUN, "-", "r" * 16)  # API key committed in a repo's metadata.json
ALL_SECRETS["repo-config-key"] = REPO_CONFIG_KEY


@pytest.fixture(scope="module")
def github(artifacts):
    server = MockGitHub(artifacts / "mock-github", token=GH_TOKEN).start()
    # `fmcp github` and the from-github API launch repository servers over stdio.
    # The server leaks the API key from its metadata env, like a misbehaving MCP server.
    metadata = lambda name: json.dumps({"mcpServers": {name: {
        "command": "python3",
        "args": [str(LEAKY), "--mode", "serve", "--transport", "stdio", "--leak-env", "VENDOR_API_KEY"],
        "env": {"VENDOR_API_KEY": REPO_CONFIG_KEY}}}}, indent=2)
    server.create_repo("fluid-e2e", "public-mcp", {"main": {"metadata.json": metadata("public-echo")}})
    server.create_repo("fluid-e2e", "private-mcp", {
        "main": {"metadata.json": metadata("private-echo"), "branch.txt": "main"},
        "feature-x": {"branch.txt": "feature-x"},
    }, private=True)
    yield server
    server.stop()


@pytest.fixture(scope="module")
def git_shim(artifacts):
    """A 'git' first on PATH that records every invocation's argv, then runs real git."""
    shim_dir = artifacts / "git-shim"
    shim_dir.mkdir()
    argv_log = artifacts / "git-argv.log"
    real_git = shutil.which("git")
    shim = shim_dir / "git"
    shim.write_text(
        "#!/bin/sh\n"
        f"printf 'ARGV:' >> '{argv_log}'\n"
        f"for a in \"$@\"; do printf ' [%s]' \"$a\" >> '{argv_log}'; done\n"
        f"printf ' ASKPASS=%s TOKEN_ENV=%s\\n' \"${{GIT_ASKPASS:+set}}\" \"${{FMCP_GIT_ASKPASS_TOKEN:+set}}\" >> '{argv_log}'\n"
        f"exec '{real_git}' \"$@\"\n")
    shim.chmod(0o755)
    return {"dir": shim_dir, "log": argv_log}


def with_shim(env, shim):
    env["PATH"] = os.pathsep.join([str(shim["dir"]), env["PATH"]])
    return env


# ── Shared fmcp serve (Railway parity: secure mode + real MongoDB) ───────────

@pytest.fixture(scope="module")
def serve(module_launcher, artifacts, mongo, github):
    port = free_port()
    database = f"fmcp_e2e_{RUN}"
    env = module_launcher.env(
        artifacts / "serve-home",
        FMCP_BEARER_TOKEN=BEARER, FMCP_HEALTH_CHECK_INTERVAL=1, GITHUB_TOKEN=GH_TOKEN,
        E2E_VENDOR_TOKEN=SERVE_OPAQUE, FMCP_MONGODB_SERVER_TIMEOUT=5000, FMCP_MONGODB_CONNECT_TIMEOUT=5000,
        **github.git_redirect_env())
    proc = module_launcher.serve("serve-mongo", env, port, "--mongodb-uri", mongo.uri(),
                                 "--database", database, "--require-persistence", in_memory=False)
    url = f"http://127.0.0.1:{port}"
    proc.wait_http(f"{url}/health")
    with http() as client:
        add = client.post(f"{url}/api/servers", headers=AUTH, json={
            "id": "e2e-echo", "name": "e2e-echo", "command": "python3",
            "args": [str(FAKE_ECHO), "--transport", "http", "--artifacts", str(artifacts / "echo-journal")],
            "transport": "http", "working_dir": str(artifacts), "install_path": str(artifacts)})
        assert add.status_code == 200, add.text
        start = client.post(f"{url}/api/servers/e2e-echo/start", headers=AUTH)
        assert start.status_code == 200, start.text
    return {"url": url, "proc": proc, "database": database, "home": artifacts / "serve-home", "env": env}


def add_and_start(serve, server_id, args, env=None, **extra):
    with http() as client:
        add = client.post(f"{serve['url']}/api/servers", headers=AUTH, json={
            "id": server_id, "name": server_id, "command": "python3", "args": [str(LEAKY), *args],
            "env": env or {}, "transport": "http", "working_dir": str(serve["home"]),
            "install_path": str(serve["home"]), "restart_policy": "never", **extra})
        assert add.status_code == 200, add.text
        return client.post(f"{serve['url']}/api/servers/{server_id}/start", headers=AUTH)


@pytest.fixture(scope="module")
def leak_file(artifacts):
    """Every category credential, delivered to the MCP server outside FluidMCP's config
    (so only pattern-based detection can catch it)."""
    path = artifacts / "category-leaks.txt"
    path.write_text("\n".join(context for context, _ in CATEGORY_LEAKS.values()) + "\n")
    return path


def leak_args(leak_file):
    """--api-key (command-line credential) + VENDOR_API_KEY (config env credential) + category file."""
    return ["--api-key", ARG_KEY, "--leak-env", "VENDOR_API_KEY", "--leak-file", str(leak_file)]


LEAK_ENV = {"VENDOR_API_KEY": VENDOR_KEY}


# ═════════════════════════════════════════════════════════════════════════════
# A. GitHub authentication and repository cloning
# ═════════════════════════════════════════════════════════════════════════════

class TestGitHubCloning:
    def _assert_git_argv_clean(self, shim, *tokens):
        argv = shim["log"].read_text() if shim["log"].exists() else ""
        assert "ARGV: [-c] [credential.helper=] [clone]" in argv, "FluidMCP did not invoke git clone"
        assert_no_secrets(argv, {f"token-{i}": t for i, t in enumerate(tokens)}, "git argv")
        assert "https://github.com/" in argv and "@github.com" not in argv, "clone URL must carry no credentials"

    def test_public_repo_clone_via_github_command(self, launcher, artifacts, github, git_shim):
        port = free_port()
        home = artifacts / "github-public-home"
        env = with_shim(launcher.env(home, MCP_CLIENT_SERVER_PORT=port, MCP_CLIENT_SERVER_ALL_PORT=port,
                                     **github.git_redirect_env()), git_shim)
        proc = launcher.start("github-public", ["github", "fluid-e2e/public-mcp", "--github-token", GH_TOKEN,
                                                "--branch", "main", "--start-server", "--verbose"], env)
        # `fmcp github`'s /health reports 503 even while serving (it reads run_servers' process
        # registry, which github_command does not populate - pre-existing, unrelated to PR #967),
        # so readiness is a successful tool call through the gateway.
        with http() as client:
            def tool_call():
                if proc.process.poll() is not None:
                    pytest.fail(f"fmcp github exited ({proc.process.returncode}):\n{proc.log()[-6000:]}")
                return client.post(f"http://127.0.0.1:{port}/public-echo/mcp/tools/call",
                                   json={"name": "ping", "arguments": {"message": "public"}})
            call = poll(lambda: (r := tool_call()).status_code == 200 and r, 90,
                        message=f"fmcp github never served the cloned server; see {proc.log_path}")
        assert "pong: public" in call.text, call.text
        public = github.requests_for("fluid-e2e", "public-mcp")
        assert public and all(r["status"] == 200 for r in public)
        assert not any(r["auth_password"] for r in public), "token sent to a public repo that never asked for it"
        clone = home / "packages" / "fluid-e2e" / "public-mcp" / "main"
        assert_no_secrets((clone / ".git" / "config").read_text(), {"github-token": GH_TOKEN}, ".git/config")
        log = proc.log()
        # E: the repository's server config (env block) is dumped in masked form only.
        assert "'VENDOR_API_KEY': '***REDACTED***'" in log, "server config not logged in masked form"
        assert "auth failed for credentials" in log, "leaky server output was not logged at all"
        assert_no_secrets(log, {"github-token": GH_TOKEN, "repo-config-key": REPO_CONFIG_KEY}, "fmcp github log")
        self._assert_git_argv_clean(git_shim, GH_TOKEN)

    def test_private_branch_clone_with_github_token_only(self, launcher, artifacts, github, git_shim):
        """fmcp run with only GITHUB_TOKEN set (no FMCP_GITHUB_TOKEN, no token in the config)."""
        port = free_port()
        home = artifacts / "run-private-home"
        config = home / "config.json"
        home.mkdir()
        config.write_text(json.dumps({"mcpServers": {"private-echo": {
            "github_repo": "fluid-e2e/private-mcp", "branch": "feature-x", "command": "python3",
            "args": [str(FAKE_ECHO), "--transport", "http", "--artifacts", str(artifacts / "echo-journal")],
            "transport": "http", "env": {}}}}))
        before = len(github.requests_for("fluid-e2e", "private-mcp"))
        env = with_shim(launcher.env(home, MCP_CLIENT_SERVER_ALL_PORT=port, GITHUB_TOKEN=GH_TOKEN,
                                     **github.git_redirect_env()), git_shim)
        assert "FMCP_GITHUB_TOKEN" not in env
        proc = launcher.start("run-private", ["run", str(config), "--file", "--start-server"], env)
        proc.wait_http(f"http://127.0.0.1:{port}/health", lambda r: r.json().get("running_servers") == 1)

        clone = home / "packages" / "fluid-e2e" / "private-mcp" / "feature-x"
        assert (clone / "branch.txt").read_text() == "feature-x", "wrong branch cloned"
        wire = github.requests_for("fluid-e2e", "private-mcp")[before:]
        assert wire[0]["status"] == 401 and not wire[0]["auth_password"], "expected GitHub's auth challenge first"
        authed = [r for r in wire if r["auth_password"]]
        assert authed and all(r["auth_user"] == "x-access-token" and r["auth_password"] == GH_TOKEN
                              and r["status"] == 200 for r in authed), "askpass did not supply GITHUB_TOKEN"
        assert all(GH_TOKEN not in r["path"] + r["query"] for r in wire), "token in request URL"
        assert "ASKPASS=set TOKEN_ENV=set" in git_shim["log"].read_text()
        assert_no_secrets((clone / ".git" / "config").read_text(), {"github-token": GH_TOKEN}, ".git/config")
        with http() as client:
            call = client.post(f"http://127.0.0.1:{port}/private-echo/mcp/tools/call", json={
                "name": "echo", "arguments": {"user_id": "u", "response_id": "private", "batch": RUN, "delay": 1}})
        assert call.status_code == 200 and "private" in call.text, call.text
        assert_no_secrets(proc.log(), {"github-token": GH_TOKEN}, "fmcp run log")
        self._assert_git_argv_clean(git_shim, GH_TOKEN)

    def test_wrong_token_fails_without_exposing_it(self, launcher, artifacts, github, git_shim):
        home = artifacts / "run-wrong-home"
        home.mkdir()
        config = home / "config.json"
        config.write_text(json.dumps({"mcpServers": {"private-echo": {
            "github_repo": "fluid-e2e/private-mcp", "branch": "feature-x"}}}))
        env = with_shim(launcher.env(home, MCP_CLIENT_SERVER_ALL_PORT=free_port(), GITHUB_TOKEN=GH_WRONG,
                                     **github.git_redirect_env()), git_shim)
        proc = launcher.start("run-wrong-token", ["run", str(config), "--file", "--start-server"], env)
        proc.wait_for_log("Repository cloning failed for fluid-e2e/private-mcp, branch feature-x")
        log = proc.log()
        assert "Reason: GitHub authentication failed" in log
        assert "Traceback" in log, "expected the clone failure to be logged with a traceback"
        assert_no_secrets(log, {"wrong-token": GH_WRONG, "real-token": GH_TOKEN}, "fmcp run log (auth failure)")
        sent = [r for r in github.requests_for("fluid-e2e", "private-mcp") if r["auth_password"] == GH_WRONG]
        assert sent and all(r["status"] == 401 for r in sent), "wrong token was not rejected by 'GitHub'"
        self._assert_git_argv_clean(git_shim, GH_WRONG)
        assert not (home / "packages" / "fluid-e2e" / "private-mcp" / "feature-x" / "branch.txt").exists()

    def test_auto_reclone_in_serve_uses_github_token(self, serve, github, artifacts):
        """Railway's ephemeral-disk path: the stored server's working_dir is gone; start re-clones it."""
        working_dir = serve["home"] / "reclone-packages" / "fluid-e2e" / "private-mcp" / "feature-x"
        assert not working_dir.exists()
        with http() as client:
            add = client.post(f"{serve['url']}/api/servers", headers=AUTH, json={
                "id": "reclone-echo", "name": "reclone-echo", "source": "github",
                "github_repo": "fluid-e2e/private-mcp", "github_branch": "feature-x",
                "command": "python3",
                "args": [str(FAKE_ECHO), "--transport", "http", "--artifacts", str(artifacts / "echo-journal")],
                "transport": "http", "working_dir": str(working_dir), "install_path": str(working_dir)})
            assert add.status_code == 200, add.text
            start = client.post(f"{serve['url']}/api/servers/reclone-echo/start", headers=AUTH)
            assert start.status_code == 200, f"{start.status_code}: {start.text}"
            assert_no_secrets(start.text, {"github-token": GH_TOKEN}, "start response")
        assert (working_dir / "branch.txt").read_text() == "feature-x"
        assert_no_secrets((working_dir / ".git" / "config").read_text(), {"github-token": GH_TOKEN}, ".git/config")
        serve["proc"].wait_for_log("auto-recloned successfully")
        assert_no_secrets(serve["proc"].log(), {"github-token": GH_TOKEN}, "serve log after reclone")

    def test_auto_reclone_failure_is_sanitized(self, launcher, artifacts, github):
        port = free_port()
        home = artifacts / "serve-wrong-gh-home"
        env = launcher.env(home, FMCP_BEARER_TOKEN=BEARER, GITHUB_TOKEN=GH_WRONG, **github.git_redirect_env())
        proc = launcher.serve("serve-wrong-github-token", env, port)
        url = f"http://127.0.0.1:{port}"
        proc.wait_http(f"{url}/health")
        working_dir = home / "reclone" / "fluid-e2e" / "private-mcp" / "feature-x"
        with http() as client:
            assert client.post(f"{url}/api/servers", headers=AUTH, json={
                "id": "reclone-fail", "name": "reclone-fail", "source": "github",
                "github_repo": "fluid-e2e/private-mcp", "github_branch": "feature-x",
                "command": "python3", "args": [str(FAKE_ECHO)], "working_dir": str(working_dir),
                "install_path": str(working_dir)}).status_code == 200
            start = client.post(f"{url}/api/servers/reclone-fail/start", headers=AUTH)
        assert start.status_code >= 400
        proc.wait_for_log("Failed to auto-reclone repository fluid-e2e/private-mcp@feature-x")
        log = proc.log()
        assert "Repository cloning failed for fluid-e2e/private-mcp, branch feature-x" in log
        assert_no_secrets(log + start.text, {"wrong-token": GH_WRONG}, "serve log / API response (reclone failure)")

    def test_add_from_github_api_with_header_token(self, serve, github):
        before = len(github.requests_for("fluid-e2e", "private-mcp"))
        with http() as client:
            response = client.post(f"{serve['url']}/api/servers/from-github",
                                   headers={**AUTH, "X-GitHub-Token": GH_TOKEN},
                                   json={"github_repo": "fluid-e2e/private-mcp", "server_id": "gh-api-echo",
                                         "branch": "main", "test_before_save": True})
        assert response.status_code == 200, response.text
        assert_no_secrets(response.text, {"github-token": GH_TOKEN}, "from-github response")
        wire = github.requests_for("fluid-e2e", "private-mcp")[before:]
        assert any(r["auth_password"] == GH_TOKEN and r["status"] == 200 for r in wire)
        assert_no_secrets(serve["proc"].log(), {"github-token": GH_TOKEN}, "serve log after from-github")


# ═════════════════════════════════════════════════════════════════════════════
# B. MongoDB credential protection
# ═════════════════════════════════════════════════════════════════════════════

class TestMongoCredentialProtection:
    def test_serve_connects_with_special_char_password_and_masks_uri(self, serve, mongo):
        with http() as client:
            health = client.get(f"{serve['url']}/health").json()
        assert health["database"]["status"] == "connected", health
        log = serve["proc"].log()
        assert f"Using MongoDB persistence backend at mongodb://***:***@127.0.0.1:{mongo.port}/" in log
        assert_no_secrets(log, {"mongo-password": MONGO_PASSWORD}, "serve startup log")

    @pytest.mark.parametrize("case", ["wrong-password", "unencoded-special-chars", "unreachable-host"])
    def test_failed_connection_never_logs_password(self, case, launcher, artifacts, mongo):
        """Railway's fail-fast mode (--require-persistence): the crash loop must not leak the password."""
        bad_password = _d("Wr0ng@pa:ss/w#rd%25-", RUN)
        uri = {
            "wrong-password": mongo.uri(password=bad_password),
            "unencoded-special-chars": mongo.uri(password=bad_password, encode=False),
            "unreachable-host": mongo.uri(port=free_port()),
        }[case]
        env = launcher.env(artifacts / f"mongo-fail-{case}", FMCP_BEARER_TOKEN=BEARER,
                           FMCP_MONGODB_SERVER_TIMEOUT=1500, FMCP_MONGODB_CONNECT_TIMEOUT=1500)
        proc = launcher.serve(f"serve-mongo-{case}", env, free_port(), "--mongodb-uri", uri,
                              "--require-persistence", in_memory=False)
        code = proc.wait_exit(timeout=120)
        log = proc.log()
        assert code != 0, "require-persistence must still fail fast (crash loop) on a bad MongoDB URI"
        assert "mongodb://***:***@" in log, "masked URI not logged"
        assert_no_secrets(log, {"bad-password": bad_password, "mongo-password": MONGO_PASSWORD},
                          f"serve log ({case})")


# ═════════════════════════════════════════════════════════════════════════════
# C. Bearer token security
# ═════════════════════════════════════════════════════════════════════════════

def _token_fragments(token):
    return {"token": token, "prefix-8": token[:8], "suffix-8": token[-8:]}


class TestBearerTokenSecurity:
    def test_configured_token_respected_across_restarts(self, launcher, artifacts):
        home = artifacts / "restart-home"
        for attempt in (1, 2):
            port = free_port()
            proc = launcher.serve(f"serve-restart-{attempt}", launcher.env(home, FMCP_BEARER_TOKEN=BEARER), port)
            url = f"http://127.0.0.1:{port}"
            proc.wait_http(f"{url}/health")
            with http() as client:
                assert client.get(f"{url}/api/servers", headers=AUTH).status_code == 200
                assert client.get(f"{url}/api/servers").status_code == 401
                assert client.get(f"{url}/api/servers", headers={"Authorization": "Bearer nope"}).status_code == 401
            proc.stop()
            log = proc.log()
            assert "BEARER TOKEN GENERATED" not in log, "a token was generated despite FMCP_BEARER_TOKEN"
            assert_no_secrets(log, _token_fragments(BEARER), f"serve log (start {attempt})")
        assert not (home / ".fmcp" / "tokens" / "current_token.txt").exists()

    def test_generated_token_never_printed_by_fmcp_serve(self, launcher, artifacts):
        home = artifacts / "generated-token-home"
        port = free_port()
        proc = launcher.serve("serve-generated-token", launcher.env(home), port)
        url = f"http://127.0.0.1:{port}"
        proc.wait_http(f"{url}/health")
        token_file = home / ".fmcp" / "tokens" / "current_token.txt"
        token = token_file.read_text().strip()
        assert len(token) >= 32
        assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
        with http() as client:
            assert client.get(f"{url}/api/servers", headers={"Authorization": f"Bearer {token}"}).status_code == 200
            assert client.get(f"{url}/api/servers").status_code == 401
        log = proc.log()
        assert "not printed because output is not a terminal" in log
        assert_no_secrets(log, _token_fragments(token), "serve log (generated token)")

    def test_generated_token_not_logged_by_server_module(self, launcher, artifacts):
        """The standalone `python -m fluidmcp.cli.server` entry point logged an 8-char prefix before PR #967."""
        home = artifacts / "server-module-home"
        env = launcher.env(home, FMCP_MONGODB_SERVER_TIMEOUT=500, FMCP_MONGODB_CONNECT_TIMEOUT=500)
        proc = launcher.start("server-module-generated-token",
                              ["--secure", "--host", "127.0.0.1", "--port", str(free_port()),
                               "--mongodb-uri", f"mongodb://127.0.0.1:{free_port()}/x"],
                              env, module="fluidmcp.cli.server")
        proc.wait_for_log("Bearer token generated (value not logged)")
        token = (home / ".fmcp" / "tokens" / "current_token.txt").read_text().strip()
        proc.stop()
        assert_no_secrets(proc.log(), _token_fragments(token), "server module log")


# ═════════════════════════════════════════════════════════════════════════════
# D. Management API authentication (live server)
# ═════════════════════════════════════════════════════════════════════════════

PREVIOUSLY_OPEN = [
    "/api/servers",
    "/api/servers/e2e-echo/status",
    "/api/servers/e2e-echo/logs",
    "/api/servers/e2e-echo/instance/env",
    "/api/servers/e2e-echo/tools",
]
PUBLIC_ROUTES = {"/health", "/", "/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}


class TestManagementApiAuthentication:
    @pytest.mark.parametrize("path", PREVIOUSLY_OPEN)
    def test_previously_open_endpoint(self, serve, path):
        url = serve["url"] + path
        with http() as client:
            assert client.get(url).status_code == 401, "missing token accepted"
            assert client.get(url, headers={"Authorization": f"Bearer wrong-{RUN}"}).status_code == 401
            for scheme in (f"Basic {BEARER}", f"Token {BEARER}", BEARER):
                assert client.get(url, headers={"Authorization": scheme}).status_code == 401, scheme.split()[0]
            ok = client.get(url, headers=AUTH)
        assert ok.status_code == 200, f"{ok.status_code}: {ok.text[:300]}"
        if path.endswith("/tools"):
            assert any(tool["name"] == "echo" for tool in ok.json()["tools"])

    def test_public_routes_stay_accessible(self, serve):
        with http() as client:
            for path in ("/health", "/", "/docs", "/openapi.json"):
                assert client.get(serve["url"] + path).status_code == 200, path

    def test_every_documented_route_rejects_bad_tokens(self, serve):
        with http() as client:
            schema = client.get(f"{serve['url']}/openapi.json").json()
            failures, checked = [], 0
            for path, operations in schema["paths"].items():
                if path in PUBLIC_ROUTES:
                    continue
                url = serve["url"] + path.replace("{", "").replace("}", "")  # e.g. /api/servers/id -> 'id'
                for method in operations:
                    checked += 1
                    for headers in ({}, {"Authorization": f"Bearer wrong-{RUN}"}):
                        status = client.request(method.upper(), url, headers=headers, json={}).status_code
                        if status not in (401, 403):
                            failures.append(f"{method.upper()} {path} {'no-token' if not headers else 'bad-token'} -> {status}")
        assert checked > 50, f"only {checked} operations documented"
        assert failures == []


# ═════════════════════════════════════════════════════════════════════════════
# E + G. MCP server configuration and child-process output protection
# ═════════════════════════════════════════════════════════════════════════════

class TestMcpServerOutputProtection:
    def test_startup_crash_output_sanitized_in_logs_api_and_records(self, serve, leak_file):
        start = add_and_start(serve, "leak-crash", ["--mode", "crash", *leak_args(leak_file)], LEAK_ENV)
        assert start.status_code == 500, start.text
        assert_no_secrets(start.text, {**CATEGORY_SECRETS, **OPAQUE_SECRETS}, "start error response")
        with http() as client:
            stderr = client.get(f"{serve['url']}/api/servers/leak-crash/stderr", headers=AUTH)
            server = client.get(f"{serve['url']}/api/servers/leak-crash/status", headers=AUTH)
        assert stderr.status_code == 200 and "auth failed for credentials" in stderr.text, stderr.text[:300]
        assert_no_secrets(stderr.text, {**CATEGORY_SECRETS, **OPAQUE_SECRETS}, "/stderr API")
        assert_no_secrets(server.text, {**CATEGORY_SECRETS, **OPAQUE_SECRETS}, "/status API")
        serve["proc"].wait_for_log("[leak-crash]")
        log = serve["proc"].log()
        assert "auth failed for credentials" in log, "crash output was not logged at all"
        assert f"--api-key ***REDACTED***" in log, "spawn command line not logged in redacted form"
        assert_no_secrets(log, {**CATEGORY_SECRETS, **OPAQUE_SECRETS}, "serve log (startup crash)")

    def test_runtime_crash_record_sanitized_before_persistence(self, serve, mongo, leak_file):
        start = add_and_start(serve, "leak-runtime",
                              ["--mode", "serve", "--exit-after", "3", *leak_args(leak_file)], LEAK_ENV)
        assert start.status_code == 200, start.text
        with http() as client:
            crashes = poll(lambda: (r := client.get(f"{serve['url']}/api/servers/leak-runtime/crashes",
                                                    headers=AUTH)).json()["crashes"] and r,
                           45, interval=1, message="health monitor never recorded the crash")
        assert "auth failed for credentials" in crashes.text, "crash record has no stderr evidence"
        assert_no_secrets(crashes.text, {**CATEGORY_SECRETS, **OPAQUE_SECRETS}, "/crashes API")
        with mongo.client() as client:
            stored = list(client[serve["database"]].fluidmcp_crash_events.find({"server_id": "leak-runtime"}))
        assert stored, "crash event not persisted to MongoDB"
        assert_no_secrets(json.dumps(stored, default=str), {**CATEGORY_SECRETS, **OPAQUE_SECRETS},
                          "MongoDB fluidmcp_crash_events document")
        assert_no_secrets(serve["proc"].log(), {**CATEGORY_SECRETS, **OPAQUE_SECRETS}, "serve log (runtime crash)")

    def test_legacy_raw_records_sanitized_when_read(self, serve, mongo):
        """Records written before PR #967 (raw) must still be served sanitized."""
        with http() as client:
            assert client.post(f"{serve['url']}/api/servers", headers=AUTH, json={
                "id": "legacy-records", "name": "legacy-records", "command": "python3",
                "args": [str(FAKE_ECHO)]}).status_code == 200
        raw = " ".join(context for context, _ in CATEGORY_LEAKS.values()) + f" opaque={SERVE_OPAQUE}"
        with mongo.client() as client:
            db = client[serve["database"]]
            db.fluidmcp_server_logs.insert_one({"server_name": "legacy-records", "stream": "stderr",
                                                "content": f"legacy {raw}", "timestamp": datetime.now(timezone.utc)})
            db.fluidmcp_crash_events.insert_one({"server_id": "legacy-records", "exit_code": 1,
                                                 "stderr_tail": f"legacy {raw}", "timestamp": datetime.now(timezone.utc)})
        secrets = {**CATEGORY_SECRETS, "serve-env-opaque": SERVE_OPAQUE}
        with http() as client:
            logs = client.get(f"{serve['url']}/api/servers/legacy-records/logs", headers=AUTH)
            crashes = client.get(f"{serve['url']}/api/servers/legacy-records/crashes", headers=AUTH)
        assert logs.status_code == 200 and "legacy" in logs.text, logs.text[:300]
        assert crashes.status_code == 200 and "legacy" in crashes.text, crashes.text[:300]
        assert_no_secrets(logs.text, secrets, "/logs API (legacy record)")
        assert_no_secrets(crashes.text, secrets, "/crashes API (legacy record)")

    def test_fmcp_run_masks_config_and_stdio_output(self, launcher, artifacts, leak_file):
        """fmcp run (stdio): spawn args, stderr and stdout noise are all sanitized."""
        port = free_port()
        home = artifacts / "run-stdio-home"
        home.mkdir()
        config = home / "config.json"
        config.write_text(json.dumps({"mcpServers": {"leaky-stdio": {
            "command": "python3", "args": [str(LEAKY), "--mode", "serve", "--transport", "stdio",
                                           *leak_args(leak_file)],
            "env": LEAK_ENV}}}))
        proc = launcher.start("run-stdio-leaky", ["run", str(config), "--file", "--start-server", "--verbose"],
                              launcher.env(home, MCP_CLIENT_SERVER_ALL_PORT=port))
        proc.wait_http(f"http://127.0.0.1:{port}/health", lambda r: r.json().get("running_servers") == 1)
        with http() as client:
            call = client.post(f"http://127.0.0.1:{port}/leaky-stdio/mcp/tools/call",
                               json={"name": "ping", "arguments": {"message": "still works"}})
        assert call.status_code == 200 and "pong: still works" in call.text, call.text
        proc.wait_for_log("auth failed for credentials")
        log = proc.log()
        assert "--api-key ***REDACTED***" in log, "spawn command line not logged in redacted form"
        assert "[stdio.non_json]" in log, "stdout noise from the stdio server was not logged"
        assert_no_secrets(log, {**CATEGORY_SECRETS, **OPAQUE_SECRETS}, "fmcp run log (stdio)")


# ═════════════════════════════════════════════════════════════════════════════
# F. Every credential category, every output channel
# ═════════════════════════════════════════════════════════════════════════════

class _SentryIngest:
    """Minimal Sentry ingest endpoint capturing raw envelopes."""

    def __init__(self):
        self.bodies = []
        ingest = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                encoding = self.headers.get("Content-Encoding", "")
                if encoding == "gzip":
                    body = gzip.decompress(body)
                elif encoding == "deflate":
                    body = zlib.decompress(body)
                elif encoding == "br":
                    import brotli
                    body = brotli.decompress(body)
                ingest.bodies.append(body.decode("utf-8", errors="replace"))
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def dsn(self):
        return f"http://e2epublickey@127.0.0.1:{self.server.server_address[1]}/1"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def _run_harness(mode, artifacts, launcher, **env_extra):
    secrets_file = artifacts / f"harness-{mode}-secrets.json"
    secrets_file.write_text(json.dumps([VENDOR_KEY, *(context for context, _ in CATEGORY_LEAKS.values())]))
    env = launcher.env(artifacts / f"harness-{mode}-home", E2E_SECRETS_FILE=secrets_file,
                       VENDOR_API_KEY=VENDOR_KEY, **env_extra)
    result = subprocess.run([sys.executable, str(HARNESS), mode], env=env, capture_output=True, text=True, timeout=120)
    (artifacts / f"harness-{mode}.out").write_text(result.stdout + "\n--- stderr ---\n" + result.stderr)
    return result


class TestEveryCredentialCategory:
    SECRETS = {**CATEGORY_SECRETS, "vendor-env-key": VENDOR_KEY}

    def test_live_server_access_log_and_api_errors(self, serve):
        """stdlib (uvicorn access log) and API error responses on the running server."""
        query = "&".join([f"api_key={CATEGORY_SECRETS['openai']}", f"key={CATEGORY_SECRETS['gemini']}",
                          f"access_token={CATEGORY_SECRETS['jwt']}", f"sig={CATEGORY_SECRETS['azure']}"])
        with http() as client:
            assert client.get(f"{serve['url']}/health?{query}").status_code == 200
            responses = [
                # Invalid env var name echoed in a 400 detail
                client.post(f"{serve['url']}/api/servers", headers=AUTH, json={
                    "id": "bad-env", "name": "bad-env", "command": "python3", "args": [],
                    "env": {CATEGORY_SECRETS["openai"]: "x"}}),
                # Dangerous argument echoed in a 400 detail
                client.post(f"{serve['url']}/api/servers", headers=AUTH, json={
                    "id": "bad-arg", "name": "bad-arg", "command": "python3",
                    "args": [f"{CATEGORY_LEAKS['github'][0]};{CATEGORY_LEAKS['stripe'][0]}"]}),
                # 422 validation error echoing the submitted body
                client.post(f"{serve['url']}/api/llm/models", headers=AUTH, json={
                    "model_id": 7, "type": "replicate", "api_key": VENDOR_KEY + "-unregistered",
                    "default_params": {"token": CATEGORY_SECRETS["huggingface"]}}),
            ]
        statuses = [r.status_code for r in responses]
        assert statuses[0] == 400 and statuses[1] == 400 and statuses[2] == 422, statuses
        for response in responses:
            assert_no_secrets(response.text, {**self.SECRETS, "unregistered": VENDOR_KEY + "-unregistered"},
                              f"API error response {response.request.url.path}")
        log = serve["proc"].log()
        assert "GET /health?api_key=***REDACTED***" in log, "uvicorn access log line not found/redacted"
        assert_no_secrets(log, self.SECRETS, "serve log (access log + API errors)")

    def test_production_logging_pipeline_in_real_process(self, artifacts, launcher):
        """loguru, stdlib logging, nested tracebacks, print() and an uncaught exception."""
        result = _run_harness("logs", artifacts, launcher)
        output = result.stdout + result.stderr
        assert result.returncode == 1, "harness should end with an uncaught exception"
        for marker in ("loguru info", "loguru exception", "stdlib request", "stdlib exception", "print"):
            assert f"E2E-MARKER {marker}" in output, f"{marker} output missing"
        assert "The above exception was the direct cause" in output, "nested traceback missing"
        assert output.count("RuntimeError: provider call failed") >= 3
        assert_no_secrets(output, self.SECRETS, "process stdout/stderr")

    def test_sentry_payloads(self, artifacts, launcher):
        ingest = _SentryIngest()
        try:
            result = _run_harness("sentry", artifacts, launcher, SENTRY_DSN=ingest.dsn, ENVIRONMENT="e2e")
            assert result.returncode == 0, result.stderr[-3000:]
            assert "E2E-MARKER logged error" in result.stdout + result.stderr
            assert_no_secrets(result.stdout + result.stderr, self.SECRETS, "Sentry process console output")
            payload = "\n".join(ingest.bodies)
            (artifacts / "sentry-envelopes.txt").write_text(payload)
        finally:
            ingest.close()
        assert '"type":"RuntimeError"' in payload.replace(" ", ""), "exception event not delivered"
        assert "ConnectionError" in payload, "chained cause not delivered"
        assert "E2E-MARKER breadcrumb" in payload, "breadcrumb not delivered"
        assert '"vars"' not in payload, "stack-frame local variables were sent"
        assert_no_secrets(payload, self.SECRETS, "Sentry envelopes")


# ═════════════════════════════════════════════════════════════════════════════
# H. Regression: normal operation still works with the security changes
# ═════════════════════════════════════════════════════════════════════════════

class TestRegression:
    def test_serve_mcp_traffic_metrics_and_ui_auth(self, serve):
        url = serve["url"]
        call = {"name": "echo", "arguments": {"user_id": "u", "response_id": f"r-{RUN}", "batch": RUN, "delay": 1}}
        with http() as client:
            assert client.post(f"{url}/e2e-echo/mcp/tools/call", json=call).status_code == 401
            ok = client.post(f"{url}/e2e-echo/mcp/tools/call", headers=AUTH, json=call)
            assert ok.status_code == 200 and f"r-{RUN}" in ok.text, ok.text
            assert client.get(f"{url}/metrics").status_code == 401
            metrics = client.get(f"{url}/metrics", headers=AUTH)
            assert metrics.status_code == 200 and "fluidmcp_" in metrics.text
            # UI: shell is public; the UI's API client sends the bearer header on every request.
            assert client.get(f"{url}/").status_code == 200
            listing = client.get(f"{url}/api/servers", headers={**AUTH, "Accept": "application/json"})
            assert listing.status_code == 200 and "e2e-echo" in listing.text
            stop = client.post(f"{url}/api/servers/e2e-echo/stop", headers=AUTH)
            assert stop.status_code == 200, stop.text
            restart = client.post(f"{url}/api/servers/e2e-echo/start", headers=AUTH)
            assert restart.status_code == 200, restart.text

    def test_fmcp_run_secure_mode(self, launcher, artifacts):
        port = free_port()
        home = artifacts / "run-secure-home"
        home.mkdir()
        config = home / "config.json"
        config.write_text(json.dumps({"mcpServers": {"run-echo": {
            "command": "python3",
            "args": [str(FAKE_ECHO), "--transport", "http", "--artifacts", str(artifacts / "echo-journal")],
            "transport": "http"}}}))
        proc = launcher.start("run-secure", ["run", str(config), "--file", "--start-server", "--secure"],
                              launcher.env(home, MCP_CLIENT_SERVER_ALL_PORT=port, FMCP_BEARER_TOKEN=BEARER))
        url = f"http://127.0.0.1:{port}"
        proc.wait_http(f"{url}/health", lambda r: r.json().get("running_servers") == 1)
        call = {"name": "echo", "arguments": {"user_id": "u", "response_id": f"run-{RUN}", "batch": RUN, "delay": 1}}
        with http() as client:
            assert client.post(f"{url}/run-echo/mcp/tools/call", json=call).status_code == 401
            ok = client.post(f"{url}/run-echo/mcp/tools/call", headers=AUTH, json=call)
        assert ok.status_code == 200 and f"run-{RUN}" in ok.text, ok.text
        assert_no_secrets(proc.log(), _token_fragments(BEARER), "fmcp run log (secure)")


# ═════════════════════════════════════════════════════════════════════════════
# Final sweep: nothing in any captured artifact (logs of every process, the
# git argv record, Sentry envelopes) contains any secret used by this module.
# ═════════════════════════════════════════════════════════════════════════════

def test_zz_no_secret_in_any_artifact(artifacts, serve):
    allowed_to_contain = {
        # Inputs the tests wrote on purpose (configs, harness secrets, the leaky server's input).
        "config.json", "harness-logs-secrets.json", "harness-sentry-secrets.json", "category-leaks.txt",
    }
    checked = 0
    raw_child_logs = []
    for path in artifacts.rglob("*"):
        if not path.is_file():
            continue
        if ".fluidmcp" in path.parts:
            # Documented limitation: the child process writes its own stderr file directly
            # (FluidMCP never sees those bytes in transit). It must be owner-only; every
            # reader sanitizes it (asserted via the /stderr and /crashes APIs above).
            raw_child_logs.append(path)
            assert stat.S_IMODE(path.stat().st_mode) == 0o600, f"{path} is not owner-only"
            continue
        if (path.name in allowed_to_contain or "mock-github" in path.parts or "packages" in path.parts
                or "reclone-packages" in path.parts or path.suffix == ".jsonl"):
            continue
        assert_no_secrets(path.read_text(errors="replace"), ALL_SECRETS,
                          f"artifact {path.relative_to(artifacts)}")
        checked += 1
    assert checked >= 10, f"only {checked} artifacts were swept"
    assert raw_child_logs, "expected per-server stderr files under ~/.fluidmcp/logs"
