import argparse
import os
import sys
from pathlib import Path
from fluidai_mcp.services import install_package, edit_env_variables, parse_package_string
import socket
import os
import json
import boto3
from botocore.exceptions import ClientError
from loguru import logger
import secrets
import subprocess
import threading
from fluidai_mcp.services.network_utils import is_port_in_use,kill_process_on_port,find_free_port
from fluidai_mcp.services.s3_utils import s3_upload_file, s3_download_file, load_json_file, write_json_file,validate_metadata_config
from fluidai_mcp.services.package_list import get_latest_version_dir
from fluidai_mcp.services.package_installer import package_exists,install_package_from_file,replace_package_metadata_from_package_name
from fluidai_mcp.services.env_manager import update_env_from_config
from fluidai_mcp.services.package_launcher import launch_mcp_using_fastapi_proxy
import requests
from fastapi import FastAPI, Request, APIRouter
import uvicorn
import re
import shlex

# Get S3 credentials from environment variables
bucket_name = os.environ.get("S3_BUCKET_NAME")
access_key = os.environ.get("S3_ACCESS_KEY")
secret_key = os.environ.get("S3_SECRET_KEY")
region = os.environ.get("S3_REGION")

# Initialize environment variables
client_server_port = int(os.environ.get("MCP_CLIENT_SERVER_PORT", "8090"))
client_server_all_port = int(os.environ.get("MCP_CLIENT_SERVER_ALL_PORT", "8099"))
# Fetch the installation directory
INSTALLATION_DIR = os.environ.get("MCP_INSTALLATION_DIR", Path.cwd() / ".fmcp-packages")
# Fetch the client server directory
CLIENT_SERVER_DIR = os.environ.get('MCP_FASTAPI_DIR',Path.cwd() /"client_server")
ALL_CLIENT_SERVER_DIR = os.environ.get('MCP_FASTAPI_ALL_DIR',Path.cwd() /"client_server_all")

DEFAULT_GITHUB_BRANCH = "main"

def normalize_github_repo(repo_path: str) -> tuple[str, str]:
    """Normalize a GitHub repo path or URL to (owner, repo)."""
    cleaned = repo_path.strip()
    cleaned = cleaned.replace("https://github.com/", "").replace("http://github.com/", "")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    if cleaned.count("/") != 1:
        raise ValueError("GitHub repo path must be in the form 'owner/repo'")
    owner, repo = cleaned.split("/", 1)
    return owner, repo


def clone_github_repo(repo_path: str, github_token: str, branch: str | None = None) -> Path:
    """Clone a GitHub repository into the standard FMCP package layout."""
    if not github_token:
        raise ValueError("GitHub token is required to clone the repository")

    owner, repo = normalize_github_repo(repo_path)
    target_branch = branch or DEFAULT_GITHUB_BRANCH
    dest_dir = Path(INSTALLATION_DIR) / owner / repo / target_branch
    dest_dir.parent.mkdir(parents=True, exist_ok=True)

    if dest_dir.exists() and any(dest_dir.iterdir()):
        print(f"Repository already cloned at {dest_dir}, reusing existing files")
        return dest_dir

    clone_url = f"https://{github_token}@github.com/{owner}/{repo}.git"
    try:
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                target_branch,
                clone_url,
                str(dest_dir),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        print(f"✅ Cloned {owner}/{repo} to {dest_dir}")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        raise RuntimeError(f"Failed to clone repository: {error_msg}")

    return dest_dir


def find_readme_file(directory: Path) -> Path:
    """
    Find a README file in the given directory.
    Searches for common README file names.

    args:
        directory (Path): Directory to search in
    returns:
        Path: Path to the README file
    raises:
        FileNotFoundError: If no README file is found
    """
    readme_patterns = [
        "README.md", "readme.md", "Readme.md",
        "README.MD", "README", "readme",
        "README.txt", "readme.txt"
    ]

    for pattern in readme_patterns:
        readme_path = directory / pattern
        if readme_path.exists() and readme_path.is_file():
            return readme_path

    raise FileNotFoundError(f"No README file found in {directory}")

def extract_json_from_readme(readme_content: str) -> dict:
    """
    Extract JSON content from README file.
    Looks for JSON in markdown code blocks or raw JSON.
    Prioritizes JSON blocks that contain 'mcpServers' key.

    args:
        readme_content (str): Content of the README file
    returns:
        dict: Extracted JSON data
    raises:
        ValueError: If no valid JSON is found
    """
    import re

    all_candidates = []

    # Try to find JSON in markdown code blocks first
    # Pattern 1: ```json ... ```
    json_block_pattern = r'```json\s*\n(.*?)\n```'
    matches = re.findall(json_block_pattern, readme_content, re.DOTALL | re.IGNORECASE)

    for match in matches:
        try:
            data = json.loads(match.strip())
            if isinstance(data, dict):
                all_candidates.append(data)
        except json.JSONDecodeError:
            continue

    # Pattern 2: ``` ... ``` (code block without language specifier)
    code_block_pattern = r'```\s*\n(.*?)\n```'
    matches = re.findall(code_block_pattern, readme_content, re.DOTALL)

    for match in matches:
        try:
            data = json.loads(match.strip())
            if isinstance(data, dict):
                all_candidates.append(data)
        except json.JSONDecodeError:
            continue

    # Pattern 3: Try to find raw JSON (looking for { ... } blocks with proper nesting)
    # More sophisticated pattern that handles nested braces better
    json_pattern = r'\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\}))*\}))*\}'
    matches = re.findall(json_pattern, readme_content, re.DOTALL)

    # Try the largest JSON-like blocks first
    sorted_matches = sorted(matches, key=len, reverse=True)
    for match in sorted_matches[:10]:  # Limit to top 10 largest to avoid processing too many
        try:
            data = json.loads(match.strip())
            if isinstance(data, dict):
                all_candidates.append(data)
        except json.JSONDecodeError:
            continue

    # Now prioritize candidates with 'mcpServers' key
    for candidate in all_candidates:
        if "mcpServers" in candidate:
            return candidate

    # If no candidate has mcpServers, return the first valid one
    if all_candidates:
        return all_candidates[0]

    raise ValueError("No valid JSON found in README file")

def validate_mcp_metadata(metadata: dict) -> bool:
    """
    Validate that the extracted JSON has the correct MCP metadata structure.

    args:
        metadata (dict): JSON data to validate
    returns:
        bool: True if valid, raises exception otherwise
    raises:
        ValueError: If metadata structure is invalid
    """
    if not isinstance(metadata, dict):
        raise ValueError("Metadata must be a dictionary")

    if "mcpServers" not in metadata:
        raise ValueError("Metadata must contain 'mcpServers' key")

    mcp_servers = metadata["mcpServers"]
    if not isinstance(mcp_servers, dict):
        raise ValueError("'mcpServers' must be a dictionary")

    if len(mcp_servers) == 0:
        raise ValueError("'mcpServers' must contain at least one server configuration")

    # Validate each server configuration
    for server_name, server_config in mcp_servers.items():
        if not isinstance(server_config, dict):
            raise ValueError(f"Server '{server_name}' configuration must be a dictionary")

        if "command" not in server_config:
            raise ValueError(f"Server '{server_name}' must have a 'command' field")

        if "args" not in server_config:
            raise ValueError(f"Server '{server_name}' must have an 'args' field")

        if not isinstance(server_config["args"], list):
            raise ValueError(f"Server '{server_name}' 'args' must be a list")

    return True


def run_github_server(args, secure_mode=False, token=None):
    """Clone an MCP server from GitHub and run it via FastAPI."""
    try:
        dest_dir = clone_github_repo(args.repo, args.github_token, args.branch)

        # Check if metadata.json exists
        metadata_path = dest_dir / "metadata.json"
        
        if not metadata_path.exists():
            print(f"📄 No metadata.json found, searching for configuration in README...")
            
            try:
                # Find README file
                readme_path = find_readme_file(dest_dir)
                print(f"✅ Found README at: {readme_path.name}")
                
                # Read README content
                with open(readme_path, 'r', encoding='utf-8') as f:
                    readme_content = f.read()
                
                # Extract JSON from README
                print(f"🔍 Extracting JSON from README...")
                metadata = extract_json_from_readme(readme_content)
                print(f"✅ JSON extracted successfully")
                
                # Validate the metadata structure
                print(f"✔️  Validating metadata structure...")
                validate_mcp_metadata(metadata)
                print(f"✅ Metadata validation passed")
                
                # Create metadata.json file
                with open(metadata_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2)
                print(f"✅ Created metadata.json from README")
                
                # Extract package name from metadata
                package_name = list(metadata["mcpServers"].keys())[0]
                pkg_info = {"package_name": package_name}
                
                # Process environment variables if they exist
                from fluidai_mcp.services.env_manager import write_keys_during_install
                
                # Prompt for environment variables (skip_env=False to prompt user)
                print(f"\n🔑 Checking for environment variables...")
                write_keys_during_install(dest_dir, pkg_info, skip_env=False)
                
            except FileNotFoundError as e:
                print(f"❌ {str(e)}")
                print(f"Please ensure the repository contains either metadata.json or a README with MCP configuration")
                sys.exit(1)
            except ValueError as e:
                print(f"❌ Error extracting/validating JSON: {str(e)}")
                print(f"Please ensure the README contains valid MCP server configuration in JSON format")
                sys.exit(1)
            except Exception as e:
                print(f"❌ Unexpected error processing README: {str(e)}")
                sys.exit(1)

        if secure_mode and token:
            os.environ["FMCP_BEARER_TOKEN"] = token
            os.environ["FMCP_SECURE_MODE"] = "true"
            print(f"🔒 Secure mode enabled with bearer token")

        # Launch MCP server using single-threading approach
        package_name, router = launch_mcp_using_fastapi_proxy(dest_dir)

        if not router:
            print("❌ Failed to launch MCP server")
            sys.exit(1)

        print(f"✅ MCP server {package_name} launched successfully from GitHub source")

        if args.start_server:
            fastapi_port_busy = is_port_in_use(client_server_port)
            if fastapi_port_busy:
                print(f"Port {client_server_port} is already in use.")
                if args.force_reload:
                    print(f"Force reloading the server on port {client_server_port}")
                    kill_process_on_port(client_server_port)
                else:
                    choice = input("Do you want to kill the existing process and reload? (y/n): ").strip().lower()
                    if choice == 'y':
                        kill_process_on_port(client_server_port)
                    elif choice == 'n':
                        print(f"Keeping the existing process on port {client_server_port}")
                        return
                    else:
                        print("Invalid choice. Please enter 'y' or 'n'.")
                        return

            app = FastAPI(
                title=f"FluidMCP Server - {package_name}",
                description=f"Gateway for {package_name} MCP server using STDIO", 
                version="2.0.0"
            )

            app.include_router(router, tags=[package_name])

            logger.info(f"Starting FastAPI client server on port {client_server_port}")
            print(f"🚀 Starting FastAPI server for {package_name}")
            print(f"📖 Swagger UI available at: http://localhost:{client_server_port}/docs")

            uvicorn.run(app, host="0.0.0.0", port=client_server_port)

    except Exception as e:
        print(f"Error running GitHub MCP server: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def parse_github_package_string(fmcp_package: str) -> dict:
    """
    Parse GitHub package string from S3 config format.

    Format: "owner/repo --github-token TOKEN [--branch BRANCH] [--start-server]"

    args:
        fmcp_package (str): Package string containing GitHub repo and token
    returns:
        dict: Parsed components with keys: repo, token, branch
    raises:
        ValueError: If format is invalid
    """

    # Split the string respecting quotes
    parts = shlex.split(fmcp_package)

    if not parts:
        raise ValueError("Empty fmcp_package string")

    # First part is the repository
    repo = parts[0]

    # Parse flags
    token = None
    branch = DEFAULT_GITHUB_BRANCH

    i = 1
    while i < len(parts):
        if parts[i] == '--github-token' and i + 1 < len(parts):
            token = parts[i + 1]
            i += 2
        elif parts[i] == '--branch' and i + 1 < len(parts):
            branch = parts[i + 1]
            i += 2
        elif parts[i] == '--start-server':
            i += 1
        else:
            i += 1

    if not token:
        raise ValueError("GitHub token not found in fmcp_package string. Expected '--github-token TOKEN'")

    return {
        'repo': normalize_github_repo(repo)[0] + '/' + normalize_github_repo(repo)[1],
        'token': token,
        'branch': branch
    }


def resolve_package_dest_dir(package_str: str) -> Path:
    """
    Resolve the destination directory for a package string.
    Handles formats: author/package@version, author/package, package@version, package
    Returns the Path to the resolved directory or raises FileNotFoundError.
    """
    install_dir = Path(INSTALLATION_DIR)
    if '/' in package_str:
        author, package_with_version = package_str.split('/', 1)
        if '@' in package_with_version:
            package_name, version = package_with_version.split('@', 1)
            dest_dir = install_dir / author / package_name / version
        else:
            package_name = package_with_version
            package_dir = install_dir / author / package_name
            dest_dir = get_latest_version_dir(package_dir)
    else:
        if '@' in package_str:
            package_name, version = package_str.split('@', 1)
            dest_dir = None
            if install_dir.exists():
                for author in install_dir.iterdir():
                    if author.is_dir():
                        package_path = author / package_name / version
                        if package_path.exists():
                            dest_dir = package_path
                            break
            if dest_dir is None:
                raise FileNotFoundError(f"Package not found: {package_str}")
        else:
            package_name = package_str
            dest_dir = None
            if install_dir.exists():
                for author in install_dir.iterdir():
                    if author.is_dir():
                        package_dir = author / package_name
                        if package_dir.exists():
                            try:
                                dest_dir = get_latest_version_dir(package_dir)
                                break
                            except FileNotFoundError:
                                continue
            if dest_dir is None:
                raise FileNotFoundError(f"Package not found: {package_str}")
    return dest_dir


def list_installed_packages() -> None:
    '''
    Print all installed packages in the installation directory.
    args:
        none
    returns:
        none
    '''
    try:
        # Check if the installation directory exists
        #print(os.path.abspath(os.path.join(os.getcwd(), os.pardir)))
        install_dir = Path(INSTALLATION_DIR)
  
        # Check if the directory is empty
        if not install_dir.exists() or not any(install_dir.iterdir()):
            print("No mcp packages found.")
            # return none if the directory is empty
            return
        
        print(f"Installation directory: {install_dir}")
        # If the directory is not empty, list all packages
        found_packages = False
        # Iterate through the installation directory
        for author in install_dir.iterdir():
            # Check if the author is a directory
            if author.is_dir():
                # Iterate through the packages for each author
                for pkg in author.iterdir():
                    # Check if the package is a directory
                    if pkg.is_dir():
                        # Iterate through the versions for each package
                        for version in pkg.iterdir():
                            # Log the author package name and version 
                            if version.is_dir():
                                found_packages = True
                                print(f"{author.name}/{pkg.name}@{version.name}")
        if not found_packages:
            print("No packages found in the installation directory structure.")
    except Exception as e:
        # Handle any errors that occur while listing packages
        print(f"Error listing installed packages: {str(e)}")


def edit_env(args):
    '''
    Edit environment variables for a package.
    args:
        args (argparse.Namespace): The parsed command line arguments.
    returns:
        None
    '''
    try:
        dest_dir = resolve_package_dest_dir(args.package)
        if not package_exists(dest_dir):
            print(f"Package not found at {dest_dir}. Have you installed it?")
            sys.exit(1)
        edit_env_variables(dest_dir)
    except Exception as e:
        print(f"Error editing environment variables: {str(e)}")
        sys.exit(1)



def collect_installed_servers_metadata(install_dir, taken_ports=None, secure_mode=False, token=None):
    """
    Scan installed packages, read metadata.json, assign unique ports, and merge metadata.
    Returns a dict with merged server metadata.
    """
    taken_ports = taken_ports or set()
    all_servers = {}

    for author_dir in install_dir.iterdir():
        if not author_dir.is_dir():
            continue
        for pkg_dir in author_dir.iterdir():
            if not pkg_dir.is_dir():
                continue
            try:
                version_dir = get_latest_version_dir(pkg_dir)
            except FileNotFoundError:
                continue
            md = version_dir / "metadata.json"
            if not md.exists():
                continue
            try:
                metadata = json.loads(md.read_text())
            except json.JSONDecodeError:
                print(f"Invalid JSON in {md}")
                continue
            for key, cfg in metadata.get("mcpServers", {}).items():
                port = find_free_port(taken_ports=taken_ports)
                cfg["port"] = str(port)
                cfg["install_path"] = str(version_dir)
                if secure_mode and token:
                    cfg["bearer_token"] = token
                all_servers[key] = cfg
                taken_ports.add(port)
    merged = {"mcpServers": all_servers}
    return merged




def start_fastapi_client_server(script_path, port, env_vars, cwd=None, log_output=False):
    """Start the FastAPI client server as a subprocess."""
    env = {**os.environ, "MCP_CLIENT_SERVER_PORT": str(port), **env_vars}
    process = subprocess.Popen(
        [sys.executable, script_path],
        env=env,
        cwd=cwd or os.path.dirname(os.path.abspath(__file__)),
        stdout=subprocess.PIPE if log_output else None,
        stderr=subprocess.PIPE if log_output else None,
        text=True if log_output else None
    )
    if log_output:
        def _log_subprocess_output(process_object):
            for line in process_object.stdout:
                logger.info(f"Fast API server logs: {line}")
        log_thread = threading.Thread(target=_log_subprocess_output, args=(process,))
        log_thread.start()
    return process

def run_all(secure_mode=False, token=None):
    """
    Run all installed MCP servers by scanning their metadata,
    dynamically assigning unique ports that aren't already assigned, and launching each from its own directory.
    """
    # Check if the installation directory exists
    install_dir = Path(INSTALLATION_DIR)
    if not install_dir.exists():
        print("No installations found.")
        return

    # Fetch the client server all directory
    meta_all_path = install_dir / "metadata_all.json"
    taken_ports = set()

    #Load existing metadata_all.json to get already assigned ports
    if meta_all_path.exists():
        # Load existing metadata_all.json to get already assigned ports
        try:
            merged = json.loads(meta_all_path.read_text())
            for server_name, server_metadata in merged.get("mcpServers", {}).items():
                taken_ports.add(int(server_metadata.get("port", -1)))
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"❌ Error loading existing metadata_all.json: {e}")

    # Use helper to collect/merge metadata
    merged = collect_installed_servers_metadata(install_dir, taken_ports, secure_mode, token)

    #Write merged metadata_all.json with the unique port for each server
    try:
        meta_all_path.write_text(json.dumps(merged, indent=2))
        print(f"✅ Wrote merged metadata to {meta_all_path}")
    except Exception as e:
        print(f"❌ Failed to write metadata_all.json: {e}")
        return
    
    if secure_mode and token:
        os.environ["FMCP_BEARER_TOKEN"] = token
        os.environ["FMCP_SECURE_MODE"] = "true"
        print(f"🔒 Secure mode enabled with bearer token")
        
    # Create main FastAPI app
    app = FastAPI(
        title="FluidMCP Multi-Server Gateway",
        description="Unified gateway for multiple MCP servers",
        version="2.0.0"
    )
    
    launched_servers = 0

    # Launch each server and add its router to the main app
    for pkg, server in merged["mcpServers"].items():
        dest_dir = Path(server["install_path"])
        try:
            
            package_name, router = launch_mcp_using_fastapi_proxy(dest_dir)
            
            if router:
                # Add this package's router to main app
                app.include_router(router, tags=[package_name])
                print(f"✅ Added {package_name} endpoints")
                launched_servers += 1
                
        except Exception as e:
            print(f"❌ Error launching {pkg}: {e}")

    if launched_servers == 0:
        print("❌ No servers were successfully launched")
        return
    

    pid_killed = kill_process_on_port(client_server_all_port)
    logger.info(f"Starting FastAPI client server on port {client_server_all_port}")
    uvicorn.run(app, host="0.0.0.0", port=client_server_all_port)

def run_server(args, secure_mode=False, token=None):
    '''
    Run the MCP server from the specified package.
    args:
        args (argparse.Namespace): The parsed command line arguments.
    returns:
        '''
    try:
        dest_dir = resolve_package_dest_dir(args.package)
        if not package_exists(dest_dir):
            print(f"Package not found at {dest_dir}. Have you installed it?")
            sys.exit(1)
            
        start_server = args.start_server
        force_reload = args.force_reload
        
        # KEEP: Set up secure mode environment variables for future use
        if secure_mode and token:
            os.environ["FMCP_BEARER_TOKEN"] = token
            os.environ["FMCP_SECURE_MODE"] = "true"
            print(f"🔒 Secure mode enabled with bearer token")
        
        print(f"Running MCP server from {dest_dir}")
        
        # REPLACE: Use new STDIO method instead of SuperGateway
        package_name, router = launch_mcp_using_fastapi_proxy(dest_dir)
        
        if not router:
            print(f"❌ Failed to launch MCP server")
            sys.exit(1)
            
        print(f"✅ MCP server {package_name} launched successfully")

        # check if start_server was given in the command line arguments
        if start_server:
            fastapi_port_busy = is_port_in_use(client_server_port)
            # If the port is busy, check if force_reload was given in the command line arguments
            if fastapi_port_busy:
                print(f"Port {client_server_port} is already in use.")
                # If force_reload is set, kill the existing process
                if force_reload:
                    print(f"Force reloading the server on port {client_server_port}")
                    kill_process_on_port(client_server_port)
                else:
                    # If force_reload is not set, prompt the user for confirmation
                    choice = input("Do you want to kill the existing process and reload? (y/n): ").strip().lower()
                    # take action based on user input
                    # if the user chooses to kill the process, kill it
                    if choice == 'y':
                        kill_process_on_port(client_server_port)
                    # if the user chooses not to kill the process, exit
                    elif choice == 'n':
                        print(f"Keeping the existing process on port {client_server_port}")
                        return
                    # if the user enters an invalid choice, print an error message
                    else:
                        print("Invalid choice. Please enter 'y' or 'n'.")
                        return

            # REPLACE: Create FastAPI app directly instead of external process
            app = FastAPI(
                title=f"FluidMCP Server - {package_name}",
                description=f"Gateway for {package_name} MCP server using STDIO",
                version="2.0.0"
            )
            
            # Add the router to the app
            app.include_router(router, tags=[package_name])
            
            logger.info(f"Starting FastAPI client server on port {client_server_port}")
            print(f"🚀 Starting FastAPI server for {package_name}")
            print(f"📖 Swagger UI available at: http://localhost:{client_server_port}/docs")
               
            uvicorn.run(app, host="0.0.0.0", port=client_server_port)

    except Exception as e:
        print(f"Error running MCP server: {str(e)}")
        sys.exit(1)



def run_all_master(args, secure_mode=False, token=None):
    """
    Run all installed MCP servers by scanning their metadata and using S3 storage.
    - Checks if s3_metadata_all.json exists in S3
    - If it exists, downloads it to local system
    - If not, creates a new file and uploads it to S3
    - Uses installation paths in s3_metadata_all.json to run servers
    """

    # Create S3 client
    s3_client = boto3.client(
        's3',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region
    )

    # Check if the installation directory exists
    install_dir = Path(INSTALLATION_DIR)
    if not install_dir.exists():
        print("No installations found.")
        return

    # Fetch the client server all directory
    meta_all_path = install_dir / "s3_metadata_all.json"
    taken_ports = set()
    s3_file_key = "s3_metadata_all.json"

    # Check if file exists in S3
    try:
        print(f"Checking if {s3_file_key} exists in S3 bucket {bucket_name}...")
        s3_client.head_object(Bucket=bucket_name, Key=s3_file_key)
        file_exists = True
        print(f"File {s3_file_key} found in S3 bucket")
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            file_exists = False
            print(f"File {s3_file_key} not found in S3 bucket")
        else:
            print(f"Error checking S3: {e}")
            return

    # If file exists, download it; if not, create and upload it
    if file_exists:
        s3_download_file(s3_client, bucket_name, s3_file_key, meta_all_path)
    else:
        merged = collect_installed_servers_metadata(install_dir, taken_ports, secure_mode, token)
        write_json_file(meta_all_path, merged)
        s3_upload_file(s3_client, meta_all_path, bucket_name, s3_file_key)
    # Load the metadata from the downloaded file
    try:
        s3_metadata_all = load_json_file(meta_all_path)
        if s3_metadata_all is None:
            return
    except Exception as e:
        print(f"Error reading s3_metadata_all.json: {e}")
        return
    
    
    try:
        # Restart Ports that were assigned
        s3_metadata_ports = []
        for server_name, server_metadata in s3_metadata_all.get("mcpServers", {}).items():
            s3_metadata_ports.append(int(server_metadata.get("port", -1)))

        for port in s3_metadata_ports:
            if port != client_server_all_port:
                kill_process_on_port(port)
    except Exception as e:
        print(f"Error processing ports from s3_metadata_all.json: {e}")
        return

    # Check if mcpServers exists in the file
    if "mcpServers" not in s3_metadata_all:
        print("Invalid metadata format: 'mcpServers' key not found")
        return

    fmcp_packages = []
    for server_name, server_metadata in s3_metadata_all.get("mcpServers", {}).items():
        fmcp_packages.append(server_metadata.get("fmcp_package"))

    # Install packages using --master logic (skip_env=True and update_env_from_common_env)
    for package in fmcp_packages:
        print("**** Installing package:", package)
        pkg = parse_package_string(package)
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
                continue
        if not dest_dir.exists():
            print(f"Package not found at {dest_dir}. Have you installed it?")
            continue
        update_env_from_common_env(dest_dir, pkg)

    # Create fresh FastAPI app
    app = FastAPI(
        title="FluidMCP Multi-Server Gateway - Master Mode",
        description="Gateway for MCP servers from S3 configuration using STDIO",
        version="2.0.0"
    )
    
    # Set up environment variables for secure mode
    if secure_mode and token:
        os.environ["FMCP_BEARER_TOKEN"] = token
        os.environ["FMCP_SECURE_MODE"] = "true"
        print(f"🔒 Secure mode enabled with bearer token")
    
    print("Starting MCP servers based on installation paths in s3_metadata_all.json")
    
    # Track successful servers
    launched_servers = 0
    
    for server_name, server_config in s3_metadata_all["mcpServers"].items():
        # Check if install_path exists in the config
        if "install_path" not in server_config:
            print(f"No installation path found for server '{server_name}', skipping")
            continue
            
        # Get the installation path and check if it exists
        install_path = Path(server_config["install_path"])
        if not install_path.exists():
            print(f"Installation path '{install_path}' for server '{server_name}' does not exist, skipping")
            continue
            
        # Check if the path has a metadata.json file
        metadata_path = install_path / "metadata.json"
        if not metadata_path.exists():
            print(f"No metadata.json found in '{install_path}' for server '{server_name}' skipping")
            continue
            
        try:
            print(f"🚀 Launching server '{server_name}' from path: {install_path}")
            
            # Use existing STDIO function instead of SuperGateway
            package_name, router = launch_mcp_using_fastapi_proxy(install_path)
            
            if router:
                # Add this package's router to main app
                app.include_router(router, tags=[server_name])
                print(f"✅ Added {package_name} endpoints to unified app")
                launched_servers += 1
            else:
                print(f"❌ Failed to create router for {server_name}")
                
        except Exception as e:
            print(f"❌ Error launching server '{server_name}': {e}")
    
    # Report on launches
    if launched_servers > 0:
        print(f"Successfully launched {launched_servers} MCP servers")
    else:
        print("No servers were launched. Check if installation paths exist.")
        return
    
    # Kill existing process and start unified app
    pid_killed = kill_process_on_port(client_server_all_port)
    logger.info(f"Starting unified FastAPI server on port {client_server_all_port}")
    uvicorn.run(app, host="0.0.0.0", port=client_server_all_port)



def update_env_from_common_env(dest_dir, pkg):
    """
    Update metadata.json env section from a common .env file in the installation directory.
    If .env or required keys are missing, create/add them with "dummy-key".
    
    args:
        dest_dir (Path): The destination directory of the package.
        pkg (dict): The package metadata dictionary.
    returns:
        None
    """
    install_dir = Path(INSTALLATION_DIR)
    env_path = install_dir / ".env"
    metadata_path = dest_dir / "metadata.json"

    # Load .env if exists, else start with empty dict
    env_vars = {}
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    env_vars[k.strip()] = v.strip()
    else:
        # Ensure the parent directory exists
        env_path.parent.mkdir(parents=True, exist_ok=True)
        # Actually create the .env file (empty for now)
        env_path.touch()

    # Load metadata.json
    with open(metadata_path, "r") as f:
        metadata = json.load(f)

    # Get env section
    try:
        env_section = metadata["mcpServers"][pkg["package_name"]]["env"]
    except Exception:
        return

    updated = False
    for key in env_section:
        # Determine if structured or simple env
        if isinstance(env_section[key], dict):
            # Structured format
            if "required" in env_section[key] and env_section[key]["required"]:
                if key in env_vars:
                    metadata["mcpServers"][pkg["package_name"]]["env"][key]["value"] = env_vars[key]
                else:
                    env_vars[key] = "dummy-key"
                    metadata["mcpServers"][pkg["package_name"]]["env"][key]["value"] = "dummy-key"
                    updated = True
        else:
            # Simple format
            if key in env_vars:
                metadata["mcpServers"][pkg["package_name"]]["env"][key] = env_vars[key]
            else:
                env_vars[key] = "dummy-key"
                metadata["mcpServers"][pkg["package_name"]]["env"][key] = "dummy-key"
                updated = True

    # Always write .env (create if missing, update if exists)
    with open(env_path, "w") as f:
        for k, v in env_vars.items():
            f.write(f"{k}={v}\n")

    # Write back metadata.json
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)


def install_command(args):
    """
    Handles the 'install' CLI command, including --master logic.
    """
    pkg = parse_package_string(args.package)
    # Install the package, skip env prompts if --master
    install_package(args.package, skip_env=getattr(args, "master", False))
    try:
        dest_dir = resolve_package_dest_dir(args.package)
    except Exception as e:
        print(str(e))
        sys.exit(1)
    if not package_exists(dest_dir):
        print(f"Package not found at {dest_dir}. Have you installed it?")
        sys.exit(1)
    if getattr(args, "master", False):
        update_env_from_common_env(dest_dir, pkg)

def run_from_source(source, source_path, secure_mode=False, token=None):
    try:
        if source == "file":
            config = extract_config_from_file(source_path)
        elif source == "s3":
            config = extract_config_from_s3(source_path)

        # Restart Ports that were assigned 
        try:
            file_metadata_ports = []
            for server_name, server_metadata in config.get("mcpServers", {}).items():
                file_metadata_ports.append(int(server_metadata.get("port", -1)))
        except Exception as e:
            print(f"Error processing ports from config: {e}")
            return
        
        if secure_mode and token:
            os.environ["FMCP_BEARER_TOKEN"] = token
            os.environ["FMCP_SECURE_MODE"] = "true"
            print(f"🔒 Secure mode enabled with bearer token")
        
        # Install packages - loop directly over config items
        for server_name, server_config in config.get("mcpServers", {}).items():
            # Check if this is a GitHub package (new structured format)
            if "github_repo" in server_config:
                print(f"🔍 Detected GitHub package: {server_name}")

                try:
                    # Extract GitHub info directly from structured config
                    repo = server_config["github_repo"]
                    github_token = server_config["github_token"]
                    branch = server_config.get("branch", DEFAULT_GITHUB_BRANCH)

                    print(f"📦 Repository: {repo}")
                    print(f"🌿 Branch: {branch}")

                    # Clone the repository
                    dest_dir = clone_github_repo(repo, github_token, branch)
                    print(f"✅ Cloned to {dest_dir}")

                    # Look for metadata.json, if not found extract from README
                    metadata_path = dest_dir / "metadata.json"

                    if not metadata_path.exists():
                        print(f"📄 No metadata.json found, extracting from README...")

                        try:
                            readme_path = find_readme_file(dest_dir)
                            print(f"✅ Found README at: {readme_path.name}")

                            with open(readme_path, 'r', encoding='utf-8') as f:
                                readme_content = f.read()

                            metadata = extract_json_from_readme(readme_content)
                            print(f"✅ JSON extracted successfully")

                            validate_mcp_metadata(metadata)
                            print(f"✅ Metadata validation passed")

                        except (FileNotFoundError, ValueError) as e:
                            print(f"❌ Error processing README: {str(e)}")
                            continue
                    else:
                        with open(metadata_path, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)

                    # Get the server name from metadata
                    server_name_in_metadata = list(metadata["mcpServers"].keys())[0]

                    # CRITICAL: Rename package in metadata to match config server name
                    if server_name != server_name_in_metadata:
                        print(f"🔧 Renaming package in metadata from '{server_name_in_metadata}' to '{server_name}'")
                        metadata["mcpServers"][server_name] = metadata["mcpServers"].pop(server_name_in_metadata)

                    # Override env variables from config
                    if "env" in server_config:
                        print(f"🔧 Overriding environment variables from config")
                        metadata["mcpServers"][server_name]["env"] = server_config["env"]

                    # Override port from config
                    if "port" in server_config:
                        print(f"🔧 Setting port to {server_config['port']}")
                        metadata["mcpServers"][server_name]["port"] = server_config["port"]

                    # Save the updated metadata.json
                    with open(metadata_path, 'w', encoding='utf-8') as f:
                        json.dump(metadata, f, indent=2)
                    print(f"✅ Saved metadata.json with updated configuration")

                    # Update install_path in config
                    server_config["install_path"] = str(dest_dir)
                    print(f"✅ Updated installation path for {server_name} to {dest_dir}")

                except Exception as e:
                    print(f"❌ Error processing GitHub package {server_name}: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    continue

            # Registry package - check for fmcp_package field
            elif "fmcp_package" in server_config:
                package = server_config["fmcp_package"]
                print(f"🔍 Detected registry package: {package}")

                try:
                    pkg = parse_package_string(package)
                    dest_dir = install_package_from_file(package, INSTALLATION_DIR, pkg)
                    
                    server_config["install_path"] = str(dest_dir)
                    print(f"✅ Updated installation path for {package} to {dest_dir}")
                    
                    # Update env variables from the config file            
                    metadata_path = dest_dir / "metadata.json"
                    if not metadata_path.exists():
                        print(f"⚠️  No metadata.json found in '{dest_dir}', skipping env variable update")
                        continue
                    
                    update_env_from_config(metadata_path, package, config, pkg)
                    
                except Exception as e:
                    print(f"❌ Error installing package {package}: {str(e)}")
                    continue
            else:
                print(f"⚠️  Skipping {server_name}: neither 'github_repo' nor 'fmcp_package' found")
                continue

        # Launch each MCP server based on installation paths
        print("Starting MCP servers based on installation paths in config file")
        
        launched_servers = 0
        app = FastAPI()
        
        for server_name, server_config in config["mcpServers"].items():
            if "install_path" not in server_config:
                print(f"⚠️  No installation path found for server '{server_name}', skipping")
                continue
                
            install_path = Path(server_config["install_path"])
            if not install_path.exists():
                print(f"❌ Installation path '{install_path}' for server '{server_name}' does not exist, skipping")
                continue
                
            metadata_path = install_path / "metadata.json"
            if not metadata_path.exists():
                print(f"❌ No metadata.json found in '{install_path}' for server '{server_name}', skipping")
                continue
                
            print(f"✅ Launching server '{server_name}' from path: {install_path}")
            
            pkg_name, router = launch_mcp_using_fastapi_proxy(install_path)
            app.include_router(router, tags=[server_name])
            launched_servers += 1
            
        if launched_servers > 0:
            print(f"✅ Successfully launched {launched_servers} MCP servers")
        else:
            print("❌ No servers were launched. Check if installation paths exist.")
            return

        pid_killed = kill_process_on_port(client_server_all_port)
        logger.info(f"Starting unified FastAPI server on port {client_server_all_port}")
        uvicorn.run(app, host="0.0.0.0", port=int(client_server_all_port))
                
    except FileNotFoundError:
        print(f"❌ Error: Configuration file not found: {source_path}")
    except json.JSONDecodeError:
        print(f"❌ Error: Invalid JSON format in configuration file: {source_path}")
    except Exception as e:
        print(f"❌ Error running servers from source: {str(e)}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")

def extract_config_from_file(file_path):

    # Preprocess the metadata file to fetch actual metadata from the package name present in the metadata.json file.
    preprocess_metadata_file(file_path)

    try:
        # Load the JSON configuration file
        with open(file_path, 'r') as file:
            config = json.load(file)
        
        # Validate the configuration
        if not validate_metadata_config(config, file_path):
            return
            
        print(f"Loading server configurations from file: {file_path}")
        return config
    except FileNotFoundError:
        print(f"Error: Configuration file not found: {file_path}")
        return
    
def extract_config_from_s3(presigned_url):
    
    
    # Download the JSON configuration file using the presigned URL
    try:
        install_dir = Path(INSTALLATION_DIR)
        print(f"Installation directory: {install_dir}")
        install_dir.mkdir(parents=True, exist_ok=True)
        temp_file_path = install_dir / "s3_metadata_all.json"
        print(f"Temporary file path: {temp_file_path}")
    except Exception as e:
        print(f"Error creating temporary file path: {e}")
        return
    
    print(f"Downloading configuration file from presigned URL")
    # Download the file using requests 
    try:
        # Download the file using requests
        response = requests.get(presigned_url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Save the content to a temporary file
        with open(temp_file_path, 'wb') as f:
            f.write(response.content)
    except Exception as e:
        print(f"Error downloading S3 configuration file: {e}")
        return
    
    # Preprocess the metadata file to fetch actual metadata from the package name present in the metadata.json file.
    preprocess_metadata_file(temp_file_path)

    # Load the JSON configuration file
    try:
        # Load the JSON configuration file
        with open(temp_file_path, 'r') as file:
            config = json.load(file)
        # Validate the configuration
        if not validate_metadata_config(config, temp_file_path):
            return        
        print(f"Loading server configurations from file: {temp_file_path}")
        return config
    except Exception as e:
        print(f"Error loading configuration file: {e}")

def preprocess_metadata_file(metadata_path):
    '''
    Preprocess the metadata file to fetch actual metadata from the package name present in the metadata.json file.
    args:
        metadata_path (str): The path to the metadata.json file.
    returns:
        None
    '''
    # Get the preprocessed metadata from metadata_path and read it
    try:
        # Load the JSON configuration file
        with open(metadata_path, 'r') as file:
            raw_metadata = json.load(file)
    except FileNotFoundError:
        print(f"Error: Configuration file not found: {metadata_path}")
        return
    
    # Update the metadata file with the actual metadata from the package name if package name is present in the metadata.json file
    taken_ports = set()
    # Loop through the mcpServers in the metadata and check if the package name is a dictionary
    for package in list(raw_metadata['mcpServers'].keys()):
        # Check if the package name is a dictionary, if yes, extract the port from the dictionary and add it to the taken_ports set and continue
        if isinstance(raw_metadata['mcpServers'][package], dict):
            # If the package name is a dictionary, check if it has a port key and add it to the taken_ports set for later use
            taken_ports.add(int(raw_metadata['mcpServers'][package].get("port", -1)))
            continue
        # Check if the package name is a string, if yes, replace the package metadata with the actual metadata from the package name
        else:
            # Fetch the acutal metadata from the package name using a rest API call
            replaced_metadata = replace_package_metadata_from_package_name(raw_metadata['mcpServers'][package])
            #Store the fmcp package name before deletion from the metadata
            fmcp_package = raw_metadata['mcpServers'][package]
            # Delete the package with the package string, it will be replaced with the actual metadata from the package name
            del raw_metadata['mcpServers'][package]
            # Get the package name from the actual metadata and make it the key in the metadata
            package_name = list(replaced_metadata['mcpServers'].keys())[0]
            # Add the actual metadata to the metadata with the package name as the key
            value = replaced_metadata['mcpServers'][package_name]
            # Add additional required keys to the metadata
            raw_metadata['mcpServers'][package_name] = value
            raw_metadata['mcpServers'][package_name]['fmcp_package'] = fmcp_package
            # Convert install_path to string to avoid JSON serialization error
            raw_metadata['mcpServers'][package_name]['install_path'] = str(metadata_path)
            raw_metadata['mcpServers'][package_name]['port'] = find_free_port(taken_ports=taken_ports)
            # Add the port to the taken_ports set for later use
            taken_ports.add(raw_metadata['mcpServers'][package_name]['port'])
    
    # Write the updated metadata back to the file after collecting all the metadata 
    try:
        updated_metadata = raw_metadata
        # Write the updated metadata to the file
        with open(metadata_path, 'w') as file:
            file.write(json.dumps(updated_metadata, indent=2))
    except Exception as e:
        print(f"Error writing metadata file: {e}")

def main():
    '''
    Main function to handle command line arguments and execute the appropriate action.
    '''
    # Parse command line arguments with the commands given in setup.py 
    parser = argparse.ArgumentParser(description="FluidAI MCP CLI")
    subparsers = parser.add_subparsers(dest="command")

    # Add subparsers for different commands
    # install command 
    install_parser = subparsers.add_parser("install", help="Install a package")
    install_parser.add_argument("package", type=str, help="<author/package@version>")
    install_parser.add_argument("--master", action="store_true", help="Use master env file for API keys")

    # run command
    run_parser = subparsers.add_parser("run", help="Run a package")
    run_parser.add_argument("package", type=str, help="<package[@version]> or path to JSON file when --file is used")
    run_parser.add_argument("--port", type=int, help="Port for SuperGateway (default: 8111)")
    run_parser.add_argument("--start-server", action="store_true", help="Start FastAPI client server")
    run_parser.add_argument("--force-reload", action="store_true", help="Force reload by killing process on the port without prompt")
    run_parser.add_argument("--master", action="store_true", help="Use master metadata file from S3")
    run_parser.add_argument("--secure", action="store_true", help="Enable secure mode with bearer token authentication")
    run_parser.add_argument("--token", type=str, help="Bearer token for secure mode (if not provided, a token will be generated)")
    run_parser.add_argument("--file", action="store_true", help="Treat package argument as path to a local JSON configuration file")
    run_parser.add_argument("--s3", action="store_true", help="Treat package argument as path to S3 URL to a JSON file containing server configurations (format: s3://bucket-name/key)")

    # list command
    subparsers.add_parser("list", help="List installed packages")

    # edit-env commannd
    edit_env_parser = subparsers.add_parser("edit-env", help="Edit environment variables for a package")
    edit_env_parser.add_argument("package", type=str, help="<package[@version]>")

    # github command
    github_parser = subparsers.add_parser("github", help="Clone and run an MCP server from GitHub")
    github_parser.add_argument("repo", type=str, help="GitHub repo path or URL (e.g., owner/repo)")
    github_parser.add_argument("--github-token", required=True, help="GitHub access token with repo read permissions")
    github_parser.add_argument("--branch", type=str, help="Branch to clone (default: main)")
    github_parser.add_argument("--start-server", action="store_true", help="Start FastAPI client server")
    github_parser.add_argument("--force-reload", action="store_true", help="Force reload by killing process on the port without prompt")
    github_parser.add_argument("--secure", action="store_true", help="Enable secure mode with bearer token authentication")
    github_parser.add_argument("--token", type=str, help="Bearer token for secure mode (if not provided, a token will be generated)")

    # Parse the command line arguments and run the appropriate command to the subparsers 
    args = parser.parse_args()

    # Secure mode logic
    # Check if secure mode is enabled and if a token is provided
    secure_mode = getattr(args, "secure", False)
    token = getattr(args, "token", None)
    # If secure mode is enabled
    if secure_mode:
        # generate a token if not provided
        if not token:
            # Generate a secure random token
            token = secrets.token_urlsafe(32)
        # else use the provided token and set it in the environment variables
        os.environ["FMCP_BEARER_TOKEN"] = token
        os.environ["FMCP_SECURE_MODE"] = "true"
        print(f"Secure mode enabled. Bearer token: {token}")

    # Main Command dispatch Logic 
    if args.command == "install":
        install_command(args)
    elif args.command == "run":
        if hasattr(args, 's3') and args.s3:
            run_from_source("s3",args.package, secure_mode=secure_mode, token=token)
        elif hasattr(args, 'file') and args.file:
            # When --file flag is used, treat args.package as the file path
            run_from_source("file",args.package, secure_mode=secure_mode, token=token)
        elif args.package.lower() == "all":
            if args.master:
                run_all_master(args, secure_mode=secure_mode, token=token)
            else:
                run_all(secure_mode=secure_mode, token=token)
        else:
            run_server(args, secure_mode=secure_mode, token=token)
    elif args.command == "edit-env":
        edit_env(args)
    elif args.command == "github":
        run_github_server(args, secure_mode=secure_mode, token=token)
    elif args.command == "list":
        list_installed_packages()
    else:
        parser.print_help()
