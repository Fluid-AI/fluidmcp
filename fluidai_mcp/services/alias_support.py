
import requests
import os
from typing import Tuple, List, Dict, Any, Optional
from fuzzywuzzy import fuzz, process

# Registry API URL 
REGISTRY_API_URL = os.environ.get("MCP_REGISTRY_API_URL", "https://registry-dev.fluidmcp.com//")

def find_similar_aliases(target: str, aliases: List[str], threshold: int = 60) -> List[Tuple[str, int]]:
    """
    Find similar aliases using fuzzy string matching.
    
    Args:
        target (str): The alias to find matches for
        aliases (list): List of available aliases
        threshold (int): Minimum similarity score (0-100)
        
    Returns:
        list: List of (alias, score) tuples sorted by similarity score
    """
    # Use process.extract to find matches above threshold
    matches = process.extract(target, aliases, 
                             scorer=fuzz.ratio,  # Basic ratio algorithm
                             limit=None)  # Get all matches
    
    # Filter by threshold and sort (process.extract already sorts)
    results = [(alias, score) for alias, score in matches if score >= threshold]
    
    return results

def process_alias(package_str: str) -> str:
    '''
    Check if the package string is an alias and resolve it if it is.
    Handles both simple aliases and versioned aliases (format: "alias==version").
    Uses fuzzy matching to suggest similar aliases when an exact match isn't found.
    
    Args:
        package_str (str): The package string to check
        
    Returns:
        str: The resolved package name if it's an alias, or the original string if not
    '''
    try:
        # Check if version is specified with ==
        requested_version = None
        base_package = package_str
        
        if "==" in package_str:
            base_package, requested_version = package_str.split('==', 1)
            base_package = base_package.strip()
            requested_version = requested_version.strip()
        
        # Make a request to the get-alias endpoint
        response = requests.get(f"{REGISTRY_API_URL}/get-alias")
        
        # Check if the request was successful
        if response.status_code == 200:
            # Get the aliases dictionary
            aliases = response.json()
            
            # Check if the base package is an alias
            if base_package in aliases:
                # Get the list of available versions
                versions_list = aliases[base_package]
                
                # Handle different response formats (string or list)
                if isinstance(versions_list, str):
                    # Single version format
                    return versions_list
                
                elif isinstance(versions_list, list) and versions_list:
                    # If a specific version was requested
                    if requested_version:
                        # Look for the requested version
                        for version_str in versions_list:
                            if f"@{requested_version}" in version_str:
                                print(f"Resolved alias '{package_str}' to '{version_str}'")
                                return version_str
                        
                        # If requested version not found, use latest and show warning
                        # Find the latest version (usually marked with @latest)
                        latest_version = None
                        for version_str in versions_list:
                            if "@latest" in version_str:
                                latest_version = version_str
                                break
                        
                        # If no @latest tag, use the first one in the list
                        if not latest_version and versions_list:
                            latest_version = versions_list[0]
                        
                        if latest_version:
                            print(f"Warning: Requested version {requested_version} not found for '{base_package}'.")
                            print(f"Using latest version instead: '{latest_version}'")
                            return latest_version
                    
                    # If no specific version was requested, use the latest
                    else:
                        # Find the latest version (usually marked with @latest)
                        for version_str in versions_list:
                            if "@latest" in version_str:
                                print(f"Resolved alias '{base_package}' to '{version_str}'")
                                return version_str
                        
                        # If no @latest tag, use the first one in the list
                        if versions_list:
                            print(f"Resolved alias '{base_package}' to '{versions_list[0]}'")
                            return versions_list[0]
            else:
                # No exact alias match found - try fuzzy matching
                all_alias_names = list(aliases.keys())
                similar_aliases = find_similar_aliases(base_package, all_alias_names)
                
                if similar_aliases:
                    print(f"No exact match found for '{base_package}'.") 
                    print("-" * 60)
                    print("Did you mean:")
                    print()

                    for i, (alias, score) in enumerate(similar_aliases[:5], 1):  # Show top 5 matches
                        print(f"{i}. {alias}")
                        print()
                    
                    choice = input("Enter number to use, or 'n' to continue with original: ").strip().lower()
                    
                    if choice.isdigit() and 1 <= int(choice) <= len(similar_aliases[:3]):
                        selected_alias = similar_aliases[int(choice)-1][0]
                        print(f"Using '{selected_alias}' instead of '{base_package}'")
                        
                        # Now process the selected alias with the original version if specified
                        if requested_version:
                            return process_alias(f"{selected_alias}=={requested_version}")
                        else:
                            return process_alias(selected_alias)
        
        # If the request failed, the alias wasn't found, or no valid versions were found
        # Return the original string
        return package_str
    
    except Exception as e:
        # If there was an error, log it and return the original string
        print(f"Warning: Failed to check for aliases: {str(e)}")
        return package_str