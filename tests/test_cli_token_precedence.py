"""Token precedence for `fmcp serve --secure`: --token > FMCP_BEARER_TOKEN > generate."""
import os
import sys
from unittest.mock import patch, AsyncMock

import pytest

from fluidmcp.cli import cli


def _run_serve(monkeypatch, tmp_path, argv, env_token=None):
    monkeypatch.delenv("FMCP_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("FMCP_SECURE_MODE", raising=False)
    if env_token is not None:
        monkeypatch.setenv("FMCP_BEARER_TOKEN", env_token)
    token_file = tmp_path / "tokens" / "current_token.txt"
    monkeypatch.setattr(sys, "argv", ["fmcp", "serve", *argv])
    # main() loads the repo .env with override=True; keep tests hermetic.
    with patch.object(cli, "get_token_file", return_value=token_file), \
            patch.object(cli, "load_dotenv"), \
            patch("fluidmcp.cli.server.main", new=AsyncMock()):
        cli.main()
    return token_file


def test_env_token_used_when_no_cli_token(monkeypatch, tmp_path, capsys):
    token_file = _run_serve(monkeypatch, tmp_path, ["--secure"], env_token="abc")
    assert os.environ["FMCP_BEARER_TOKEN"] == "abc"
    assert os.environ["FMCP_SECURE_MODE"] == "true"
    assert not token_file.exists()
    assert "BEARER TOKEN GENERATED" not in capsys.readouterr().out


def test_env_token_is_stripped(monkeypatch, tmp_path):
    _run_serve(monkeypatch, tmp_path, ["--secure"], env_token="abc\n")
    assert os.environ["FMCP_BEARER_TOKEN"] == "abc"


def test_cli_token_overrides_env(monkeypatch, tmp_path):
    _run_serve(monkeypatch, tmp_path, ["--secure", "--token", "xyz"], env_token="abc")
    assert os.environ["FMCP_BEARER_TOKEN"] == "xyz"


def test_generates_token_when_none_provided(monkeypatch, tmp_path, capsys):
    token_file = _run_serve(monkeypatch, tmp_path, ["--secure"])
    generated = os.environ["FMCP_BEARER_TOKEN"]
    assert len(generated) >= 32
    assert token_file.read_text() == generated
    assert "BEARER TOKEN GENERATED" in capsys.readouterr().out


def test_blank_env_token_falls_back_to_generation(monkeypatch, tmp_path):
    _run_serve(monkeypatch, tmp_path, ["--secure"], env_token="   ")
    assert os.environ["FMCP_BEARER_TOKEN"].strip()
    assert len(os.environ["FMCP_BEARER_TOKEN"]) >= 32
