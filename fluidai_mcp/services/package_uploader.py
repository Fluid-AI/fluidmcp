import os
import json
import tarfile
import requests
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger

# Environment variables (reusing existing ones)
UPLOAD_URL = os.getenv("MCP_UPLOAD_URL", "https://registry.fluidmcp.com/upload-verified-mcp-package")
AUTH_TOKEN = os.getenv("MCP_TOKEN")


def should_create_tarball(source_dir: Path) -> bool:
    """
    Check if directory contains only metadata.json or has additional files/folders.
    
    Args:
        source_dir (Path): The source directory to check
        
    Returns:
        bool: True if tarball should be created, False if only metadata.json exists
    """
    if not source_dir.exists():
        raise FileNotFoundError(f"Directory does not exist: {source_dir}")
    
    # Get all items in the directory
    items = list(source_dir.iterdir())
    
    # If only metadata.json exists, no need for tarball
    if len(items) == 1 and items[0].name == "metadata.json":
        return False
    
    # If metadata.json + other files/folders exist, create tarball
    return True


def create_tar_gz_from_directory(source_dir: Path) -> Path:
    """
    Create tar.gz file from directory contents.
    
    Args:
        source_dir (Path): The source directory to compress
        
    Returns:
        Path: Path to the created tar.gz file
    """
    tar_filename = f"{source_dir.name}.tar.gz"
    tar_path = source_dir.parent / tar_filename
    
    logger.info(f"Creating tar.gz file: {tar_path}")
    
    try:
        with tarfile.open(tar_path, "w:gz") as tar:
            for item in source_dir.iterdir():
                tar.add(item, arcname=item.name)
        
        logger.info(f"Successfully created tar.gz: {tar_path}")
        return tar_path
        
    except Exception as e:
        logger.error(f"Failed to create tar.gz: {e}")
        raise


def upload_package_to_registry(
    pkg: Dict[str, str], 
    file_path: Path, 
    description: str,
    alias: Optional[str] = None
) -> bool:
    """
    Upload package file to the registry API.
    
    Args:
        pkg (Dict[str, str]): Package info with author, package_name, version
        file_path (Path): Path to the file to upload (JSON or tar.gz)
        description (str): Package description
        alias (Optional[str]): Optional alias name
        
    Returns:
        bool: True if upload successful, False otherwise
    """
    try:
        headers = {"Authorization": AUTH_TOKEN}
        
        # Determine content type based on file extension
        if file_path.suffix == '.json':
            content_type = 'application/json'
        elif file_path.suffix == '.gz':
            content_type = 'application/gzip'
        else:
            content_type = 'application/octet-stream'
        
        # Prepare query parameters (since FastAPI expects them as query params, not form data)
        params = {
            'author': pkg['author'],
            'package_name': pkg['package_name'],
            'version': pkg['version'],
            'description': description
        }
        
        if alias:
            params['alias'] = alias
        
        # Upload file with query parameters
        with open(file_path, 'rb') as f:
            files = {'file': (file_path.name, f, content_type)}
            
            logger.info(f"Uploading {pkg['author']}/{pkg['package_name']}@{pkg['version']} to registry...")
            
            response = requests.post(UPLOAD_URL, headers=headers, files=files, params=params)
            response.raise_for_status()
            
        logger.info("Upload successful!")
        return True
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Upload failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_detail = e.response.json()
                logger.error(f"Server response: {error_detail}")
            except:
                logger.error(f"Server response: {e.response.text}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during upload: {e}")
        return False


def upload_package(pkg: Dict[str, str], source_dir: Path, description: str, alias: Optional[str] = None) -> bool:
    """
    Main function to handle package upload process.
    
    Args:
        pkg (Dict[str, str]): Package info with author, package_name, version
        source_dir (Path): Source directory containing package files
        description (str): Package description
        alias (Optional[str]): Optional alias name
        
    Returns:
        bool: True if upload successful, False otherwise
    """
    temp_files = []
    
    try:
        # Check if we need to create a tarball
        if should_create_tarball(source_dir):
            logger.info("Directory contains multiple files, creating tar.gz...")
            file_to_upload = create_tar_gz_from_directory(source_dir)
            temp_files.append(file_to_upload)  # Mark for cleanup
        else:
            logger.info("Directory contains only metadata.json, uploading directly...")
            file_to_upload = source_dir / "metadata.json"
            
            if not file_to_upload.exists():
                logger.error("metadata.json not found in directory")
                return False
        
        # Upload to registry
        success = upload_package_to_registry(pkg, file_to_upload, description, alias)
        
        return success
        
    except Exception as e:
        logger.error(f"Package upload failed: {e}")
        return False
        
    finally:
        # Cleanup temporary files
        for temp_file in temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
                    logger.info(f"Cleaned up temporary file: {temp_file}")
            except Exception as e:
                logger.warning(f"Failed to cleanup {temp_file}: {e}")