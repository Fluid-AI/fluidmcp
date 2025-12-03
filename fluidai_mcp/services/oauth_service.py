"""
OAuth 2.0 stateless helper service for gateway-based authentication.

This module provides stateless functions for OAuth 2.0 PKCE flow.
No local storage - tokens are returned to the client to manage.
"""

import hashlib
import secrets
import base64
import os
import requests
from urllib.parse import urlencode
from typing import Dict, Tuple
from loguru import logger


def generate_pkce_pair() -> Tuple[str, str]:
    """
    Generate PKCE code verifier and challenge pair.

    Returns:
        Tuple of (verifier, challenge)
    """
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode('utf-8')).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode('utf-8')
    return verifier, challenge


def build_authorization_url(
    auth_config: Dict,
    redirect_uri: str,
    state: str,
    code_challenge: str
) -> str:
    """
    Build OAuth 2.0 authorization URL with PKCE.

    Args:
        auth_config: OAuth configuration from package metadata
        redirect_uri: Callback URL for this package
        state: Random state string for CSRF protection
        code_challenge: PKCE code challenge

    Returns:
        Complete authorization URL

    Raises:
        RuntimeError: If client_id cannot be resolved
    """
    # Resolve client_id from config or environment
    client_id = auth_config.get("client_id")
    if not client_id and auth_config.get("client_id_env"):
        client_id = os.environ.get(auth_config.get("client_id_env"))

    if not client_id:
        raise RuntimeError(
            f"client_id not found. Set {auth_config.get('client_id_env', 'client_id')} "
            "in environment or auth config"
        )

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        "scope": " ".join(auth_config.get("scopes", [])),
        "access_type": "offline",
        "prompt": "consent"
    }

    authorization_url = auth_config.get("authorization_url")
    if not authorization_url:
        raise RuntimeError("authorization_url not found in auth config")

    return f"{authorization_url}?{urlencode(params)}"


def exchange_code_for_token(
    code: str,
    verifier: str,
    redirect_uri: str,
    auth_config: Dict
) -> Dict:
    """
    Exchange authorization code for access token.

    Args:
        code: Authorization code from OAuth provider
        verifier: PKCE code verifier
        redirect_uri: Same redirect URI used in authorization
        auth_config: OAuth configuration from package metadata

    Returns:
        Token response dictionary containing:
            - access_token: The OAuth access token
            - refresh_token: Optional refresh token
            - expires_in: Token expiration time in seconds
            - token_type: Usually "Bearer"

    Raises:
        RuntimeError: If token exchange fails
    """
    # Resolve client_id
    client_id = auth_config.get("client_id")
    if not client_id and auth_config.get("client_id_env"):
        client_id = os.environ.get(auth_config.get("client_id_env"))

    if not client_id:
        raise RuntimeError(
            f"client_id not found. Set {auth_config.get('client_id_env', 'client_id')} "
            "in environment or auth config"
        )

    token_url = auth_config.get("token_url")
    if not token_url:
        raise RuntimeError("token_url not found in auth config")

    # Build token request
    token_data = {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
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
        logger.info(f"Exchanging authorization code for token at {token_url}")
        response = requests.post(token_url, data=token_data, timeout=30)
        response.raise_for_status()
        tokens = response.json()
        logger.info("Successfully exchanged code for access token")
        return tokens
    except requests.exceptions.RequestException as e:
        logger.error(f"Token exchange failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response: {e.response.text}")
        raise RuntimeError(f"Failed to exchange authorization code: {e}")


def get_env_var(env_var_name: str) -> str:
    """
    Get environment variable value.

    Args:
        env_var_name: Name of the environment variable

    Returns:
        Environment variable value

    Raises:
        RuntimeError: If environment variable is not set
    """
    value = os.environ.get(env_var_name)
    if not value:
        raise RuntimeError(f"Environment variable {env_var_name} is not set")
    return value
