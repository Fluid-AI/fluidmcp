import os
import json
from pathlib import Path
import subprocess
from typing import Union
from loguru import logger
from typing import Dict, Any

def edit_env_variables(dest_dir: Union[str, Path]):

    '''
    Interactive environment variable editor for a package.
    
    Allows users to view and modify environment variables defined in a package's
    metadata.json file.
    
    Args:
        dest_dir (str or Path): The directory containing the metadata.json file.
        
    Returns:
        None
    '''

    dest_dir = Path(dest_dir)
    logger.info(f"Editing environment variables for package in {dest_dir}")
    metadata_path = dest_dir / "metadata.json"

    # Check if metadata.json exists
    if not metadata_path.exists():
        logger.warning(f"No metadata.json found at {metadata_path}")
        return
    
    try:
        # Read metadata.json
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
        
        try:
            pkg = list(metadata["mcpServers"].keys())[0]
        except (KeyError, IndexError, TypeError):
            logger.warning("No package found in metadata.json")
            return

        # Check if env variables exist
        if "env" not in metadata['mcpServers'][pkg]:
            logger.info("No environment variables found for this package")
            return
        
        env_vars = metadata['mcpServers'][pkg]["env"]
        
        # Display package information

        logger.info(f"Editing environment variables for {pkg}")
        
        # Create a list of environment variables with their information
        env_list = []
        for key, value in env_vars.items():
            if isinstance(value, dict):
                # Handle structured format
                required = value.get("required", False)
                description = value.get("description", f"Environment variable: {key}")
                current_value = value.get("value", "")
                env_list.append({
                    "key": key,
                    "description": description,
                    "required": required,
                    "current_value": current_value,
                    "structured": True
                })
            else:
                # Handle simple key-value format
                env_list.append({
                    "key": key,
                    "description": f"Environment variable: {key}",
                    "required": False,
                    "current_value": value,
                    "structured": False
                })
        
        # Initialize variables for tracking changes
        modified_vars = set()
        
        # Start interactive loop
        while True:
            # Display available environment variables
            print(f"\nFound {len(env_list)} environment variables:")
            for i, env_var in enumerate(env_list, 1):
                # Prepare display string
                required_tag = " [Required]" if env_var["required"] else ""
                modified_tag = " [Modified]" if env_var["key"] in modified_vars else ""
                print(f"{i}. {env_var['key']}: {env_var['description']}{required_tag}{modified_tag}")

            # Prompt user for selection
            choice = input("\nEnter number to edit (or 'q' to quit): ").strip().lower()
            
            # Check if user wants to quit
            if choice == 'q':
                break
            
            # Validate choice
            try:
                index = int(choice) - 1
                if not (0 <= index < len(env_list)):
                    print(f"Invalid selection. Please enter a number between 1 and {len(env_list)}")
                    continue
            except ValueError:
                print("Invalid input. Please enter a number or 'q' to quit")
                continue
            
            # Get selected environment variable
            selected_var = env_list[index]
            print(f"\nSelected: {selected_var['key']} ({selected_var['description']})")

            # Display current value (mask sensitive data)
            masked_value = "******" if "api" in selected_var["key"].lower() or "key" in selected_var["key"].lower() or "token" in selected_var["key"].lower() else selected_var["current_value"]
            print(f"Current value: {masked_value}")

            # Prompt for new value
            new_value = input("Enter new value (or press Enter to keep current value): ").strip()
            
            # Update value if changed
            if new_value:
                # Update in env_list
                env_list[index]["current_value"] = new_value
                # Mark as modified
                modified_vars.add(selected_var["key"])
                print(f"{selected_var['key']} updated successfully")
            else:
                print(f"No changes made to {selected_var['key']}")
        
        # If changes were made, update metadata.json
        if modified_vars:
            logger.info("Saving changes to metadata.json")
            
            # Update metadata with new values
            for env_var in env_list:
                key = env_var["key"]
                if key in modified_vars:
                    if env_var["structured"]:
                        # Update the value field in structured format
                        metadata['mcpServers'][pkg]["env"][key]["value"] = env_var["current_value"]
                    else:
                        # Update directly for simple format
                        metadata['mcpServers'][pkg]["env"][key] = env_var["current_value"]
            
            # Write updated metadata back to file
            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=2)

            logger.info(f"Successfully updated {len(modified_vars)} environment variable(s)")
        else:
            logger.info("No changes were made")

    except Exception:
        logger.exception("Error editing environment variables")


def write_keys_during_install(dest_dir: Union[str, Path], pkg: Dict[str, str], skip_env: bool = False):
    '''
    Process metadata.json and ask for API keys during installation.
    args:
        dest_dir (str or Path): The directory containing the metadata.json file.
        pkg (Dict): The package information dictionary.
        skip_env (bool): If True, skip asking for API keys (used for --master).
    returns:
        None
    '''
    # Convert dest_dir to Path object
    metadata_path = dest_dir / "metadata.json"
    
    # Check if metadata.json exists
    if metadata_path.exists():

        logger.info("Reading metadata.json for API key configuration")
        try:
            with open(metadata_path, "r") as f:
                metadata = json.load(f)
            
            # Check if metadata has environment variables that need API keys
            if "env" in metadata['mcpServers'][pkg["package_name"]]:
                if skip_env:
                    # Do not prompt for API keys in master mode
                    return
                env_vars = process_env_variables(metadata['mcpServers'][pkg["package_name"]]["env"])
                if env_vars:
                    logger.info("Saving API key(s) to metadata.json")
                    
                    # Update the metadata.json with the provided API keys
                    for key, value in env_vars.items():
                        if isinstance(metadata['mcpServers'][pkg["package_name"]]["env"][key], dict):
                            # Update the "value" field in the structured format
                            metadata['mcpServers'][pkg["package_name"]]["env"][key]["value"] = value
                        else:
                            # Update directly for simple key-value pairs
                            metadata['mcpServers'][pkg["package_name"]]["env"][key] = value
                    
                    # Write the updated metadata back to the file
                    with open(metadata_path, "w") as f:
                        json.dump(metadata, f, indent=2)


                    logger.info("API key(s) saved to metadata.json")
            else:
                logger.info("No environment variables found for this package")
        except Exception:
            logger.exception("Error processing metadata.json")

def process_env_variables(env_config: Dict[str, Any]) -> Dict[str, str]:
    """
    Process environment variables configuration and prompt for API keys if needed.
    
    Args:
        env_config (Dict): The environment configuration from metadata.json
        
    Returns:
        Dict[str, str]: Processed environment variables with user-provided API keys
    """
    processed_env = {}
    
    # If env_config is None or not a dictionary, return empty dict
    if not env_config or not isinstance(env_config, dict):
        return processed_env
    
    # Check each environment variable
    for key, value in env_config.items():
        # Handle structured environment variables (with required flag)
        if isinstance(value, dict) and "required" in value:
            if value.get("required") is True:
                # Get description if available
                description = value.get("description", f"API key for {key}")
                # Prompt the user for the API key
                print("This server requires authentication")
                api_key = input(f"Enter {description}: ")

                # Only add non-empty values to the environment
                if api_key.strip():
                    processed_env[key] = api_key
                else:
                    logger.warning(f"No value provided for required API key: {key}")
            # For non-required keys, use the default value if available
            elif "value" in value and value["value"]:
                processed_env[key] = value["value"]
        # Handle simple key-value pairs (legacy format)
        elif isinstance(value, str):
            if value == "YOUR_API_KEY_HERE":
                # Legacy format that requires user input
                api_key = input(f"Enter API key for {key}: ")
                if api_key.strip():
                    processed_env[key] = api_key
            else:
                # Just use the provided value
                processed_env[key] = value
                
    # Return the processed environment variables
    return processed_env

def update_env_from_config(metadata_path: Path, package: str, config: Dict[str, Any],pkg : Dict[str, str]):
    '''
    Update the environment variables in the installed package's metadata.json file
    based on the provided configuration.
    args :
        metadata_path (Path): The path to the metadata.json file.
        package (str): The package name to update.
        config (Dict[str, Any]): The configuration dictionary containing environment variables.
        pkg (Dict[str, str]): The package dictionary containing author, name, and version.
    returns:
        None
    '''
    # Load the metadata.json file
    with open(metadata_path, 'r') as mdf:
        metadata = json.load(mdf)

    # Find the server config in the provided file that matches this package
    for server_name, server_config in config["mcpServers"].items():
        if server_config.get("fmcp_package") == package:
            # If the config contains env variables, update them in the installed package
            if "env" in server_config:
                logger.info(f"Updating environment variables for {package}")
                if pkg["package_name"] in metadata.get("mcpServers", {}):
                    # Ensure env section exists
                    if "env" not in metadata["mcpServers"][pkg["package_name"]]:
                        metadata["mcpServers"][pkg["package_name"]]["env"] = {}
                        
                    # Update each env variable
                    for key, value in server_config["env"].items():
                        # Handle both simple and structured env formats
                        if isinstance(value, dict):
                            if "value" in value:
                                if key in metadata["mcpServers"][pkg["package_name"]]["env"]:
                                    if isinstance(metadata["mcpServers"][pkg["package_name"]]["env"][key], dict):
                                        metadata["mcpServers"][pkg["package_name"]]["env"][key]["value"] = value["value"]
                                    else:
                                        metadata["mcpServers"][pkg["package_name"]]["env"][key] = value["value"]
                        else:
                            metadata["mcpServers"][pkg["package_name"]]["env"][key] = value
                            
                    # Write back the updated metadata
                    with open(metadata_path, 'w') as mdf_out:
                        json.dump(metadata, mdf_out, indent=2)

                    logger.info(f"Updated environment variables for {package}")
            break