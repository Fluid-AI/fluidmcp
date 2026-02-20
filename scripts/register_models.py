#!/usr/bin/env python3
"""
Auto-register LLM models from a config file to a running fmcp serve instance.

Usage:
    # Recommended: Bearer token from environment variable (more secure)
    FMCP_BEARER_TOKEN=<token> python register_models.py <config_file> <server_url>

    # Alternative: Bearer token as positional argument (visible in process list)
    python register_models.py <config_file> <server_url> <bearer_token>

Environment Variables:
    FMCP_BEARER_TOKEN    Bearer token for API authentication (preferred over CLI arg)
    REPLICATE_API_TOKEN  Replicate API token (expanded from ${REPLICATE_API_TOKEN} in config)

Examples:
    # Secure method (recommended)
    FMCP_BEARER_TOKEN=mytoken123 python register_models.py railway-llama4-config.json http://localhost:8099

    # Legacy method (token visible in ps/top)
    python register_models.py railway-llama4-config.json http://localhost:8099 mytoken123
"""

import sys
import json
import time
import requests
import os


def load_config(config_path: str) -> dict:
    """Load configuration file with environment variable expansion."""
    with open(config_path, 'r') as f:
        config = json.load(f)

    # Track unexpanded variables for validation
    unexpanded_vars = []
    required_env_vars = set()  # Track all env vars referenced in config

    # Pre-scan config to find all env var references
    def find_env_vars(obj, path=""):
        """Find all environment variable references in config for pre-validation."""
        import re
        env_var_pattern = r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)'

        if isinstance(obj, dict):
            for k, v in obj.items():
                child_path = f"{path}.{k}" if path else k
                # Skip api_key fields (intentionally unexpanded)
                if k != "api_key":
                    find_env_vars(v, child_path)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                find_env_vars(item, f"{path}[{i}]")
        elif isinstance(obj, str):
            # Find all env var references
            matches = re.findall(env_var_pattern, obj)
            for match in matches:
                var_name = match[0] or match[1]  # Match either ${VAR} or $VAR
                required_env_vars.add(var_name)

    # Pre-validate: find all required env vars
    find_env_vars(config)

    # Check that all required env vars are set (except those that might be intentionally missing)
    missing_vars = []
    for var_name in required_env_vars:
        if var_name not in os.environ:
            missing_vars.append(var_name)

    if missing_vars:
        print("\n❌ ERROR: Required environment variables are not set:")
        for var_name in sorted(missing_vars):
            print(f"  {var_name}")
        print("\nPlease set these environment variables before running this script.")
        print("Note: api_key fields should reference env vars (e.g., ${REPLICATE_API_TOKEN}).")
        print("")
        raise SystemExit(1)

    # Recursively expand environment variables in config
    def expand_env_vars(obj, path=""):
        """
        Recursively expand environment variables in nested structures.

        IMPORTANT: Skips expansion for api_key fields to preserve placeholders.
        The server requires api_key as a placeholder (e.g., ${REPLICATE_API_TOKEN})
        and will expand it server-side, preventing plaintext storage in MongoDB.
        """
        if isinstance(obj, dict):
            result = {}
            for k, v in obj.items():
                child_path = f"{path}.{k}" if path else k
                # Skip expansion for api_key fields (must remain as placeholder)
                if k == "api_key" and isinstance(v, str):
                    result[k] = v  # Preserve placeholder (intentionally unexpanded)
                else:
                    result[k] = expand_env_vars(v, child_path)
            return result
        elif isinstance(obj, list):
            return [expand_env_vars(item, f"{path}[{i}]") for i, item in enumerate(obj)]
        elif isinstance(obj, str):
            # Use os.path.expandvars for safe expansion
            expanded = os.path.expandvars(obj)

            # Check if variable was not expanded (detect ${VAR} or $VAR patterns remaining)
            # Pattern matches env_utils.py for consistency (supports both upper and lowercase)
            import re
            if re.search(r'\$\{[A-Za-z_][A-Za-z0-9_]*\}|\$[A-Za-z_][A-Za-z0-9_]*', expanded):
                # Only track as unexpanded if NOT an intentionally preserved api_key placeholder
                # (api_key placeholders are skipped above and don't reach this check)
                unexpanded_vars.append((path, expanded))

            return expanded
        else:
            return obj

    result = expand_env_vars(config)

    # Warn about unexpanded variables (but don't fail - server validation will catch it)
    # NOTE: api_key placeholders are intentionally preserved and NOT included in this warning
    if unexpanded_vars:
        # Filter out api_key paths (intentionally preserved placeholders)
        non_api_key_unexpanded = [(p, v) for p, v in unexpanded_vars
                                   if ".api_key" not in p and not p.endswith("api_key")]

        if non_api_key_unexpanded:
            # Hard failure for non-api_key unexpanded variables
            print("\n❌ ERROR: Required environment variables were not expanded:")
            for path, value in non_api_key_unexpanded:
                print(f"  {path}: {value}")
            print("\nMake sure all required environment variables are set before running this script.")
            print("Note: api_key fields are intentionally preserved as placeholders for server-side expansion.")
            print("")
            raise SystemExit(1)

    return result


def wait_for_server(server_url: str, max_retries: int = 30, delay: int = 2):
    """Wait for fmcp serve to be ready."""
    health_url = f"{server_url}/health"

    print(f"Waiting for server at {server_url}...")

    for attempt in range(max_retries):
        try:
            response = requests.get(health_url, timeout=5)
            if response.status_code == 200:
                print(f"✓ Server is ready!")
                return True
        except requests.exceptions.RequestException as e:
            print(f"  Attempt {attempt + 1}/{max_retries}: Server not ready yet...")

        if attempt < max_retries - 1:
            time.sleep(delay)

    print(f"✗ Server did not become ready after {max_retries} attempts")
    return False


def sanitize_config(config: dict) -> dict:
    """
    Remove sensitive fields for logging.

    Redacts api_key, api_token, auth_token, password, secret, and token fields.
    """
    sanitized = config.copy()
    sensitive_fields = {'api_key', 'api_token', 'auth_token', 'password', 'secret', 'token', 'bearer_token'}

    for field in sensitive_fields:
        if field in sanitized:
            key = sanitized[field]
            # Show only last 4 chars if string and longer than 4 chars
            if isinstance(key, str):
                sanitized[field] = '***' + key[-4:] if len(key) > 4 else '***'
            else:
                sanitized[field] = '***'

    return sanitized


def check_model_exists(server_url: str, bearer_token: str, model_id: str) -> bool:
    """
    Check if a model already exists (from MongoDB or previous registration).

    Returns:
        True if model exists, False if not found or on error
    """
    url = f"{server_url}/api/llm/models"
    headers = {"Authorization": f"Bearer {bearer_token}"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        models_data = response.json()
        existing_ids = [m["id"] for m in models_data.get("models", [])]
        return model_id in existing_ids
    except requests.exceptions.RequestException as e:
        # Network/auth/server error: log and continue (will attempt registration)
        print(f"⚠ Error checking if model {model_id} exists: {e}")
        print(f"  Will attempt registration anyway...")
        return False
    except (ValueError, json.JSONDecodeError, KeyError) as e:
        # Unexpected response format: log and assume model does not exist
        print(f"⚠ Unexpected response while checking model {model_id}: {e}")
        return False


def register_model(server_url: str, bearer_token: str, model_id: str, model_config: dict):
    """
    Register a single model via the API.

    Returns:
        tuple: (success: bool, was_new: bool) where was_new indicates if this was a new registration
    """
    # COPILOT COMMENT 3 FIX: Removed redundant early existence check
    # The API endpoint (POST /api/llm/models) already checks for duplicates atomically inside a lock
    # Checking here creates a TOCTOU race condition where another process could register between our check and the POST
    # The API will return 400 if the model already exists, which we handle in the exception logic below

    url = f"{server_url}/api/llm/models"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {bearer_token}"
    }

    # COPILOT COMMENT 4 FIX: Improved model_id mismatch warning clarity
    # Prepare payload - ensure model_id from config doesn't override function argument
    config_model_id = model_config.get("model_id")
    if config_model_id is not None and config_model_id != model_id:
        print(
            f"⚠ WARNING: Configuration contains model_id='{config_model_id}' but key in llmModels is '{model_id}'.\n"
            f"  The key name takes precedence. Registering as '{model_id}' (ignoring '{config_model_id}' from config).\n"
            f"  To fix: Remove 'model_id' field from the config, or ensure it matches the key name."
        )
    # Filter out model_id from model_config to prevent override
    filtered_model_config = {k: v for k, v in model_config.items() if k != "model_id"}
    payload = {
        "model_id": model_id,
        **filtered_model_config
    }

    print(f"Registering model: {model_id}...")
    print(f"  Config: {sanitize_config(model_config)}")

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        # Parse JSON response with error handling
        try:
            result = response.json()
        except (ValueError, json.JSONDecodeError) as e:
            print(f"✗ Server returned invalid JSON for {model_id}: {e}")
            print(f"  Response status: {response.status_code}")
            print(f"  Response preview: {response.text[:200]}...")
            return (False, False)

        print(f"✓ Successfully registered: {model_id}")
        print(f"  Status: {result.get('status')}")
        print(f"  Persisted to MongoDB: {result.get('persisted', 'unknown')}")
        return (True, True)  # Success, and it was a new registration

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 400 and "already registered" in e.response.text:
            print(f"⚠ Model {model_id} already registered, skipping...")
            return (True, False)  # Success, but not a new registration
        else:
            print(f"✗ Failed to register {model_id}: {e}")
            print(f"  Status: {e.response.status_code}")
            # Don't print full response (may contain echoed api_key)
            return (False, False)

    except requests.exceptions.RequestException as e:
        print(f"✗ Network error registering {model_id}: {e}")
        return (False, False)
    except Exception as e:
        print(f"✗ Unexpected error registering {model_id}: {e}")
        return (False, False)


def main():
    # Support both command-line args and environment variables
    # Prefer env var for security (not visible in ps output)
    if len(sys.argv) == 3:
        # Token from environment variable (secure)
        config_path = sys.argv[1]
        server_url = sys.argv[2].rstrip('/')
        bearer_token = os.getenv("FMCP_BEARER_TOKEN")

        if not bearer_token:
            print("ERROR: FMCP_BEARER_TOKEN environment variable not set")
            print("Usage: FMCP_BEARER_TOKEN=<token> python register_models.py <config_file> <server_url>")
            sys.exit(1)

        print("✓ Using bearer token from environment variable (secure)")

    elif len(sys.argv) == 4:
        # Token from command line (legacy, insecure)
        config_path = sys.argv[1]
        server_url = sys.argv[2].rstrip('/')
        bearer_token = sys.argv[3]

        print("⚠️  WARNING: Bearer token passed as command-line argument")
        print("⚠️  This is visible in process list (ps/top)")
        print("⚠️  Use environment variable instead: FMCP_BEARER_TOKEN=<token>")

    else:
        print("Usage:")
        print("  Secure:   FMCP_BEARER_TOKEN=<token> python register_models.py <config_file> <server_url>")
        print("  Legacy:   python register_models.py <config_file> <server_url> <bearer_token>")
        print()
        print("Examples:")
        print("  FMCP_BEARER_TOKEN=mytoken python register_models.py config.json http://localhost:8099")
        print("  python register_models.py config.json http://localhost:8099 mytoken")
        sys.exit(1)

    print("=" * 60)
    print("FluidMCP Model Registration Script")
    print("=" * 60)
    print(f"Config file: {config_path}")
    print(f"Server URL: {server_url}")
    print(f"Bearer token: {'*' * min(len(bearer_token), 10)}")
    print()

    # Load config
    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"✗ Failed to load config file: {e}")
        sys.exit(1)

    # Wait for server
    if not wait_for_server(server_url):
        print("✗ Server not ready, aborting")
        sys.exit(1)

    print()

    # Register models
    llm_models = config.get("llmModels", {})

    if not llm_models:
        print("⚠ No llmModels found in config file")
        sys.exit(0)

    print(f"Found {len(llm_models)} model(s) to register")
    print()

    success_count = 0
    failed_count = 0
    registered_models = []  # Track successfully registered models for rollback

    for model_id, model_config in llm_models.items():
        # Register model (no pre-check to avoid race condition)
        success, was_new = register_model(server_url, bearer_token, model_id, model_config)

        if success:
            success_count += 1
            # Only track newly registered models (not pre-existing ones)
            if was_new:
                registered_models.append(model_id)
        else:
            failed_count += 1
            # Rollback: unregister all successfully registered models from this run
            if registered_models and os.getenv("FMCP_ROLLBACK_ON_FAILURE", "false").lower() == "true":
                print()
                print("=" * 60)
                print("⚠️  Registration failed, rolling back...")
                print("=" * 60)

                # Track rollback results
                rollback_succeeded = []
                rollback_failed = []

                for rollback_id in registered_models:
                    try:
                        delete_url = f"{server_url}/api/llm/models/{rollback_id}"
                        headers = {"Authorization": f"Bearer {bearer_token}"}
                        response = requests.delete(delete_url, headers=headers, timeout=10)
                        if response.status_code == 200:
                            print(f"✓ Rolled back {rollback_id}")
                            rollback_succeeded.append(rollback_id)
                        else:
                            print(f"✗ Failed to rollback {rollback_id}: {response.status_code}")
                            rollback_failed.append(rollback_id)
                    except Exception as e:
                        print(f"✗ Error rolling back {rollback_id}: {e}")
                        rollback_failed.append(rollback_id)

                # Report rollback results
                print()
                print(f"Rollback complete: {len(rollback_succeeded)} succeeded, {len(rollback_failed)} failed")
                if rollback_failed:
                    print(f"\n⚠️  WARNING: {len(rollback_failed)} models were NOT rolled back:")
                    for model_id in rollback_failed:
                        print(f"  - {model_id}")
                    print("\nThese models may need manual cleanup.")
                print()
            break  # Stop registration after first failure
        print()

    # Summary
    print("=" * 60)
    print("Registration Summary")
    print("=" * 60)
    print(f"✓ Successful: {success_count}")
    print(f"✗ Failed: {failed_count}")
    print(f"Total: {len(llm_models)}")

    if failed_count > 0:
        print()
        print("Note: Set FMCP_ROLLBACK_ON_FAILURE=true to automatically rollback on failure")
        sys.exit(1)

    print()
    print("✓ All models registered successfully!")


if __name__ == "__main__":
    main()
