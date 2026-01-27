"""
Authentication API routes for Auth0 OAuth flow.

This module provides FastAPI endpoints for Auth0 authentication.
"""

from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Depends, Security
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger
from .config import Auth0Config
from .oauth_client import Auth0Client
from .token_manager import TokenManager
from .session_store import session_store
from ..services.package_launcher import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Security instance for optional authentication (auto_error=False for idempotent operations)
security = HTTPBearer(auto_error=False)

# Initialize Auth0 components (will be set during app startup)
config: Auth0Config = None
oauth_client: Auth0Client = None
token_manager: TokenManager = None


def init_auth_routes(auth_config: Auth0Config):
    """Initialize auth routes with configuration"""
    global config, oauth_client, token_manager
    config = auth_config
    oauth_client = Auth0Client(config)
    token_manager = TokenManager(config)


@router.get("/login")
async def login(request: Request, connection: str = None):
    """
    Initiate Auth0 OAuth flow.

    Args:
        request: FastAPI request object
        connection: Optional provider connection (e.g., 'google-oauth2', 'github', 'zoho', 'atlassian', 'waad')
    """
    if not oauth_client:
        raise HTTPException(status_code=500, detail="Auth0 not configured")

    # Generate state for CSRF protection
    state = session_store.create_state()

    # Use callback URL from config (supports Codespaces and custom domains)
    redirect_uri = config.callback_url
    auth_url = oauth_client.get_authorization_url(state, redirect_uri, connection=connection)

    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def callback(request: Request, code: str = None, state: str = None, error: str = None):
    """Handle Auth0 OAuth callback"""
    # Extract request metadata for logging
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get('user-agent', '')

    if error:
        # Log failed authentication attempt
        if oauth_client and session_store.db:
            try:
                session_store.db.log_auth_event({
                    'event_type': 'login_failed',
                    'ip_address': ip_address,
                    'user_agent': user_agent,
                    'success': False,
                    'error_message': error
                })
            except Exception as e:
                logger.error(f"Failed to log auth failure: {e}")

        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Error</title>
            <style>
                body {{ font-family: system-ui; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #f5f5f5; }}
                .error-box {{ background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; }}
                h1 {{ color: #dc3545; }}
                a {{ color: #667eea; text-decoration: none; }}
            </style>
        </head>
        <body>
            <div class="error-box">
                <h1>Authentication Error</h1>
                <p>{error}</p>
                <p><a href="/">Return to login</a></p>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html)

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    # Validate state
    if not session_store.validate_state(state):
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    # Exchange code for tokens
    try:
        # Use callback URL from config (must match the one used in authorization)
        redirect_uri = config.callback_url
        tokens = oauth_client.exchange_code_for_tokens(code, redirect_uri)

        # Get user info
        user_info = oauth_client.get_user_info(tokens['access_token'])

        # Create our custom JWT token
        access_token = token_manager.create_access_token(user_info)

        # Get token expiration
        from jose import jwt
        try:
            decoded = jwt.decode(access_token, options={"verify_signature": False})
            expires_at = datetime.fromtimestamp(decoded.get('exp', 0)).isoformat() if decoded.get('exp') else ''
        except:
            expires_at = ''

        # Create session with metadata
        session_id = session_store.create_session(
            user_info,
            ip_address=ip_address,
            user_agent=user_agent,
            access_token=access_token,
            expires_at=expires_at
        )

        # Return HTML that stores token and redirects
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
                <p>Redirecting to dashboard...</p>
                <div class="spinner"></div>
            </div>
            <script>
                localStorage.setItem('access_token', '{access_token}');
                localStorage.setItem('session_id', '{session_id}');
                setTimeout(function() {{
                    window.location.href = '/docs';
                }}, 1000);
            </script>
        </body>
        </html>
        """

        return HTMLResponse(content=success_html)

    except Exception as e:
        # Log failed token exchange
        if session_store.db:
            try:
                session_store.db.log_auth_event({
                    'event_type': 'login_failed',
                    'ip_address': ip_address,
                    'user_agent': user_agent,
                    'success': False,
                    'error_message': str(e)
                })
            except Exception as log_error:
                logger.error(f"Failed to log token exchange failure: {log_error}")

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
                .error-details {{ background: #f8f9fa; padding: 15px; border-radius: 4px; margin: 20px 0; font-family: monospace; font-size: 12px; text-align: left; }}
            </style>
        </head>
        <body>
            <div class="error-box">
                <h1>Authentication Failed</h1>
                <p>Unable to complete authentication with Auth0.</p>
                <div class="error-details">{str(e)}</div>
                <p><a href="/">Try again</a></p>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html)


@router.get("/me")
async def get_user_info(user: dict = Depends(get_current_user)):
    """Get current user information.

    Returns user data if authenticated, otherwise returns unauthenticated status.
    This endpoint is developer-friendly for no-auth mode testing.
    """
    if not user:
        # In no-auth mode, return friendly response instead of 401
        return {"authenticated": False, "mode": "no-auth"}
    return {"authenticated": True, "user": user}


@router.post("/logout")
async def logout(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(security)
):
    """Logout user and clear session.

    This endpoint is idempotent and works even if:
    - User is already logged out
    - Token is invalid/expired
    - No authentication is enabled
    """
    # Extract request metadata for logging
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get('user-agent', '')

    # Try to validate token if provided (optional, non-blocking)
    user = None
    if credentials:
        try:
            user = get_current_user(credentials)
        except Exception:
            # Invalid token - that's okay for logout
            pass

    # Get session ID from request if available
    session_id = request.headers.get('X-Session-ID')
    if session_id:
        session_store.delete_session(
            session_id,
            ip_address=ip_address,
            user_agent=user_agent
        )

    # Generate Auth0 logout URL
    logout_url = oauth_client.logout_url(str(request.base_url))

    return {
        "success": True,
        "logout_url": logout_url,
        "user_authenticated": bool(user)
    }
