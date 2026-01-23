# Security Fixes Testing Guide

## Overview
This guide covers testing the P0 and P1 security fixes implemented in commits `d90ebc4` and `d5e08bf`.

## Quick Test
Open [test_security_validation.html](test_security_validation.html) in a browser.
Tests run automatically on page load.

## Prerequisites
1. Backend server running (FluidMCP API)
2. Frontend development server running
3. At least one MCP server configured (e.g., Time MCP, Wikimedia)

---

## Test Scenarios

### 🔴 Test 1: Image MIME Type Validation

**Purpose:** Verify that only whitelisted image types are rendered

**Whitelisted Types:** PNG, JPEG, JPG, GIF, WebP
**Note:** SVG is intentionally excluded due to XSS vulnerabilities

**Test Cases:**

#### ✅ Test 1.1: Valid Image MIME Type (Should Pass)
```json
{
  "content": [
    {
      "type": "image",
      "mimeType": "image/png",
      "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    }
  ]
}
```
**Expected:** Image renders successfully with MIME type label "image/png"

#### ❌ Test 1.2: Invalid Image MIME Type (Should Fail)
```json
{
  "content": [
    {
      "type": "image",
      "mimeType": "image/bmp",
      "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    }
  ]
}
```
**Expected:** Red warning box with message:
> ⚠️ Image Validation Failed: Unsupported image type: image/bmp

#### ❌ Test 1.3: Dangerous MIME Type (Should Fail)
```json
{
  "content": [
    {
      "type": "image",
      "mimeType": "application/x-executable",
      "data": "malicious_data_here"
    }
  ]
}
```
**Expected:** Red warning box rejecting the content

---

### 🔴 Test 2: Image Size Limits

**Purpose:** Verify that images >10MB are rejected

**Test Cases:**

#### ✅ Test 2.1: Small Image (Should Pass)
- Base64 string length: ~1000 chars (~750 bytes)
- **Expected:** Image renders normally

#### ❌ Test 2.2: Large Image (Should Fail)
- Base64 string length: >14,000,000 chars (~10.5MB)
- **Expected:** Red warning box with message:
> ⚠️ Image Validation Failed: Image too large: 10.5MB (max 10MB)

**How to generate large base64:**
```bash
# Create a large image (11MB)
dd if=/dev/zero bs=1M count=11 | base64 > large_image.txt
```

---

### 🔴 Test 3: URL Scheme Validation

**Purpose:** Verify that only HTTP/HTTPS URLs are allowed

**Test Cases:**

#### ✅ Test 3.1: Safe HTTP URL (Should Pass)
```json
{
  "content": [
    {
      "type": "resource",
      "uri": "http://example.com/resource"
    }
  ]
}
```
**Expected:** Clickable blue link with text "http://example.com/resource"

#### ✅ Test 3.2: Safe HTTPS URL (Should Pass)
```json
{
  "content": [
    {
      "type": "resource",
      "uri": "https://github.com/Fluid-AI/fluidmcp"
    }
  ]
}
```
**Expected:** Clickable blue link

#### ❌ Test 3.3: JavaScript URL (Should Fail - XSS Vector)
```json
{
  "content": [
    {
      "type": "resource",
      "uri": "javascript:alert('XSS')"
    }
  ]
}
```
**Expected:** Red warning box with message:
> ⚠️ Unsafe URL: `javascript:alert('XSS')`
> Only HTTP and HTTPS URLs are allowed for security reasons.

#### ❌ Test 3.4: Data URL (Should Fail)
```json
{
  "content": [
    {
      "type": "resource",
      "uri": "data:text/html,<script>alert('XSS')</script>"
    }
  ]
}
```
**Expected:** Red warning box rejecting the URL

#### ❌ Test 3.5: File URL (Should Fail)
```json
{
  "content": [
    {
      "type": "resource",
      "uri": "file:///etc/passwd"
    }
  ]
}
```
**Expected:** Red warning box rejecting the URL

---

### 🟡 Test 4: Error Boundary

**Purpose:** Verify that rendering errors don't crash the entire UI

**Test Cases:**

#### ❌ Test 4.1: Malformed MCP Content (Should Catch Error)
```json
{
  "content": [
    {
      "type": "image",
      "mimeType": "image/png",
      "data": "INVALID_BASE64_!!!@#$%"
    }
  ]
}
```
**Expected:** Error boundary catches the error and shows:
> Error Rendering Content
> Failed to render result content. The content may be malformed.

**Critical:** Application should remain functional, Tool Runner should not crash

---

## Manual Testing Steps

### Step 1: Start the Stack
```bash
# Terminal 1: Start backend
cd /workspaces/fluidmcp
python -m fluidmcp.cli.api.main

# Terminal 2: Start frontend
cd /workspaces/fluidmcp/fluidmcp/frontend
npm run dev
```

### Step 2: Navigate to Tool Runner
1. Open browser to `http://localhost:5173` (or configured port)
2. Navigate to "Tool Runner" page
3. Select an MCP server (e.g., Wikimedia Image Search)

### Step 3: Execute Test Cases

**For Image Tests:**
1. Use Wikimedia Image Search MCP server
2. Search for an image (e.g., "sunset")
3. Observe that valid images render
4. Modify response in browser DevTools to test invalid MIME types

**For URL Tests:**
1. Use any MCP server that returns resource content
2. Check that HTTP/HTTPS URLs are clickable
3. Modify response in DevTools to test `javascript:` URLs

**For Error Boundary:**
1. Use browser DevTools to corrupt the MCP content response
2. Verify that error boundary catches it
3. Verify rest of app remains functional

### Step 4: Browser DevTools Testing

**Intercept and Modify Responses:**
```javascript
// In Chrome DevTools Console
// Override fetch to inject test data
const originalFetch = window.fetch;
window.fetch = function(...args) {
  return originalFetch(...args).then(response => {
    if (args[0].includes('execute-tool')) {
      return response.clone().json().then(data => {
        // Inject test data here
        data.content = [{
          type: "resource",
          uri: "javascript:alert('test')"
        }];
        return new Response(JSON.stringify(data));
      });
    }
    return response;
  });
};
```

---

## Expected Security Behavior

### ✅ Whitelisted Content Renders Normally
- Valid PNG/JPEG/GIF/WebP/SVG images
- HTTP/HTTPS resource URLs
- Text content
- JSON objects

### ⚠️ Dangerous Content Shows Warnings
- Invalid image MIME types
- Large images (>10MB)
- Non-HTTP/HTTPS URLs
- Shows clear red warning box with explanation

### 🛡️ Malformed Content Caught Gracefully
- Error boundary prevents app crash
- Shows user-friendly error message
- Application remains usable
- Error details available in console

---

## Visual Indicators

### Security Warning Style
- **Background:** Light red (#fef2f2)
- **Border:** Red with 4px left accent (#ef4444)
- **Icon:** ⚠️ emoji
- **Text Color:** Dark red (#991b1b)
- **Code blocks:** Pink background (#fee2e2)

### Error Boundary Style
- **Background:** Light gray
- **Border:** Standard result error styling
- **Message:** "Error Rendering Content"
- **Details:** Collapsible error message

---

## Automated Testing (Future)

Recommended test cases for unit tests:

```typescript
describe('Image Validation', () => {
  it('accepts PNG images', () => {
    const result = validateImage(validBase64, 'image/png');
    expect(result.valid).toBe(true);
  });

  it('rejects BMP images', () => {
    const result = validateImage(validBase64, 'image/bmp');
    expect(result.valid).toBe(false);
    expect(result.error).toContain('Unsupported');
  });

  it('rejects images over 10MB', () => {
    const largeData = 'A'.repeat(14000000);
    const result = validateImage(largeData, 'image/png');
    expect(result.valid).toBe(false);
    expect(result.error).toContain('too large');
  });
});

describe('URL Validation', () => {
  it('accepts HTTPS URLs', () => {
    expect(isSafeUrl('https://example.com')).toBe(true);
  });

  it('rejects javascript: URLs', () => {
    expect(isSafeUrl('javascript:alert(1)')).toBe(false);
  });

  it('rejects data: URLs', () => {
    expect(isSafeUrl('data:text/html,<script>')).toBe(false);
  });
});
```

---

## Success Criteria

- [ ] Valid images render correctly
- [ ] Invalid MIME types show warning (not render)
- [ ] Large images show size warning
- [ ] HTTP/HTTPS URLs are clickable
- [ ] javascript: URLs show security warning
- [ ] data: URLs show security warning
- [ ] file: URLs show security warning
- [ ] Malformed content caught by Error Boundary
- [ ] Application remains stable after errors
- [ ] Warning messages are clear and actionable

---

## Reporting Issues

If any test fails, capture:
1. Browser console errors
2. Network tab request/response
3. Screenshot of UI
4. Steps to reproduce

File issue with tag: `security` or `bug`
