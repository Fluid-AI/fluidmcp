import argparse
import os
import sys
from pathlib import Path
import json
from loguru import logger
import secrets
import importlib.metadata
import platform
import shutil
from dotenv import load_dotenv

from .services import (
    install_package,
    edit_env_variables,
    parse_package_string,
    resolve_config,
    run_servers,
)
from .services.package_installer import package_exists
from .services.package_list import get_latest_version_dir
from .services.config_resolver import INSTALLATION_DIR


def configure_logger(verbose: bool = False) -> None:
    """
    Configure loguru logger based on verbosity flag.

    Args:
        verbose: If True, set level to DEBUG; otherwise INFO
    """
    # Remove default handler
    logger.remove()

    # Set level based on verbose flag
    log_level = "DEBUG" if verbose else "INFO"

    # Add new handler with specified level and simple format
    logger.add(
        sys.stderr,
        level=log_level,
        format="<level>{message}</level>",
        colorize=True
    )



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

def print_version_info() -> None:
    '''
    Print version details about FluidMCP.
    args:
        none
    returns:
        none
    '''
    logger.debug("Retrieving FluidMCP version information")
    try:
        package_name = "fluidmcp"

        version = importlib.metadata.version(package_name)
        dist = importlib.metadata.distribution(package_name)
        install_path = dist.locate_file("")

        logger.debug(f"Version: {version}, Install path: {install_path}")

        print(f"FluidMCP version: {version}")
        print(f"Python version: {platform.python_version()}")
        print(f"Installation path: {install_path}")

    except importlib.metadata.PackageNotFoundError:
        logger.exception("FluidMCP package metadata not found")
        print("FluidMCP is not installed as a package")
        sys.exit(1)
    
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
        install_dir = Path(INSTALLATION_DIR)
        logger.debug(f"Checking installation directory: {install_dir}")

        # Check if the directory is empty
        if not install_dir.exists() or not any(install_dir.iterdir()):
            logger.info("No mcp packages found")
            # return none if the directory is empty
            return

        logger.info(f"Installation directory: {install_dir}")
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
                                logger.info(f"{author.name}/{pkg.name}@{version.name}")
        if not found_packages:
            logger.info("No packages found in the installation directory structure")
    except Exception:
        # Handle any errors that occur while listing packages
        logger.exception("Error listing installed packages")


def get_token_file() -> Path:
    """Get path to token file."""
    return Path.home() / ".fmcp" / "tokens" / "current_token.txt"


def token_show() -> None:
    """Display the current saved token."""
    token_file = get_token_file()

    if not token_file.exists():
        logger.error("No token found. Generate one with: fluidmcp serve --secure")
        logger.error("Or: fluidmcp token regenerate")
        sys.exit(1)

    token = token_file.read_text().strip()

    print("\n" + "="*70)
    print("🔐 CURRENT BEARER TOKEN:")
    print("="*70)
    print(f"\n{token}\n")
    print("="*70)
    print(f"Saved at: {token_file}")
    print("="*70 + "\n")


def token_regenerate() -> None:
    """Generate and save a new token."""
    token = secrets.token_urlsafe(32)

    token_dir = get_token_file().parent
    token_dir.mkdir(parents=True, exist_ok=True)

    token_file = get_token_file()
    token_file.write_text(token)
    token_file.chmod(0o600)

    print("\n" + "="*70)
    print("🔐 NEW BEARER TOKEN GENERATED:")
    print("="*70)
    print(f"\n{token}\n")
    print("="*70)
    print(f"Saved to: {token_file}")
    print("Use this token with: fluidmcp serve --secure --token <token>")
    print("="*70 + "\n")

    logger.info("New bearer token generated and saved")


def token_clear() -> None:
    """Remove the saved token."""
    token_file = get_token_file()

    if not token_file.exists():
        logger.info("No token file to clear")
        return

    token_file.unlink()
    logger.info(f"Token cleared from {token_file}")
    print("Token removed successfully")


def validate_command(args) -> None:
    """
    Validate MCP configuration without running servers.

    Args:
        args (argparse.Namespace): Parsed CLI arguments

    Returns:
        None

    Separates validation issues into errors (fatal) and warnings (non-fatal).
    Exits with code 1 if errors are found, code 0 if only warnings or success.
    """
    logger.debug(f"validate_command called for package: {args.package}")
    logger.debug(f"File mode: {getattr(args, 'file', False)}")

    errors = []
    warnings = []

    try:
        # 1. Resolve configuration from the appropriate source
        logger.debug("Resolving configuration")
        config = resolve_config(args)
        logger.debug(f"Configuration resolved with {len(config.servers)} server(s)")

    except FileNotFoundError as e:
        errors.append(str(e))

    except ValueError as e:
        errors.append(f"Configuration error: {e}")

    except Exception as e:
        errors.append(f"Unexpected error while resolving config: {e}")

    if errors:
        print("❌ Validation failed with the following errors:")

        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    # 2. Validate command availability
    logger.debug("Validating command availability")
    for server_name, server_cfg in config.servers.items():
        command = server_cfg.get("command")

        if not command:
            errors.append(f"Missing command for server '{server_name}'")
            continue

        if shutil.which(command) is None:
            errors.append(
                f"Command '{command}' not found in PATH (server: {server_name})"
            )


    # 3. Check environment variables & token validation
    logger.debug("Validating environment variables")
    for server_name, server_cfg in config.servers.items():
        env_cfg = server_cfg.get("env", {})

        for key, val in env_cfg.items():
            # Structured format: {required: true/false, value: "..."}
            if isinstance(val, dict):
                required = val.get("required", False)
                value = val.get("value")

                # Check if value is provided or available in environment
                # Try both original case and uppercase (common env var convention)
                env_value = os.environ.get(key) or os.environ.get(key.upper())
                has_value = value or env_value

                if required and not has_value:
                    # Missing required env var is an ERROR
                    errors.append(f"Missing required env var '{key}' (server: {server_name})")
                elif not required and not has_value:
                    # Missing optional env var is a WARNING
                    warnings.append(f"Optional env var '{key}' is not set (server: {server_name})")

            # Simple format: "KEY": "value" or "KEY": ""
            else:
                # Try both original case and uppercase (common env var convention)
                env_value = os.environ.get(key) or os.environ.get(key.upper())
                has_value = val or env_value

                if not has_value:
                    # Check if it's a TOKEN variable (case-insensitive check)
                    if key.upper().endswith("TOKEN"):
                        # Missing TOKEN is a WARNING (not explicitly marked as required)
                        warnings.append(f"Token env var '{key}' is not set (server: {server_name})")
                    else:
                        # Missing non-token env var is a WARNING
                        warnings.append(f"Env var '{key}' is not set (server: {server_name})")

    # Print results
    logger.debug(f"Validation complete: {len(errors)} error(s), {len(warnings)} warning(s)")

    if errors:
        logger.error(f"Validation failed with {len(errors)} error(s)")
        print("❌ Configuration validation failed with errors:")
        for err in errors:
            print(f"  - {err}")
        if warnings:
            print("\n⚠️  Warnings:")
            for warn in warnings:
                print(f"  - {warn}")
        sys.exit(1)
    elif warnings:
        logger.warning(f"Validation passed with {len(warnings)} warning(s)")
        print("⚠️  Configuration is valid with warnings:")
        for warn in warnings:
            print(f"  - {warn}")
        print("\n✔ No fatal errors found. You may proceed, but consider addressing the warnings above.")
        sys.exit(0)
    else:
        logger.info("Validation passed with no issues")
        print("✔ Configuration is valid with no issues found.")
        sys.exit(0)


def edit_env(args):
    '''
    Edit environment variables for a package.
    args:
        args (argparse.Namespace): The parsed command line arguments.
    returns:
        None
    '''
    logger.debug(f"edit_env called for package: {args.package}")
    try:
        dest_dir = resolve_package_dest_dir(args.package)
        logger.debug(f"Resolved package directory: {dest_dir}")
        if not package_exists(dest_dir):
            logger.error(f"Package not found at {dest_dir}. Have you installed it?")
            sys.exit(1)
        edit_env_variables(dest_dir)
    except Exception:
        logger.exception("Error editing environment variables")
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
    logger.debug(f"install_command called for package: {args.package}")
    master_mode = getattr(args, "master", False)
    logger.debug(f"Master mode: {master_mode}")

    pkg = parse_package_string(args.package)
    # Install the package, skip env prompts if --master
    install_package(args.package, skip_env=master_mode)
    try:
        dest_dir = resolve_package_dest_dir(args.package)
    except Exception:
        logger.exception("Package resolution failed")
        sys.exit(1)
    if not package_exists(dest_dir):
        logger.error(f"Package not found at {dest_dir}. Have you installed it?")
        sys.exit(1)
    if master_mode:
        logger.debug("Updating environment from common .env file")
        update_env_from_common_env(dest_dir, pkg)


def github_command(args, secure_mode: bool = False, token: str = None) -> None:
    """
    Clone and run an MCP server directly from a GitHub repository.

    Args:
        args: Parsed command line arguments with repo, github_token, branch
        secure_mode: Enable bearer token authentication
        token: Bearer token for secure mode
    """
    from .services import (
        clone_github_repo,
        extract_or_create_metadata,
    )
    from .services.package_launcher import launch_mcp_using_fastapi_proxy
    from .services.network_utils import is_port_in_use, kill_process_on_port
    from fastapi import FastAPI
    import uvicorn

    logger.debug(f"github_command called for repo: {args.repo}")
    logger.debug(f"Branch: {args.branch}, Secure mode: {secure_mode}")

    # Get port configuration
    client_server_port = int(os.environ.get("MCP_CLIENT_SERVER_PORT", "8090"))
    logger.debug(f"Using port: {client_server_port}")

    try:
        # Set up secure mode
        if secure_mode and token:
            os.environ["FMCP_BEARER_TOKEN"] = token
            os.environ["FMCP_SECURE_MODE"] = "true"
            logger.info("Secure mode enabled with bearer token")

        # Clone the repository
        logger.info(f"Cloning GitHub repository: {args.repo}")
        dest_dir = clone_github_repo(args.repo, args.github_token, args.branch)
        logger.debug(f"Repository cloned to: {dest_dir}")

        # Extract or create metadata.json
        logger.info("Processing metadata")
        metadata_path = extract_or_create_metadata(dest_dir)
        logger.debug(f"Metadata processed: {metadata_path}")

        # Launch the MCP server
        logger.info("Launching MCP server")
        package_name, router = launch_mcp_using_fastapi_proxy(dest_dir)

        if not router:
            logger.error("Failed to launch MCP server")
            sys.exit(1)

        logger.info(f"MCP server '{package_name}' launched successfully from GitHub")

        # Start FastAPI server if requested
        if args.start_server:
            logger.debug("Starting FastAPI server")
            # Check if port is in use
            if is_port_in_use(client_server_port):
                logger.warning(f"Port {client_server_port} is already in use")
                if args.force_reload:
                    logger.info(f"Force reloading server on port {client_server_port}")
                    kill_process_on_port(client_server_port)
                else:
                    choice = input("Kill existing process and reload? (y/n): ").strip().lower()
                    if choice == 'y':
                        kill_process_on_port(client_server_port)
                    elif choice == 'n':
                        logger.info(f"Keeping existing process on port {client_server_port}")
                        return
                    else:
                        print("Invalid choice. Aborting")
                        return

            # Create FastAPI app
            app = FastAPI(
                title=f"FluidMCP Server - {package_name}",
                description=f"Gateway for {package_name} MCP server from GitHub",
                version="2.0.0"
            )

            app.include_router(router, tags=[package_name])

            logger.info(f"Starting FastAPI server for {package_name}")
            logger.info(f"Swagger UI available at: http://localhost:{client_server_port}/docs")

            uvicorn.run(app, host="0.0.0.0", port=client_server_port)

    except ValueError:
        logger.exception("Configuration error")
        sys.exit(1)
    except RuntimeError:
        logger.exception("Runtime error")
        sys.exit(1)
    except Exception:
        logger.exception("Error running GitHub MCP server")
        sys.exit(1)


def main():
    '''
    Main function to handle command line arguments and execute the appropriate action.
    '''
    # Load environment variables from .env file
    env_path = Path(__file__).parent / '.env'
    load_dotenv(dotenv_path=env_path)

    # Parse command line arguments with the commands given in setup.py
    parser = argparse.ArgumentParser(description="FluidAI MCP CLI")

    # Add global flags
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging (DEBUG level)")
    parser.add_argument("--version", action="store_true", help="Show FluidMCP version information and exit")

    subparsers = parser.add_subparsers(dest="command")

    # Add subparsers for different commands
    # install command
    install_parser = subparsers.add_parser("install", help="Install a package")
    install_parser.add_argument("package", type=str, help="<author/package@version>")
    install_parser.add_argument("--master", action="store_true", help="Use master env file for API keys")
    install_parser.add_argument("--verbose", action="store_true", help="Enable verbose logging (DEBUG level)")

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
    run_parser.add_argument("--verbose", action="store_true", help="Enable verbose logging (DEBUG level)")

    # list command
    list_parser = subparsers.add_parser("list", help="List installed packages")
    list_parser.add_argument("--verbose", action="store_true", help="Enable verbose logging (DEBUG level)")

    # token command - Manage bearer tokens
    token_parser = subparsers.add_parser("token", help="Manage bearer tokens for secure mode")
    token_subparsers = token_parser.add_subparsers(dest="token_command", help="Token management commands")

    # token show
    token_show_parser = token_subparsers.add_parser("show", help="Display current saved token")

    # token regenerate
    token_regen_parser = token_subparsers.add_parser("regenerate", help="Generate and save a new token")

    # token clear
    token_clear_parser = token_subparsers.add_parser("clear", help="Remove saved token")

    # edit-env commannd
    edit_env_parser = subparsers.add_parser("edit-env", help="Edit environment variables for a package")
    edit_env_parser.add_argument("package", type=str, help="<package[@version]>")
    edit_env_parser.add_argument("--verbose", action="store_true", help="Enable verbose logging (DEBUG level)")

    # github command
    github_parser = subparsers.add_parser("github", help="Clone and run an MCP server from GitHub")
    github_parser.add_argument("repo", type=str, help="GitHub repo path or URL (e.g., owner/repo)")
    github_parser.add_argument("--github-token", required=True, help="GitHub access token with repo read permissions")
    github_parser.add_argument("--branch", type=str, help="Branch to clone (default: main)")
    github_parser.add_argument("--start-server", action="store_true", help="Start FastAPI client server")
    github_parser.add_argument("--force-reload", action="store_true", help="Force reload by killing process on the port without prompt")
    github_parser.add_argument("--secure", action="store_true", help="Enable secure mode with bearer token authentication")
    github_parser.add_argument("--token", type=str, help="Bearer token for secure mode (if not provided, a token will be generated)")
    github_parser.add_argument("--verbose", action="store_true", help="Enable verbose logging (DEBUG level)")

    # serve command - NEW: Run as standalone API server
    serve_parser = subparsers.add_parser("serve", help="Run as standalone API server (backend starts without MCP servers)")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    serve_parser.add_argument("--port", type=int, default=8099, help="Port to listen on (default: 8099)")
    serve_parser.add_argument("--mongodb-uri",
                              default=os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
                              help="MongoDB connection URI (default: env MONGODB_URI or mongodb://localhost:27017)")
    serve_parser.add_argument("--database", default="fluidmcp",
                              help="MongoDB database name (default: fluidmcp)")
    serve_parser.add_argument("--secure", action="store_true",
                              help="Enable secure mode with bearer token authentication (RECOMMENDED)")
    serve_parser.add_argument("--allow-insecure", action="store_true",
                              help="Explicitly allow running without authentication (NOT RECOMMENDED)")
    serve_parser.add_argument("--token", type=str,
                              help="Bearer token for secure mode (will be generated if not provided)")
    serve_parser.add_argument("--persistence-mode", choices=['mongodb', 'memory'], default='mongodb',
                              help="Persistence backend: 'mongodb' (default) or 'memory' (in-memory, data lost on restart)")
    serve_parser.add_argument("--in-memory", action="store_true",
                              help="Use in-memory persistence (shorthand for --persistence-mode memory)")
    serve_parser.add_argument("--verbose", action="store_true", help="Enable verbose logging (DEBUG level)")

    # validate comand
    validate_parser = subparsers.add_parser("validate", help="Validate MCP configuration without running servers")
    validate_parser.add_argument("package", type=str, help="<package[@version]> or path to JSON file when --file is used")
    validate_parser.add_argument("--file", action="store_true", help="Treat package argument as path to a local JSON configuration file")
    validate_parser.add_argument("--verbose", action="store_true", help="Enable verbose logging (DEBUG level)")

    # Parse the command line arguments and run the appropriate command to the subparsers
    args = parser.parse_args()

    # Configure logger based on verbose flag
    configure_logger(verbose=getattr(args, "verbose", False))
    logger.debug(f"CLI started with command: {args.command}")

    # Secure mode logic
    # Check if secure mode is enabled and if a token is provided
    secure_mode = getattr(args, "secure", False)
    token = getattr(args, "token", None)
    # If secure mode is enabled
    if secure_mode:
        logger.debug("Secure mode requested")
        # generate a token if not provided
        if not token:
            # Generate a secure random token
            token = secrets.token_urlsafe(32)
            logger.debug("Generated new bearer token")
        else:
            logger.debug("Using provided bearer token")
        # else use the provided token and set it in the environment variables
        os.environ["FMCP_BEARER_TOKEN"] = token
        os.environ["FMCP_SECURE_MODE"] = "true"
        logger.info(f"Secure mode enabled. Bearer token (prefix: {token[:8]}...)")

    # version flag
    if args.version:
        print_version_info()
        sys.exit(0)

    # Main Command dispatch Logic
    if args.command == "install":
        logger.debug(f"Dispatching to install_command for package: {args.package}")
        install_command(args)
    elif args.command == "validate":
        validate_command(args)
    elif args.command == "run":
        logger.debug(f"Dispatching to run_command for: {args.package}")
        run_command(args, secure_mode=secure_mode, token=token)
    elif args.command == "edit-env":
        logger.debug(f"Dispatching to edit_env for package: {args.package}")
        edit_env(args)
    elif args.command == "github":
        logger.debug(f"Dispatching to github_command for repo: {args.repo}")
        github_command(args, secure_mode=secure_mode, token=token)
    elif args.command == "list":
        logger.debug("Dispatching to list_installed_packages")
        list_installed_packages()
    elif args.command == "token":
        if args.token_command == "show":
            token_show()
        elif args.token_command == "regenerate":
            token_regenerate()
        elif args.token_command == "clear":
            token_clear()
        else:
            token_parser.print_help()
    elif args.command == "serve":
        # Check authentication requirements
        if not args.secure and not getattr(args, 'allow_insecure', False):
            logger.error("❌ ERROR: Server requires authentication for security")
            logger.error("❌ Use --secure to enable authentication (recommended)")
            logger.error("❌ Or use --allow-insecure to explicitly disable (NOT recommended)")
            sys.exit(1)

        if getattr(args, 'allow_insecure', False):
            logger.warning("⚠️  WARNING: Running in INSECURE mode - no authentication!")
            logger.warning("⚠️  Anyone can access this API without credentials!")
            logger.warning("⚠️  This should ONLY be used for local development!")

        # Run standalone API server
        from .server import main as server_main
        import asyncio

        # Generate token if secure mode enabled but no token provided
        if secure_mode and not token:
            token = secrets.token_urlsafe(32)
            logger.info(f"Generated bearer token: {token}")

        try:
            asyncio.run(server_main(args))
        except KeyboardInterrupt:
            logger.info("Server interrupted by user")
        except Exception as e:
            logger.exception(f"Server error: {e}")
            sys.exit(1)
    else:
        logger.debug("No command specified, showing help")
        parser.print_help()


def run_command(args, secure_mode: bool = False, token: str = None) -> None:
    """
    Unified run command handler using the new architecture.

    Args:
        args: Parsed argparse namespace
        secure_mode: Enable bearer token authentication
        token: Bearer token for secure mode
    """
    logger.debug("=== run_command started ===")
    logger.debug(f"Arguments - package: {args.package}, s3: {getattr(args, 's3', False)}, file: {getattr(args, 'file', False)}")
    logger.debug(f"Arguments - start_server: {getattr(args, 'start_server', False)}, force_reload: {getattr(args, 'force_reload', False)}")

    try:
        # Resolve configuration from the appropriate source
        config = resolve_config(args)

        # Determine if this is a single package run
        single_package = not (
            getattr(args, 's3', False) or
            getattr(args, 'file', False) or
            args.package.lower() == "all"
        )
        logger.debug(f"Single package mode determined: {single_package}")

        # Run the servers
        run_servers(
            config=config,
            secure_mode=secure_mode,
            token=token,
            single_package=single_package,
            start_server=getattr(args, 'start_server', False),
            force_reload=getattr(args, 'force_reload', False)
        )

    except FileNotFoundError:
        logger.exception("File not found error")
        sys.exit(1)
    except ValueError:
        logger.exception("Configuration error")
        sys.exit(1)
    except Exception:
        logger.exception("Error running servers")
        sys.exit(1)
