#!/usr/bin/env python3
"""
Image Verification MCP Server
Detects AI-generated, tampered, and fake document images
"""

from mcp.server.fastmcp import FastMCP
from detectors.pipeline import analyze_image
from pdf2image import convert_from_path
import base64
import tempfile
import os

mcp = FastMCP("image-verification")

@mcp.tool()
def verify_image_authenticity(
    image_base64: str,
    document_type: str = "generic",
    source_type: str = "auto"
) -> dict:
    """
    Verify if an image or PDF is authentic, AI-generated, or tampered.

    Args:
        image_base64: Base64 encoded image or PDF data
        document_type: Type of document - "boarding_pass", "irctc", or "generic"
        source_type: Source type - "auto" (detect), "image", or "pdf"

    Returns:
        dict with verification results including confidence scores and reasoning
    """
    try:
        # Decode base64 image
        image_bytes = base64.b64decode(image_base64)

        # Auto-detect PDF from magic bytes
        is_pdf = image_bytes.startswith(b'%PDF')

        if is_pdf:
            # Save as PDF and convert first page to image
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as pdf_file:
                pdf_file.write(image_bytes)
                pdf_path = pdf_file.name

            try:
                # Convert PDF first page to image
                images = convert_from_path(pdf_path, first_page=1, last_page=1)
                if not images:
                    raise ValueError("Could not extract image from PDF")

                # Save converted image
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as img_file:
                    images[0].save(img_file.name, 'JPEG')
                    temp_path = img_file.name

                # Set source_type for pipeline
                if source_type == "auto":
                    source_type = "pdf"
            finally:
                # Clean up PDF file
                if os.path.exists(pdf_path):
                    os.unlink(pdf_path)
        else:
            # Regular image - detect format from magic bytes
            suffix = ".jpg" if image_bytes.startswith(b'\xff\xd8') else ".png"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(image_bytes)
                temp_path = f.name

            if source_type == "auto":
                source_type = "image"

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

def main():
    """Entry point for uv run"""
    mcp.run(transport="sse")

if __name__ == "__main__":
    main()
