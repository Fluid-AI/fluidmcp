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
