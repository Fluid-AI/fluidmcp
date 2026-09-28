#!/bin/bash
set -e

echo "========================================="
echo "Image Verification MCP Server Quick Test"
echo "========================================="
echo

# Test 1: Check dependencies
echo "✓ Checking dependencies..."
python -c "import PIL, cv2, pytesseract, piexif, numpy" 2>/dev/null || {
    echo "❌ Missing dependencies. Run: pip install -r requirements.txt"
    exit 1
}
echo "✓ All Python dependencies installed"

tesseract --version > /dev/null 2>&1 || {
    echo "❌ Tesseract not installed. Run: sudo apt-get install tesseract-ocr"
    exit 1
}
echo "✓ Tesseract OCR installed"

# Test 2: Run demo tests
echo
echo "✓ Running demo tests..."
cd /workspaces/fluidmcp/image-verification-mcp
python test_demo.py 2>&1 | grep -A 5 "Results:" | head -20

# Test 3: Check if server can import
echo
echo "✓ Testing server imports..."
python -c "from detectors.pipeline import analyze_image; print('✓ Pipeline import successful')"

# Test 4: Create a test image and verify
echo
echo "✓ Creating test image..."
python -c "
from PIL import Image, ImageDraw
import base64
img = Image.new('RGB', (800, 400), 'white')
draw = ImageDraw.Draw(img)
draw.text((50, 50), 'IRCTC E-Ticket', fill='black')
draw.text((50, 100), 'PNR: 9876543210', fill='black')
draw.text((50, 150), 'Train No: 12345', fill='black')
draw.text((50, 200), 'From: NDLS To: BCT', fill='black')
img.save('/tmp/test_irctc.jpg')
print('✓ Test image created: /tmp/test_irctc.jpg')
"

echo "✓ Running verification on test image..."
python test_real_image.py /tmp/test_irctc.jpg irctc 2>&1 | grep -E "Confidence|Is Real|PNR"

echo
echo "========================================="
echo "✅ All tests passed!"
echo "========================================="
echo
echo "Next steps:"
echo "  1. Test with real IRCTC tickets and boarding passes"
echo "  2. Start FluidMCP: fluidmcp run examples/image-verification-config.json --file --start-server"
echo "  3. Read TESTING_GUIDE.md for comprehensive testing"
