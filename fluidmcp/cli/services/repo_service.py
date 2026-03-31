"""
RepoService — Pre-microservice boundary for repository and package management.

Wraps config_resolver, github_utils, and package_installer.
In Phase 2, this becomes a separate HTTP service (Repo Service [A]).
"""
import asyncio
from typing import List, Dict, Any
from loguru import logger

from .config_resolver import ServerConfig, resolve_from_file as _resolve_from_file
from .package_installer import install_package as _install_package


class RepoService:
    async def load_from_config_file(self, config_path: str) -> ServerConfig:
        """Resolve all config formats (direct, github, package string) from a JSON file."""
        logger.info(f"RepoService: loading config from {config_path}")
        return await asyncio.to_thread(_resolve_from_file, config_path)

    async def install_packages(self, server_config: ServerConfig) -> None:
        """Install registry packages that need downloading."""
        if not server_config.needs_install:
            return
        for _, srv in server_config.servers.items():
            pkg = srv.get("fmcp_package")
            if pkg:
                logger.info(f"RepoService: installing {pkg}")
                await asyncio.to_thread(_install_package, pkg)

    def build_server_configs_from_resolved(
        self, server_config: ServerConfig
    ) -> List[Dict[str, Any]]:
        """
        Convert ServerConfig → flat dicts ready for ServerManager.start_server().
        install_path is already set by config_resolver after cloning/downloading.
        """
        configs = []
        for server_id, srv in server_config.servers.items():
            install_path = srv.get("install_path", ".")
            cfg = {
                "id": server_id,
                "name": srv.get("name", server_id),
                "command": srv.get("command"),
                "args": srv.get("args", []),
                "env": srv.get("env", {}),
                "working_dir": srv.get("working_dir", install_path),
                "install_path": install_path,
                "source": "config",
                "enabled": True,
                "restart_policy": "never",
            }
            if srv.get("github_repo"):
                cfg["source"] = "github"
                cfg["github_repo"] = srv["github_repo"]
                cfg["github_branch"] = srv.get("branch", "main")
            configs.append(cfg)
        return configs
