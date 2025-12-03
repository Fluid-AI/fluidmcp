"""
OAuth2 PKCE (Proof Key for Code Exchange) implementation for FluidMCP.

This module provides OAuth2 authentication using the PKCE flow, designed for securing
the FastAPI gateway endpoints. It supports both automatic browser-based authentication
and manual token management.
"""

import os
import json
import hashlib
import base64
import secrets
import webbrowser
import time
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from urllib.parse import urlencode, parse_qs, urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

from loguru import logger
import requests


# Token storage location
TOKEN_STORAGE_DIR = Path.home() / ".fluidmcp" / "oauth"
TOKEN_FILE = TOKEN_STORAGE_DIR / "tokens.json"

# Default OAuth2 configuration (can be overridden via environment variables)
DEFAULT_OAUTH_CONFIG = {
    "authorization_endpoint": os.environ.get("FMCP_OAUTH_AUTH_ENDPOINT", ""),
    "token_endpoint": os.environ.get("FMCP_OAUTH_TOKEN_ENDPOINT", ""),
    "client_id": os.environ.get("FMCP_OAUTH_CLIENT_ID", ""),
    "redirect_uri": os.environ.get("FMCP_OAUTH_REDIRECT_URI", "http://localhost:8088/callback"),
    "scope": os.environ.get("FMCP_OAUTH_SCOPE", "openid profile email"),
}


class PKCEGenerator:
    """Generate PKCE code verifier and challenge."""

    @staticmethod
    def generate_code_verifier() -> str:
        """Generate a cryptographically random code verifier (43-128 characters)."""
        return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')

    @staticmethod
    def generate_code_challenge(verifier: str) -> str:
        """Generate code challenge from verifier using SHA256."""
        digest = hashlib.sha256(verifier.encode('utf-8')).digest()
        return base64.urlsafe_b64encode(digest).decode('utf-8').rstrip('=')


class TokenStorage:
    """Manage OAuth2 token storage and retrieval."""

    @staticmethod
    def ensure_storage_dir():
        """Ensure the token storage directory exists."""
        TOKEN_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def save_tokens(tokens: Dict[str, Any]):
        """Save tokens to disk."""
        TokenStorage.ensure_storage_dir()
        with open(TOKEN_FILE, 'w') as f:
            json.dump(tokens, f, indent=2)
        # Set restrictive permissions (owner read/write only)
        TOKEN_FILE.chmod(0o600)
        logger.info(f"Tokens saved to {TOKEN_FILE}")

    @staticmethod
    def load_tokens() -> Optional[Dict[str, Any]]:
        """Load tokens from disk."""
        if not TOKEN_FILE.exists():
            return None
        try:
            with open(TOKEN_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading tokens: {e}")
            return None

    @staticmethod
    def delete_tokens():
        """Delete stored tokens."""
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
            logger.info("Tokens deleted")

    @staticmethod
    def is_token_expired(tokens: Dict[str, Any]) -> bool:
        """Check if the access token is expired."""
        if not tokens or 'expires_at' not in tokens:
            return True
        expires_at = datetime.fromisoformat(tokens['expires_at'])
        # Consider token expired 5 minutes before actual expiration
        return datetime.now() >= (expires_at - timedelta(minutes=5))


class CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback."""

    auth_code = None
    error = None

    def do_GET(self):
        """Handle GET request to callback endpoint."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if 'code' in params:
            CallbackHandler.auth_code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"""
                <html>
                <body>
                    <h1>Authentication Successful!</h1>
                    <p>You can close this window and return to the terminal.</p>
                </body>
                </html>
            """)
        elif 'error' in params:
            CallbackHandler.error = params['error'][0]
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(f"""
                <html>
                <body>
                    <h1>Authentication Failed</h1>
                    <p>Error: {CallbackHandler.error}</p>
                </body>
                </html>
            """.encode())

        # Signal the server to stop
        threading.Thread(target=self.server.shutdown).start()

    def log_message(self, format, *args):
        """Suppress server logs."""
        pass


class OAuth2PKCEClient:
    """OAuth2 PKCE client for authentication."""

    def __init__(self, config: Optional[Dict[str, str]] = None):
        """Initialize OAuth2 client with configuration."""
        self.config = config or DEFAULT_OAUTH_CONFIG
        self.validate_config()

    def validate_config(self):
        """Validate OAuth2 configuration."""
        required_fields = ['authorization_endpoint', 'token_endpoint', 'client_id']
        missing = [f for f in required_fields if not self.config.get(f)]
        if missing:
            raise ValueError(f"Missing OAuth2 configuration: {', '.join(missing)}")

    def start_authorization_flow(self) -> Dict[str, Any]:
        """
        Start the OAuth2 PKCE authorization flow.
        Opens browser for user authentication and waits for callback.
        Returns the tokens received from the token endpoint.
        """
        # Generate PKCE parameters
        code_verifier = PKCEGenerator.generate_code_verifier()
        code_challenge = PKCEGenerator.generate_code_challenge(code_verifier)
        state = secrets.token_urlsafe(16)

        # Build authorization URL
        auth_params = {
            'response_type': 'code',
            'client_id': self.config['client_id'],
            'redirect_uri': self.config['redirect_uri'],
            'scope': self.config['scope'],
            'state': state,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
        }
        auth_url = f"{self.config['authorization_endpoint']}?{urlencode(auth_params)}"

        logger.info("Starting OAuth2 authorization flow...")
        print(f"\nOpening browser for authentication...")
        print(f"If the browser doesn't open, visit this URL:\n{auth_url}\n")

        # Start local callback server
        redirect_port = int(urlparse(self.config['redirect_uri']).port or 8088)
        server = HTTPServer(('localhost', redirect_port), CallbackHandler)

        # Open browser
        webbrowser.open(auth_url)

        # Wait for callback (with timeout)
        logger.info(f"Waiting for callback on port {redirect_port}...")
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()

        # Wait for auth code (max 5 minutes)
        timeout = 300
        start_time = time.time()
        while CallbackHandler.auth_code is None and CallbackHandler.error is None:
            if time.time() - start_time > timeout:
                raise TimeoutError("Authentication timeout - no response received")
            time.sleep(0.5)

        if CallbackHandler.error:
            raise Exception(f"Authentication failed: {CallbackHandler.error}")

        auth_code = CallbackHandler.auth_code
        CallbackHandler.auth_code = None  # Reset for next use

        # Exchange code for tokens
        return self.exchange_code_for_tokens(auth_code, code_verifier)

    def exchange_code_for_tokens(self, auth_code: str, code_verifier: str) -> Dict[str, Any]:
        """Exchange authorization code for tokens."""
        token_data = {
            'grant_type': 'authorization_code',
            'code': auth_code,
            'redirect_uri': self.config['redirect_uri'],
            'client_id': self.config['client_id'],
            'code_verifier': code_verifier,
        }

        logger.info("Exchanging authorization code for tokens...")
        response = requests.post(
            self.config['token_endpoint'],
            data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )

        if response.status_code != 200:
            raise Exception(f"Token exchange failed: {response.text}")

        tokens = response.json()

        # Add expiration timestamp
        if 'expires_in' in tokens:
            expires_at = datetime.now() + timedelta(seconds=tokens['expires_in'])
            tokens['expires_at'] = expires_at.isoformat()

        logger.info("Successfully obtained tokens")
        return tokens

    def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh the access token using refresh token."""
        token_data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': self.config['client_id'],
        }

        logger.info("Refreshing access token...")
        response = requests.post(
            self.config['token_endpoint'],
            data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )

        if response.status_code != 200:
            raise Exception(f"Token refresh failed: {response.text}")

        tokens = response.json()

        # Add expiration timestamp
        if 'expires_in' in tokens:
            expires_at = datetime.now() + timedelta(seconds=tokens['expires_in'])
            tokens['expires_at'] = expires_at.isoformat()

        logger.info("Successfully refreshed tokens")
        return tokens


class OAuth2TokenManager:
    """Manage OAuth2 tokens with automatic refresh."""

    def __init__(self, config: Optional[Dict[str, str]] = None):
        """Initialize token manager."""
        self.client = OAuth2PKCEClient(config)

    def get_valid_access_token(self) -> Optional[str]:
        """
        Get a valid access token.
        Attempts to load from storage, refresh if expired, or return None.
        Does not trigger new authentication flow.
        """
        # Check for manual token in environment
        manual_token = os.environ.get("FMCP_OAUTH_ACCESS_TOKEN")
        if manual_token:
            logger.info("Using access token from environment variable")
            return manual_token

        # Load stored tokens
        tokens = TokenStorage.load_tokens()
        if not tokens:
            logger.warning("No stored tokens found")
            return None

        # Check if expired
        if not TokenStorage.is_token_expired(tokens):
            return tokens.get('access_token')

        # Try to refresh
        if 'refresh_token' in tokens:
            try:
                new_tokens = self.client.refresh_access_token(tokens['refresh_token'])
                # Preserve refresh_token if not included in response
                if 'refresh_token' not in new_tokens and 'refresh_token' in tokens:
                    new_tokens['refresh_token'] = tokens['refresh_token']
                TokenStorage.save_tokens(new_tokens)
                return new_tokens.get('access_token')
            except Exception as e:
                logger.error(f"Token refresh failed: {e}")
                return None

        logger.warning("Token expired and no refresh token available")
        return None

    def login(self) -> str:
        """
        Perform OAuth2 login flow.
        Returns the access token.
        """
        tokens = self.client.start_authorization_flow()
        TokenStorage.save_tokens(tokens)
        return tokens['access_token']

    def logout(self):
        """Logout and delete stored tokens."""
        TokenStorage.delete_tokens()
        logger.info("Logged out successfully")


def verify_oauth_token(token: str) -> bool:
    """
    Verify an OAuth2 access token.

    This is a placeholder - in production, you should:
    1. Validate the token signature (for JWT tokens)
    2. Check token expiration
    3. Optionally call the OAuth provider's introspection endpoint

    Args:
        token: The access token to verify

    Returns:
        True if token is valid, False otherwise
    """
    # For now, just check if token exists and is not empty
    # In production, implement proper token validation
    if not token or len(token) < 10:
        return False

    # If using JWT, decode and verify here
    # If using opaque tokens, call introspection endpoint

    return True
