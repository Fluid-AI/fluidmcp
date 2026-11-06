"""Local stand-in for github.com: real git Smart HTTP over ``git http-backend``.

FluidMCP always clones ``https://github.com/<owner>/<repo>.git``. The E2E tests
point git at this server with ``url.<base>.insteadOf=https://github.com/``
(set through ``GIT_CONFIG_*`` environment variables), so the real git binary
performs a real HTTP clone and a real credential exchange:

* public repositories are served without authentication;
* private repositories answer 401 until the request carries HTTP Basic
  credentials whose password equals the configured token (GitHub accepts any
  username with a PAT; FluidMCP's askpass helper sends ``x-access-token``).

Every request is recorded (path, query, credentials presented, status) so the
tests can prove what was sent on the wire and that tokens never appear in URLs.
"""

import base64
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

# Isolate every git invocation from the host's global/system configuration
# (e.g. credential helpers in developer machines and CI images).
GIT_ISOLATION = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0"}


def git_env():
    env = {key: os.environ[key] for key in ("PATH", "LANG", "SYSTEMROOT") if key in os.environ}
    env.update(GIT_ISOLATION)
    return env


def run_git(*args, cwd):
    subprocess.run(
        ["git", "-c", "user.name=fmcp-e2e", "-c", "user.email=e2e@example.invalid",
         "-c", "commit.gpgsign=false", *args],
        cwd=cwd, env=git_env(), check=True, capture_output=True, text=True,
    )


class MockGitHub:
    def __init__(self, root: Path, token: str):
        self.root = Path(root)
        self.repos_dir = self.root / "repos"
        self.repos_dir.mkdir(parents=True, exist_ok=True)
        self.token = token
        self.private = set()
        self.requests = []
        self._lock = threading.Lock()
        self._server = None
        self._thread = None

    # ── repositories ──────────────────────────────────────────────────────────
    def create_repo(self, owner, repo, branches, private=False):
        """branches: {branch_name: {relative_path: text}} - first entry is the default branch."""
        work = self.root / "work" / owner / repo
        work.mkdir(parents=True)
        branch_names = list(branches)
        run_git("init", "-q", "-b", branch_names[0], cwd=work)
        for index, name in enumerate(branch_names):
            if index:
                run_git("checkout", "-q", "-b", name, cwd=work)
            for rel, text in branches[name].items():
                path = work / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            run_git("add", "-A", cwd=work)
            run_git("commit", "-q", "-m", f"{name} content", cwd=work)
        bare = self.repos_dir / owner / f"{repo}.git"
        bare.parent.mkdir(parents=True, exist_ok=True)
        run_git("clone", "-q", "--bare", str(work), str(bare), cwd=self.root)
        shutil.rmtree(work)
        if private:
            self.private.add(f"{owner}/{repo}")

    # ── server lifecycle ──────────────────────────────────────────────────────
    @property
    def base_url(self):
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def start(self):
        handler = self._make_handler()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, name="mock-github", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._thread.join(timeout=5)

    def git_redirect_env(self):
        """Environment that makes any git process clone from this server instead of github.com."""
        return {**GIT_ISOLATION, "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": f"url.{self.base_url}/.insteadOf",
                "GIT_CONFIG_VALUE_0": "https://github.com/"}

    def requests_for(self, owner, repo):
        prefix = f"/{owner}/{repo}.git/"
        with self._lock:
            return [r for r in self.requests if r["path"].startswith(prefix)]

    # ── HTTP handling ─────────────────────────────────────────────────────────
    def _make_handler(self):
        mock = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep test output clean
                pass

            def _credentials(self):
                header = self.headers.get("Authorization", "")
                if not header.lower().startswith("basic "):
                    return None, None
                try:
                    user, _, password = base64.b64decode(header[6:]).decode().partition(":")
                except ValueError:
                    return None, None
                return user, password

            def _read_body(self):
                if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
                    chunks = []
                    while True:
                        size = int(self.rfile.readline().strip() or b"0", 16)
                        if size == 0:
                            self.rfile.readline()
                            break
                        chunks.append(self.rfile.read(size))
                        self.rfile.readline()
                    return b"".join(chunks)
                return self.rfile.read(int(self.headers.get("Content-Length") or 0))

            def _handle(self):
                parts = urlsplit(self.path)
                segments = parts.path.strip("/").split("/")
                repo_key = f"{segments[0]}/{segments[1][:-4]}" if len(segments) > 1 and segments[1].endswith(".git") else ""
                user, password = self._credentials()
                record = {"method": self.command, "path": parts.path, "query": parts.query,
                          "repo": repo_key, "auth_user": user, "auth_password": password,
                          "authorized": repo_key not in mock.private or password == mock.token}
                body = self._read_body() if self.command == "POST" else b""
                if not record["authorized"]:
                    record["status"] = 401
                    with mock._lock:
                        mock.requests.append(record)
                    self.send_response(401)
                    self.send_header("WWW-Authenticate", 'Basic realm="GitHub"')
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                env = git_env()
                env.update({
                    "GIT_PROJECT_ROOT": str(mock.repos_dir), "GIT_HTTP_EXPORT_ALL": "1",
                    "PATH_INFO": parts.path, "QUERY_STRING": parts.query,
                    "REQUEST_METHOD": self.command, "REMOTE_ADDR": "127.0.0.1",
                    "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                    "CONTENT_LENGTH": str(len(body)),
                    "HTTP_CONTENT_ENCODING": self.headers.get("Content-Encoding", ""),
                    "GIT_PROTOCOL": self.headers.get("Git-Protocol", ""),
                })
                if user:
                    env["REMOTE_USER"] = user
                result = subprocess.run(["git", "http-backend"], input=body, env=env, capture_output=True)
                head, _, payload = result.stdout.partition(b"\r\n\r\n")
                status, headers = 200, []
                for line in head.decode("latin-1").split("\r\n"):
                    name, _, value = line.partition(":")
                    if name.lower() == "status":
                        status = int(value.strip().split()[0])
                    elif name:
                        headers.append((name, value.strip()))
                record["status"] = status
                with mock._lock:
                    mock.requests.append(record)
                self.send_response(status)
                for name, value in headers:
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = _handle
            do_POST = _handle

        return Handler
