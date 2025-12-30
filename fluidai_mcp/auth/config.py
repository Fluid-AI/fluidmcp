"""
Auth0 configuration management.

This module handles loading and validation of Auth0 configuration
from environment variables.
"""

import os
from typing import Optional
from pydantic import BaseModel, Field


class Auth0Config(BaseModel):
    """Auth0 configuration from environment variables"""
    domain: Optional[str] = Field(default=None)
    client_id: Optional[str] = Field(default=None)
    client_secret: Optional[str] = Field(default=None)
    callback_url: str = Field(default='http://localhost:8099/auth/callback')
    audience: Optional[str] = Field(default=None)

    # JWT settings
    jwt_secret: Optional[str] = Field(default=None)
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 30

    class Config:
        # Allow extra fields for pydantic v2 compatibility
        extra = 'allow'

    @classmethod
    def from_env(cls) -> 'Auth0Config':
        """Load configuration from environment variables"""
        return cls(
            domain=os.getenv('AUTH0_DOMAIN'),
            client_id=os.getenv('AUTH0_CLIENT_ID'),
            client_secret=os.getenv('AUTH0_CLIENT_SECRET'),
            callback_url=os.getenv('AUTH0_CALLBACK_URL', 'http://localhost:8099/auth/callback'),
            audience=os.getenv('AUTH0_AUDIENCE'),
            jwt_secret=os.getenv('FMCP_JWT_SECRET')
        )

    def validate_required(self) -> None:
        """Ensure all required fields are present"""
        if not self.domain:
            raise ValueError("AUTH0_DOMAIN environment variable is required")
        if not self.client_id:
            raise ValueError("AUTH0_CLIENT_ID environment variable is required")
        if not self.client_secret:
            raise ValueError("AUTH0_CLIENT_SECRET environment variable is required")
        if not self.jwt_secret:
            raise ValueError("FMCP_JWT_SECRET environment variable is required")
