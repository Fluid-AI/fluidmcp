"""
Token storage service for OAuth authentication.

Provides secure storage using system keyring with fallback to encrypted local file.
"""

import os
import json
import keyring
from pathlib import Path
from typing import Optional, Dict
from loguru import logger

FALLBACK_DIR = Path.home() / ".fluidmcp"
FALLBACK_FILE = FALLBACK_DIR / "tokens.json"


def _load_fallback() -> Dict:
    """Load tokens from fallback JSON file."""
    if not FALLBACK_FILE.exists():
        return {}
    try:
        return json.loads(FALLBACK_FILE.read_text())
    except Exception as e:
        logger.warning(f"Failed to load fallback tokens: {e}")
        return {}


def _save_fallback(data: Dict):
    """Save tokens to fallback JSON file with restricted permissions."""
    FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    FALLBACK_FILE.write_text(json.dumps(data, indent=2))
    os.chmod(FALLBACK_FILE, 0o600)
    logger.info(f"Saved tokens to fallback file: {FALLBACK_FILE}")


def save_token(package_name: str, token_data: Dict):
    """
    Save OAuth tokens for a package.

    Tries to use system keyring first, falls back to local file if unavailable.

    Args:
        package_name: Name of the package (e.g., "gmail", "jira")
        token_data: Dictionary containing tokens (access_token, refresh_token, etc.)
    """
    data_str = json.dumps(token_data)
    service_name = f"fluidmcp-{package_name}"

    try:
        keyring.set_password("fluidmcp", service_name, data_str)
        logger.info(f"Saved tokens for {package_name} in system keyring")
    except Exception as e:
        logger.warning(f"Keyring unavailable ({e}), using file fallback")
        current = _load_fallback()
        current[package_name] = token_data
        _save_fallback(current)


def get_token(package_name: str) -> Optional[Dict]:
    """
    Retrieve OAuth tokens for a package.

    Tries system keyring first, falls back to local file.

    Args:
        package_name: Name of the package

    Returns:
        Dictionary containing tokens or None if not found
    """
    service_name = f"fluidmcp-{package_name}"

    # Try keyring first
    try:
        data_str = keyring.get_password("fluidmcp", service_name)
        if data_str:
            logger.debug(f"Retrieved tokens for {package_name} from keyring")
            return json.loads(data_str)
    except Exception as e:
        logger.debug(f"Could not retrieve from keyring: {e}")

    # Fallback to file
    tokens = _load_fallback().get(package_name)
    if tokens:
        logger.debug(f"Retrieved tokens for {package_name} from fallback file")
    return tokens


def delete_token(package_name: str):
    """
    Delete OAuth tokens for a package.

    Removes from both keyring and fallback file.

    Args:
        package_name: Name of the package
    """
    service_name = f"fluidmcp-{package_name}"

    # Try to delete from keyring
    try:
        keyring.delete_password("fluidmcp", service_name)
        logger.info(f"Deleted tokens for {package_name} from keyring")
    except Exception:
        pass

    # Delete from fallback file
    current = _load_fallback()
    if package_name in current:
        del current[package_name]
        _save_fallback(current)
        logger.info(f"Deleted tokens for {package_name} from fallback file")
