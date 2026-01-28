"""
Auth0 configuration management.

This module handles loading and validation of Auth0 configuration
from environment variables or JSON configuration file.
"""

import os
import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from .url_utils import get_callback_url


class Auth0Config(BaseModel):
    """Auth0 configuration from environment variables"""
    domain: Optional[str] = Field(default=None)
    client_id: Optional[str] = Field(default=None)
    client_secret: Optional[str] = Field(default=None)
    callback_url: Optional[str] = Field(default=None)  # Will be dynamically set if None
    audience: Optional[str] = Field(default=None)

    # JWT settings
    jwt_secret: Optional[str] = Field(default=None)
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60  # 1 hour

    # Port for URL generation
    port: int = Field(default=8099)

    class Config:
        # Allow extra fields for pydantic v2 compatibility
        extra = 'allow'

    @classmethod
    def from_env(cls, port: int = 8099) -> 'Auth0Config':
        """
        Load configuration from environment variables.

        Args:
            port: Port number for dynamic URL generation
        """
        # Get callback URL - use env var if set, otherwise will be dynamically generated
        callback_url = os.getenv('FMCP_AUTH0_CALLBACK_URL')
        if not callback_url:
            callback_url = get_callback_url(port)

        return cls(
            domain=os.getenv('FMCP_AUTH0_DOMAIN'),
            client_id=os.getenv('FMCP_AUTH0_CLIENT_ID'),
            client_secret=os.getenv('FMCP_AUTH0_CLIENT_SECRET'),
            callback_url=callback_url,
            audience=os.getenv('FMCP_AUTH0_AUDIENCE'),
            jwt_secret=os.getenv('FMCP_JWT_SECRET'),
            port=port
        )

    @classmethod
    def from_file(cls, file_path: str) -> 'Auth0Config':
        """
        Load configuration from JSON file.

        Args:
            file_path: Path to auth0-config.json file

        Returns:
            Auth0Config instance

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config file is invalid JSON
        """
        config_path = Path(file_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Auth0 config file not found: {file_path}")

        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file {file_path}: {e}")

        return cls(**config_data)

    @classmethod
    def from_env_or_file(cls, file_path: Optional[str] = None, port: int = 8099) -> 'Auth0Config':
        """
        Load configuration with priority: env vars > file > defaults.

        Priority order:
        1. Environment variables (highest priority)
        2. Specified file path (--auth0-config flag)
        3. Default file path (./auth0-config.json)
        4. Dynamic URL detection (for remote environments)
        5. Default values (fallback)

        Args:
            file_path: Optional path to config file. If not provided, looks for
                      './auth0-config.json' in current directory.
            port: Port number for dynamic URL generation

        Returns:
            Auth0Config instance with merged configuration
        """
        # Start with defaults
        config_data = {
            'jwt_algorithm': 'HS256',
            'jwt_expiration_minutes': 60,  # 1 hour
            'port': port
        }

        # Try to load from file
        if file_path is None:
            # Check default location
            file_path = 'auth0-config.json'

        if Path(file_path).exists():
            try:
                with open(file_path, 'r') as f:
                    file_data = json.load(f)
                    config_data.update(file_data)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load {file_path}: {e}")

        # Environment variables override file config (updated to use FMCP_ prefix)
        env_overrides = {}
        if os.getenv('FMCP_AUTH0_DOMAIN'):
            env_overrides['domain'] = os.getenv('FMCP_AUTH0_DOMAIN')
        if os.getenv('FMCP_AUTH0_CLIENT_ID'):
            env_overrides['client_id'] = os.getenv('FMCP_AUTH0_CLIENT_ID')
        if os.getenv('FMCP_AUTH0_CLIENT_SECRET'):
            env_overrides['client_secret'] = os.getenv('FMCP_AUTH0_CLIENT_SECRET')
        if os.getenv('FMCP_AUTH0_CALLBACK_URL'):
            env_overrides['callback_url'] = os.getenv('FMCP_AUTH0_CALLBACK_URL')
        if os.getenv('FMCP_AUTH0_AUDIENCE'):
            env_overrides['audience'] = os.getenv('FMCP_AUTH0_AUDIENCE')
        if os.getenv('FMCP_JWT_SECRET'):
            env_overrides['jwt_secret'] = os.getenv('FMCP_JWT_SECRET')

        config_data.update(env_overrides)

        # If callback_url is still not set, generate it dynamically
        if 'callback_url' not in config_data or not config_data['callback_url']:
            config_data['callback_url'] = get_callback_url(port)

        return cls(**config_data)

    def validate_required(self) -> None:
        """Ensure all required fields are present"""
        missing_fields = []

        if not self.domain:
            missing_fields.append("domain (FMCP_AUTH0_DOMAIN or auth0-config.json)")
        if not self.client_id:
            missing_fields.append("client_id (FMCP_AUTH0_CLIENT_ID or auth0-config.json)")
        if not self.client_secret:
            missing_fields.append("client_secret (FMCP_AUTH0_CLIENT_SECRET or auth0-config.json)")
        if not self.jwt_secret:
            missing_fields.append("jwt_secret (FMCP_JWT_SECRET or auth0-config.json)")

        if missing_fields:
            raise ValueError(
                f"Missing required Auth0 configuration fields: {', '.join(missing_fields)}\n"
                "Either set environment variables or create auth0-config.json file.\n"
                "Run 'python setup-auth0-config.py' to create config file interactively."
            )
