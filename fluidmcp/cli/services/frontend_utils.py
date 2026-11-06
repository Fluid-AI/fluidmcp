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
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
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
    port: int = 8499
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

    # Known SPA routes that should redirect /route → /ui/route when hit bare
    _SPA_ROUTES = {
        "status", "servers", "documentation", "inspector",
        "llm",
    }

    try:
        index_html = frontend_dist / "index.html"
        assets_dir = frontend_dist / "assets"

        # Mount /ui/assets separately so static asset requests are served directly
        # without going through the SPA fallback handler.
        if assets_dir.exists():
            app.mount("/ui/assets", StaticFiles(directory=str(assets_dir)), name="ui-assets")

        # Explicit /ui and /ui/ routes — Starlette's StaticFiles mount redirects
        # /ui → /ui/ via an absolute Location header built from the raw Host header.
        # Behind GitHub Codespaces / Railway that points at localhost:port instead of
        # the public hostname. Serving index.html directly avoids the redirect entirely.
        @app.get("/ui", include_in_schema=False)
        @app.get("/ui/", include_in_schema=False)
        async def ui_root():
            return FileResponse(str(index_html))

        # SPA catch-all: any /ui/{path} that isn't a real file gets index.html.
        # Starlette's StaticFiles(html=True) falls back to 404.html (not index.html)
        # when a path doesn't match a file, so deep-links like /ui/status would 404.
        #
        # SECURITY: Path traversal protection
        # User-controlled path segments like "../../../etc/passwd" are resolved and
        # checked to ensure they stay within frontend_dist before serving.
        @app.get("/ui/{path:path}", include_in_schema=False)
        async def ui_spa(path: str):
            # Build candidate path and resolve it to absolute form
            candidate = (frontend_dist / path).resolve()
            frontend_dist_resolved = frontend_dist.resolve()

            # Containment check: ensure resolved path is under frontend_dist
            # This prevents path traversal attacks (e.g., /ui/../../../etc/passwd)
            try:
                candidate.relative_to(frontend_dist_resolved)
            except ValueError:
                # Path escaped frontend_dist - serve index.html instead of error
                # (error would leak information about server filesystem structure)
                return FileResponse(str(index_html))

            # Safe to serve: path is contained within frontend_dist
            if candidate.exists() and candidate.is_file():
                return FileResponse(str(candidate))
            return FileResponse(str(index_html))

        # Redirect bare SPA routes (/status, /servers, etc.) → /ui/<route> so that
        # copy-pasting a deep-link without the /ui prefix still works.
        def _make_redirect_handler():
            async def handler(request: Request):
                return RedirectResponse(url="/ui" + str(request.url.path), status_code=302)
            return handler

        for _route in _SPA_ROUTES:
            _handler = _make_redirect_handler()
            app.add_api_route(f"/{_route}", _handler, include_in_schema=False)
            app.add_api_route(f"/{_route}/{{rest:path}}", _handler, include_in_schema=False)

        logger.info("✓ Frontend UI routes registered")

        display_host = "localhost" if host == "0.0.0.0" else host
        logger.info(f"✓ Frontend UI available at http://{display_host}:{port}/ui")

        return True

    except Exception as e:
        logger.warning(f"Failed to mount frontend static files: {e}")
        return False
