#!/usr/bin/env python3
"""
Standalone FastAPI server for image verification with file upload support
This wraps the MCP tools and provides REST API with file upload
"""

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from detectors.pipeline import analyze_image
import tempfile
import os
import uvicorn
from pdf2image import convert_from_path
from PIL import Image

app = FastAPI(
    title="Image Verification API",
    description="Detect AI-generated, tampered, and fake documents (boarding passes, IRCTC tickets)",
    version="1.0.0"
)

# Enable CORS for web access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/verify", response_model=dict)
async def verify_image(
    image: UploadFile = File(..., description="Image or PDF file to verify (JPEG, PNG, PDF)"),
    document_type: str = Form("generic", description="Document type: boarding_pass, irctc, or generic")
):
    """
    Verify if an uploaded image or PDF is authentic, AI-generated, or tampered.

    **Supported file types:**
    - Images: JPEG, PNG, GIF, BMP, TIFF
    - PDF: First page will be extracted and analyzed

    **Supported document types:**
    - `boarding_pass`: Flight boarding passes
    - `irctc`: Indian Railway tickets
    - `generic`: Generic image verification

    **Returns:**
    - `is_real_image`: Boolean indicating if image appears authentic
    - `is_ai_generated`: Boolean indicating if image is AI-generated
    - `is_tampered`: Boolean indicating if image has been edited
    - `confidence`: Float 0-1 indicating overall confidence
    - `signals`: Detailed detection signals and scores
    - `reasoning`: List of human-readable reasons for the decision
    """

    # Validate document type - fallback to generic if invalid
    valid_types = ["boarding_pass", "irctc", "generic"]
    original_type = document_type

    if document_type not in valid_types:
        # Auto-fallback to generic instead of rejecting
        document_type = "generic"

    # Validate file type - support both images and PDFs
    is_pdf = False
    if image.content_type == "application/pdf" or (image.filename and image.filename.lower().endswith('.pdf')):
        is_pdf = True
    elif not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="File must be an image (JPEG, PNG, etc.) or PDF"
        )

    try:
        # Save uploaded file to temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(image.filename)[1]) as temp_file:
            content = await image.read()
            temp_file.write(content)
            temp_path = temp_file.name

        image_path_to_analyze = temp_path
        converted_image_path = None

        try:
            # If PDF, convert first page to image
            if is_pdf:
                try:
                    # Convert first page of PDF to image
                    images = convert_from_path(temp_path, first_page=1, last_page=1)
                    if images:
                        # Save converted image
                        converted_image_path = temp_path.replace('.pdf', '_page1.jpg')
                        images[0].save(converted_image_path, 'JPEG')
                        image_path_to_analyze = converted_image_path

                        # Add info to result
                        pdf_note = "📄 PDF uploaded - analyzing first page"
                    else:
                        raise Exception("Could not extract pages from PDF")
                except Exception as e:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to process PDF: {str(e)}"
                    )

            # Analyze the image (pass source_type so pipeline knows how to weight factors)
            source_type = "pdf" if is_pdf else "image"
            result = analyze_image(image_path_to_analyze, document_type, source_type)

            # Add PDF note if applicable
            if is_pdf:
                if "reasoning" not in result:
                    result["reasoning"] = []
                result["reasoning"].insert(0, pdf_note)

            # Add warning if document type was invalid
            if original_type != document_type:
                if "reasoning" not in result:
                    result["reasoning"] = []
                result["reasoning"].insert(0, f"⚠️ Invalid document_type '{original_type}' - using 'generic' instead. Valid types: {', '.join(valid_types)}")

            return JSONResponse(content=result)

        finally:
            # Clean up temp files
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            if converted_image_path and os.path.exists(converted_image_path):
                os.unlink(converted_image_path)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Verification failed: {str(e)}"
        )

@app.get("/document-types")
async def get_document_types():
    """Get list of supported document types"""
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

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "image-verification"}

@app.get("/")
async def root():
    """API information"""
    return {
        "service": "Image Verification API",
        "version": "1.0.0",
        "endpoints": {
            "verify": "POST /verify - Upload and verify an image",
            "document_types": "GET /document-types - List supported document types",
            "health": "GET /health - Health check",
            "docs": "GET /docs - Interactive API documentation"
        }
    }

if __name__ == "__main__":
    print("=" * 60)
    print("Image Verification API Server")
    print("=" * 60)
    print("Starting server on http://0.0.0.0:8099")
    print("API Documentation: http://localhost:8099/docs")
    print("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=8099)
