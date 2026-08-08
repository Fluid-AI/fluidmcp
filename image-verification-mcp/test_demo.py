#!/usr/bin/env python3
"""
Demo script to test image verification MCP server
Creates sample test images and verifies them
"""

import base64
import json
import subprocess
import sys
from PIL import Image, ImageDraw, ImageFont
import io

def create_fake_irctc_ticket():
    """Create a simple fake IRCTC ticket image for testing"""
    img = Image.new('RGB', (800, 400), color='white')
    draw = ImageDraw.Draw(img)

    # Add some text
    draw.text((50, 50), "IRCTC E-Ticket", fill='black')
    draw.text((50, 100), "PNR: 1234567890", fill='black')
    draw.text((50, 150), "Train No: 12345", fill='black')
    draw.text((50, 200), "From: NDLS To: BCT", fill='black')
    draw.text((50, 250), "Date: 25-01-2026", fill='black')

    # Save to bytes
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='JPEG')
    return img_bytes.getvalue()

def create_fake_boarding_pass():
    """Create a simple fake boarding pass for testing"""
    img = Image.new('RGB', (800, 400), color='lightblue')
    draw = ImageDraw.Draw(img)

    draw.text((50, 50), "BOARDING PASS", fill='black')
    draw.text((50, 100), "Flight: AI123", fill='black')
    draw.text((50, 150), "PNR: ABC123", fill='black')
    draw.text((50, 200), "From: DEL To: BOM", fill='black')
    draw.text((50, 250), "Gate: 5A Seat: 12B", fill='black')

    img_bytes = io.BytesIO()
    img.save(img_bytes, format='JPEG')
    return img_bytes.getvalue()

def test_verification(image_bytes, document_type, description):
    """Test image verification"""
    print(f"\n{'='*60}")
    print(f"Testing: {description}")
    print(f"Document Type: {document_type}")
    print('='*60)

    # Encode to base64
    image_b64 = base64.b64encode(image_bytes).decode('utf-8')

    # Create JSON-RPC request
    request = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "verify_image_authenticity",
            "arguments": {
                "image_base64": image_b64,
                "document_type": document_type
            }
        },
        "id": 1
    }

    # For testing directly without MCP server running
    # We'll import and call the function directly
    try:
        from detectors.pipeline import analyze_image
        import tempfile
        import os

        # Save image to temp file
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(image_bytes)
            temp_path = f.name

        try:
            result = analyze_image(temp_path, document_type)
            print_result(result)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()

def print_result(result):
    """Pretty print verification result"""
    print(f"\nResults:")
    print(f"  Is Real Image: {result['is_real_image']}")
    print(f"  Is AI Generated: {result['is_ai_generated']}")
    print(f"  Is Tampered: {result['is_tampered']}")
    print(f"  Confidence: {result['confidence']:.2f}")

    print(f"\nDetailed Signals:")
    for key, value in result['signals'].items():
        print(f"  {key}: {value}")

    print(f"\nReasoning:")
    for reason in result['reasoning']:
        print(f"  • {reason}")

def main():
    print("Image Verification MCP Server - Demo Test")
    print("="*60)

    # Test 1: Fake IRCTC Ticket
    irctc_img = create_fake_irctc_ticket()
    test_verification(irctc_img, "irctc", "Simple Fake IRCTC Ticket")

    # Test 2: Fake Boarding Pass
    bp_img = create_fake_boarding_pass()
    test_verification(bp_img, "boarding_pass", "Simple Fake Boarding Pass")

    # Test 3: Generic
    test_verification(irctc_img, "generic", "Generic Image Test")

    print("\n" + "="*60)
    print("Demo test completed!")
    print("="*60)
    print("\nNote: These are simple test images.")
    print("For production use, test with real boarding passes and tickets.")
    print("\nTo test with real images:")
    print("  1. Save your image as 'test_image.jpg'")
    print("  2. Run: python test_real_image.py test_image.jpg irctc")

if __name__ == "__main__":
    main()
