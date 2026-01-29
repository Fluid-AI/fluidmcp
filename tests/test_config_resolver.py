"""Unit tests for config_resolver.py"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from argparse import Namespace

from fluidmcp.cli.services.config_resolver import (
    ServerConfig,
    resolve_config,
    resolve_from_package,
    resolve_from_installed,
    resolve_from_file,
    _resolve_package_dest_dir,
    _collect_installed_servers,
)


class TestServerConfig:
    """Tests for ServerConfig dataclass"""

    def test_default_values(self):
        config = ServerConfig()
        assert config.servers == {}
        assert config.needs_install is False
        assert config.sync_to_s3 is False
        assert config.source_type == "package"
        assert config.metadata_path is None

    def test_custom_values(self):
        servers = {"test": {"command": "npx", "args": ["-y", "test"]}}
        config = ServerConfig(
            servers=servers,
            needs_install=True,
            sync_to_s3=True,
            source_type="file",
            metadata_path=Path("/tmp/test.json")
        )
        assert config.servers == servers
        assert config.needs_install is True
        assert config.sync_to_s3 is True
        assert config.source_type == "file"
        assert config.metadata_path == Path("/tmp/test.json")


class TestResolveConfig:
    """Tests for resolve_config dispatcher"""

    def test_routes_to_s3_url_when_s3_flag(self):
        args = Namespace(s3=True, file=False, master=False, package="https://example.com/config.json")
        with patch('fluidmcp.cli.services.config_resolver.resolve_from_s3_url') as mock:
            mock.return_value = ServerConfig(source_type="s3_url")
            result = resolve_config(args)
            mock.assert_called_once_with("https://example.com/config.json")
            assert result.source_type == "s3_url"

    def test_routes_to_file_when_file_flag(self):
        args = Namespace(s3=False, file=True, master=False, package="config.json")
        with patch('fluidmcp.cli.services.config_resolver.resolve_from_file') as mock:
            mock.return_value = ServerConfig(source_type="file")
            result = resolve_config(args)
            mock.assert_called_once_with("config.json")
            assert result.source_type == "file"

    def test_routes_to_installed_when_all(self):
        args = Namespace(s3=False, file=False, master=False, package="all")
        with patch('fluidmcp.cli.services.config_resolver.resolve_from_installed') as mock:
            mock.return_value = ServerConfig(source_type="installed")
            result = resolve_config(args)
            mock.assert_called_once()
            assert result.source_type == "installed"

    def test_routes_to_s3_master_when_all_with_master(self):
        args = Namespace(s3=False, file=False, master=True, package="all")
        with patch('fluidmcp.cli.services.config_resolver.resolve_from_s3_master') as mock:
            mock.return_value = ServerConfig(source_type="s3_master")
            result = resolve_config(args)
            mock.assert_called_once()
            assert result.source_type == "s3_master"

    def test_routes_to_package_for_single_package(self):
        args = Namespace(s3=False, file=False, master=False, package="author/pkg@1.0.0")
        with patch('fluidmcp.cli.services.config_resolver.resolve_from_package') as mock:
            mock.return_value = ServerConfig(source_type="package")
            result = resolve_config(args)
            mock.assert_called_once_with("author/pkg@1.0.0")
            assert result.source_type == "package"


class TestResolveFromPackage:
    """Tests for resolve_from_package"""

    def test_returns_config_with_servers(self, tmp_path):
        # Setup mock package directory
        pkg_dir = tmp_path / "Author" / "TestPkg" / "1.0.0"
        pkg_dir.mkdir(parents=True)
        metadata = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["-y", "@test/server"]
                }
            }
        }
        (pkg_dir / "metadata.json").write_text(json.dumps(metadata))

        with patch('fluidmcp.cli.services.config_resolver.INSTALLATION_DIR', tmp_path):
            config = resolve_from_package("Author/TestPkg@1.0.0")

        assert "test-server" in config.servers
        assert config.servers["test-server"]["install_path"] == str(pkg_dir)
        assert config.needs_install is False
        assert config.source_type == "package"

    def test_raises_error_for_missing_package(self, tmp_path):
        with patch('fluidmcp.cli.services.config_resolver.INSTALLATION_DIR', tmp_path):
            with pytest.raises(FileNotFoundError):
                resolve_from_package("NonExistent/Pkg@1.0.0")


class TestResolveFromFile:
    """Tests for resolve_from_file"""

    def test_loads_config_from_file(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_data = {
            "mcpServers": {
                "maps": {
                    "command": "npx",
                    "args": ["-y", "@google-maps/mcp-server"],
                    "fmcp_package": "Google/maps@1.0.0"
                }
            }
        }
        config_file.write_text(json.dumps(config_data))

        with patch('fluidmcp.cli.services.config_resolver.validate_metadata_config', return_value=True):
            config = resolve_from_file(str(config_file))

        assert "maps" in config.servers
        # Direct configs with "command" don't need installation
        assert config.needs_install is False
        assert config.source_type == "file"

    def test_raises_error_for_missing_file(self):
        with pytest.raises(FileNotFoundError):
            resolve_from_file("/nonexistent/config.json")


class TestCollectInstalledServers:
    """Tests for _collect_installed_servers helper"""

    def test_collects_servers_from_multiple_packages(self, tmp_path):
        # Create two mock packages
        pkg1 = tmp_path / "Author1" / "Pkg1" / "1.0.0"
        pkg1.mkdir(parents=True)
        (pkg1 / "metadata.json").write_text(json.dumps({
            "mcpServers": {"server1": {"command": "cmd1", "args": []}}
        }))

        pkg2 = tmp_path / "Author2" / "Pkg2" / "2.0.0"
        pkg2.mkdir(parents=True)
        (pkg2 / "metadata.json").write_text(json.dumps({
            "mcpServers": {"server2": {"command": "cmd2", "args": []}}
        }))

        taken_ports = set()
        with patch('fluidmcp.cli.services.config_resolver.find_free_port', side_effect=[8001, 8002]):
            servers = _collect_installed_servers(tmp_path, taken_ports)

        assert "server1" in servers
        assert "server2" in servers
        # Verify both servers have ports assigned (order may vary based on directory iteration)
        assert servers["server1"]["port"] in ["8001", "8002"]
        assert servers["server2"]["port"] in ["8001", "8002"]
        # Verify they have different ports
        assert servers["server1"]["port"] != servers["server2"]["port"]

    def test_skips_invalid_json(self, tmp_path):
        pkg = tmp_path / "Author" / "Pkg" / "1.0.0"
        pkg.mkdir(parents=True)
        (pkg / "metadata.json").write_text("invalid json{")

        servers = _collect_installed_servers(tmp_path, set())
        assert servers == {}


class TestResolvePackageDestDir:
    """Tests for _resolve_package_dest_dir helper"""

    def test_resolves_full_path(self, tmp_path):
        pkg_dir = tmp_path / "Author" / "Package" / "1.0.0"
        pkg_dir.mkdir(parents=True)

        result = _resolve_package_dest_dir("Author/Package@1.0.0", tmp_path)
        assert result == pkg_dir

    def test_resolves_without_version(self, tmp_path):
        pkg_dir = tmp_path / "Author" / "Package" / "2.0.0"
        pkg_dir.mkdir(parents=True)

        with patch('fluidmcp.cli.services.config_resolver.get_latest_version_dir', return_value=pkg_dir):
            result = _resolve_package_dest_dir("Author/Package", tmp_path)
        assert result == pkg_dir

    def test_raises_for_nonexistent_package(self, tmp_path):
        # Create the install_dir but not the package
        tmp_path.mkdir(exist_ok=True)
        with pytest.raises(FileNotFoundError):
            _resolve_package_dest_dir("Missing@1.0.0", tmp_path)
