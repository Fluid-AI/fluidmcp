"""
Server configuration builder for GitHub-sourced MCP servers.

Handles ID normalisation (slugification) and config assembly for both
single-server and multi-server repositories.

The produced config dict uses the FLAT format expected by:
- ServerManager._spawn_mcp_process()  (reads command/args/env at top level)
- DatabaseManager.save_server_config() (converts flat -> nested for MongoDB)
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


class ServerBuilder:
    """Builds normalised MCP server configurations from repository metadata."""

    @staticmethod
    def slugify(text: str) -> str:
        """
        Normalise text to a URL-friendly slug.

        Examples:
            "My Server"   -> "my-server"
            "API v2.0"    -> "api-v2-0"
            "file_system" -> "file-system"

        Args:
            text: Text to slugify

        Returns:
            Lowercase hyphenated slug
        """
        text = text.lower()
        # Replace spaces and underscores with hyphens
        text = re.sub(r'[\s_]+', '-', text)
        # Remove non-alphanumeric characters (except hyphens)
        text = re.sub(r'[^a-z0-9-]', '', text)
        # Collapse consecutive hyphens
        text = re.sub(r'-+', '-', text)
        return text.strip('-')

    @staticmethod
    def generate_server_id(base_id: str, server_name: str, is_multi_server: bool) -> str:
        """
        Generate a normalised server ID.

        Single-server repo:
            base_id="my-server", name="filesystem"  -> "my-server"

        Multi-server repo:
            base_id="tools", name="filesystem"       -> "tools-filesystem"
            base_id="tools", name="API Server"       -> "tools-api-server"

        Args:
            base_id: Base identifier provided by the user
            server_name: Server name as it appears in metadata.json
            is_multi_server: True when the repository defines more than one server

        Returns:
            Normalised server ID string
        """
        if not is_multi_server:
            return base_id

        name_slug = ServerBuilder.slugify(server_name)
        return f"{base_id}-{name_slug}"

    @staticmethod
    def build_config(
        base_id: str,
        server_name: str,
        server_config: Dict,
        clone_path: Path,
        repo_path: str,
        branch: str,
        env: Optional[Dict[str, str]],
        restart_policy: str,
        max_restarts: int,
        enabled: bool,
        is_multi_server: bool,
        install_path: Optional[Path] = None,
        created_by: Optional[str] = None,
    ) -> Dict:
        """
        Build a complete flat server configuration ready for MongoDB.

        Uses flat format (command/args/env at top-level) so that it works
        directly with ServerManager._spawn_mcp_process() and
        DatabaseManager.save_server_config().

        Supports both stdio (default) and SSE transport. If the server block
        in metadata.json contains a ``transport`` field set to ``"sse"``, the
        produced config will include ``transport`` and ``url`` fields and
        ServerManager will skip the stdio handshake in favour of HTTP.

        Args:
            base_id: User-provided base identifier
            server_name: Server name from metadata.json
            server_config: Individual server block from metadata (command, args, env, ...)
            clone_path: Repo root — used as ``working_dir``
            repo_path: Original GitHub repo path (owner/repo)
            branch: Branch that was cloned
            env: Additional environment variables merged on top of repo defaults
            restart_policy: "never", "on-failure", or "always"
            max_restarts: Maximum restart attempts
            enabled: Whether the server should be enabled after creation
            is_multi_server: True when repo has more than one server
            install_path: Optional override for install_path.  Defaults to ``clone_path``.
            created_by: User performing the operation (for audit)

        Returns:
            Flat config dict compatible with ServerManager and DatabaseManager
        """
        server_id = ServerBuilder.generate_server_id(base_id, server_name, is_multi_server)

        # Merge env: metadata env is the base, user-supplied env takes precedence
        merged_env = {**server_config.get("env", {}), **(env or {})}

        effective_install_path = install_path if install_path is not None else clone_path

        # ── Detect transport type from metadata.json server block ────────────
        # Repos declare SSE transport by adding "transport": "sse" (and
        # optionally "url": "http://127.0.0.1:<port>") to their mcpServers block.
        # Example metadata.json entry:
        #   "game-hub": {
        #     "command": "uv",
        #     "args": ["--directory", "game-hub-mcp/game-hub", "run", "server.py"],
        #     "env": {},
        #     "transport": "sse",
        #     "url": "http://127.0.0.1:8000"
        #   }
        transport = server_config.get("transport", "stdio")
        sse_url = server_config.get("url", "http://127.0.0.1:8000")

        config = {
            "id": server_id,
            "name": server_config.get("name", server_name),
            "description": server_config.get(
                "description", f"MCP server cloned from GitHub: {repo_path}"
            ),
            "enabled": enabled,
            # Flat format expected by ServerManager._spawn_mcp_process()
            "command": server_config["command"],
            "args": server_config.get("args", []),
            "env": merged_env,
            # working_dir = repo root so that --directory <subdir> args resolve correctly
            "working_dir": str(clone_path),
            "install_path": str(effective_install_path),
            # Restart configuration
            "restart_policy": restart_policy,
            "max_restarts": max_restarts,
            # GitHub provenance metadata
            "source": "github",
            "github_repo": repo_path,
            "github_branch": branch,
            "github_server_name": server_name,
            # Audit fields
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc),
        }

        # ── SSE-specific fields ───────────────────────────────────────────────
        # Only written when transport is explicitly "sse" so that existing stdio
        # configs are completely unaffected.
        if transport == "sse":
            config["transport"] = "sse"
            config["url"] = sse_url
            logger.info(
                f"Server '{server_id}' configured with SSE transport at {sse_url}"
            )

        return config


# ---------------------------------------------------------------------------
# Module-level logger (mirrors the pattern used everywhere else in the package)
# ---------------------------------------------------------------------------
from loguru import logger  # noqa: E402  (imported after class to keep class self-contained)