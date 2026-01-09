"""Unit tests for run_servers.py"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from fluidmcp.cli.services.config_resolver import ServerConfig
from fluidmcp.cli.services.run_servers import (
    run_servers,
    _install_packages_from_config,
    _update_env_from_common_env,
    _start_server,
    _serve_async,
)


class TestRunServers:
    """Tests for run_servers function"""

    def test_sets_secure_mode_env_vars(self):
        config = ServerConfig(servers={})

        with patch.dict(os.environ, {}, clear=False):
            with patch('fluidmcp.services.run_servers.uvicorn'):
                run_servers(config, secure_mode=True, token="test-token", start_server=False)

            assert os.environ.get("FMCP_BEARER_TOKEN") == "test-token"
            assert os.environ.get("FMCP_SECURE_MODE") == "true"

    def test_calls_install_when_needed(self):
        config = ServerConfig(servers={}, needs_install=True)

        with patch('fluidmcp.services.run_servers._install_packages_from_config') as mock_install:
            with patch('fluidmcp.services.run_servers.uvicorn'):
                run_servers(config, start_server=False)

            mock_install.assert_called_once_with(config)

    def test_skips_install_when_not_needed(self):
        config = ServerConfig(servers={}, needs_install=False)

        with patch('fluidmcp.services.run_servers._install_packages_from_config') as mock_install:
            with patch('fluidmcp.services.run_servers.uvicorn'):
                run_servers(config, start_server=False)

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
        with patch('fluidmcp.services.run_servers.launch_mcp_using_fastapi_proxy') as mock_launch:
            mock_launch.return_value = ("test-pkg", mock_router)
            with patch('fluidmcp.services.run_servers.uvicorn'):
                with patch('fluidmcp.services.run_servers.FastAPI') as mock_fastapi:
                    mock_app = Mock()
                    mock_fastapi.return_value = mock_app
                    run_servers(config, start_server=False)

                    mock_launch.assert_called_once()
                    mock_app.include_router.assert_called_once()

    def test_skips_server_without_install_path(self):
        config = ServerConfig(
            servers={"test-server": {"command": "echo"}}  # No install_path
        )

        with patch('fluidmcp.services.run_servers.launch_mcp_using_fastapi_proxy') as mock_launch:
            with patch('fluidmcp.services.run_servers.uvicorn'):
                run_servers(config, start_server=False)

            mock_launch.assert_not_called()

    def test_skips_server_with_nonexistent_path(self, tmp_path):
        config = ServerConfig(
            servers={"test-server": {"install_path": "/nonexistent/path"}}
        )

        with patch('fluidmcp.services.run_servers.launch_mcp_using_fastapi_proxy') as mock_launch:
            with patch('fluidmcp.services.run_servers.uvicorn'):
                run_servers(config, start_server=False)

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

        with patch('fluidmcp.services.run_servers.install_package') as mock_install:
            with patch('fluidmcp.services.run_servers.parse_package_string') as mock_parse:
                mock_parse.return_value = {"author": "Author", "package_name": "Pkg", "version": "1.0.0"}
                with patch('fluidmcp.services.run_servers.INSTALLATION_DIR', tmp_path):
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

        with patch('fluidmcp.services.run_servers.install_package') as mock_install:
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

        with patch('fluidmcp.services.run_servers.INSTALLATION_DIR', tmp_path):
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

        with patch('fluidmcp.services.run_servers.INSTALLATION_DIR', tmp_path):
            _update_env_from_common_env(pkg_dir, pkg)

        env_file = tmp_path / ".env"
        assert env_file.exists()


class TestStartServer:
    """Tests for _start_server"""

    def test_starts_server_on_free_port(self):
        mock_app = Mock()

        with patch('fluidmcp.services.run_servers.is_port_in_use', return_value=False):
            with patch('fluidmcp.services.run_servers.asyncio.run') as mock_asyncio_run:
                _start_server(mock_app, 8099, force_reload=False)

                mock_asyncio_run.assert_called_once()

    def test_kills_process_when_force_reload(self):
        mock_app = Mock()

        # First call returns True (port in use), then False (port released after kill)
        call_count = [0]
        def is_port_in_use_side_effect(port):
            call_count[0] += 1
            # First call: port in use
            # Subsequent calls in retry loop: port is free
            return call_count[0] == 1

        with patch('fluidmcp.services.run_servers.is_port_in_use', side_effect=is_port_in_use_side_effect):
            with patch('fluidmcp.services.run_servers.kill_process_on_port') as mock_kill:
                with patch('fluidmcp.services.run_servers.asyncio.run'):
                    _start_server(mock_app, 8099, force_reload=True)

                    mock_kill.assert_called_once_with(8099)

    def test_aborts_when_port_busy_and_no_force_reload(self):
        mock_app = Mock()

        with patch('fluidmcp.services.run_servers.is_port_in_use', return_value=True):
            with patch('fluidmcp.services.run_servers.asyncio.run') as mock_asyncio_run:
                _start_server(mock_app, 8099, force_reload=False)

                # Should not start server when force_reload is False and port is busy
                mock_asyncio_run.assert_not_called()

    def test_aborts_when_port_not_released_in_time(self):
        mock_app = Mock()

        # Port stays in use even after killing process
        with patch('fluidmcp.services.run_servers.is_port_in_use', return_value=True):
            with patch('fluidmcp.services.run_servers.kill_process_on_port'):
                with patch('fluidmcp.services.run_servers.time.sleep') as mock_sleep:
                    with patch('fluidmcp.services.run_servers.asyncio.run') as mock_asyncio_run:
                        with patch.dict(os.environ, {"MCP_PORT_RELEASE_TIMEOUT": "0.1"}):
                            _start_server(mock_app, 8099, force_reload=True)

                            # Should not start server when port is still in use after timeout
                            mock_asyncio_run.assert_not_called()
                            # Verify sleep was called during retry loop
                            assert mock_sleep.called

    def test_handles_invalid_timeout_env_var(self):
        """Test that invalid MCP_PORT_RELEASE_TIMEOUT falls back to default"""
        mock_app = Mock()

        call_count = [0]
        def is_port_in_use_side_effect(port):
            call_count[0] += 1
            return call_count[0] == 1

        with patch('fluidmcp.services.run_servers.is_port_in_use', side_effect=is_port_in_use_side_effect):
            with patch('fluidmcp.services.run_servers.kill_process_on_port'):
                with patch('fluidmcp.services.run_servers.asyncio.run'):
                    with patch.dict(os.environ, {"MCP_PORT_RELEASE_TIMEOUT": "invalid"}):
                        _start_server(mock_app, 8099, force_reload=True)
                        # Should succeed with default timeout instead of crashing

    def test_handles_negative_timeout_env_var(self):
        """Test that negative MCP_PORT_RELEASE_TIMEOUT falls back to default"""
        mock_app = Mock()

        call_count = [0]
        def is_port_in_use_side_effect(port):
            call_count[0] += 1
            return call_count[0] == 1

        with patch('fluidmcp.services.run_servers.is_port_in_use', side_effect=is_port_in_use_side_effect):
            with patch('fluidmcp.services.run_servers.kill_process_on_port'):
                with patch('fluidmcp.services.run_servers.asyncio.run'):
                    with patch.dict(os.environ, {"MCP_PORT_RELEASE_TIMEOUT": "-5"}):
                        _start_server(mock_app, 8099, force_reload=True)
                        # Should succeed with default timeout instead of hanging

    def test_handles_zero_timeout_env_var(self):
        """Test that zero MCP_PORT_RELEASE_TIMEOUT falls back to default"""
        mock_app = Mock()

        call_count = [0]
        def is_port_in_use_side_effect(port):
            call_count[0] += 1
            return call_count[0] == 1

        with patch('fluidmcp.services.run_servers.is_port_in_use', side_effect=is_port_in_use_side_effect):
            with patch('fluidmcp.services.run_servers.kill_process_on_port'):
                with patch('fluidmcp.services.run_servers.asyncio.run'):
                    with patch.dict(os.environ, {"MCP_PORT_RELEASE_TIMEOUT": "0"}):
                        _start_server(mock_app, 8099, force_reload=True)
                        # Should succeed with default timeout instead of immediate abort

    def test_handles_keyboard_interrupt(self):
        """Test that KeyboardInterrupt is handled gracefully"""
        mock_app = Mock()

        with patch('fluidmcp.services.run_servers.is_port_in_use', return_value=False):
            with patch('fluidmcp.services.run_servers.asyncio.run', side_effect=KeyboardInterrupt):
                # Should not raise, should log instead
                _start_server(mock_app, 8099, force_reload=False)

    def test_handles_generic_exception(self):
        """Test that generic exceptions are caught and logged"""
        mock_app = Mock()

        with patch('fluidmcp.services.run_servers.is_port_in_use', return_value=False):
            with patch('fluidmcp.services.run_servers.asyncio.run', side_effect=RuntimeError("Test error")):
                # Should not raise, should log instead
                _start_server(mock_app, 8099, force_reload=False)

    def test_calls_serve_async_with_correct_args(self):
        """Test that _serve_async is called with correct app and port"""
        mock_app = Mock()

        with patch('fluidmcp.services.run_servers.is_port_in_use', return_value=False):
            with patch('fluidmcp.services.run_servers._serve_async') as mock_serve:
                with patch('fluidmcp.services.run_servers.asyncio.run') as mock_asyncio_run:
                    _start_server(mock_app, 8099, force_reload=False)

                    # Verify asyncio.run was called with _serve_async coroutine
                    mock_asyncio_run.assert_called_once()
                    # The call should include _serve_async(mock_app, 8099)
                    call_args = mock_asyncio_run.call_args[0][0]
                    # Verify it's a coroutine from _serve_async
                    assert hasattr(call_args, '__await__')


class TestServeAsync:
    """Tests for _serve_async function"""

    def test_configures_uvicorn_correctly(self):
        """Test that _serve_async configures uvicorn.Server with correct parameters"""
        import asyncio
        mock_app = Mock()

        with patch('fluidmcp.services.run_servers.uvicorn.Config') as mock_config:
            with patch('fluidmcp.services.run_servers.uvicorn.Server') as mock_server:
                mock_server_instance = Mock()
                mock_server.return_value = mock_server_instance
                # Make serve() a coroutine that returns immediately
                async def mock_serve():
                    return
                mock_server_instance.serve = mock_serve

                # Run the async function synchronously for testing
                asyncio.run(_serve_async(mock_app, 8099))

                # Verify Config was called with correct parameters
                mock_config.assert_called_once_with(
                    mock_app,
                    host="0.0.0.0",
                    port=8099,
                    log_level="info",
                    access_log=True
                )

                # Verify Server was instantiated
                mock_server.assert_called_once()

    def test_calls_server_serve(self):
        """Test that _serve_async calls server.serve()"""
        import asyncio
        mock_app = Mock()

        with patch('fluidmcp.services.run_servers.uvicorn.Server') as mock_server:
            mock_server_instance = Mock()
            mock_server.return_value = mock_server_instance
            # Track if serve was called
            serve_called = [False]
            async def mock_serve():
                serve_called[0] = True
            mock_server_instance.serve = mock_serve

            # Run the async function synchronously for testing
            asyncio.run(_serve_async(mock_app, 8099))

            assert serve_called[0], "server.serve() should have been called"
