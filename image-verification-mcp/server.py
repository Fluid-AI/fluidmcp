#!/usr/bin/env python3
"""
Image Verification MCP Server
Detects AI-generated, tampered, and fake document images
"""

from mcp.server.fastmcp import FastMCP
from detectors.pipeline import analyze_image
import base64
import tempfile
import os
from pathlib import Path

mcp = FastMCP("image-verification")

@mcp.tool()
def verify_image_authenticity(
    image_base64: str,
    document_type: str = "generic"
) -> dict:
    """
    Verify if an image is authentic, AI-generated, or tampered.

    Args:
        image_base64: Base64 encoded image data
        document_type: Type of document - "boarding_pass", "irctc", or "generic"

    Returns:
        dict with verification results including confidence scores and reasoning
    """
    try:
        # Decode base64 image
        image_bytes = base64.b64decode(image_base64)

        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(image_bytes)
            temp_path = f.name

        try:
            # Analyze image
            result = analyze_image(temp_path, document_type)
            return result
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    except Exception as e:
        return {
            "error": str(e),
            "is_real_image": False,
            "confidence": 0.0,
            "reasoning": [f"Analysis failed: {str(e)}"]
        }

@mcp.tool()
def verify_image_from_file(
    file_path: str,
    document_type: str = "generic"
) -> dict:
    """
    Verify if an image/PDF file is authentic, AI-generated, or tampered.

    This tool accepts a local file path or URL to download the image.

    Args:
        file_path: Path to the image or PDF file, or URL (supports JPEG, PNG, PDF)
        document_type: Type of document - "boarding_pass", "irctc", or "generic"

    Returns:
        dict with verification results including confidence scores and reasoning
    """
    try:
        # Check if it's a URL
        if file_path.startswith(('http://', 'https://')):
            import requests
            # Download the file to a temporary location
            response = requests.get(file_path, timeout=30)
            response.raise_for_status()

            # Determine file extension from URL or content-type
            content_type = response.headers.get('content-type', '')
            if 'pdf' in content_type:
                ext = '.pdf'
            elif 'png' in content_type:
                ext = '.png'
            else:
                ext = '.jpg'

            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                f.write(response.content)
                temp_path = f.name

            try:
                # Analyze the downloaded image
                result = analyze_image(temp_path, document_type)
                return result
            finally:
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

        # Handle local file path
        path = Path(file_path).resolve()

        # Security check: file must exist and be a file
        if not path.exists():
            return {
                "error": "file_not_found",
                "is_real_image": False,
                "confidence": 0.0,
                "reasoning": [f"File not found: {file_path}"]
            }

        if not path.is_file():
            return {
                "error": "not_a_file",
                "is_real_image": False,
                "confidence": 0.0,
                "reasoning": [f"Path is not a file: {file_path}"]
            }

        # Check file size (max 100MB)
        file_size_mb = path.stat().st_size / (1024 * 1024)
        if file_size_mb > 100:
            return {
                "error": "file_too_large",
                "is_real_image": False,
                "confidence": 0.0,
                "reasoning": [f"File too large: {file_size_mb:.1f}MB (max 100MB)"]
            }

        # Validate file extension
        valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.pdf'}
        if path.suffix.lower() not in valid_extensions:
            return {
                "error": "unsupported_format",
                "is_real_image": False,
                "confidence": 0.0,
                "reasoning": [f"Unsupported file format: {path.suffix}. Supported: {', '.join(valid_extensions)}"]
            }

        # Analyze the image
        result = analyze_image(str(path), document_type)
        return result

    except Exception as e:
        return {
            "error": str(e),
            "is_real_image": False,
            "confidence": 0.0,
            "reasoning": [f"Analysis failed: {str(e)}"]
        }


@mcp.tool()
def get_supported_document_types() -> dict:
    """Get list of supported document types for verification."""
    return {
        "supported_types": [
            {
                "type": "boarding_pass",
                "description": "Flight boarding passes (airline tickets)"
            },
            {
                "type": "irctc",
                "description": "Indian Railway (IRCTC) tickets"
            },
            {
                "type": "generic",
                "description": "Generic image verification"
            }
        ]
    }

if __name__ == "__main__":
    mcp.run()
