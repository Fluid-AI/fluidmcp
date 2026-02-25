"""
Authentication API routes for Auth0 OAuth flow.

This module provides FastAPI endpoints for Auth0 authentication.
"""

import os
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse, Response
from loguru import logger
from .config import Auth0Config
from .oauth_client import Auth0Client
from .dependencies import get_current_user

# Create router
auth_router = APIRouter(prefix="/auth", tags=["Authentication"])

# Initialize Auth0 components (will be set during app startup)
config: Auth0Config = None
oauth_client: Auth0Client = None

# Simple in-memory state store for CSRF protection
_state_store = {}


def init_auth_routes(auth_config: Auth0Config):
    """Initialize auth routes with configuration"""
    global config, oauth_client
    config = auth_config
    oauth_client = Auth0Client(config)


def create_state() -> str:
    """Generate random state for CSRF protection"""
    state = secrets.token_urlsafe(32)
    _state_store[state] = datetime.utcnow()
    # Clean old states (older than 10 minutes)
    cutoff = datetime.utcnow() - timedelta(minutes=10)
    expired = [s for s, t in _state_store.items() if t < cutoff]
    for s in expired:
        del _state_store[s]
    return state


def validate_state(state: str) -> bool:
    """Validate CSRF state token"""
    if state in _state_store:
        del _state_store[state]
        return True
    return False


def is_local_development() -> bool:
    """Check if running in local development (HTTP allowed for cookies)"""
    base_url = os.getenv("FMCP_BASE_URL", "")
    return "localhost" in base_url or "127.0.0.1" in base_url or not base_url


@auth_router.get("/login")
async def login(request: Request, connection: str = None):
    """
    Initiate Auth0 OAuth flow.

    Args:
        request: FastAPI request object
        connection: Optional provider connection (e.g., 'google-oauth2', 'github')
    """
    if not oauth_client:
        raise HTTPException(status_code=500, detail="OAuth not configured. Please set FMCP_AUTH0_* environment variables.")

    # Generate state for CSRF protection
    state = create_state()

    # Use callback URL from config (supports Codespaces and custom domains)
    redirect_uri = config.callback_url
    auth_url = oauth_client.get_authorization_url(state, redirect_uri, connection=connection)

    logger.info(f"Initiating OAuth login flow. Redirect URI: {redirect_uri}")
    return RedirectResponse(url=auth_url)


@auth_router.get("/callback")
async def callback(request: Request, code: str = None, state: str = None, error: str = None):
    """Handle Auth0 OAuth callback"""
    ip_address = request.client.host if request.client else "unknown"

    if error:
        logger.error(f"OAuth callback error: {error}")
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Error</title>
            <style>
                body {{ font-family: system-ui; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #f5f5f5; }}
                .error-box {{ background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; max-width: 500px; }}
                h1 {{ color: #dc3545; }}
                a {{ color: #667eea; text-decoration: none; }}
            </style>
        </head>
        <body>
            <div class="error-box">
                <h1>Authentication Error</h1>
                <p>{error}</p>
                <p><a href="/auth/login">Try again</a></p>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html)

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter")

    # Validate state for CSRF protection
    if not validate_state(state):
        logger.warning(f"Invalid state parameter from {ip_address}")
        raise HTTPException(status_code=400, detail="Invalid state parameter. Possible CSRF attack.")

    # Exchange code for tokens
    try:
        redirect_uri = config.callback_url
        tokens = oauth_client.exchange_code_for_tokens(code, redirect_uri)

        # Get user info from Auth0
        user_info = oauth_client.get_user_info(tokens['access_token'])

        # Use Auth0's id_token directly (RS256 signed by Auth0)
        # This allows jwt_validator.py to validate it properly using JWKS
        access_token = tokens.get('id_token') or tokens.get('access_token')

        if not access_token:
            raise ValueError("No id_token or access_token returned from Auth0")

        logger.info(f"OAuth login successful for user: {user_info.get('email', user_info.get('sub'))}")

        # Create HTML response WITHOUT localStorage (token in httpOnly cookie)
        success_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Login Successful</title>
            <style>
                body {{ font-family: system-ui; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }}
                .success-box {{ background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; }}
                h1 {{ color: #28a745; }}
                .spinner {{ border: 3px solid #f3f3f3; border-top: 3px solid #667eea; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 20px auto; }}
                @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
            </style>
        </head>
        <body>
            <div class="success-box">
                <h1>✓ Login Successful!</h1>
                <p>Welcome, {user_info.get('name', user_info.get('email', 'User'))}!</p>
                <p>Redirecting to dashboard...</p>
                <div class="spinner"></div>
            </div>
            <script>
                // Token stored in httpOnly cookie (secure, XSS-safe)
                // Redirect to dashboard/docs after 1 second
                setTimeout(function() {{
                    window.location.href = '/ui';
                }}, 1000);
            </script>
        </body>
        </html>
        """

        # Create response with httpOnly cookie for security
        response = Response(content=success_html, media_type="text/html")

        # Set secure httpOnly cookie (XSS protection + CSRF protection)
        response.set_cookie(
            key="fmcp_auth_token",
            value=access_token,
            httponly=True,  # Not accessible to JavaScript (XSS protection)
            secure=not is_local_development(),  # HTTPS only in production, HTTP ok for localhost
            samesite="lax",  # CSRF protection + allows OAuth redirects
            max_age=86400,  # 24 hours
            path="/"
        )

        return response

    except Exception as e:
        logger.error(f"OAuth token exchange failed: {e}")
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Failed</title>
            <style>
                body {{ font-family: system-ui; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #f5f5f5; }}
                .error-box {{ background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; max-width: 500px; }}
                h1 {{ color: #dc3545; }}
                a {{ color: #667eea; text-decoration: none; }}
                .error-details {{ background: #f8f9fa; padding: 15px; border-radius: 4px; margin: 20px 0; font-family: monospace; font-size: 12px; text-align: left; word-break: break-word; }}
            </style>
        </head>
        <body>
            <div class="error-box">
                <h1>Authentication Failed</h1>
                <p>Unable to complete authentication with Auth0.</p>
                <div class="error-details">{str(e)}</div>
                <p><a href="/auth/login">Try again</a></p>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html)


@auth_router.get("/me")
async def get_user_info(user: dict = Depends(get_current_user)):
    """
    Get current user information.

    Requires authentication via Authorization header.
    """
    return user


@auth_router.post("/logout")
async def logout(request: Request):
    """Logout user and clear cookie"""
    if not oauth_client:
        raise HTTPException(status_code=500, detail="OAuth not configured")

    # Generate Auth0 logout URL
    base_url = str(request.base_url).rstrip('/')
    logout_url = oauth_client.logout_url(base_url)

    # Create response that clears the cookie
    response = JSONResponse(content={
        "logout_url": logout_url,
        "message": "Cookie cleared, redirect to logout_url"
    })

    # Clear the auth cookie
    response.delete_cookie(
        key="fmcp_auth_token",
        path="/"
    )

    return response


@auth_router.get("/config")
async def get_auth_config():
    """
    Get OAuth configuration for frontend.

    Returns public configuration needed for OAuth flow (no secrets).
    """
    if not config:
        # OAuth not configured, return empty config
        return {
            "enabled": False,
            "domain": None,
            "clientId": None
        }

    return {
        "enabled": True,
        "domain": config.domain,
        "clientId": config.client_id,
        "audience": config.audience
    }
