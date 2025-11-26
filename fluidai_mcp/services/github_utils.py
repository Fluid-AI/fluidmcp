"""
GitHub utilities for cloning and managing MCP servers from GitHub repositories.

This module provides functionality to:
- Clone GitHub repositories
- Extract metadata from README files
- Validate and create metadata.json files
- Handle GitHub-based MCP server configurations
"""

import json
import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple, Dict
from loguru import logger


DEFAULT_GITHUB_BRANCH = "main"


def normalize_github_repo(repo_path: str) -> Tuple[str, str]:
    """
    Normalize a GitHub repo path or URL to (owner, repo).

    Supports:
    - owner/repo
    - https://github.com/owner/repo
    - https://github.com/owner/repo.git

    Args:
        repo_path: GitHub repository path or URL

    Returns:
        Tuple of (owner, repo)

    Raises:
        ValueError: If the repo path format is invalid
    """
    cleaned = repo_path.strip()

    # Remove GitHub URL prefixes
    cleaned = cleaned.replace("https://github.com/", "").replace("http://github.com/", "")

    # Remove .git suffix
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]

    # Validate format
    if cleaned.count("/") != 1:
        raise ValueError("GitHub repo path must be in the form 'owner/repo'")

    owner, repo = cleaned.split("/", 1)
    return owner, repo


def clone_github_repo(
    repo_path: str,
    github_token: str,
    branch: Optional[str] = None,
    install_dir: Optional[Path] = None
) -> Path:
    """
    Clone a GitHub repository into the standard FMCP package layout.

    Args:
        repo_path: GitHub repository path (owner/repo)
        github_token: GitHub personal access token
        branch: Branch to clone (defaults to 'main')
        install_dir: Base installation directory (defaults to .fmcp-packages)

    Returns:
        Path to the cloned repository

    Raises:
        ValueError: If github_token is missing
        RuntimeError: If git clone fails
    """
    if not github_token:
        raise ValueError("GitHub token is required to clone the repository")

    owner, repo = normalize_github_repo(repo_path)
    target_branch = branch or DEFAULT_GITHUB_BRANCH

    # Use provided install_dir or default
    if install_dir is None:
        from .config_resolver import INSTALLATION_DIR
        install_dir = Path(INSTALLATION_DIR)

    dest_dir = install_dir / owner / repo / target_branch
    dest_dir.parent.mkdir(parents=True, exist_ok=True)

    # Check if already cloned
    if dest_dir.exists() and any(dest_dir.iterdir()):
        logger.info(f"Repository already cloned at {dest_dir}, reusing existing files")
        return dest_dir

    # Clone with depth=1 for faster cloning
    clone_url = f"https://{github_token}@github.com/{owner}/{repo}.git"

    try:
        result = subprocess.run(
            [
                "git",
                "clone",
                "--depth", "1",
                "--branch", target_branch,
                clone_url,
                str(dest_dir),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        logger.info(f"Cloned {owner}/{repo}@{target_branch} to {dest_dir}")
        print(f"✅ Cloned {owner}/{repo} to {dest_dir}")
        return dest_dir

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        raise RuntimeError(f"Failed to clone repository {owner}/{repo}: {error_msg}")


def find_readme_file(directory: Path) -> Path:
    """
    Search for README file with common naming patterns.

    Args:
        directory: Directory to search in

    Returns:
        Path to README file

    Raises:
        FileNotFoundError: If no README found
    """
    readme_patterns = [
        "README.md",
        "readme.md",
        "Readme.md",
        "README.MD",
        "README",
        "readme",
    ]

    for pattern in readme_patterns:
        readme_path = directory / pattern
        if readme_path.exists():
            return readme_path

    raise FileNotFoundError(f"No README file found in {directory}")


def extract_json_from_readme(readme_content: str) -> Dict:
    """
    Extract JSON configuration from README file.

    Looks for:
    1. JSON code blocks with ```json
    2. JSON code blocks with ```
    3. Raw JSON in the text

    Prioritizes blocks containing 'mcpServers' key.

    Args:
        readme_content: Content of README file

    Returns:
        Parsed JSON dictionary

    Raises:
        ValueError: If no valid JSON found
    """
    # Try to find JSON in code blocks
    code_block_pattern = r'```(?:json)?\s*\n([\s\S]*?)\n```'
    code_blocks = re.findall(code_block_pattern, readme_content)

    # First, look for blocks containing mcpServers
    for block in code_blocks:
        if 'mcpServers' in block or '"mcpServers"' in block:
            try:
                data = json.loads(block.strip())
                if validate_mcp_metadata(data, raise_error=False):
                    return data
            except json.JSONDecodeError:
                continue

    # Then try any JSON block
    for block in code_blocks:
        try:
            data = json.loads(block.strip())
            if 'mcpServers' in data or 'command' in data:
                return data
        except json.JSONDecodeError:
            continue

    # Try to find raw JSON with nested braces
    json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    json_matches = re.findall(json_pattern, readme_content, re.DOTALL)

    for match in json_matches:
        if 'mcpServers' in match:
            try:
                data = json.loads(match)
                return data
            except json.JSONDecodeError:
                continue

    raise ValueError("No valid JSON configuration found in README")


def validate_mcp_metadata(metadata: Dict, raise_error: bool = True) -> bool:
    """
    Validate MCP server metadata structure.

    Required structure:
    {
        "mcpServers": {
            "server-name": {
                "command": "...",
                "args": [...]
            }
        }
    }

    Args:
        metadata: Metadata dictionary to validate
        raise_error: Whether to raise ValueError on validation failure

    Returns:
        True if valid, False otherwise

    Raises:
        ValueError: If invalid and raise_error=True
    """
    if "mcpServers" not in metadata:
        if raise_error:
            raise ValueError("Metadata must contain 'mcpServers' key")
        return False

    servers = metadata["mcpServers"]
    if not isinstance(servers, dict) or not servers:
        if raise_error:
            raise ValueError("'mcpServers' must be a non-empty dictionary")
        return False

    for server_name, config in servers.items():
        if not isinstance(config, dict):
            if raise_error:
                raise ValueError(f"Server '{server_name}' configuration must be a dictionary")
            return False

        if "command" not in config:
            if raise_error:
                raise ValueError(f"Server '{server_name}' must have 'command' field")
            return False

        if "args" not in config:
            if raise_error:
                raise ValueError(f"Server '{server_name}' must have 'args' field")
            return False

    return True


def extract_or_create_metadata(repo_dir: Path) -> Path:
    """
    Extract metadata from README or use existing metadata.json.

    Workflow:
    1. Check if metadata.json exists -> use it
    2. If not, look for README -> extract JSON -> create metadata.json
    3. If no README or invalid JSON -> raise error

    Args:
        repo_dir: Path to cloned repository

    Returns:
        Path to metadata.json file

    Raises:
        FileNotFoundError: If no metadata.json or README found
        ValueError: If README doesn't contain valid metadata
    """
    metadata_path = repo_dir / "metadata.json"

    # If metadata.json exists, validate and use it
    if metadata_path.exists():
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            validate_mcp_metadata(metadata)
            logger.info(f"Using existing metadata.json from {repo_dir}")
            return metadata_path
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Existing metadata.json is invalid: {e}")
            # Continue to extract from README

    # Try to extract from README
    logger.info(f"No valid metadata.json, attempting to extract from README")

    try:
        readme_path = find_readme_file(repo_dir)
        readme_content = readme_path.read_text(encoding='utf-8')

        metadata = extract_json_from_readme(readme_content)
        validate_mcp_metadata(metadata)

        # Create metadata.json
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"Created metadata.json from README in {repo_dir}")
        print(f"✅ Extracted metadata from README and created metadata.json")

        return metadata_path

    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"No metadata.json or README found in {repo_dir}. "
            "GitHub MCP servers must have either metadata.json or README with configuration."
        ) from e
    except ValueError as e:
        raise ValueError(
            f"Failed to extract valid metadata from README in {repo_dir}: {e}"
        ) from e


def is_github_repo(directory: Path) -> bool:
    """
    Check if a directory is a cloned GitHub repository.

    Args:
        directory: Path to check

    Returns:
        True if directory contains .git folder
    """
    return (directory / ".git").exists()


def apply_env_to_metadata(metadata_path: Path, server_name: str, env_config: Dict) -> None:
    """
    Update environment variables for a server in its metadata.json.

    Args:
        metadata_path: Path to metadata.json
        server_name: Name of the server to update
        env_config: Environment variables to apply
    """
    if not metadata_path.exists():
        logger.warning(f"Metadata file not found: {metadata_path}")
        return

    with open(metadata_path, 'r') as f:
        metadata = json.load(f)

    server_block = metadata.get("mcpServers", {}).get(server_name)
    if server_block is None:
        logger.warning(f"Server '{server_name}' not found in {metadata_path}")
        return

    server_block.setdefault("env", {})

    # Apply environment variables
    for key, value in env_config.items():
        if isinstance(value, dict) and "value" in value:
            # Structured format
            if isinstance(server_block["env"].get(key), dict):
                server_block["env"][key]["value"] = value["value"]
            else:
                server_block["env"][key] = value["value"]
        else:
            # Simple format
            server_block["env"][key] = value

    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"Applied environment variables to {server_name} in {metadata_path}")
