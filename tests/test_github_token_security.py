"""
Security tests: GitHub credentials must never leak into logs, exceptions,
tracebacks, subprocess arguments or .git/config.

Regression tests for the Railway incident where a failed clone logged:
    fatal: could not read Password for 'https://github_pat_...@github.com': ...

All tokens below are fake test values. Git is either mocked, or (for the
real-git tests) redirected to local file:// repositories so no network or
real credentials are used.
"""

import base64
import io
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from loguru import logger

from fluidmcp.cli.services import github_utils
from fluidmcp.cli.services.github_utils import clone_github_repo, clone_or_update_repo
from fluidmcp.cli.utils.redact import (
    REDACTED,
    RedactingStream,
    install_log_redaction,
    redact_secrets,
    sanitize_error_message,
)

# Fake credentials, test-only. Assembled from fragments so secret scanners
# (e.g. GitHub push protection) do not mistake them for real tokens.
FAKE_PAT = "github_pat_" + "11TESTONLY0000000000_" + "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOP0123"
FAKE_CLASSIC = "gh" + "p_" + "TESTONLYabcdefghijklmnopqrstuvwxyz0123"
FAKE_OPAQUE = "0123456789abcdef0123456789abcdef01234567"  # legacy 40-hex token, no prefix

_REAL_RUN = subprocess.run  # github_utils.subprocess is the global module; keep the real one

OWNER, REPO, BRANCH ="Fluid-AI", "fluid-ai-mcp-servers", "gemini-image-mcp"

RAILWAY_STDERR = (
    f"Cloning into '/app/.fmcp-packages/{OWNER}/{REPO}/{BRANCH}'...\n"
    f"fatal: could not read Password for 'https://{FAKE_PAT}@github.com': "
    f"No such device or address\n"
)


def all_forms(token):
    """Raw token plus Base64 forms that HTTP Basic auth would carry."""
    forms = [token]
    for raw in (token, f"x-access-token:{token}"):
        enc = base64.b64encode(raw.encode()).decode()
        forms += [enc, enc.rstrip("=")]
    return forms


def assert_no_secret(text, token=FAKE_PAT):
    for form in all_forms(token):
        assert form not in text, f"secret form leaked: {form[:12]}..."


def git_failure(stderr, returncode=128):
    def _run(cmd, *args, **kwargs):
        raise subprocess.CalledProcessError(returncode, cmd, output="", stderr=stderr)
    return _run


@pytest.fixture
def captured_logs():
    """Capture loguru output through the production redaction path."""
    buf = io.StringIO()
    install_log_redaction()
    sink_id = logger.add(RedactingStream(buf), level="DEBUG", format="{message}", diagnose=False)
    yield buf
    logger.remove(sink_id)
    logger.configure(patcher=lambda record: None)


@pytest.fixture
def clean_github_env(monkeypatch):
    for name in ("GITHUB_TOKEN", "FMCP_GITHUB_TOKEN"):
        monkeypatch.delenv(name, raising=False)


# --------------------------------------------------------------------------- #
# Redaction utility
# --------------------------------------------------------------------------- #

class TestRedactSecrets:
    @pytest.mark.parametrize("token", [
        FAKE_PAT,
        FAKE_CLASSIC,
        "gho_TESTONLYabcdefghijklmnopqrstuvwxyz0123",
        "ghs_TESTONLYabcdefghijklmnopqrstuvwxyz0123",
    ])
    def test_github_token_formats(self, token, clean_github_env):
        out = redact_secrets(f"token is {token} here")
        assert token not in out
        assert REDACTED in out

    @pytest.mark.parametrize("url,host", [
        (f"https://{FAKE_PAT}@github.com/o/r.git", "github.com/o/r.git"),
        (f"https://x-access-token:{FAKE_OPAQUE}@github.com/o/r", "github.com/o/r"),
        ("mongodb+srv://admin:hunter2pass@cluster0.mongodb.net/db", "cluster0.mongodb.net/db"),
    ])
    def test_credentials_in_urls(self, url, host, clean_github_env):
        out = redact_secrets(f"fatal: unable to access '{url}'")
        assert f"://{REDACTED}@{host}" in out
        assert FAKE_PAT not in out and FAKE_OPAQUE not in out and "hunter2pass" not in out

    def test_railway_log_line(self, clean_github_env):
        out = redact_secrets(RAILWAY_STDERR)
        assert_no_secret(out)
        assert "could not read Password" in out  # useful context preserved

    def test_explicit_opaque_secret_and_base64(self, clean_github_env):
        basic = base64.b64encode(f"x-access-token:{FAKE_OPAQUE}".encode()).decode()
        text = f"raw={FAKE_OPAQUE} hdr=Authorization: Basic {basic} b64={base64.b64encode(FAKE_OPAQUE.encode()).decode()}"
        out = redact_secrets(text, extra_secrets=[FAKE_OPAQUE])
        assert_no_secret(out, FAKE_OPAQUE)

    def test_env_var_values_redacted_without_pattern(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_OPAQUE)
        out = redact_secrets(f"value {FAKE_OPAQUE} and {base64.b64encode(FAKE_OPAQUE.encode()).decode()}")
        assert_no_secret(out, FAKE_OPAQUE)

    @pytest.mark.parametrize("text,secret", [
        ("Authorization: Bearer abcdef1234567890XYZ", "abcdef1234567890XYZ"),
        ('{"password": "s3cr3t-value"}', "s3cr3t-value"),
        ("api_key=AKIAEXAMPLEKEY99", "AKIAEXAMPLEKEY99"),
        ("REPLICATE r8_abcdefghijklmnopqrstuvwxyz012345", "r8_abcdefghijklmnopqrstuvwxyz012345"),
        ("key sk_live_abcdefghijklmnop", "sk_live_abcdefghijklmnop"),
    ])
    def test_other_secret_patterns(self, text, secret, clean_github_env):
        assert secret not in redact_secrets(text)

    def test_does_not_mangle_normal_log_lines(self, clean_github_env):
        line = (
            "Cloned Fluid-AI/fluid-ai-mcp-servers@gemini-image-mcp to /app/.fmcp-packages "
            "trace_id=550e8400-e29b-41d4-a716-446655440000 sha=3f786850e387550fdab836ed7e6dc881de23001b"
        )
        assert redact_secrets(line) == line

    def test_sanitize_error_message_keeps_existing_behaviour(self, clean_github_env):
        assert "r8_" + REDACTED in sanitize_error_message("key r8_abcdefghijklmnopqrstuvwxyz0123")
        assert "abc123def456ghi789jkl012" not in sanitize_error_message("id abc123def456ghi789jkl012")
        assert FAKE_PAT not in sanitize_error_message(RAILWAY_STDERR)

    def test_management_sanitize_delegates(self, clean_github_env):
        from fluidmcp.cli.api.management import sanitize_error_message as mgmt_sanitize
        assert_no_secret(mgmt_sanitize(RAILWAY_STDERR))
        assert_no_secret(mgmt_sanitize(RuntimeError(RAILWAY_STDERR)))


# --------------------------------------------------------------------------- #
# Clone authentication (mocked git)
# --------------------------------------------------------------------------- #

class TestCloneAuthentication:
    def _mock_success(self, calls):
        def _run(cmd, *args, **kwargs):
            env = kwargs.get("env") or {}
            askpass = env.get("GIT_ASKPASS")
            snapshot = {"cmd": list(cmd), "env": dict(env), "askpass": askpass}
            if askpass:
                snapshot["askpass_exists"] = os.path.exists(askpass)
                snapshot["askpass_mode"] = stat.S_IMODE(os.stat(askpass).st_mode)
                snapshot["askpass_dir_mode"] = stat.S_IMODE(os.stat(os.path.dirname(askpass)).st_mode)
                snapshot["askpass_text"] = Path(askpass).read_text()
                if os.name != "nt":
                    snapshot["username"] = _REAL_RUN(
                        [askpass, "Username for 'https://github.com': "],
                        env=env, capture_output=True, text=True).stdout.strip()
                    snapshot["password"] = _REAL_RUN(
                        [askpass, "Password for 'https://x-access-token@github.com': "],
                        env=env, capture_output=True, text=True).stdout.strip()
            calls.append(snapshot)
            Path(cmd[-1]).mkdir(parents=True, exist_ok=True)
            return MagicMock(returncode=0, stdout="", stderr="")
        return _run

    def test_private_clone_uses_askpass_not_url(self, tmp_path):
        calls = []
        with patch.object(github_utils.subprocess, "run", side_effect=self._mock_success(calls)):
            dest = clone_github_repo(f"{OWNER}/{REPO}", FAKE_PAT, BRANCH, install_dir=tmp_path)

        assert dest == tmp_path / OWNER / REPO / BRANCH
        call = calls[0]
        # Clean URL, token absent from argv in any form
        assert f"https://github.com/{OWNER}/{REPO}.git" in call["cmd"]
        assert_no_secret(" ".join(call["cmd"]))
        assert "credential.helper=" in call["cmd"]
        # Branch-specific clone
        assert call["cmd"][call["cmd"].index("--branch") + 1] == BRANCH
        # Askpass wiring
        assert call["env"]["GIT_TERMINAL_PROMPT"] == "0"
        assert call["askpass_exists"]
        assert FAKE_PAT not in call["askpass_text"], "token must not be written to disk"
        if os.name != "nt":
            assert call["askpass_mode"] == 0o700
            assert call["askpass_dir_mode"] == 0o700
            assert call["username"] == "x-access-token"
            assert call["password"] == FAKE_PAT
        # Temp helper cleaned up
        assert not os.path.exists(call["askpass"])
        assert not os.path.exists(os.path.dirname(call["askpass"]))

    def test_token_not_leaked_into_process_environment(self, tmp_path):
        before = dict(os.environ)
        with patch.object(github_utils.subprocess, "run", side_effect=self._mock_success([])):
            clone_github_repo(f"{OWNER}/{REPO}", FAKE_PAT, BRANCH, install_dir=tmp_path)
        assert dict(os.environ) == before
        assert FAKE_PAT not in os.environ.values()

    def test_askpass_cleaned_up_on_failure(self, tmp_path):
        seen = []

        def _run(cmd, *args, **kwargs):
            seen.append(kwargs["env"]["GIT_ASKPASS"])
            raise subprocess.CalledProcessError(128, cmd, stderr=RAILWAY_STDERR)

        with patch.object(github_utils.subprocess, "run", side_effect=_run):
            with pytest.raises(RuntimeError):
                clone_github_repo(f"{OWNER}/{REPO}", FAKE_PAT, BRANCH, install_dir=tmp_path)
        assert not os.path.exists(os.path.dirname(seen[0]))

    def test_missing_token_still_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            clone_github_repo(f"{OWNER}/{REPO}", "", BRANCH, install_dir=tmp_path)


# --------------------------------------------------------------------------- #
# Error sanitization
# --------------------------------------------------------------------------- #

class TestCloneErrors:
    @pytest.mark.parametrize("stderr,reason", [
        (RAILWAY_STDERR, "GitHub authentication failed"),
        ("fatal: could not read Username for 'https://github.com': terminal prompts disabled",
         "GitHub authentication failed"),
        (f"remote: Invalid username or token. Password authentication is not supported.\n"
         f"fatal: Authentication failed for 'https://{FAKE_PAT}@github.com/{OWNER}/{REPO}.git/'",
         "GitHub authentication failed"),
        (f"remote: Repository not found.\nfatal: repository 'https://{FAKE_PAT}@github.com/{OWNER}/{REPO}.git/' not found",
         "Repository or branch not found"),
        (f"warning: Could not find remote branch {BRANCH} to clone.\nfatal: Remote branch {BRANCH} not found in upstream origin",
         "Repository or branch not found"),
        (f"remote: Write access to repository not granted.\nfatal: unable to access "
         f"'https://{FAKE_PAT}@github.com/{OWNER}/{REPO}.git/': The requested URL returned error: 403",
         "Permission denied"),
        (f"fatal: something odd happened with https://{FAKE_PAT}@github.com", "Unexpected git error"),
    ])
    def test_errors_are_useful_and_sanitized(self, stderr, reason, tmp_path, clean_github_env):
        with patch.object(github_utils.subprocess, "run", side_effect=git_failure(stderr)):
            with pytest.raises(RuntimeError) as exc_info:
                clone_github_repo(f"{OWNER}/{REPO}", FAKE_PAT, BRANCH, install_dir=tmp_path)

        msg = str(exc_info.value)
        assert msg.startswith(
            f"Repository cloning failed for {OWNER}/{REPO}, branch {BRANCH}. "
            "Check GitHub authentication and repository permissions."
        )
        assert f"Reason: {reason}" in msg
        assert "Exit code: 128" in msg
        assert_no_secret(msg)

    def test_exception_chain_does_not_carry_raw_stderr(self, tmp_path, clean_github_env):
        import traceback
        with patch.object(github_utils.subprocess, "run", side_effect=git_failure(RAILWAY_STDERR)):
            with pytest.raises(RuntimeError) as exc_info:
                clone_github_repo(f"{OWNER}/{REPO}", FAKE_PAT, BRANCH, install_dir=tmp_path)
        assert exc_info.value.__cause__ is None
        assert exc_info.value.__suppress_context__ is True
        assert_no_secret("".join(traceback.format_exception(exc_info.value)))

    def test_opaque_token_redacted_from_error(self, tmp_path, clean_github_env):
        stderr = f"fatal: could not read Password for 'https://{FAKE_OPAQUE}@github.com': x\n{FAKE_OPAQUE}"
        with patch.object(github_utils.subprocess, "run", side_effect=git_failure(stderr)):
            with pytest.raises(RuntimeError) as exc_info:
                clone_github_repo(f"{OWNER}/{REPO}", FAKE_OPAQUE, BRANCH, install_dir=tmp_path)
        assert_no_secret(str(exc_info.value), FAKE_OPAQUE)

    def test_pull_failure_warning_is_sanitized(self, tmp_path, captured_logs, clean_github_env):
        dest = tmp_path / OWNER / REPO / BRANCH
        dest.mkdir(parents=True)
        (dest / "README.md").write_text("x")
        with patch.object(github_utils.subprocess, "run", side_effect=git_failure(RAILWAY_STDERR, 1)):
            assert clone_or_update_repo(f"{OWNER}/{REPO}", FAKE_PAT, BRANCH, install_dir=tmp_path) == dest
        logs = captured_logs.getvalue()
        assert "git pull --rebase failed" in logs
        assert_no_secret(logs)


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #

class TestLogRedaction:
    def test_all_log_levels_redacted(self, captured_logs, clean_github_env):
        url = f"https://{FAKE_PAT}@github.com/{OWNER}/{REPO}"
        logger.debug(f"debug {url}")
        logger.info(f"info {FAKE_PAT}")
        logger.warning(f"warning {FAKE_CLASSIC}")
        logger.error(f"Failed to auto-reclone repository: {RAILWAY_STDERR}")
        out = captured_logs.getvalue()
        assert out.count(REDACTED) >= 4
        assert_no_secret(out)
        assert FAKE_CLASSIC not in out

    def test_exception_and_nested_traceback_redacted(self, captured_logs, clean_github_env):
        try:
            try:
                raise ValueError(f"inner https://{FAKE_PAT}@github.com")
            except ValueError as inner:
                raise RuntimeError(f"outer {FAKE_PAT}") from inner
        except RuntimeError:
            logger.exception("clone blew up")
        out = captured_logs.getvalue()
        assert "clone blew up" in out and "ValueError" in out
        assert_no_secret(out)

    def test_traceback_locals_not_printed(self, captured_logs, clean_github_env):
        def leaky(github_token):
            raise RuntimeError("boom")
        try:
            leaky(FAKE_OPAQUE)  # opaque token has no pattern; only diagnose=False protects it
        except RuntimeError:
            logger.exception("failed")
        assert FAKE_OPAQUE not in captured_logs.getvalue()

    def test_json_sink_redacts_msg_and_exc(self, capsys, clean_github_env):
        from fluidmcp.cli import server
        server._configure_json_logging()
        try:
            logger.bind(server_id=f"srv-{FAKE_PAT}").error(f"Failed: {RAILWAY_STDERR}")
            try:
                raise RuntimeError(f"https://{FAKE_PAT}@github.com")
            except RuntimeError:
                logger.exception("reclone failed")
        finally:
            logger.remove()
            logger.configure(patcher=lambda record: None)
            logger.add(sys.stderr)
        err = capsys.readouterr().err
        lines = [json.loads(line) for line in err.splitlines() if line.startswith("{")]
        assert len(lines) == 2
        assert "exc" in lines[1]
        assert_no_secret(err)

    def test_cli_configure_logger_redacts(self, capsys, clean_github_env):
        from fluidmcp.cli.cli import configure_logger
        configure_logger(verbose=True)
        try:
            logger.error(f"git said: {RAILWAY_STDERR}")
        finally:
            logger.remove()
            logger.configure(patcher=lambda record: None)
            logger.add(sys.stderr)
        err = capsys.readouterr().err
        assert "git said" in err
        assert_no_secret(err)


# --------------------------------------------------------------------------- #
# Auto-reclone (server_manager) + token env var compatibility
# --------------------------------------------------------------------------- #

class TestAutoReclone:
    def _config(self, tmp_path):
        return {
            "id": "gemini",
            "name": "gemini",
            "source": "github",
            "github_repo": f"{OWNER}/{REPO}",
            "github_branch": BRANCH,
            "command": "fmcp-test-nonexistent-binary",
            "args": [],
            "env": {},
            "working_dir": str(tmp_path / ".fmcp-packages" / OWNER / REPO / BRANCH),
        }

    async def _spawn(self, config):
        from fluidmcp.cli.repositories import InMemoryBackend
        from fluidmcp.cli.services.server_manager import ServerManager
        return await ServerManager(InMemoryBackend())._spawn_mcp_process("gemini", config)

    @pytest.mark.parametrize("env_name", ["GITHUB_TOKEN", "FMCP_GITHUB_TOKEN"])
    async def test_reclone_uses_token_from_env(self, env_name, tmp_path, monkeypatch, clean_github_env, captured_logs):
        monkeypatch.setenv(env_name, FAKE_PAT)
        config = self._config(tmp_path)

        def fake_clone(repo_path, branch, github_token, install_dir):
            Path(config["working_dir"]).mkdir(parents=True)
            return Path(config["working_dir"])

        with patch.object(github_utils, "clone_github_repo", side_effect=fake_clone) as mock_clone:
            await self._spawn(config)

        kwargs = mock_clone.call_args.kwargs
        assert kwargs["github_token"] == FAKE_PAT
        assert kwargs["repo_path"] == f"{OWNER}/{REPO}" and kwargs["branch"] == BRANCH
        assert kwargs["install_dir"] == tmp_path / ".fmcp-packages"
        logs = captured_logs.getvalue()
        assert "auto-recloned successfully" in logs
        assert_no_secret(logs)

    async def test_reclone_failure_log_is_sanitized(self, tmp_path, monkeypatch, clean_github_env, captured_logs):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_PAT)
        with patch.object(github_utils.subprocess, "run", side_effect=git_failure(RAILWAY_STDERR)):
            result = await self._spawn(self._config(tmp_path))
        assert result is None
        logs = captured_logs.getvalue()
        assert f"Repository cloning failed for {OWNER}/{REPO}, branch {BRANCH}" in logs
        assert_no_secret(logs)

    async def test_reclone_unexpected_exception_is_sanitized(self, tmp_path, monkeypatch, clean_github_env, captured_logs):
        monkeypatch.setenv("GITHUB_TOKEN", FAKE_OPAQUE)
        with patch.object(github_utils, "clone_github_repo", side_effect=OSError(f"weird {FAKE_OPAQUE}")):
            assert await self._spawn(self._config(tmp_path)) is None
        assert FAKE_OPAQUE not in captured_logs.getvalue()

    async def test_reclone_requires_token(self, tmp_path, clean_github_env, captured_logs):
        with patch.object(github_utils, "clone_github_repo") as mock_clone:
            assert await self._spawn(self._config(tmp_path)) is None
        mock_clone.assert_not_called()
        assert "GITHUB_TOKEN" in captured_logs.getvalue()


# --------------------------------------------------------------------------- #
# Real git, redirected to local repositories (no network)
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
class TestRealGit:
    @pytest.fixture
    def local_github(self, tmp_path, monkeypatch):
        """Create OWNER/REPO with 'main' and BRANCH, and redirect https://github.com/ to it."""
        root = tmp_path / "remote"
        src = root / OWNER / f"{REPO}.git"
        work = tmp_path / "work"
        git = lambda *a, cwd=work: subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)
        work.mkdir()
        git("init", "-b", "main")
        git("config", "user.email", "t@example.com")
        git("config", "user.name", "t")
        (work / "README.md").write_text("main branch")
        git("add", ".")
        git("commit", "-m", "main")
        git("checkout", "-b", BRANCH)
        (work / "README.md").write_text("feature branch")
        git("commit", "-am", "feature")
        src.parent.mkdir(parents=True)
        git("clone", "--bare", str(work), str(src), cwd=tmp_path)

        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.{root.as_uri()}/.insteadOf")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", "https://github.com/")
        return tmp_path / "install"

    def test_public_clone_default_branch(self, local_github):
        dest = clone_github_repo(f"{OWNER}/{REPO}", FAKE_PAT, install_dir=local_github)
        assert (dest / "README.md").read_text() == "main branch"

    def test_branch_specific_clone_has_clean_remote(self, local_github):
        dest = clone_github_repo(f"{OWNER}/{REPO}", FAKE_PAT, BRANCH, install_dir=local_github)
        assert (dest / "README.md").read_text() == "feature branch"
        assert_no_secret((dest / ".git" / "config").read_text())

    def test_missing_branch_gives_sanitized_error(self, local_github):
        with pytest.raises(RuntimeError) as exc_info:
            clone_github_repo(f"{OWNER}/{REPO}", FAKE_PAT, "no-such-branch", install_dir=local_github)
        msg = str(exc_info.value)
        assert "Repository or branch not found" in msg
        assert_no_secret(msg)

    def test_legacy_token_in_remote_is_scrubbed(self, local_github):
        dest = clone_github_repo(f"{OWNER}/{REPO}", FAKE_PAT, BRANCH, install_dir=local_github)
        # Simulate a clone made by the old code: token stored in the remote URL
        subprocess.run(["git", "remote", "set-url", "origin",
                        f"https://{FAKE_PAT}@github.com/{OWNER}/{REPO}.git"], cwd=dest, check=True)
        assert FAKE_PAT in (dest / ".git" / "config").read_text()

        clone_or_update_repo(f"{OWNER}/{REPO}", FAKE_PAT, BRANCH, install_dir=local_github)

        config_text = (dest / ".git" / "config").read_text()
        assert_no_secret(config_text)
        assert f"https://github.com/{OWNER}/{REPO}.git" in config_text
