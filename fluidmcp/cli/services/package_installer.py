import os
import re
import json
import shutil
import tarfile
import requests
from typing import Dict, Any
from pathlib import Path
from loguru import logger
from io import BytesIO
from .env_manager import write_keys_during_install
from .package_list import get_latest_version_dir

# Environment variables for configuration
API_URL = os.getenv("MCP_FETCH_URL", "https://registry.fluidmcp.com/fetch-mcp-package")
AUTH_TOKEN = os.getenv("MCP_TOKEN")
INSTALL_BASE = os.environ.get("MCP_INSTALLATION_DIR", Path.cwd() / ".fmcp-packages")
proxy_port = int(os.environ.get("MCP_FASTAPI_PORT", "8080"))

def parse_package_string(package_str) -> dict:
    """Parse a package string into its component parts.

    Supported formats:
        "author/name@version" → Full specification
        "author/name" → Defaults version to 'latest'
        "name@version" → Defaults author to 'default'
        "name" → Defaults both to 'default' and 'latest'

    Regex Pattern:
        (?:(?P<author>[^/]+)/)?(?P<name>[^@]+)(?:@(?P<version>.+))?
        - (?:(?P<author>[^/]+)/)? : Optional author followed by '/'
        - (?P<name>[^@]+) : Required package name (anything except '@')
        - (?:@(?P<version>.+))? : Optional '@version'

    Args:
        package_str (str): Package string to parse.

    Returns:
        dict: Dictionary with keys 'author', 'package_name', 'version'.

    Raises:
        ValueError: If package_str doesn't match the expected format.

    Example:
        >>> parse_package_string("fluidai/filesystem@1.0.0")
        {'author': 'fluidai', 'package_name': 'filesystem', 'version': '1.0.0'}
    """
    # Regular expression to match the package string format
    pattern = r'(?:(?P<author>[^/]+)/)?(?P<name>[^@]+)(?:@(?P<version>.+))?'
    match = re.match(pattern, package_str)
    # Check if the package string matches the expected format
    if not match:
        # Raise an error if the package string does not match the expected format
        raise ValueError(f"Invalid package format: {package_str}")
    # Return a dictionary containing the author, name, and version
    return {
        'author': match.group('author') or 'default',
        'package_name': match.group('name'),
        'version': match.group('version') or 'latest'
    }

def is_tar_gz(data: bytes) -> bool:
    """Check if the data is a tar.gz file.

    Args:
        data (bytes): Raw file bytes to check.

    Returns:
        bool: True if the data is a tar.gz file, False otherwise.
    """
    return data[:2] == b'\x1f\x8b'  # GZIP magic number

def is_json(data: bytes) -> bool:
    """Check if the data is a JSON file.

    Args:
        data (bytes): Raw file bytes to check.

    Returns:
        bool: True if the data is a JSON file, False otherwise.
    """
    return data.lstrip().startswith(b'{')  # JSON starts with {

def install_package(package_str, skip_env=False):
    """Install an MCP package from the Fluid MCP registry.

    Installation Flow:
        1. Parse package string and build registry request
        2. Fetch package metadata and pre-signed S3 URL from registry
        3. Download package content from S3
        4. Detect file type (tar.gz or JSON metadata)
        5. Extract/save to installation directory
        6. Prompt for environment variables (unless skip_env=True)

    Args:
        package_str (str): The package string to install (e.g., "author/package@version").
        skip_env (bool): If True, skip prompting for environment variables during installation.
                         Used in master mode or batch installations.

    Returns:
        None

    Raises:
        Exception: If an unknown file type is received from S3.

    Note:
        Most errors are logged and handled gracefully with early returns rather than exceptions.
    """
    
    # Form the headers and payload for the API request
    headers,payload ,pkg =make_registry_request(package_str,auth=False)
    
    try:
        logger.info("Installing package from Fluid MCP registry")
        try:
            # Make the API request to fetch the package
            response = requests.post(API_URL, headers=headers, json=payload)
            response.raise_for_status()
        except requests.RequestException:
            logger.exception("Error fetching package from MCP registry")
            return

        logger.info("Downloading packages")
        # Check if the response contains a valid pre-signed URL
        try:
            # Extract the pre-signed URL from the response
            s3_url = response.json().get("pre_signed_url")
            logger.debug(f"S3 URL: {s3_url[:100]}...")
            # Download file from S3
            s3_response = requests.get(s3_url)
            s3_response.raise_for_status()
            s3_content = s3_response.content
        except requests.RequestException:
            logger.exception("Error downloading package from S3")
            return
     
        # Form the destination directory path
        dest_dir = INSTALL_BASE / pkg["author"] / pkg["package_name"] / pkg["version"]
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Detect file type
        if is_tar_gz(s3_content):
            logger.info("Extracting tar.gz contents")
            with tarfile.open(fileobj=BytesIO(s3_content), mode="r:gz") as tar:
                 tar.extractall(path=dest_dir)
            logger.debug(f"Extracted to {dest_dir}")
        elif is_json(s3_content):
            logger.info("Saving metadata.json")
            metadata_path = dest_dir / "metadata.json"
            with open(metadata_path, "wb") as f:
                f.write(s3_content)
            logger.debug(f"Saved metadata to {metadata_path}")
        else:
            raise Exception("Unknown file type received from S3")

        try:
            write_keys_during_install(dest_dir, pkg, skip_env=skip_env)
        except Exception:
            logger.exception("Error writing keys during installation")
            return

        logger.info("Installation completed successfully")
    except Exception:
        # Handle any errors that occur during the installation process
        logger.exception("Installation failed")

def package_exists(dest_dir: Path) -> bool:
    """Check if the package destination directory exists.

    Args:
        dest_dir (Path): The path to the destination directory.

    Returns:
        bool: True if the directory exists, False otherwise.
    """
    return dest_dir.exists()

def install_package_from_file(package: str, INSTALLATION_DIR: str, pkg: Dict[str, Any]) -> str:
    """Install a package listed in a configuration file.

    This is a helper function used when installing packages from a config file
    or master configuration. It calls install_package() with skip_env=True and
    then locates the installed package directory.

    Args:
        package (str): The package string to install.
        INSTALLATION_DIR (str): The installation directory base path.
        pkg (Dict[str, Any]): The package metadata dictionary with 'author', 'package_name', 'version'.

    Returns:
        str: Path to the installed package directory.

    Raises:
        FileNotFoundError: If the package cannot be located after installation.

    Note:
        May return with dest_dir undefined if FileNotFoundError is caught and logged.
    """
    logger.info(f"Installing package: {package}")
    install_package(package, skip_env=True)
    # Find installed package directory
    author, package_name = pkg["author"], pkg["package_name"]
    version = pkg.get("version")
    if version:
        dest_dir = Path(INSTALLATION_DIR) / author / package_name / version
    else:
        package_dir = Path(INSTALLATION_DIR) / author / package_name
        try:
            dest_dir = get_latest_version_dir(package_dir)
        except FileNotFoundError:
            logger.error(f"Package not found: {author}/{package_name}")
    return dest_dir
    

def make_registry_request(package_str: str, auth: bool) -> tuple:
    """Build HTTP headers, payload, and package metadata for registry API request.

    This function prepares the data needed to interact with the FluidMCP registry API.
    It parses the package string, constructs the JSON payload, and optionally adds
    authentication headers.

    Registry API Interaction:
        - Endpoint: MCP_FETCH_URL environment variable (default: https://registry.fluidmcp.com/fetch-mcp-package)
        - Method: POST
        - Authentication: Optional bearer token from MCP_TOKEN environment variable

    Args:
        package_str (str): The package string to parse (e.g., "author/package@version").
        auth (bool): If True, include Authorization header with MCP_TOKEN.

    Returns:
        tuple: (headers, payload, pkg_dict) where:
            - headers (dict): Dict with Content-Type and optional Authorization
            - payload (dict): Dict with author, package_name, version for API
            - pkg_dict (dict): Parsed package dictionary from parse_package_string()
    """
    # Parse the package string to extract author, name, and version
    pkg = parse_package_string(package_str)
    logger.info(f"Installing {pkg['author']}/{pkg['package_name']}@{pkg['version']}")

    # Payload for the API request to fetch the package
    payload = {
        "author": pkg['author'],
        "package_name": pkg["package_name"],
        "version": pkg["version"]
    }

    # Headers for the API request
    headers = {
        "Content-Type": "application/json"
    }

    # Add authorization token to headers if auth is enabled
    if auth:
        headers["Authorization"] = AUTH_TOKEN

    return headers, payload, pkg

def replace_package_metadata_from_package_name(package_name: str) -> Dict[str, Any]:
    """Fetch package metadata from the registry for a given package name.

    This function queries the FluidMCP registry metadata endpoint to retrieve
    the full package configuration without downloading the package itself.

    Args:
        package_name (str): The package string (e.g., "author/package@version").

    Returns:
        Dict[str, Any]: Dictionary containing the package metadata from the registry.
                        Returns empty dict {} if the request fails.
    """
    headers, payload ,pkg = make_registry_request(package_name, auth=True)
    
    try:
        # Make the API request to fetch the package metadata
        response = requests.get("https://registry-dev.fluidmcp.com/fetch-metadata", headers=headers, params=payload)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        logger.exception("Error fetching package metadata")
        return {}
