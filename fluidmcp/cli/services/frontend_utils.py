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

    Tries multiple locations in order:
    1. FRONTEND_DIST_PATH environment variable (custom override)
    2. Installed package location (2 levels up - for pip install, primary success path)
    3. Docker build location (/app/fluidmcp/frontend/dist - fallback for Railway)
    4. Source development location (3 levels up - fallback for editable install)

    This multi-location approach ensures the frontend is found regardless of:
    - Development vs production environment
    - Editable vs production pip install
    - Local development vs Docker deployment

    Returns:
        Path to frontend dist directory if it exists, None otherwise

    Examples:
        >>> path = get_frontend_dist_path()
        >>> if path:
        ...     print(f"Frontend found at: {path}")
    """
    import os

    # 1. Check environment variable override (highest priority)
    env_path = os.environ.get('FRONTEND_DIST_PATH')
    if env_path:
        path = Path(env_path)
        if path.exists() and path.is_dir():
            logger.debug(f"Frontend found via FRONTEND_DIST_PATH: {path}")
            return path
        logger.warning(f"FRONTEND_DIST_PATH set but directory not found: {env_path}")

    # Current file location:
    # - Source: fluidmcp/cli/services/frontend_utils.py
    # - Installed: site-packages/fluidmcp/services/frontend_utils.py (cli removed by package_dir)

    # 2. Try installed package location (2 levels up)
    # After pip install, setup.py maps 'fluidmcp/cli/' -> 'fluidmcp/' package
    # So we need 2 levels: services -> fluidmcp -> frontend/dist
    installed_root = Path(__file__).parent.parent
    installed_dist = installed_root / "frontend" / "dist"
    if installed_dist.exists() and installed_dist.is_dir():
        logger.debug(f"Frontend found at installed location: {installed_dist}")
        return installed_dist

    # 3. Try Docker build location (Railway/container deployment)
    # Frontend is built to /app/fluidmcp/frontend/dist during Docker build
    # Fallback for when package_data doesn't work as expected
    docker_dist = Path("/app/fluidmcp/frontend/dist")
    if docker_dist.exists() and docker_dist.is_dir():
        logger.debug(f"Frontend found at Docker location: {docker_dist}")
        return docker_dist

    # 4. Try source development location (3 levels up)
    # In source code: cli/services -> cli -> fluidmcp -> frontend/dist
    # For editable installs or pre-install scenarios
    source_root = Path(__file__).parent.parent.parent
    source_dist = source_root / "frontend" / "dist"
    if source_dist.exists() and source_dist.is_dir():
        logger.debug(f"Frontend found at source location: {source_dist}")
        return source_dist

    # All locations failed
    logger.debug(f"Frontend not found. Tried locations:")
    logger.debug(f"  - Installed: {installed_dist}")
    logger.debug(f"  - Docker: {docker_dist}")
    logger.debug(f"  - Source: {source_dist}")
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

        # Log attempted paths for troubleshooting
        current_file = Path(__file__)
        logger.debug(f"frontend_utils.py location: {current_file}")
        logger.debug(f"Attempted paths:")
        logger.debug(f"  - Installed (2 levels up): {current_file.parent.parent / 'frontend' / 'dist'}")
        logger.debug(f"  - Docker path: /app/fluidmcp/frontend/dist")
        logger.debug(f"  - Source (3 levels up): {current_file.parent.parent.parent / 'frontend' / 'dist'}")

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
