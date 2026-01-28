"""
Frontend serving utilities for FluidMCP.

This module provides functionality to:
- Locate the frontend dist directory
- Mount frontend static files to FastAPI applications
- Configure frontend routes for single-page applications
"""

from pathlib import Path
from typing import Optional
from loguru import logger
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def get_frontend_dist_path() -> Optional[Path]:
    """
    Get the path to the frontend dist directory.

    The frontend is located at fluidmcp/frontend/dist relative to the package root.
    This function works regardless of where it's called from within the package.

    Returns:
        Path to frontend dist directory if it exists, None otherwise

    Examples:
        >>> path = get_frontend_dist_path()
        >>> if path:
        ...     print(f"Frontend found at: {path}")
    """
    # Get the fluidmcp package root
    # This file is at: fluidmcp/cli/services/frontend_utils.py
    # Package root is 3 levels up: ../../..  ->  fluidmcp/
    package_root = Path(__file__).parent.parent.parent
    frontend_dist = package_root / "frontend" / "dist"

    if frontend_dist.exists() and frontend_dist.is_dir():
        return frontend_dist

    return None


def setup_frontend_routes(
    app: FastAPI,
    host: str = "0.0.0.0",
    port: int = 8099
) -> bool:
    """
    Set up frontend routes for serving the built UI.

    Mounts the frontend static files at /ui path if the dist directory exists.
    The StaticFiles mount with html=True handles SPA routing automatically by
    serving index.html for all unmatched routes under /ui.

    NOTE:
    - Development: Frontend runs separately via Vite (port 5173) with hot reload
    - Production: Frontend is pre-built via 'npm run build' and served at /ui
    - This function only works when dist directory exists (after build)

    Args:
        app: FastAPI application instance to mount routes on
        host: Host address for URL logging (e.g., "0.0.0.0", "localhost", "127.0.0.1")
        port: Port number for URL logging

    Returns:
        True if frontend routes were successfully mounted, False otherwise

    Examples:
        >>> from fastapi import FastAPI
        >>> app = FastAPI()
        >>> success = setup_frontend_routes(app, host="localhost", port=8099)
        >>> if success:
        ...     print("Frontend available at http://localhost:8099/ui")
    """
    frontend_dist = get_frontend_dist_path()

    if not frontend_dist:
        logger.warning("Frontend dist directory not found")
        logger.warning("Run 'npm run build' in fluidmcp/frontend to build the UI")
        return False

    try:
        # Mount StaticFiles for serving built assets (JS, CSS, images)
        # The html=True parameter enables SPA mode:
        # - Serves static files normally (app.js, styles.css, etc.)
        # - Falls back to index.html for non-file paths (SPA routing)
        # This eliminates the need for separate route handlers
        app.mount("/ui", StaticFiles(directory=str(frontend_dist), html=True), name="ui")

        logger.info("✓ Frontend UI routes registered")

        # Log the URL with the correct host
        # Use localhost for better UX if host is 0.0.0.0
        display_host = "localhost" if host == "0.0.0.0" else host
        logger.info(f"✓ Frontend UI available at http://{display_host}:{port}/ui")

        return True

    except Exception as e:
        logger.warning(f"Failed to mount frontend static files: {e}")
        return False
