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

def parse_package_string(package_str: str) -> dict:
    """Parse a package string into its component parts.

    Supported formats:
        "author/name@version" → Full specification
        "author/name" → Defaults version to 'latest'
        "name@version" → Defaults author to 'default'
        "name" → Defaults both to 'default' and 'latest'

    Regex Pattern:
        (?:(?P<author>[^/]+)/)?(?P<name>[^@]+)(?:@(?P<version>.+))?
        - (?:(?P<author>[^/]+)/)? : Optional author followed by '/'
        - (?P<name>[^@]+)         : Required package name (no '@')
        - (?:@(?P<version>.+))?   : Optional '@version'

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
    '''
    Check if the data is a tar.gz file.
    args :
        data (bytes): The data to check.
    returns:
        bool: True if the data is a tar.gz file, False otherwise.
    '''
    return data[:2] == b'\x1f\x8b'  # GZIP magic number

def is_json(data: bytes) -> bool:
    '''
    Check if the data is a JSON file.
    args :
        data (bytes): The data to check.
    returns:
        bool: True if the data is a JSON file, False otherwise.'''
    return data.lstrip().startswith(b'{')  # JSON starts with {

def install_package(package_str: str, skip_env: bool = False):
    """Install an MCP package from the Fluid MCP registry.

    Installation Flow:
        1. Parse package string via make_registry_request().
        2. POST to MCP_FETCH_URL to get pre-signed S3 URL.
        3. Download package from S3 (tar.gz or JSON).
        4. Detect file type by magic number.
        5. Extract tar.gz or save metadata.json.
        6. Write environment config unless skip_env=True.

    Args:
        package_str (str): Package identifier (e.g., "author/name@version").
        skip_env (bool): Skip writing environment keys. Defaults to False.

    Returns:
        None

    Raises:
        ValueError: Invalid package_str format.
        requests.RequestException: If registry or S3 download fails.
        Exception: For unknown file type or key writing failure.

    Example:
        >>> install_package("fluidai/filesystem@1.0.0")
    """
    # Form the headers and payload for the API request
    headers,payload ,pkg =make_registry_request(package_str,auth=False)
    
    try:
        print(f":cloud: Installing package from Fluid MCP registry...")
        try:
            # Make the API request to fetch the package
            response = requests.post(API_URL, headers=headers, json=payload)        
            response.raise_for_status()
        except:
            print(f":x: Error fetching package from MCP registry: {response.json()}")
            return

        print(f":cloud: Downloading packages")
        # Check if the response contains a valid pre-signed URL
        try:
            # Extract the pre-signed URL from the response
            s3_url = response.json().get("pre_signed_url")
            # Download file from S3
            s3_response = requests.get(s3_url)
            s3_response.raise_for_status()
            s3_content = s3_response.content  
        except:
            print(f":x: Error fetching package from MCP registry: {response.json()}")
            return
     
        # Form the destination directory path
        dest_dir = INSTALL_BASE / pkg["author"] / pkg["package_name"] / pkg["version"]
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Detect file type
        if is_tar_gz(s3_content):
            print(":package: Extracting tar.gz contents...")
            with tarfile.open(fileobj=BytesIO(s3_content), mode="r:gz") as tar:
                 tar.extractall(path=dest_dir)
        elif is_json(s3_content):
            print(":package: Saving metadata.json...")
            metadata_path = dest_dir / "metadata.json"
            with open(metadata_path, "wb") as f:
                f.write(s3_content)
        else:
            raise Exception("Unknown file type received from S3")

        try:
            write_keys_during_install(dest_dir, pkg, skip_env=skip_env)
        except Exception as e:
            print(f":x: Error writing keys during installation: {e}")
            return
        
        print(f":white_check_mark: Installation completed successfully.")
    except Exception as e:
        # Handle any errors that occur during the installation process
        print(f":x: Installation failed: {e}")

def package_exists(dest_dir: Path) -> bool:
    """Check if the destination directory exists.
    args :
        dest_dir (Path): The path to the destination directory.
    returns:
        bool: True if the directory exists, False otherwise.
    """
    return dest_dir.exists()

def install_package_from_file(package: str, INSTALLATION_DIR: str, pkg: Dict[str, Any]) -> str:
    '''
    Installs a package from a listed by a file.
    args :
        package (str): The package string to install.
        INSTALLATION_DIR (str): The installation directory.
        pkg (Dict[str, Any]): The package metadata.
    returns:
        dest_dir (str): The destination directory of the installed package.
    '''
    print("**** Installing package:", package)
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
            print(f"Package not found: {author}/{package_name}")
    return dest_dir
    

def make_registry_request(package_str: str, auth: bool) -> tuple[dict, dict, dict]:
    """Prepare headers and payload for MCP registry API request.

    Registry Interaction:
        1. Parse package_str via parse_package_string().
        2. Build JSON payload: {'author', 'package_name', 'version'}.
        3. Build headers: {'Content-Type': 'application/json'}.
        4. Add Authorization header if auth=True (MCP_TOKEN).

    Args:
        package_str (str): Package string to install.
        auth (bool): If True, include Authorization header.

    Returns:
        tuple: (headers dict, payload dict, parsed package dict)

    Raises:
        ValueError: Invalid package_str format.

    Example:
        >>> headers, payload, pkg = make_registry_request("filesystem@1.0.0", auth=False)
    """
    # Parse the package string to extract author, name, and version
    pkg = parse_package_string(package_str)
    print(f":wrench: Installing {pkg['author']}/{pkg['package_name']}@{pkg['version']}")
    
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

    return headers, payload ,pkg

def replace_package_metadata_from_package_name(package_name: str) -> Dict[str, Any]:
    '''
    Replaces the package metadata json with the package name.
    args :
        package_name (str): The package name to replace.
    returns:
        Dict[str, Any]: The updated package metadata.
    '''
    headers, payload ,pkg = make_registry_request(package_name, auth=True)
    
    try:
        # Make the API request to fetch the package metadata
        response = requests.get("https://registry-dev.fluidmcp.com/fetch-metadata", headers=headers, params=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching package metadata: {e}")
        return {}
