"""Unit tests for run_servers.py"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from fluidai_mcp.services.config_resolver import ServerConfig
from fluidai_mcp.services.run_servers import (
    run_servers,
    _install_packages_from_config,
    _update_env_from_common_env,
    _start_server,
)


class TestRunServers:
    """Tests for run_servers function"""

    def test_sets_secure_mode_env_vars(self):
        config = ServerConfig(servers={})

        with patch.dict(os.environ, {}, clear=False):
            with patch('fluidai_mcp.services.run_servers.uvicorn'):
                run_servers(config, secure_mode=True, token="test-token")

            assert os.environ.get("FMCP_BEARER_TOKEN") == "test-token"
            assert os.environ.get("FMCP_SECURE_MODE") == "true"

    def test_calls_install_when_needed(self):
        config = ServerConfig(servers={}, needs_install=True)

        with patch('fluidai_mcp.services.run_servers._install_packages_from_config') as mock_install:
            with patch('fluidai_mcp.services.run_servers.uvicorn'):
                run_servers(config)

            mock_install.assert_called_once_with(config)

    def test_skips_install_when_not_needed(self):
        config = ServerConfig(servers={}, needs_install=False)

        with patch('fluidai_mcp.services.run_servers._install_packages_from_config') as mock_install:
            with patch('fluidai_mcp.services.run_servers.uvicorn'):
                run_servers(config)

            mock_install.assert_not_called()

    def test_launches_servers_and_adds_routers(self, tmp_path):
        # Setup mock package
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "metadata.json").write_text(json.dumps({
            "mcpServers": {"test": {"command": "echo", "args": ["test"]}}
        }))

        config = ServerConfig(
            servers={"test-server": {"install_path": str(pkg_dir)}}
        )

        mock_router = Mock()
        with patch('fluidai_mcp.services.run_servers.launch_mcp_using_fastapi_proxy') as mock_launch:
            mock_launch.return_value = ("test-pkg", mock_router)
            with patch('fluidai_mcp.services.run_servers.uvicorn'):
                with patch('fluidai_mcp.services.run_servers.FastAPI') as mock_fastapi:
                    mock_app = Mock()
                    mock_fastapi.return_value = mock_app
                    run_servers(config)

                    mock_launch.assert_called_once()
                    mock_app.include_router.assert_called_once()

    def test_skips_server_without_install_path(self):
        config = ServerConfig(
            servers={"test-server": {"command": "echo"}}  # No install_path
        )

        with patch('fluidai_mcp.services.run_servers.launch_mcp_using_fastapi_proxy') as mock_launch:
            with patch('fluidai_mcp.services.run_servers.uvicorn'):
                run_servers(config)

            mock_launch.assert_not_called()

    def test_skips_server_with_nonexistent_path(self, tmp_path):
        config = ServerConfig(
            servers={"test-server": {"install_path": "/nonexistent/path"}}
        )

        with patch('fluidai_mcp.services.run_servers.launch_mcp_using_fastapi_proxy') as mock_launch:
            with patch('fluidai_mcp.services.run_servers.uvicorn'):
                run_servers(config)

            mock_launch.assert_not_called()


class TestInstallPackagesFromConfig:
    """Tests for _install_packages_from_config"""

    def test_installs_packages_with_fmcp_package(self, tmp_path):
        config = ServerConfig(
            servers={
                "test": {
                    "fmcp_package": "Author/Pkg@1.0.0",
                    "install_path": str(tmp_path)
                }
            },
            metadata_path=tmp_path / "config.json"
        )

        with patch('fluidai_mcp.services.run_servers.install_package') as mock_install:
            with patch('fluidai_mcp.services.run_servers.parse_package_string') as mock_parse:
                mock_parse.return_value = {"author": "Author", "package_name": "Pkg", "version": "1.0.0"}
                with patch('fluidai_mcp.services.run_servers.INSTALLATION_DIR', tmp_path):
                    # Create expected directory
                    pkg_dir = tmp_path / "Author" / "Pkg" / "1.0.0"
                    pkg_dir.mkdir(parents=True)
                    (pkg_dir / "metadata.json").write_text("{}")

                    _install_packages_from_config(config)

                    mock_install.assert_called_once_with("Author/Pkg@1.0.0", skip_env=True)

    def test_skips_servers_without_fmcp_package(self):
        config = ServerConfig(
            servers={"test": {"command": "echo"}}  # No fmcp_package
        )

        with patch('fluidai_mcp.services.run_servers.install_package') as mock_install:
            _install_packages_from_config(config)
            mock_install.assert_not_called()


class TestUpdateEnvFromCommonEnv:
    """Tests for _update_env_from_common_env"""

    def test_reads_env_file_and_updates_metadata(self, tmp_path):
        # Create .env file
        env_file = tmp_path / ".env"
        env_file.write_text("API_KEY=secret123\nOTHER=value")

        # Create metadata.json
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        metadata = {
            "mcpServers": {
                "test-pkg": {
                    "env": {
                        "API_KEY": "placeholder"
                    }
                }
            }
        }
        metadata_file = pkg_dir / "metadata.json"
        metadata_file.write_text(json.dumps(metadata))

        pkg = {"package_name": "test-pkg"}

        with patch('fluidai_mcp.services.run_servers.INSTALLATION_DIR', tmp_path):
            _update_env_from_common_env(pkg_dir, pkg)

        # Verify metadata was updated
        updated = json.loads(metadata_file.read_text())
        assert updated["mcpServers"]["test-pkg"]["env"]["API_KEY"] == "secret123"

    def test_creates_env_file_if_missing(self, tmp_path):
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        metadata = {
            "mcpServers": {
                "test-pkg": {
                    "env": {"NEW_KEY": ""}
                }
            }
        }
        (pkg_dir / "metadata.json").write_text(json.dumps(metadata))

        pkg = {"package_name": "test-pkg"}

        with patch('fluidai_mcp.services.run_servers.INSTALLATION_DIR', tmp_path):
            _update_env_from_common_env(pkg_dir, pkg)

        env_file = tmp_path / ".env"
        assert env_file.exists()


class TestStartServer:
    """Tests for _start_server"""

    def test_starts_uvicorn_on_free_port(self):
        mock_app = Mock()

        with patch('fluidai_mcp.services.run_servers.is_port_in_use', return_value=False):
            with patch('fluidai_mcp.services.run_servers.uvicorn') as mock_uvicorn:
                _start_server(mock_app, 8099, force_reload=False)

                mock_uvicorn.run.assert_called_once_with(
                    mock_app, host="0.0.0.0", port=8099
                )

    def test_kills_process_when_force_reload(self):
        mock_app = Mock()

        with patch('fluidai_mcp.services.run_servers.is_port_in_use', return_value=True):
            with patch('fluidai_mcp.services.run_servers.kill_process_on_port') as mock_kill:
                with patch('fluidai_mcp.services.run_servers.uvicorn'):
                    _start_server(mock_app, 8099, force_reload=True)

                    mock_kill.assert_called_once_with(8099)

    def test_prompts_user_when_port_busy(self):
        mock_app = Mock()

        with patch('fluidai_mcp.services.run_servers.is_port_in_use', return_value=True):
            with patch('builtins.input', return_value='n'):
                with patch('fluidai_mcp.services.run_servers.uvicorn') as mock_uvicorn:
                    _start_server(mock_app, 8099, force_reload=False)

                    # Should not start server when user says 'n'
                    mock_uvicorn.run.assert_not_called()
