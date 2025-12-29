"""
Config resolver module for FluidMCP CLI.

This module provides a unified way to resolve server configurations from different sources:
- Single installed package
- All installed packages
- Local JSON file
- S3 presigned URL
- S3 master mode (with sync)
"""

import os
import json
import requests
import boto3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError
from loguru import logger

from .network_utils import find_free_port
from .package_list import get_latest_version_dir
from .package_installer import parse_package_string, replace_package_metadata_from_package_name
from .s3_utils import s3_download_file, s3_upload_file, load_json_file, write_json_file, validate_metadata_config


# Environment variables
INSTALLATION_DIR = os.environ.get("MCP_INSTALLATION_DIR", Path.cwd() / ".fmcp-packages")

# S3 credentials
bucket_name = os.environ.get("S3_BUCKET_NAME")
access_key = os.environ.get("S3_ACCESS_KEY")
secret_key = os.environ.get("S3_SECRET_KEY")
region = os.environ.get("S3_REGION")


@dataclass
class ServerConfig:
    """Unified configuration for running MCP servers."""

    servers: Dict[str, dict] = field(default_factory=dict)  # mcpServers config
    needs_install: bool = False  # Whether to install packages first
    sync_to_s3: bool = False  # Whether to sync metadata to S3
    source_type: str = "package"  # For logging: package, installed, file, s3_url, s3_master
    metadata_path: Optional[Path] = None  # Path to save/load metadata


def resolve_config(args) -> ServerConfig:
    """
    Single entry point that resolves configuration based on CLI arguments.

    Args:
        args: Parsed argparse namespace with run command arguments

    Returns:
        ServerConfig with unified server configuration
    """
    logger.debug("Resolving configuration from CLI arguments")

    if getattr(args, 's3', False):
        logger.debug(f"Resolving from S3 URL: {args.package}")
        return resolve_from_s3_url(args.package)
    elif getattr(args, 'file', False):
        logger.debug(f"Resolving from file: {args.package}")
        return resolve_from_file(args.package)
    elif args.package.lower() == "all":
        if getattr(args, 'master', False):
            logger.debug("Resolving from S3 master mode")
            return resolve_from_s3_master()
        logger.debug("Resolving from all installed packages")
        return resolve_from_installed()
    else:
        logger.debug(f"Resolving from single package: {args.package}")
        return resolve_from_package(args.package)


def resolve_from_package(package_str: str) -> ServerConfig:
    """
    Resolve config from a single installed package.

    Args:
        package_str: Package identifier (author/package@version)

    Returns:
        ServerConfig for the single package
    """
    install_dir = Path(INSTALLATION_DIR)
    dest_dir = _resolve_package_dest_dir(package_str, install_dir)

    metadata_path = dest_dir / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"No metadata.json found at {metadata_path}")

    with open(metadata_path, "r") as f:
        metadata = json.load(f)

    # Add install_path to each server config
    servers = metadata.get("mcpServers", {})
    for key in servers:
        servers[key]["install_path"] = str(dest_dir)

    return ServerConfig(
        servers=servers,
        needs_install=False,
        sync_to_s3=False,
        source_type="package"
    )


def resolve_from_installed() -> ServerConfig:
    """
    Resolve config from all installed packages.

    Returns:
        ServerConfig with all installed packages merged
    """
    install_dir = Path(INSTALLATION_DIR)
    if not install_dir.exists():
        raise FileNotFoundError("No installations found.")

    meta_all_path = install_dir / "metadata_all.json"
    taken_ports = set()

    # Load existing metadata to preserve port assignments
    if meta_all_path.exists():
        try:
            existing = json.loads(meta_all_path.read_text())
            for server_cfg in existing.get("mcpServers", {}).values():
                taken_ports.add(int(server_cfg.get("port", -1)))
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    # Collect metadata from all installed packages
    servers = _collect_installed_servers(install_dir, taken_ports)

    # Save merged metadata
    merged = {"mcpServers": servers}
    meta_all_path.write_text(json.dumps(merged, indent=2))
    logger.info(f"Wrote merged metadata to {meta_all_path}")
    logger.debug(f"Merged {len(servers)} server(s)")

    return ServerConfig(
        servers=servers,
        needs_install=False,
        sync_to_s3=False,
        source_type="installed",
        metadata_path=meta_all_path
    )


def resolve_from_file(file_path: str) -> ServerConfig:
    """
    Resolve config from a local JSON configuration file.

    Supports three formats:
    1. Package strings: "author/package@version" (needs installation from registry)
    2. Direct configurations: {"command": "...", "args": [...], "env": {...}}
    3. GitHub repositories: {"github_repo": "owner/repo", "github_token": "...", ...}

    Args:
        file_path: Path to the JSON config file

    Returns:
        ServerConfig with servers from file
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {file_path}")

    with open(file_path, 'r') as f:
        config = json.load(f)

    if not validate_metadata_config(config, str(file_path)):
        raise ValueError(f"Invalid configuration in {file_path}")

    servers = config.get("mcpServers", {})
    needs_install = False

    # Get default GitHub token from config or environment
    default_github_token = (
        config.get("github_token")
        or os.environ.get("FMCP_GITHUB_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
    )

    # Check each server to determine type and prepare it
    logger.debug(f"Processing {len(servers)} server(s) from file configuration")

    for server_name, server_cfg in servers.items():
        logger.debug(f"Checking server type for '{server_name}'")

        if isinstance(server_cfg, str):
            # Package string - needs installation from registry
            logger.debug(f"'{server_name}' is a package string: {server_cfg}")
            needs_install = True

        elif isinstance(server_cfg, dict):
            if server_cfg.get("github_repo"):
                # GitHub repository - clone it
                logger.debug(f"'{server_name}' is a GitHub repo: {server_cfg.get('github_repo')}")
                _handle_github_server(server_name, server_cfg, default_github_token)

            elif server_cfg.get("command"):
                # Direct configuration - create temp directory with metadata.json
                logger.debug(f"'{server_name}' is a direct configuration with command: {server_cfg.get('command')}")
                temp_dir = _create_temp_server_dir(server_name, server_cfg)
                servers[server_name]["install_path"] = str(temp_dir)
                logger.debug(f"Created temp directory for '{server_name}': {temp_dir}")
            else:
                # Unknown format
                logger.warning(f"Unknown format for server '{server_name}'")
                logger.debug(f"Unknown format for '{server_name}': {server_cfg}")
        else:
            logger.warning(f"Invalid server configuration for '{server_name}'")
            logger.debug(f"Invalid configuration type for '{server_name}': {type(server_cfg)}")

    # Preprocess only if we have package strings
    if needs_install:
        _preprocess_metadata_file(file_path)
        # Re-read the preprocessed file
        with open(file_path, 'r') as f:
            config = json.load(f)
        servers = config.get("mcpServers", {})

    return ServerConfig(
        servers=servers,
        needs_install=needs_install,
        sync_to_s3=False,
        source_type="file",
        metadata_path=file_path
    )


def resolve_from_s3_url(presigned_url: str) -> ServerConfig:
    """
    Resolve config from an S3 presigned URL.

    Args:
        presigned_url: S3 presigned URL to the config JSON

    Returns:
        ServerConfig with servers from S3 (needs installation)
    """
    install_dir = Path(INSTALLATION_DIR)
    install_dir.mkdir(parents=True, exist_ok=True)
    temp_file_path = install_dir / "s3_metadata_all.json"

    # Download config from S3
    logger.info("Downloading configuration file from presigned URL")
    logger.debug(f"Presigned URL: {presigned_url[:100]}...")
    response = requests.get(presigned_url)
    response.raise_for_status()

    with open(temp_file_path, 'wb') as f:
        f.write(response.content)

    # Preprocess to expand package strings
    _preprocess_metadata_file(temp_file_path)

    with open(temp_file_path, 'r') as f:
        config = json.load(f)

    if not validate_metadata_config(config, str(temp_file_path)):
        raise ValueError("Invalid configuration from S3")

    servers = config.get("mcpServers", {})

    return ServerConfig(
        servers=servers,
        needs_install=True,
        sync_to_s3=False,
        source_type="s3_url",
        metadata_path=temp_file_path
    )


def resolve_from_s3_master() -> ServerConfig:
    """
    Resolve config from S3 master mode with bidirectional sync.

    Returns:
        ServerConfig with servers from S3 (needs installation, syncs back)
    """
    s3_client = boto3.client(
        's3',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region
    )

    install_dir = Path(INSTALLATION_DIR)
    if not install_dir.exists():
        raise FileNotFoundError("No installations found.")

    meta_all_path = install_dir / "s3_metadata_all.json"
    s3_file_key = "s3_metadata_all.json"
    taken_ports = set()

    # Check if file exists in S3
    try:
        logger.info(f"Checking if {s3_file_key} exists in S3 bucket {bucket_name}...")
        logger.debug(f"S3 bucket: {bucket_name}, Key: {s3_file_key}")
        s3_client.head_object(Bucket=bucket_name, Key=s3_file_key)
        file_exists = True
        logger.success(f"File {s3_file_key} found in S3 bucket")
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            file_exists = False
            logger.info(f"File {s3_file_key} not found in S3 bucket")
            logger.debug("Will create new metadata file")
        else:
            raise

    # Download or create metadata
    if file_exists:
        s3_download_file(s3_client, bucket_name, s3_file_key, meta_all_path)
    else:
        servers = _collect_installed_servers(install_dir, taken_ports)
        merged = {"mcpServers": servers}
        write_json_file(meta_all_path, merged)
        s3_upload_file(s3_client, meta_all_path, bucket_name, s3_file_key)

    # Load metadata
    s3_metadata = load_json_file(meta_all_path)
    if s3_metadata is None:
        raise ValueError("Failed to load s3_metadata_all.json")

    servers = s3_metadata.get("mcpServers", {})

    return ServerConfig(
        servers=servers,
        needs_install=True,
        sync_to_s3=True,
        source_type="s3_master",
        metadata_path=meta_all_path
    )


# ============================================================================
# Helper functions
# ============================================================================

def _resolve_package_dest_dir(package_str: str, install_dir: Path) -> Path:
    """
    Resolve the destination directory for a package string.
    Handles formats: author/package@version, author/package, package@version, package
    """
    if '/' in package_str:
        author, package_with_version = package_str.split('/', 1)
        if '@' in package_with_version:
            package_name, version = package_with_version.split('@', 1)
            dest_dir = install_dir / author / package_name / version
        else:
            package_name = package_with_version
            package_dir = install_dir / author / package_name
            dest_dir = get_latest_version_dir(package_dir)
    else:
        if '@' in package_str:
            package_name, version = package_str.split('@', 1)
            dest_dir = None
            if install_dir.exists():
                for author in install_dir.iterdir():
                    if author.is_dir():
                        package_path = author / package_name / version
                        if package_path.exists():
                            dest_dir = package_path
                            break
            if dest_dir is None:
                raise FileNotFoundError(f"Package not found: {package_str}")
        else:
            package_name = package_str
            dest_dir = None
            if install_dir.exists():
                for author in install_dir.iterdir():
                    if author.is_dir():
                        package_dir = author / package_name
                        if package_dir.exists():
                            try:
                                dest_dir = get_latest_version_dir(package_dir)
                                break
                            except FileNotFoundError:
                                continue
            if dest_dir is None:
                raise FileNotFoundError(f"Package not found: {package_str}")
    return dest_dir


def _handle_github_server(server_name: str, server_cfg: dict, default_github_token: str) -> None:
    """
    Handle GitHub server configuration by cloning the repo and setting up metadata.

    Supports two modes:
    1. Command specified: Use provided command/args directly
    2. Command not specified: Extract from README or existing metadata.json

    Args:
        server_name: Name of the server
        server_cfg: Server configuration dict with github_repo, github_token, branch, command, args, env
        default_github_token: Default GitHub token from config or environment

    Raises:
        ValueError: If github_token is missing
        RuntimeError: If cloning or metadata extraction fails
    """
    from .github_utils import clone_github_repo, extract_or_create_metadata, apply_env_to_metadata

    github_repo = server_cfg.get("github_repo")
    github_token = server_cfg.get("github_token") or default_github_token
    branch = server_cfg.get("branch") or server_cfg.get("github_branch")

    if not github_token:
        raise ValueError(
            f"GitHub token missing for server '{server_name}'. "
            "Set it in the config, FMCP_GITHUB_TOKEN, or GITHUB_TOKEN environment variable."
        )

    try:
        # Clone the repository
        dest_dir = clone_github_repo(github_repo, github_token, branch)
        metadata_path = dest_dir / "metadata.json"

        # Check if command is provided directly in config
        has_command = server_cfg.get("command") and server_cfg.get("args") is not None

        if has_command:
            # Mode 1: Use provided command directly
            logger.info(f"📝 Using provided command for '{server_name}'")
            logger.debug(f"Command: {server_cfg.get('command')}, Args: {server_cfg.get('args')}")

            # Create metadata.json with provided command
            metadata = {
                "mcpServers": {
                    server_name: {
                        "command": server_cfg.get("command"),
                        "args": server_cfg.get("args"),
                        "env": server_cfg.get("env", {})
                    }
                }
            }

            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)

            logger.success(f"✅ Created metadata.json with provided command")
        else:
            # Mode 2: Extract from README or use existing metadata.json
            logger.info(f"📄 Extracting metadata from repository")
            metadata_path = extract_or_create_metadata(dest_dir)
            logger.debug(f"Metadata extracted/created at: {metadata_path}")

            # Apply environment variables if provided
            if server_cfg.get("env"):
                logger.debug(f"Applying environment variables to {server_name}")
                apply_env_to_metadata(metadata_path, server_name, server_cfg["env"])

        # Set install_path for the launcher
        server_cfg["install_path"] = str(dest_dir)

        logger.success(f"✅ GitHub server '{server_name}' prepared from {github_repo}")
        logger.debug(f"Install path set to: {dest_dir}")

    except Exception as e:
        logger.error(f"Error preparing GitHub server '{server_name}': {e}")
        logger.debug(f"Exception details: {type(e).__name__}: {e}")
        raise


def _create_temp_server_dir(server_name: str, server_cfg: dict) -> Path:
    """
    Create a temporary directory with metadata.json for a direct server configuration.

    Args:
        server_name: Name of the server
        server_cfg: Server configuration dict with command, args, env

    Returns:
        Path to the created temporary directory
    """
    import tempfile

    # Create temp directory in a persistent location
    install_dir = Path(INSTALLATION_DIR)
    temp_base = install_dir / ".temp_servers"
    temp_base.mkdir(parents=True, exist_ok=True)

    # Create server-specific directory
    server_dir = temp_base / server_name
    server_dir.mkdir(parents=True, exist_ok=True)

    # Create metadata.json
    metadata = {
        "mcpServers": {
            server_name: {
                "command": server_cfg.get("command"),
                "args": server_cfg.get("args", []),
                "env": server_cfg.get("env", {})
            }
        }
    }

    metadata_path = server_dir / "metadata.json"
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    return server_dir


def _collect_installed_servers(install_dir: Path, taken_ports: set) -> Dict[str, dict]:
    """
    Scan installed packages, read metadata.json, assign unique ports.
    """
    all_servers = {}

    for author_dir in install_dir.iterdir():
        if not author_dir.is_dir():
            continue
        for pkg_dir in author_dir.iterdir():
            if not pkg_dir.is_dir():
                continue
            try:
                version_dir = get_latest_version_dir(pkg_dir)
            except FileNotFoundError:
                continue

            md = version_dir / "metadata.json"
            if not md.exists():
                continue

            try:
                metadata = json.loads(md.read_text())
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in {md}")
                logger.debug(f"Skipping package at {version_dir}")
                continue

            for key, cfg in metadata.get("mcpServers", {}).items():
                port = find_free_port(taken_ports=taken_ports)
                cfg["port"] = str(port)
                cfg["install_path"] = str(version_dir)
                all_servers[key] = cfg
                taken_ports.add(port)

    return all_servers


def _preprocess_metadata_file(metadata_path: Path) -> None:
    """
    Preprocess metadata file to expand package strings to full metadata.
    Modifies the file in place.
    """
    with open(metadata_path, 'r') as f:
        raw_metadata = json.load(f)

    taken_ports = set()

    for package in list(raw_metadata.get('mcpServers', {}).keys()):
        server_entry = raw_metadata['mcpServers'][package]

        # If already a dict with config, just track the port
        if isinstance(server_entry, dict):
            taken_ports.add(int(server_entry.get("port", -1)))
            continue

        # If it's a string, replace with actual metadata from registry
        replaced_metadata = replace_package_metadata_from_package_name(server_entry)
        if not replaced_metadata or "mcpServers" not in replaced_metadata:
            logger.warning(f"Could not fetch metadata for {server_entry}")
            logger.debug(f"Skipping package string: {server_entry}")
            continue

        # Store original package string
        fmcp_package = server_entry

        # Delete the string entry
        del raw_metadata['mcpServers'][package]

        # Get the actual package name from fetched metadata
        package_name = list(replaced_metadata['mcpServers'].keys())[0]
        value = replaced_metadata['mcpServers'][package_name]

        # Add metadata with additional fields
        raw_metadata['mcpServers'][package_name] = value
        raw_metadata['mcpServers'][package_name]['fmcp_package'] = fmcp_package
        raw_metadata['mcpServers'][package_name]['install_path'] = str(metadata_path)
        raw_metadata['mcpServers'][package_name]['port'] = find_free_port(taken_ports=taken_ports)
        taken_ports.add(raw_metadata['mcpServers'][package_name]['port'])

    # Write back
    with open(metadata_path, 'w') as f:
        json.dump(raw_metadata, f, indent=2)
