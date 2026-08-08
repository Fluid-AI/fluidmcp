# Quick Start Guide - Image Verification MCP Server

This guide will help you set up the Image Verification MCP Server from scratch.

## 🚀 Step-by-Step Installation

### Step 1: Check Prerequisites

Before starting, verify you have these installed:

```bash
# Check Python version (need 3.8+)
python3 --version

# Check pip
pip --version

# If not installed:
# Ubuntu/Debian: sudo apt-get install python3 python3-pip
# macOS: brew install python3
# Windows: Download from python.org
```

### Step 2: Install System Dependencies

#### Ubuntu/Debian Linux:
```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr poppler-utils
```

#### macOS:
```bash
brew install tesseract poppler
```

#### Windows:
1. **Tesseract OCR**:
   - Download from: https://github.com/UB-Mannheim/tesseract/wiki
   - Run installer
   - Add to PATH: `C:\Program Files\Tesseract-OCR`

2. **Poppler**:
   - Download from: http://blog.alivate.com.au/poppler-windows/
   - Extract to: `C:\Program Files\poppler`
   - Add to PATH: `C:\Program Files\poppler\bin`

### Step 3: Verify System Dependencies

```bash
# Verify Tesseract
tesseract --version
# Should show: tesseract 4.x.x or 5.x.x

# Verify Poppler
pdfinfo -v
# Should show version info
```

### Step 4: Install Python Dependencies

```bash
# Navigate to project directory
cd image-verification-mcp

# Install all Python packages
pip install -r requirements.txt

# This will install:
# - fastmcp (MCP server framework)
# - pillow (image processing)
# - pytesseract (OCR wrapper)
# - opencv-python (computer vision)
# - transformers + torch (AI detection)
# - pdf2image (PDF conversion)
# - fastapi + uvicorn (REST API)
```

**⏱️ Note**: This may take 5-10 minutes as PyTorch and transformers are large packages (~2GB).

### Step 5: Test Installation

```bash
# Test imports
python3 -c "
import PIL
import pytesseract
import cv2
import torch
from transformers import pipeline
from pdf2image import convert_from_path
print('✅ All dependencies installed successfully!')
"
```

If you see any errors, check the Troubleshooting section below.

---

## 🎯 Running the Server

### Option A: Run as REST API (Recommended for Testing)

```bash
# Start the FastAPI server
python3 api_server.py

# Server will start on http://localhost:8099
# Swagger UI: http://localhost:8099/docs
```

**Test with cURL:**
```bash
curl -X POST http://localhost:8099/verify \
  -F "image=@your_ticket.jpg" \
  -F "document_type=irctc"
```

### Option B: Run with FluidMCP

1. **Create config file** (`image-verification-config.json`):
```json
{
  "mcpServers": {
    "image-verification": {
      "command": "python3",
      "args": ["image-verification-mcp/server.py"],
      "env": {}
    }
  }
}
```

2. **Start the server:**
```bash
fluidmcp run image-verification-config.json --file --start-server
```

3. **Test the MCP endpoint:**
```bash
# Convert image to base64
IMAGE_B64=$(base64 -w 0 your_ticket.jpg)

# Call MCP tool
curl -X POST http://localhost:8099/image-verification/mcp \
  -H "Content-Type: application/json" \
  -d "{
    \"jsonrpc\": \"2.0\",
    \"method\": \"tools/call\",
    \"params\": {
      \"name\": \"verify_image_authenticity\",
      \"arguments\": {
        \"image_base64\": \"$IMAGE_B64\",
        \"document_type\": \"irctc\"
      }
    },
    \"id\": 1
  }"
```

---

## 🧪 Testing Your Installation

### Test 1: Upload a Real Image

```bash
# Test with a real ticket image
curl -X POST http://localhost:8099/verify \
  -F "image=@real_ticket.jpg" \
  -F "document_type=irctc"

# Expected result:
# {
#   "is_real_image": true,
#   "confidence": 0.85,
#   "reasoning": ["✓ IRCTC keywords found", "✓ Valid PNR format", ...]
# }
```

### Test 2: Test with PDF

```bash
# Test with a PDF document
curl -X POST http://localhost:8099/verify \
  -F "image=@ticket.pdf" \
  -F "document_type=irctc"

# Expected: PDF converted and analyzed
```

### Test 3: Check Available Document Types

```bash
curl http://localhost:8099/document-types

# Returns:
# {
#   "supported_types": [
#     {"type": "boarding_pass", "description": "Flight boarding passes"},
#     {"type": "irctc", "description": "Indian Railway tickets"},
#     {"type": "generic", "description": "Generic image verification"}
#   ]
# }
```

---

## ⚙️ Configuration

### Supported Document Types

1. **`irctc`**: Indian Railway (IRCTC) tickets
   - Validates PNR (10 digits)
   - Checks train numbers, station codes
   - Detects suspicious PNR patterns

2. **`boarding_pass`**: Flight boarding passes
   - Validates PNR (6 characters)
   - Checks flight numbers, airport codes
   - Validates gate and seat numbers

3. **`generic`**: Generic image verification
   - Basic AI detection
   - Metadata analysis
   - No specific document validation

### Confidence Thresholds

- **≥ 0.6**: Image appears authentic
- **< 0.6**: Image flagged as fake/tampered

You can adjust business logic based on confidence:
- **High (0.8+)**: Auto-approve
- **Medium (0.6-0.8)**: Manual review
- **Low (< 0.6)**: Reject or escalate

---

## 🔧 Troubleshooting

### Issue: "Tesseract not found"

**Solution:**
```bash
# Check if installed
tesseract --version

# If not found, install:
# Ubuntu: sudo apt-get install tesseract-ocr
# macOS: brew install tesseract
# Windows: Add to PATH

# Set path manually (if needed)
export PATH=$PATH:/usr/local/bin
```

### Issue: "Could not load AI model"

**Solution:**
- This is non-critical - the system falls back to heuristic detection
- To fix, ensure you have internet connection for first run
- The model (Organika/sdxl-detector) will be downloaded automatically (~500MB)
- Downloaded models are cached in `~/.cache/huggingface/`

### Issue: "PDF conversion failed"

**Solution:**
```bash
# Ensure Poppler is installed
pdfinfo -v

# Ubuntu: sudo apt-get install poppler-utils
# macOS: brew install poppler
# Windows: Add poppler/bin to PATH
```

### Issue: "Out of memory" or "Killed"

**Solution:**
- PyTorch and transformers require ~2GB RAM
- Close other applications
- Or disable AI detection by setting smaller model
- Heuristic detection still works without ML model

### Issue: "Import error: No module named 'PIL'"

**Solution:**
```bash
pip install --upgrade pillow
```

### Issue: Port 8099 already in use

**Solution:**
```bash
# Find what's using the port
lsof -i :8099

# Kill the process (replace PID)
kill -9 <PID>

# Or change the port in api_server.py (line 186)
```

---

## 📊 Understanding Results

### Example Response

```json
{
  "is_real_image": true,
  "is_ai_generated": false,
  "is_tampered": false,
  "confidence": 0.87,
  "signals": {
    "ai_probability": 0.12,
    "metadata_score": 0.90,
    "ocr_score": 0.85,
    "document_score": 0.88
  },
  "reasoning": [
    "✓ Multiple IRCTC keywords: indian railway, pnr, train",
    "✓ Valid PNR format: 1234567890",
    "✓ Camera Make: Apple",
    "✓ JPEG format (standard for camera photos)"
  ],
  "document_type": "irctc",
  "source_type": "image"
}
```

### Key Fields Explained

- **`is_real_image`**: Final verdict (true = authentic, false = fake)
- **`confidence`**: Overall score 0-1 (higher = more confident)
- **`is_ai_generated`**: true if created by AI (Midjourney, DALL-E, etc.)
- **`is_tampered`**: true if edited/modified (Photoshop, screenshots, etc.)
- **`signals`**: Individual detector scores
- **`reasoning`**: Human-readable reasons for the decision
- **`source_type`**: "image" (photo) or "pdf" (document)

---

## 🚀 Next Steps

1. **Test with your own images** - Try real and fake tickets
2. **Review the API docs** - Visit http://localhost:8099/docs
3. **Integrate with your app** - Use the REST API endpoints
4. **Adjust thresholds** - Based on your false positive/negative rate
5. **Add business logic** - Combine with external API validation

---

## 📚 Additional Resources

- **Full Documentation**: See [README.md](README.md)
- **API Reference**: http://localhost:8099/docs (when server running)
- **Architecture Details**: See [ARCHITECTURE_REFACTOR.md](ARCHITECTURE_REFACTOR.md)
- **Testing Guide**: See [TESTING_GUIDE.md](TESTING_GUIDE.md)

---

## ✅ Checklist

Use this checklist to verify your installation:

- [ ] Python 3.8+ installed
- [ ] pip working
- [ ] Tesseract OCR installed (`tesseract --version` works)
- [ ] Poppler installed (`pdfinfo -v` works)
- [ ] Python dependencies installed (`pip install -r requirements.txt`)
- [ ] All imports work (test command successful)
- [ ] Server starts without errors
- [ ] Can access http://localhost:8099
- [ ] Test API call succeeds
- [ ] Can upload and verify images

**If all items checked ✅ - You're ready to go!**

---

## 💡 Tips

1. **First Run**: The AI model downloads automatically (~500MB) - be patient
2. **Testing**: Use the Swagger UI at /docs for interactive testing
3. **PDF Files**: Make sure they're not too large (keep under 10MB)
4. **Image Quality**: Higher resolution = better OCR accuracy (min 300 DPI recommended)
5. **EXIF Data**: Photos should have camera metadata - screenshots won't pass strict validation

---

## 🆘 Need Help?

If you're still having issues:

1. Check the [Troubleshooting](#troubleshooting) section above
2. Review error messages in terminal
3. Check logs for detailed error information
4. Verify all dependencies with the checklist
5. Contact FluidMCP team for support

**Happy verifying! 🎉**
