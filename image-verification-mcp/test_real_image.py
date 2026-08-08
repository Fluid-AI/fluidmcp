#!/usr/bin/env python3
"""
Test script for verifying real images
Usage: python test_real_image.py <image_path> <document_type>
"""

import sys
import base64
from detectors.pipeline import analyze_image

def main():
    if len(sys.argv) < 2:
        print("Usage: python test_real_image.py <image_path> [document_type]")
        print("Example: python test_real_image.py ticket.jpg irctc")
        print("\nSupported document types:")
        print("  - irctc: Indian Railway tickets")
        print("  - boarding_pass: Flight boarding passes")
        print("  - generic: Generic image verification")
        sys.exit(1)

    image_path = sys.argv[1]
    document_type = sys.argv[2] if len(sys.argv) > 2 else "generic"

    print(f"\nVerifying: {image_path}")
    print(f"Document Type: {document_type}")
    print("="*60)

    try:
        result = analyze_image(image_path, document_type)

        print(f"\n✓ Verification Complete\n")
        print(f"Is Real Image: {result['is_real_image']}")
        print(f"Is AI Generated: {result['is_ai_generated']}")
        print(f"Is Tampered: {result['is_tampered']}")
        print(f"Confidence: {result['confidence']:.2f}\n")

        print("Detailed Signals:")
        for key, value in result['signals'].items():
            print(f"  {key.replace('_', ' ').title()}: {value}")

        print(f"\nReasoning:")
        for i, reason in enumerate(result['reasoning'], 1):
            print(f"  {i}. {reason}")

        # Decision recommendation
        print("\n" + "="*60)
        confidence = result['confidence']
        if confidence > 0.8:
            print("✅ HIGH CONFIDENCE - Likely authentic")
        elif confidence > 0.5:
            print("⚠️  MEDIUM CONFIDENCE - Manual review recommended")
        else:
            print("❌ LOW CONFIDENCE - Likely fake or tampered")
        print("="*60)

    except FileNotFoundError:
        print(f"Error: Image file not found: {image_path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
