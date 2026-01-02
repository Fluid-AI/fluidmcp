"""
JWT token manager for Auth0 integration.

This module handles creation and validation of custom JWT tokens
after successful Auth0 authentication.
"""

from datetime import datetime, timedelta
from typing import Dict, Optional
from jose import jwt, JWTError
from .config import Auth0Config


class TokenManager:
    """Manage custom JWT tokens for API access"""

    def __init__(self, config: Auth0Config):
        self.config = config

    def create_access_token(self, user_data: Dict) -> str:
        """Create JWT access token from Auth0 user data"""
        now = datetime.utcnow()
        expires = now + timedelta(minutes=self.config.jwt_expiration_minutes)

        payload = {
            'sub': user_data.get('sub'),  # Auth0 user ID
            'email': user_data.get('email'),
            'name': user_data.get('name'),
            'picture': user_data.get('picture'),
            'provider': self._extract_provider(user_data.get('sub')),
            'exp': expires,
            'iat': now,
            'type': 'access'
        }

        return jwt.encode(payload, self.config.jwt_secret, algorithm=self.config.jwt_algorithm)

    def verify_token(self, token: str) -> Optional[Dict]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(
                token,
                self.config.jwt_secret,
                algorithms=[self.config.jwt_algorithm]
            )

            if payload.get('type') != 'access':
                return None

            return payload

        except JWTError:
            return None

    def _extract_provider(self, sub: str) -> str:
        """Extract provider from Auth0 subject (e.g., 'google-oauth2|123' -> 'Google')"""
        if not sub:
            return 'unknown'

        parts = sub.split('|')
        if len(parts) > 1:
            provider = parts[0]
            # Map Auth0 provider names to friendly names
            mapping = {
                'google-oauth2': 'Google',
                'github': 'GitHub',
                'auth0': 'Auth0',
                'samlp': 'SAML (Zoho/Atlassian/Confluence)',
                'waad': 'Azure AD',
                'adfs': 'ADFS',
            }
            return mapping.get(provider, provider.capitalize())

        return 'unknown'
