"""Integration tests for FluidMCP CLI"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from argparse import Namespace

from fluidmcp.services.config_resolver import ServerConfig, resolve_config
from fluidmcp.services.run_servers import run_servers
from fluidmcp.cli import run_command, main


class TestRunCommandIntegration:
    """Integration tests for the run command flow"""

    def test_single_package_flow(self, tmp_path):
        """Test complete flow: resolve_config -> run_servers for single package"""
        # Setup mock package
        pkg_dir = tmp_path / "Author" / "TestPkg" / "1.0.0"
        pkg_dir.mkdir(parents=True)
        metadata = {
            "mcpServers": {
                "test-server": {
                    "command": "echo",
                    "args": ["hello"],
                    "env": {}
                }
            }
        }
        (pkg_dir / "metadata.json").write_text(json.dumps(metadata))

        args = Namespace(
            s3=False,
            file=False,
            master=False,
            package="Author/TestPkg@1.0.0",
            start_server=False,
            force_reload=False
        )

        with patch('fluidmcp.services.config_resolver.INSTALLATION_DIR', tmp_path):
            config = resolve_config(args)

        assert config.source_type == "package"
        assert "test-server" in config.servers
        assert config.needs_install is False

    def test_file_config_flow(self, tmp_path):
        """Test complete flow for --file mode"""
        # Create config file
        config_file = tmp_path / "config.json"
        config_data = {
            "mcpServers": {
                "maps": {
                    "command": "npx",
                    "args": ["-y", "@google-maps/mcp-server"],
                    "env": {"API_KEY": "test"},
                    "fmcp_package": "Google/maps@1.0.0"
                }
            }
        }
        config_file.write_text(json.dumps(config_data))

        args = Namespace(
            s3=False,
            file=True,
            master=False,
            package=str(config_file),
            start_server=False,
            force_reload=False
        )

        with patch('fluidmcp.services.config_resolver.validate_metadata_config', return_value=True):
            config = resolve_config(args)

        assert config.source_type == "file"
        assert config.needs_install is True
        assert "maps" in config.servers

    def test_run_all_flow(self, tmp_path):
        """Test complete flow for 'run all' mode"""
        # Setup multiple packages
        pkg1 = tmp_path / "Author1" / "Pkg1" / "1.0.0"
        pkg1.mkdir(parents=True)
        (pkg1 / "metadata.json").write_text(json.dumps({
            "mcpServers": {"server1": {"command": "echo", "args": ["1"]}}
        }))

        pkg2 = tmp_path / "Author2" / "Pkg2" / "1.0.0"
        pkg2.mkdir(parents=True)
        (pkg2 / "metadata.json").write_text(json.dumps({
            "mcpServers": {"server2": {"command": "echo", "args": ["2"]}}
        }))

        args = Namespace(
            s3=False,
            file=False,
            master=False,
            package="all",
            start_server=False,
            force_reload=False
        )

        with patch('fluidmcp.services.config_resolver.INSTALLATION_DIR', tmp_path):
            with patch('fluidmcp.services.config_resolver.find_free_port', side_effect=[8001, 8002]):
                config = resolve_config(args)

        assert config.source_type == "installed"
        assert "server1" in config.servers
        assert "server2" in config.servers

    def test_run_command_handles_errors_gracefully(self):
        """Test that run_command catches and reports errors"""
        args = Namespace(
            s3=False,
            file=False,
            master=False,
            package="nonexistent/package@1.0.0",
            start_server=False,
            force_reload=False
        )

        with patch('fluidmcp.services.config_resolver.INSTALLATION_DIR', Path("/nonexistent")):
            with pytest.raises(SystemExit) as exc_info:
                run_command(args)
            assert exc_info.value.code == 1


class TestEndToEndServerLaunch:
    """End-to-end tests for server launching"""

    def test_servers_launch_with_correct_config(self, tmp_path):
        """Test that servers are launched with correct configuration"""
        # Setup package
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "metadata.json").write_text(json.dumps({
            "mcpServers": {"test": {"command": "echo", "args": ["test"]}}
        }))

        config = ServerConfig(
            servers={
                "test-server": {
                    "install_path": str(pkg_dir),
                    "command": "echo",
                    "args": ["test"]
                }
            }
        )

        mock_router = Mock()
        launched_packages = []

        def capture_launch(dest_dir):
            launched_packages.append(str(dest_dir))
            return ("test-pkg", mock_router)

        with patch('fluidmcp.services.run_servers.launch_mcp_using_fastapi_proxy', side_effect=capture_launch):
            with patch('fluidmcp.services.run_servers.uvicorn'):
                run_servers(config, start_server=False)

        assert str(pkg_dir) in launched_packages

    def test_secure_mode_propagates_through_flow(self, tmp_path):
        """Test that secure mode settings propagate correctly"""
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "metadata.json").write_text(json.dumps({
            "mcpServers": {"test": {"command": "echo", "args": []}}
        }))

        config = ServerConfig(
            servers={"test": {"install_path": str(pkg_dir)}}
        )

        with patch.dict(os.environ, {}, clear=False):
            with patch('fluidmcp.services.run_servers.launch_mcp_using_fastapi_proxy', return_value=("pkg", Mock())):
                with patch('fluidmcp.services.run_servers.uvicorn'):
                    run_servers(config, secure_mode=True, token="secret123", start_server=False)

            assert os.environ.get("FMCP_BEARER_TOKEN") == "secret123"
            assert os.environ.get("FMCP_SECURE_MODE") == "true"


class TestConfigResolverChain:
    """Test the resolver chain works correctly"""

    def test_resolver_chain_for_all_sources(self, tmp_path):
        """Verify each source type produces correct ServerConfig"""
        test_cases = [
            # (args, expected_source_type, expected_needs_install)
            (Namespace(s3=False, file=False, master=False, package="all"), "installed", False),
            (Namespace(s3=False, file=True, master=False, package="config.json"), "file", True),
        ]

        # Setup for "all" test case
        pkg = tmp_path / "Author" / "Pkg" / "1.0.0"
        pkg.mkdir(parents=True)
        (pkg / "metadata.json").write_text(json.dumps({
            "mcpServers": {"s": {"command": "e", "args": []}}
        }))

        # Setup for "file" test case
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "mcpServers": {"s": {"command": "e", "args": [], "fmcp_package": "A/B@1"}}
        }))

        for args, expected_source, expected_install in test_cases:
            if args.file:
                args.package = str(config_file)

            with patch('fluidmcp.services.config_resolver.INSTALLATION_DIR', tmp_path):
                with patch('fluidmcp.services.config_resolver.find_free_port', return_value=8000):
                    with patch('fluidmcp.services.config_resolver.validate_metadata_config', return_value=True):
                        config = resolve_config(args)

            assert config.source_type == expected_source, f"Failed for {args}"
            assert config.needs_install == expected_install, f"Failed for {args}"


class TestGitHubIntegration:
    """Integration tests for GitHub MCP server cloning and configuration"""

    def test_github_server_with_explicit_command(self, tmp_path):
        """Test complete flow: GitHub repo with explicit command -> config resolution"""
        # Create config file with GitHub server using explicit command
        config_file = tmp_path / "github_config.json"
        config_data = {
            "github_token": "fake_token_for_testing",
            "mcpServers": {
                "python-server": {
                    "github_repo": "modelcontextprotocol/python-sdk",
                    "branch": "main",
                    "command": "uv",
                    "args": ["run", "examples/snippets/servers/fastmcp_quickstart.py"],
                    "env": {}
                }
            }
        }
        config_file.write_text(json.dumps(config_data))

        # Mock the GitHub cloning to avoid actual network calls
        mock_repo_dir = tmp_path / ".fmcp-packages" / "modelcontextprotocol" / "python-sdk" / "main"
        mock_repo_dir.mkdir(parents=True)

        # Create a fake .git directory to simulate cloned repo
        (mock_repo_dir / ".git").mkdir()

        # Create metadata.json that should be generated by _handle_github_server
        metadata = {
            "mcpServers": {
                "python-server": {
                    "command": "uv",
                    "args": ["run", "examples/snippets/servers/fastmcp_quickstart.py"],
                    "env": {}
                }
            }
        }
        (mock_repo_dir / "metadata.json").write_text(json.dumps(metadata))

        args = Namespace(
            s3=False,
            file=True,
            master=False,
            package=str(config_file),
            start_server=False,
            force_reload=False
        )

        # Mock GitHub operations
        with patch('fluidmcp.services.config_resolver.validate_metadata_config', return_value=True):
            with patch('fluidmcp.services.github_utils.clone_github_repo', return_value=mock_repo_dir):
                with patch('fluidmcp.services.config_resolver.INSTALLATION_DIR', tmp_path / ".fmcp-packages"):
                    config = resolve_config(args)

        # Verify the config was resolved correctly
        assert config.source_type == "file"
        assert "python-server" in config.servers

        server_cfg = config.servers["python-server"]
        assert server_cfg["command"] == "uv"
        assert server_cfg["args"] == ["run", "examples/snippets/servers/fastmcp_quickstart.py"]
        assert "install_path" in server_cfg
        assert server_cfg["install_path"] == str(mock_repo_dir)
