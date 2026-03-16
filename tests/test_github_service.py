"""
Unit tests for GitHubService (github_utils.py) and ServerBuilder (server_builder.py).

Tests cover:
- ServerBuilder.slugify()
- ServerBuilder.generate_server_id()
- ServerBuilder.build_config()
- GitHubService.build_server_configs() (with mocked clone + metadata)
- clone_or_update_repo() (fresh clone vs existing clone)
- validate_command_allowlist() (allowlist enforcement)
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
from datetime import datetime

from fluidmcp.cli.services.server_builder import ServerBuilder
from fluidmcp.cli.services.github_utils import GitHubService, clone_or_update_repo
from fluidmcp.cli.services.validators import validate_command_allowlist


# ==================== ServerBuilder Tests ====================

class TestServerBuilderSlugify:
    def test_lowercase(self):
        assert ServerBuilder.slugify("MyServer") == "myserver"

    def test_spaces_become_hyphens(self):
        assert ServerBuilder.slugify("My Server") == "my-server"

    def test_underscores_become_hyphens(self):
        assert ServerBuilder.slugify("file_system") == "file-system"

    def test_mixed_spaces_and_underscores(self):
        assert ServerBuilder.slugify("My_File Server") == "my-file-server"

    def test_removes_special_chars(self):
        # dots are removed; no hyphen is inserted in their place
        assert ServerBuilder.slugify("API v2.0") == "api-v20"

    def test_collapses_consecutive_hyphens(self):
        assert ServerBuilder.slugify("a--b") == "a-b"

    def test_strips_leading_trailing_hyphens(self):
        assert ServerBuilder.slugify("-hello-") == "hello"

    def test_already_slug(self):
        assert ServerBuilder.slugify("my-server") == "my-server"

    def test_numbers_preserved(self):
        assert ServerBuilder.slugify("server123") == "server123"


class TestServerBuilderGenerateId:
    def test_single_server_uses_base_id_directly(self):
        result = ServerBuilder.generate_server_id("my-server", "filesystem", is_multi_server=False)
        assert result == "my-server"

    def test_multi_server_appends_slugified_name(self):
        result = ServerBuilder.generate_server_id("tools", "Filesystem Server", is_multi_server=True)
        assert result == "tools-filesystem-server"

    def test_multi_server_simple_name(self):
        result = ServerBuilder.generate_server_id("tools", "filesystem", is_multi_server=True)
        assert result == "tools-filesystem"

    def test_multi_server_name_with_version(self):
        result = ServerBuilder.generate_server_id("suite", "API v2.0", is_multi_server=True)
        assert result == "suite-api-v20"


class TestServerBuilderBuildConfig:
    def _make_config(self, **overrides):
        kwargs = dict(
            base_id="my-server",
            server_name="filesystem",
            server_config={
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem"],
                "env": {"NODE_ENV": "production"},
            },
            clone_path=Path("/tmp/clone"),
            repo_path="owner/repo",
            branch="main",
            env=None,
            restart_policy="never",
            max_restarts=3,
            enabled=True,
            is_multi_server=False,
        )
        kwargs.update(overrides)
        return ServerBuilder.build_config(**kwargs)

    def test_flat_format_has_top_level_command(self):
        config = self._make_config()
        assert config["command"] == "npx"
        assert config["args"] == ["-y", "@modelcontextprotocol/server-filesystem"]

    def test_no_nested_mcp_config_key(self):
        config = self._make_config()
        assert "mcp_config" not in config

    def test_id_single_server(self):
        config = self._make_config()
        assert config["id"] == "my-server"

    def test_id_multi_server(self):
        config = self._make_config(is_multi_server=True, base_id="tools", server_name="Database Server")
        assert config["id"] == "tools-database-server"

    def test_env_merge_user_overrides_repo(self):
        config = self._make_config(env={"NODE_ENV": "test", "EXTRA": "yes"})
        # User-supplied values take precedence
        assert config["env"]["NODE_ENV"] == "test"
        assert config["env"]["EXTRA"] == "yes"

    def test_env_empty_user_env(self):
        config = self._make_config(env=None)
        assert config["env"] == {"NODE_ENV": "production"}

    def test_working_dir_is_clone_path(self):
        config = self._make_config(clone_path=Path("/tmp/my-clone"))
        assert config["working_dir"] == "/tmp/my-clone"
        assert config["install_path"] == "/tmp/my-clone"

    def test_source_is_github(self):
        config = self._make_config()
        assert config["source"] == "github"

    def test_github_provenance_fields(self):
        config = self._make_config(repo_path="owner/repo", branch="develop", server_name="fs")
        assert config["github_repo"] == "owner/repo"
        assert config["github_branch"] == "develop"
        assert config["github_server_name"] == "fs"

    def test_restart_policy_and_max_restarts(self):
        config = self._make_config(restart_policy="on-failure", max_restarts=5)
        assert config["restart_policy"] == "on-failure"
        assert config["max_restarts"] == 5

    def test_enabled_flag(self):
        config = self._make_config(enabled=False)
        assert config["enabled"] is False

    def test_created_by(self):
        config = self._make_config(created_by="alice")
        assert config["created_by"] == "alice"

    def test_description_fallback_when_absent(self):
        config = self._make_config()
        assert "owner/repo" in config["description"]

    def test_description_from_server_config(self):
        config = self._make_config(
            server_config={
                "command": "npx",
                "args": [],
                "description": "My custom description",
            }
        )
        assert config["description"] == "My custom description"

    def test_name_fallback_to_server_name(self):
        config = self._make_config(
            server_config={"command": "npx", "args": []}
        )
        assert config["name"] == "filesystem"

    def test_created_at_is_datetime(self):
        config = self._make_config()
        assert isinstance(config["created_at"], datetime)


# ==================== validate_command_allowlist Tests ====================

class TestValidateCommandAllowlist:
    @pytest.mark.parametrize("cmd", ["npx", "node", "python", "python3", "uvx", "docker", "deno", "bun"])
    def test_allowed_commands_pass(self, cmd):
        valid, err = validate_command_allowlist(cmd)
        assert valid is True
        assert err is None

    @pytest.mark.parametrize("cmd", ["rm", "bash", "sh", "curl", "wget", "cat", "chmod"])
    def test_dangerous_commands_blocked(self, cmd):
        valid, err = validate_command_allowlist(cmd)
        assert valid is False
        assert cmd in err

    def test_empty_string_blocked(self):
        valid, err = validate_command_allowlist("")
        assert valid is False

    def test_env_var_extends_allowlist(self, monkeypatch):
        monkeypatch.setenv("FMCP_ALLOWED_COMMANDS", "mycommand,othercommand")
        valid, err = validate_command_allowlist("mycommand")
        assert valid is True
        assert err is None

    def test_env_var_does_not_remove_defaults(self, monkeypatch):
        monkeypatch.setenv("FMCP_ALLOWED_COMMANDS", "mycommand")
        valid, _ = validate_command_allowlist("npx")
        assert valid is True


# ==================== clone_or_update_repo Tests ====================

class TestCloneOrUpdateRepo:
    def test_fresh_clone_calls_clone_github_repo(self, tmp_path):
        with patch("fluidmcp.cli.services.github_utils.clone_github_repo") as mock_clone:
            mock_clone.return_value = tmp_path / "owner" / "repo" / "main"
            result = clone_or_update_repo("owner/repo", "token123", "main", install_dir=tmp_path)
            mock_clone.assert_called_once()

    def test_existing_clone_calls_git_pull(self, tmp_path):
        # Create a non-empty destination directory to simulate an existing clone
        dest = tmp_path / "owner" / "repo" / "main"
        dest.mkdir(parents=True)
        (dest / "README.md").write_text("hello")

        with patch("fluidmcp.cli.services.github_utils.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = clone_or_update_repo("owner/repo", "token123", "main", install_dir=tmp_path)

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "git" in call_args
        assert "pull" in call_args
        assert result == dest

    def test_existing_clone_continues_on_pull_failure(self, tmp_path):
        import subprocess as sp
        dest = tmp_path / "owner" / "repo" / "main"
        dest.mkdir(parents=True)
        (dest / "README.md").write_text("hello")

        with patch("fluidmcp.cli.services.github_utils.subprocess.run") as mock_run:
            mock_run.side_effect = sp.CalledProcessError(1, "git pull")
            result = clone_or_update_repo("owner/repo", "token123", "main", install_dir=tmp_path)

        # Should not raise, should return the existing path
        assert result == dest

    def test_existing_clone_continues_on_pull_timeout(self, tmp_path):
        import subprocess as sp
        dest = tmp_path / "owner" / "repo" / "main"
        dest.mkdir(parents=True)
        (dest / "README.md").write_text("hello")

        with patch("fluidmcp.cli.services.github_utils.subprocess.run") as mock_run:
            mock_run.side_effect = sp.TimeoutExpired("git pull", 30)
            result = clone_or_update_repo("owner/repo", "token123", "main", install_dir=tmp_path)

        assert result == dest


# ==================== GitHubService.build_server_configs Tests ====================

SINGLE_SERVER_METADATA = {
    "mcpServers": {
        "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem"],
            "env": {},
        }
    }
}

MULTI_SERVER_METADATA = {
    "mcpServers": {
        "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem"],
        },
        "memory": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-memory"],
        },
    }
}

DANGEROUS_COMMAND_METADATA = {
    "mcpServers": {
        "evil": {
            "command": "rm",
            "args": ["-rf", "/"],
        }
    }
}


class TestGitHubServiceBuildServerConfigs:
    def _run(self, metadata, base_id="my-server", server_name=None, tmp_path=None, extra_env=None):
        if tmp_path is None:
            tmp_path = Path("/tmp/test-clone")

        metadata_path = MagicMock()
        metadata_path.__str__ = lambda self: str(tmp_path / "metadata.json")

        with patch("fluidmcp.cli.services.github_utils.clone_or_update_repo", return_value=tmp_path), \
             patch("fluidmcp.cli.services.github_utils.extract_or_create_metadata", return_value=tmp_path / "metadata.json"), \
             patch("builtins.open", mock_open(read_data=json.dumps(metadata))):
            configs, path = GitHubService.build_server_configs(
                repo_path="owner/repo",
                token="ghp_token",
                base_server_id=base_id,
                server_name=server_name,
                env=extra_env,
            )
        return configs, path

    def test_single_server_returns_one_config(self):
        configs, _ = self._run(SINGLE_SERVER_METADATA)
        assert len(configs) == 1

    def test_single_server_id_matches_base_id(self):
        configs, _ = self._run(SINGLE_SERVER_METADATA, base_id="fs-server")
        assert configs[0]["id"] == "fs-server"

    def test_multi_server_returns_two_configs(self):
        configs, _ = self._run(MULTI_SERVER_METADATA)
        assert len(configs) == 2

    def test_multi_server_ids_include_slug(self):
        configs, _ = self._run(MULTI_SERVER_METADATA, base_id="tools")
        ids = {c["id"] for c in configs}
        assert "tools-filesystem" in ids
        assert "tools-memory" in ids

    def test_server_name_filter_selects_one(self):
        configs, _ = self._run(MULTI_SERVER_METADATA, base_id="tools", server_name="memory")
        assert len(configs) == 1
        # Single-server path: id == base_id
        assert configs[0]["id"] == "tools"

    def test_unknown_server_name_raises_value_error(self):
        with pytest.raises(ValueError, match="not found"):
            self._run(MULTI_SERVER_METADATA, server_name="nonexistent")

    def test_dangerous_command_raises_value_error(self):
        with pytest.raises(ValueError, match="not in the allowed list"):
            self._run(DANGEROUS_COMMAND_METADATA)

    def test_extra_env_merged_into_config(self):
        configs, _ = self._run(SINGLE_SERVER_METADATA, extra_env={"MY_KEY": "my_value"})
        assert configs[0]["env"]["MY_KEY"] == "my_value"

    def test_source_is_github(self):
        configs, _ = self._run(SINGLE_SERVER_METADATA)
        assert configs[0]["source"] == "github"

    def test_flat_format_command_at_top_level(self):
        configs, _ = self._run(SINGLE_SERVER_METADATA)
        assert configs[0]["command"] == "npx"
        assert "mcp_config" not in configs[0]

    def test_clone_path_returned(self, tmp_path):
        _, path = self._run(SINGLE_SERVER_METADATA, tmp_path=tmp_path)
        assert path == tmp_path
