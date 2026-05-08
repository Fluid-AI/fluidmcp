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
from typing import Optional, Tuple, Dict, List
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
        return dest_dir

    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip() if e.stderr else ""
        stderr_lower = stderr.lower()

        # Construct GitHub URL for error messages (without token)
        github_url = f"https://github.com/{owner}/{repo}"

        # Detect specific error types and provide actionable messages
        if "authentication failed" in stderr_lower or "invalid username or password" in stderr_lower:
            raise RuntimeError(
                f"Authentication failed when cloning {github_url}\n"
                f"  Branch: {target_branch}\n"
                f"  Possible causes:\n"
                f"    - Invalid GitHub token (check FMCP_GITHUB_TOKEN or GITHUB_TOKEN)\n"
                f"    - Token lacks required permissions (needs 'repo' scope for private repos)\n"
                f"    - Token has expired\n"
                f"  Suggestion: Generate a new token at https://github.com/settings/tokens"
            )

        elif "repository not found" in stderr_lower or "could not find remote ref" in stderr_lower:
            raise RuntimeError(
                f"Repository or branch not found: {github_url}\n"
                f"  Branch: {target_branch}\n"
                f"  Possible causes:\n"
                f"    - Repository doesn't exist (check spelling: '{owner}/{repo}')\n"
                f"    - Branch '{target_branch}' doesn't exist\n"
                f"    - Repository is private and token lacks access\n"
                f"  Suggestion: Verify the repository exists and is accessible"
            )

        elif "permission denied" in stderr_lower or "403" in stderr_lower:
            raise RuntimeError(
                f"Permission denied when accessing {github_url}\n"
                f"  Branch: {target_branch}\n"
                f"  Possible causes:\n"
                f"    - Repository is private and requires authentication\n"
                f"    - Token lacks required permissions\n"
                f"    - You don't have access to this repository\n"
                f"  Suggestion: Check repository visibility and token permissions"
            )

        elif "could not resolve host" in stderr_lower or "network" in stderr_lower or "connection" in stderr_lower:
            raise RuntimeError(
                f"Network error when cloning {github_url}\n"
                f"  Branch: {target_branch}\n"
                f"  Possible causes:\n"
                f"    - No internet connection\n"
                f"    - GitHub is unreachable\n"
                f"    - Firewall or proxy blocking access\n"
                f"  Suggestion: Check your network connection and try again"
            )

        else:
            # Generic error with original message
            raise RuntimeError(
                f"Failed to clone {github_url}\n"
                f"  Branch: {target_branch}\n"
                f"  Git error: {stderr if stderr else 'Unknown error'}\n"
                f"  Suggestion: Check the repository URL and your GitHub token"
            )


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


def clone_or_update_repo(
    repo_path: str,
    token: str,
    branch: Optional[str] = None,
    install_dir: Optional[Path] = None,
) -> Path:
    """
    Clone repository or pull latest changes if an existing clone is found.

    Treats the local clone as a cache: if the destination directory already
    exists, a ``git pull --rebase`` is attempted to fetch the latest commits.
    If the pull fails (e.g. no network, merge conflict), the existing files
    are used as-is so callers are not blocked.

    Args:
        repo_path: GitHub repository path (owner/repo or full URL)
        token: GitHub personal access token
        branch: Branch to clone/update (defaults to DEFAULT_GITHUB_BRANCH)
        install_dir: Base installation directory (defaults to .fmcp-packages)

    Returns:
        Path to the (possibly updated) local repository

    Raises:
        ValueError: If github_token is missing
        RuntimeError: If an initial (fresh) clone fails
    """
    owner, repo = normalize_github_repo(repo_path)
    target_branch = branch or DEFAULT_GITHUB_BRANCH

    if install_dir is None:
        from .config_resolver import INSTALLATION_DIR
        install_dir = Path(INSTALLATION_DIR)

    dest_dir = install_dir / owner / repo / target_branch

    if dest_dir.exists() and any(dest_dir.iterdir()):
        logger.info(f"Repository already cloned at {dest_dir}, pulling latest changes...")
        try:
            subprocess.run(
                ["git", "pull", "--rebase"],
                cwd=dest_dir,
                check=True,
                capture_output=True,
                timeout=30,
                text=True,
            )
            logger.info(f"Successfully pulled latest changes for {owner}/{repo}@{target_branch}")
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.strip() if e.stderr else "unknown error"
            logger.warning(f"git pull --rebase failed (using existing clone): {stderr}")
        except subprocess.TimeoutExpired:
            logger.warning("git pull --rebase timed out (using existing clone)")
        return dest_dir

    logger.info(f"No existing clone found, cloning {owner}/{repo}@{target_branch}...")
    return clone_github_repo(repo_path, token, target_branch, install_dir)


class GitHubService:
    """
    Orchestrates GitHub repository cloning and MCP server config extraction.

    This class is the primary entry point for the ``POST /api/servers/from-github``
    endpoint.  It coordinates:
    - Cloning / updating the repository
    - Extracting metadata (metadata.json or README fallback)
    - Validating each server's command against the allowlist
    - Building flat server config dicts via ServerBuilder
    """

    @staticmethod
    def build_server_configs(
        repo_path: str,
        token: str,
        base_server_id: str,
        branch: str = DEFAULT_GITHUB_BRANCH,
        server_name: Optional[str] = None,
        subdirectory: Optional[str] = None,
        env: Optional[Dict] = None,
        restart_policy: str = "never",
        max_restarts: int = 3,
        enabled: bool = True,
        created_by: Optional[str] = None,
    ) -> Tuple[List[Dict], Path]:
        """
        Clone/update a GitHub repository and build MCP server configuration(s).

        Workflow:
        1. Clone or update the repository
        2. Optionally resolve a subdirectory (for monorepos)
        3. Extract metadata (metadata.json or README)
        3. Validate each server's command against the allowlist
        4. Build flat server config(s) via ServerBuilder

        Args:
            repo_path: GitHub repo (owner/repo or full URL)
            token: GitHub personal access token
            base_server_id: Base ID for the generated server(s)
            branch: Branch to clone (default: DEFAULT_GITHUB_BRANCH)
            server_name: Select a specific server from a multi-server repo (optional)
            subdirectory: Subdirectory within the repo that contains metadata.json
                (for monorepos, e.g. "google-sheets-mcp").  The working_dir of the
                produced configs will be set to this subdirectory, not the repo root.
            env: Additional environment variables merged on top of repo defaults
            restart_policy: "never", "on-failure", or "always"
            max_restarts: Maximum restart attempts
            enabled: Whether created servers are enabled
            created_by: User performing the operation (for audit)

        Returns:
            Tuple of (list of flat server config dicts, clone path)

        Raises:
            ValueError: Invalid input, unsupported command, bad metadata, or missing subdirectory
            RuntimeError: Clone failure
        """
        from .server_builder import ServerBuilder
        from .validators import validate_command_allowlist

        # 1. Clone or update repository
        clone_path = clone_or_update_repo(repo_path, token, branch)

        # 2. Resolve the directory to look for metadata in
        #    For monorepos, ``subdirectory`` points to the specific MCP folder.
        if subdirectory:
            metadata_dir = clone_path / subdirectory
            if not metadata_dir.is_dir():
                raise ValueError(
                    f"Subdirectory '{subdirectory}' not found in cloned repository. "
                    f"Clone path: {clone_path}"
                )
            logger.info(f"Using subdirectory '{subdirectory}' for metadata lookup")
        else:
            metadata_dir = clone_path

        # 3. Extract metadata (metadata.json or README fallback)
        metadata_path = extract_or_create_metadata(metadata_dir)
        with open(metadata_path, "r") as f:
            metadata = json.load(f)

        validate_mcp_metadata(metadata)
        mcp_servers = metadata.get("mcpServers", {})

        # 4. Optionally filter to a single named server
        if server_name:
            if server_name not in mcp_servers:
                available = ", ".join(mcp_servers.keys()) or "none"
                raise ValueError(
                    f"Server '{server_name}' not found in repository metadata. "
                    f"Available servers: {available}"
                )
            mcp_servers = {server_name: mcp_servers[server_name]}

        is_multi = len(mcp_servers) > 1

        # 5. Build configs
        #
        # working_dir = clone_path (repo root) — always the root of the clone.
        #
        # Why not metadata_dir?  When a subdirectory is used, the metadata args
        # commonly reference the subdir via `--directory <subdir>` (e.g.
        # `uv --directory google-sheets-mcp run server.py`).  That pattern is
        # designed to be executed from the repo root, not from inside the subdir.
        # Setting working_dir to the repo root keeps those args correct.
        #
        # install_path = metadata_dir (the resolved lookup dir, subdir or root).
        configs: List[Dict] = []
        for name, srv_config in mcp_servers.items():
            # Validate command against allowlist before building the config
            command = srv_config.get("command", "")
            is_valid, error = validate_command_allowlist(command)
            if not is_valid:
                raise ValueError(f"Server '{name}': {error}")

            config = ServerBuilder.build_config(
                base_id=base_server_id,
                server_name=name,
                server_config=srv_config,
                clone_path=clone_path,     # working_dir = repo root
                install_path=metadata_dir, # install_path = subdir (or root)
                repo_path=repo_path,
                branch=branch,
                env=env,
                restart_policy=restart_policy,
                max_restarts=max_restarts,
                enabled=enabled,
                is_multi_server=is_multi,
                created_by=created_by,
            )
            configs.append(config)

        return configs, clone_path


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
