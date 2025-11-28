"""
OAuth 2.0 service with PKCE support.

Handles OAuth authentication flow, token refresh, and validation.
"""

import hashlib
import secrets
import base64
import webbrowser
import requests
import time
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, parse_qs, urlparse
from typing import Optional, Dict
from loguru import logger
from .token_storage import save_token, get_token


def _generate_pkce_pair():
    """Generate PKCE code verifier and challenge pair."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode('utf-8')).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode('utf-8')
    return verifier, challenge


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback."""
    code = None
    error = None

    def do_GET(self):
        query = urlparse(self.path).query
        params = parse_qs(query)

        if 'code' in params:
            self.server.code = params['code'][0]
            msg = """
            <html>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1 style="color: #4CAF50;">✓ Authentication Successful!</h1>
                    <p>You can close this window and return to the CLI.</p>
                </body>
            </html>
            """
        elif 'error' in params:
            self.server.error = params['error'][0]
            msg = f"""
            <html>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1 style="color: #f44336;">✗ Authentication Failed</h1>
                    <p>Error: {self.server.error}</p>
                    <p>Please return to the CLI and try again.</p>
                </body>
            </html>
            """
        else:
            msg = """
            <html>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1 style="color: #f44336;">✗ Authentication Failed</h1>
                    <p>No authorization code received.</p>
                </body>
            </html>
            """

        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(msg.encode('utf-8'))

    def log_message(self, format, *args):
        """Suppress logging output."""
        return


def authenticate_package(package_name: str, auth_config: Dict) -> Dict:
    """
    Authenticate a package using OAuth 2.0 with PKCE.

    Args:
        package_name: Name of the package to authenticate
        auth_config: OAuth configuration from package metadata

    Returns:
        Dictionary containing access_token, refresh_token, expires_in, etc.

    Raises:
        RuntimeError: If authentication fails
    """
    logger.info(f"Starting OAuth authentication for {package_name}")

    verifier, challenge = _generate_pkce_pair()

    # Support client_id from env var
    client_id = auth_config.get("client_id")
    if not client_id and auth_config.get("client_id_env"):
        client_id = os.environ.get(auth_config.get("client_id_env"))

    if not client_id:
        raise RuntimeError("client_id not found in auth config or environment")

    # Build authorization URL
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": "http://localhost:8888/callback",
        "scope": " ".join(auth_config.get("scopes", [])),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent"
    }

    auth_url = f"{auth_config['authorization_url']}?{urlencode(params)}"

    # Start local server to receive callback
    server = HTTPServer(('localhost', 8888), OAuthCallbackHandler)
    server.code = None
    server.error = None

    print(f"\n{'='*60}")
    print(f"OAuth Authentication Required for {package_name}")
    print(f"{'='*60}")
    print(f"\nOpening browser for authentication...")
    print(f"If the browser doesn't open, visit this URL manually:")
    print(f"\n{auth_url}\n")

    try:
        webbrowser.open(auth_url)
    except Exception as e:
        logger.warning(f"Could not open browser automatically: {e}")

    print("Waiting for authentication callback...")

    # Wait for callback
    server.handle_request()

    if server.error:
        raise RuntimeError(f"OAuth error: {server.error}")

    if not server.code:
        raise RuntimeError("Authentication failed - no authorization code received")

    logger.info("Authorization code received, exchanging for tokens...")

    # Exchange authorization code for tokens
    token_data = {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": server.code,
        "redirect_uri": "http://localhost:8888/callback",
        "code_verifier": verifier
    }

    # Add client_secret if provided
    if "client_secret" in auth_config:
        token_data["client_secret"] = auth_config["client_secret"]
    elif "client_secret_env" in auth_config:
        client_secret = os.environ.get(auth_config["client_secret_env"])
        if client_secret:
            token_data["client_secret"] = client_secret

    try:
        res = requests.post(auth_config["token_url"], data=token_data)
        res.raise_for_status()
        tokens = res.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Token exchange failed: {e}")
        if hasattr(e.response, 'text'):
            logger.error(f"Response: {e.response.text}")
        raise RuntimeError(f"Failed to exchange authorization code: {e}")

    # Store metadata
    tokens["created_at"] = time.time()
    tokens["auth_config"] = auth_config  # Store config for refresh

    save_token(package_name, tokens)
    logger.info(f"Successfully authenticated {package_name}")

    print(f"\n✓ Authentication successful for {package_name}!")

    return tokens


def refresh_token(package_name: str, tokens: Dict) -> Dict:
    """
    Refresh an expired access token using the refresh token.

    Args:
        package_name: Name of the package
        tokens: Current token data including refresh_token

    Returns:
        Updated token dictionary with new access_token

    Raises:
        RuntimeError: If refresh fails
    """
    if "refresh_token" not in tokens:
        raise RuntimeError("No refresh token available, re-authentication required")

    auth_config = tokens.get("auth_config")
    if not auth_config:
        raise RuntimeError("No auth config found in stored tokens, re-authentication required")

    logger.info(f"Refreshing access token for {package_name}")

    # Get client_id
    client_id = auth_config.get("client_id")
    if not client_id and auth_config.get("client_id_env"):
        client_id = os.environ.get(auth_config.get("client_id_env"))

    if not client_id:
        raise RuntimeError("client_id not found in auth config or environment")

    # Build refresh request
    refresh_data = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"]
    }

    # Add client_secret if provided
    if "client_secret" in auth_config:
        refresh_data["client_secret"] = auth_config["client_secret"]
    elif "client_secret_env" in auth_config:
        client_secret = os.environ.get(auth_config["client_secret_env"])
        if client_secret:
            refresh_data["client_secret"] = client_secret

    try:
        res = requests.post(auth_config["token_url"], data=refresh_data)
        res.raise_for_status()
        new_tokens = res.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Token refresh failed: {e}")
        if hasattr(e.response, 'text'):
            logger.error(f"Response: {e.response.text}")
        raise RuntimeError(f"Failed to refresh token: {e}")

    # Update tokens
    tokens["access_token"] = new_tokens["access_token"]
    tokens["created_at"] = time.time()
    tokens["expires_in"] = new_tokens.get("expires_in", tokens.get("expires_in", 3600))

    # Some providers issue new refresh tokens
    if "refresh_token" in new_tokens:
        tokens["refresh_token"] = new_tokens["refresh_token"]

    save_token(package_name, tokens)
    logger.info(f"Successfully refreshed token for {package_name}")

    return tokens


def get_valid_token(package_name: str, auth_config: Dict) -> Optional[str]:
    """
    Get a valid access token, refreshing if necessary.

    Args:
        package_name: Name of the package
        auth_config: OAuth configuration from package metadata

    Returns:
        Valid access token or None if not authenticated

    Raises:
        RuntimeError: If refresh fails and re-authentication is needed
    """
    tokens = get_token(package_name)

    if not tokens:
        logger.debug(f"No tokens found for {package_name}")
        return None

    # Check if token is expired (with 60 second buffer)
    created_at = tokens.get("created_at", 0)
    expires_in = tokens.get("expires_in", 3600)
    token_age = time.time() - created_at

    if token_age > (expires_in - 60):
        logger.info(f"Access token expired for {package_name}, attempting refresh...")
        try:
            tokens = refresh_token(package_name, tokens)
        except RuntimeError as e:
            logger.error(f"Token refresh failed: {e}")
            logger.info(f"Re-authentication required for {package_name}")
            return None

    return tokens.get("access_token")


def is_authenticated(package_name: str) -> bool:
    """
    Check if a package is authenticated.

    Args:
        package_name: Name of the package

    Returns:
        True if tokens exist, False otherwise
    """
    tokens = get_token(package_name)
    return tokens is not None and "access_token" in tokens
