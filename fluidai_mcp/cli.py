import argparse
import os
import sys
from pathlib import Path
import json
from loguru import logger
import secrets

from fluidai_mcp.services import (
    install_package,
    edit_env_variables,
    parse_package_string,
    resolve_config,
    run_servers,
)
from fluidai_mcp.services.package_installer import package_exists
from fluidai_mcp.services.package_list import get_latest_version_dir
from fluidai_mcp.services.config_resolver import INSTALLATION_DIR



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
    run_parser.add_argument("--no-start-server", action="store_false", dest="start_server", help="Don't start FastAPI client server")
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
        run_command(args, secure_mode=secure_mode, token=token)
    elif args.command == "edit-env":
        edit_env(args)
    elif args.command == "list":
        list_installed_packages()
    else:
        parser.print_help()


def run_command(args, secure_mode: bool = False, token: str = None) -> None:
    """
    Unified run command handler using the new architecture.

    Args:
        args: Parsed argparse namespace
        secure_mode: Enable bearer token authentication
        token: Bearer token for secure mode
    """
    try:
        # Resolve configuration from the appropriate source
        config = resolve_config(args)

        # Determine if this is a single package run
        single_package = not (
            getattr(args, 's3', False) or
            getattr(args, 'file', False) or
            args.package.lower() == "all"
        )

        # Run the servers
        run_servers(
            config=config,
            secure_mode=secure_mode,
            token=token,
            single_package=single_package,
            start_server=args.start_server,
            force_reload=args.force_reload
        )

    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error running servers: {e}")
        sys.exit(1)
