"""
Auth0 OAuth client wrapper.

This module provides a simple interface for Auth0 OAuth operations.
"""

import requests
from typing import Dict, Optional
from urllib.parse import urlencode
from .config import Auth0Config


class Auth0Client:
    """Wrapper for Auth0 OAuth operations"""

    def __init__(self, config: Auth0Config):
        self.config = config
        self.base_url = f"https://{config.domain}"

    def get_authorization_url(self, state: str, redirect_uri: str, connection: Optional[str] = None) -> str:
        """
        Generate Auth0 authorization URL for user login.

        Args:
            state: CSRF protection state token
            redirect_uri: Callback URL after authentication
            connection: Optional provider connection (e.g., 'google-oauth2', 'github', 'zoho', 'atlassian', 'waad')

        Returns:
            Auth0 authorization URL
        """
        params = {
            'response_type': 'code',
            'client_id': self.config.client_id,
            'redirect_uri': redirect_uri,
            'scope': 'openid profile email',
            'state': state,
        }

        if self.config.audience:
            params['audience'] = self.config.audience

        # Add connection parameter for direct provider login
        if connection:
            params['connection'] = connection

        query_string = urlencode(params)
        return f"{self.base_url}/authorize?{query_string}"

    def exchange_code_for_tokens(self, code: str, redirect_uri: str) -> Dict:
        """Exchange authorization code for access and ID tokens"""
        token_url = f"{self.base_url}/oauth/token"

        payload = {
            'grant_type': 'authorization_code',
            'client_id': self.config.client_id,
            'client_secret': self.config.client_secret,
            'code': code,
            'redirect_uri': redirect_uri,
        }

        response = requests.post(token_url, json=payload, timeout=10)
        response.raise_for_status()

        return response.json()

    def get_user_info(self, access_token: str) -> Dict:
        """Fetch user profile from Auth0"""
        userinfo_url = f"{self.base_url}/userinfo"

        headers = {
            'Authorization': f'Bearer {access_token}'
        }

        response = requests.get(userinfo_url, headers=headers, timeout=10)
        response.raise_for_status()

        return response.json()

    def logout_url(self, return_to: str) -> str:
        """Generate Auth0 logout URL"""
        params = {
            'client_id': self.config.client_id,
            'returnTo': return_to,
        }

        query_string = urlencode(params)
        return f"{self.base_url}/v2/logout?{query_string}"
