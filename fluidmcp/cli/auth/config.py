"""
OAuth 2.0 (OIDC) configuration models and loading for FluidMCP.

This module handles loading and validating OAuth configuration from .oauth.json files.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any
from loguru import logger


@dataclass
class KeycloakConfig:
    """Keycloak server configuration."""
    server_url: str
    realm: str
    well_known_url: Optional[str] = None

    def __post_init__(self):
        """Construct well_known_url if not provided."""
        if not self.well_known_url:
            # Remove trailing slash from server_url
            base_url = self.server_url.rstrip('/')
            self.well_known_url = f"{base_url}/realms/{self.realm}/.well-known/openid-configuration"


@dataclass
class JWTValidationConfig:
    """JWT token validation configuration."""
    validate_signature: bool = True
    validate_expiry: bool = True
    validate_audience: bool = True
    audience: List[str] = field(default_factory=list)
    required_scopes: List[str] = field(default_factory=list)
    issuer: Optional[str] = None


@dataclass
class CachingConfig:
    """Token and JWKS caching configuration."""
    enable_token_cache: bool = True
    token_cache_ttl_seconds: int = 300  # 5 minutes
    enable_jwks_cache: bool = True
    jwks_cache_ttl_seconds: int = 3600  # 1 hour


@dataclass
class OAuthConfig:
    """Complete OAuth 2.0 (OIDC) configuration."""
    enabled: bool
    provider: str
    keycloak: KeycloakConfig
    jwt_validation: JWTValidationConfig
    caching: CachingConfig
    fallback_to_bearer: bool = True


def load_oauth_config(config_path: Path) -> Optional[OAuthConfig]:
    """
    Load and validate OAuth configuration from file.

    Args:
        config_path: Path to .oauth.json or .keycloak.json file

    Returns:
        OAuthConfig if valid, None if file doesn't exist or is invalid
    """
    if not config_path.exists():
        logger.error(f"OAuth config file not found: {config_path}")
        return None

    try:
        with open(config_path, 'r') as f:
            raw_config = json.load(f)

        # Check if this is a simplified .keycloak.json format
        if "keycloak" in raw_config and "oauth" not in raw_config:
            logger.debug("Detected simplified Keycloak configuration format")
            raw_config = _convert_keycloak_to_oauth_format(raw_config)

        # Validate required top-level structure
        if "oauth" not in raw_config:
            logger.error("Invalid OAuth config: missing 'oauth' section")
            return None

        oauth_section = raw_config["oauth"]

        # Validate required fields
        if not oauth_section.get("enabled", False):
            logger.debug("OAuth is disabled in configuration")
            return None

        if "keycloak" not in oauth_section:
            logger.error("Invalid OAuth config: missing 'keycloak' section")
            return None

        keycloak_data = oauth_section["keycloak"]

        # Validate required Keycloak fields
        if "server_url" not in keycloak_data or "realm" not in keycloak_data:
            logger.error("Invalid OAuth config: missing 'server_url' or 'realm' in keycloak section")
            return None

        # Build KeycloakConfig
        keycloak_config = KeycloakConfig(
            server_url=keycloak_data["server_url"],
            realm=keycloak_data["realm"],
            well_known_url=keycloak_data.get("well_known_url")
        )

        # Build JWTValidationConfig with defaults
        jwt_val_data = oauth_section.get("jwt_validation", {})
        jwt_validation = JWTValidationConfig(
            validate_signature=jwt_val_data.get("validate_signature", True),
            validate_expiry=jwt_val_data.get("validate_expiry", True),
            validate_audience=jwt_val_data.get("validate_audience", True),
            audience=jwt_val_data.get("audience", []),
            required_scopes=jwt_val_data.get("required_scopes", []),
            issuer=jwt_val_data.get("issuer")
        )

        # Validate audience if audience validation is enabled
        if jwt_validation.validate_audience and not jwt_validation.audience:
            logger.error("Invalid OAuth config: 'audience' is required when validate_audience is true")
            return None

        # Build CachingConfig with defaults
        caching_data = oauth_section.get("caching", {})
        caching = CachingConfig(
            enable_token_cache=caching_data.get("enable_token_cache", True),
            token_cache_ttl_seconds=caching_data.get("token_cache_ttl_seconds", 300),
            enable_jwks_cache=caching_data.get("enable_jwks_cache", True),
            jwks_cache_ttl_seconds=caching_data.get("jwks_cache_ttl_seconds", 3600)
        )

        # Build final OAuthConfig
        config = OAuthConfig(
            enabled=True,
            provider=oauth_section.get("provider", "keycloak"),
            keycloak=keycloak_config,
            jwt_validation=jwt_validation,
            caching=caching,
            fallback_to_bearer=oauth_section.get("fallback_to_bearer", True)
        )

        logger.info(f"OAuth configuration loaded successfully from {config_path}")
        logger.debug(f"OAuth Provider: {config.provider}")
        logger.debug(f"Keycloak Server: {config.keycloak.server_url}")
        logger.debug(f"Keycloak Realm: {config.keycloak.realm}")
        logger.debug(f"Audience: {config.jwt_validation.audience}")
        logger.debug(f"Required Scopes: {config.jwt_validation.required_scopes}")
        logger.debug(f"Fallback to Bearer: {config.fallback_to_bearer}")

        return config

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OAuth configuration: {e}")
        return None
    except Exception as e:
        logger.exception(f"Error loading OAuth configuration: {e}")
        return None


def _convert_keycloak_to_oauth_format(keycloak_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert simplified .keycloak.json format to full .oauth.json format.

    Args:
        keycloak_config: Simplified Keycloak configuration

    Returns:
        Full OAuth configuration format
    """
    kc = keycloak_config["keycloak"]

    oauth_format = {
        "oauth": {
            "enabled": True,
            "provider": "keycloak",
            "keycloak": {
                "server_url": kc["server_url"],
                "realm": kc["realm"]
            },
            "jwt_validation": {
                "audience": kc.get("audience", [])
            },
            "fallback_to_bearer": kc.get("fallback_to_bearer", True)
        }
    }

    # Add optional fields if present
    if "well_known_url" in kc:
        oauth_format["oauth"]["keycloak"]["well_known_url"] = kc["well_known_url"]

    if "required_scopes" in kc:
        oauth_format["oauth"]["jwt_validation"]["required_scopes"] = kc["required_scopes"]

    if "issuer" in kc:
        oauth_format["oauth"]["jwt_validation"]["issuer"] = kc["issuer"]

    return oauth_format


def find_oauth_config(main_config_path: Optional[Path] = None) -> Optional[Path]:
    """
    Auto-discover OAuth configuration file.

    Search order:
    1. Environment variable FMCP_OAUTH_CONFIG
    2. Same directory as main config (.oauth.json or .keycloak.json)
    3. ~/.fmcp/.oauth.json
    4. ./.oauth.json

    Args:
        main_config_path: Path to main configuration file (optional)

    Returns:
        Path to OAuth config if found, None otherwise
    """
    # Check environment variable
    env_path = os.environ.get("FMCP_OAUTH_CONFIG")
    if env_path:
        path = Path(env_path)
        if path.exists():
            logger.debug(f"Found OAuth config via FMCP_OAUTH_CONFIG: {path}")
            return path
        else:
            logger.warning(f"FMCP_OAUTH_CONFIG points to non-existent file: {path}")

    # Check same directory as main config
    if main_config_path:
        parent_dir = main_config_path.parent
        for name in [".oauth.json", ".keycloak.json", "oauth.json", "keycloak.json"]:
            path = parent_dir / name
            if path.exists():
                logger.debug(f"Found OAuth config next to main config: {path}")
                return path

    # Check standard locations
    home_path = Path.home() / ".fmcp" / ".oauth.json"
    if home_path.exists():
        logger.debug(f"Found OAuth config in home directory: {home_path}")
        return home_path

    local_path = Path(".fmcp") / ".oauth.json"
    if local_path.exists():
        logger.debug(f"Found OAuth config in local directory: {local_path}")
        return local_path

    logger.debug("No OAuth configuration file found")
    return None


def validate_oauth_config(config_path: Path) -> bool:
    """
    Validate OAuth configuration file without loading full config.

    Args:
        config_path: Path to OAuth configuration file

    Returns:
        True if configuration is valid, False otherwise
    """
    try:
        config = load_oauth_config(config_path)
        return config is not None
    except Exception as e:
        logger.error(f"OAuth configuration validation failed: {e}")
        return False
