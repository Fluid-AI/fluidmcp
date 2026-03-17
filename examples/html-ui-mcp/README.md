# HTML UI MCP Server

An AI-powered Model Context Protocol (MCP) server that generates and modifies HTML user interfaces using natural language instructions with **progressive streaming** for real-time UI building.

## Overview

This MCP server acts as an intelligent HTML/CSS/JavaScript generator that can:

- ✨ Generate complete HTML UIs from natural language descriptions
- 🎨 Modify existing HTML code based on instructions
- 📱 Create responsive, mobile-friendly layouts
- 🌓 Support dark and light themes
- ⚡ Use plain HTML with inline CSS (no external frameworks)
- 🚀 **Smart chunking with parent-first, then children streaming**
- 🌊 **HTTP streaming endpoint with Server-Sent Events (SSE)**
- ♿ Follow accessibility best practices
- 🏭 Produce simple, clean, production-ready code

## Features

### Progressive HTML Streaming

This server implements **intelligent HTML chunking** for progressive rendering:

- 🏗️ **Parent-First Architecture**: Streams complete parent structure first (`<!DOCTYPE html><html><head>...</head><body><div class="container">`)
- 🧩 **Child Injection**: Then progressively streams each child element (form fields, buttons, etc.)
- 🎯 **Logical Boundaries**: Chunks at semantic HTML boundaries, not arbitrary character positions
- 📦 **Renderable Blocks**: Each chunk is a complete, valid HTML fragment that can render progressively

**Example Streaming Pattern:**
```
Chunk 1: <!DOCTYPE html><html><head>...styles...</head><body><div class="container">
Chunk 2:   <div class="form-group">username field</div>
Chunk 3:   <div class="form-group">password field</div>
Chunk 4:   <button>Log In</button>
Chunk 5: </div></body></html>
```

### Two Access Modes

#### 1. MCP Protocol (Stdio)
Standard MCP tool interface for Claude Desktop and other MCP clients.

#### 2. HTTP Streaming Endpoint (NEW!)
Direct HTTP access with Server-Sent Events for true progressive rendering.

**Endpoint:** `POST /stream-html`

**Benefits:**
- ✅ True streaming to browser/client
- ✅ Progressive rendering as HTML generates
- ✅ Real-time feedback
- ✅ No MCP client required

### Single Tool: `modify_ui_or_html`

**Purpose:** Generate or modify HTML UI using natural language instructions. Creates simple, clean HTML pages with inline CSS styling. Supports both standard and streaming modes.

**Parameters:**
- `user_prompt` (required): Natural language instruction describing the desired UI (e.g., "Create a login page", "Add a navigation menu", "Make this responsive")
- `html_code` (optional): Existing HTML to modify. If omitted, generates new HTML from scratch.

**Capabilities:**
- Create login pages, dashboards, landing pages
- Add navigation, sidebars, modals
- Improve responsiveness and mobile design
- Add dark mode toggles
- Convert layouts (tables to cards, etc.)
- Improve styling and accessibility
- Add animations and interactivity

## Installation

### 1. Install Dependencies

```bash
cd examples/html-ui-mcp
pip install -r requirements.txt
```

**Required packages:**
- `mcp>=0.9.0` - MCP protocol implementation
- `google-genai>=1.0.0` - Google Gemini AI

### 2. Configure API Keys

The server uses **Google Gemini** for AI-powered HTML generation with automatic model fallback:
1. `gemini-2.5-flash` (primary - stable, fast)
2. `gemini-flash-latest` (auto-updated)
3. `gemini-2.5-pro` (more powerful)
4. `gemini-2.0-flash` (experimental)

Set your Gemini API key:

```bash
# For Gemini
export GOOGLE_API_KEY="..."
# or
export GEMINI_API_KEY="..."
```

#### Getting Your Gemini API Key

**Google Gemini:**
1. Visit https://aistudio.google.com/app/apikey
2. Create API key
3. Free tier includes generous limits

## Usage

### Running the Server

#### Stdio Mode (Default)

```bash
python3 server.py
```

This mode is used by Claude Desktop and other MCP clients.

### Testing with FluidMCP

Run the server through FluidMCP's unified gateway:

```bash
cd /workspaces/fluidmcp

# Create a config file
cat > html-ui-config.json << 'EOF'
{
  "mcpServers": {
    "html-ui": {
      "command": "python3",
      "args": ["examples/html-ui-mcp/server.py"],
      "env": {
        "GEMINI_API_KEY": "your-api-key-here"
      }
    }
  }
}
EOF

# Start the server
fluidmcp run html-ui-config.json --file --start-server
```

Server runs on http://localhost:8099

### Example MCP Requests

#### List Available Tools

```bash
curl -X POST http://localhost:8099/html-ui/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list"
  }'
```

#### Generate a Login Page

```bash
curl -X POST http://localhost:8099/html-ui/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "modify_ui_or_html",
      "arguments": {
        "user_prompt": "Create a modern login page with email/password fields, a forgot password link, and a sign up button. Use a gradient background and card-style layout."
      }
    }
  }'
```

#### Modify Existing HTML

```bash
curl -X POST http://localhost:8099/html-ui/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "modify_ui_or_html",
      "arguments": {
        "user_prompt": "Add a dark mode toggle button in the top right corner",
        "html_code": "<!DOCTYPE html>...[existing HTML]...</html>"
      }
    }
  }'
```

### HTTP Streaming Endpoint (Server-Sent Events)

🌊 **NEW**: Direct HTTP streaming for progressive HTML rendering!

#### Start the Streaming Server

```bash
# Option 1: Using the start script
cd examples/html-ui-mcp
export GOOGLE_API_KEY="your-api-key-here"
./start-streaming-server.sh

# Option 2: Direct python command
cd examples/html-ui-mcp
export GOOGLE_API_KEY="your-api-key-here"
python3 server.py --http-only
```

Server starts on **http://localhost:8090**

#### Test with curl

```bash
# Stream HTML generation (parent-first, then children)
curl -X POST http://localhost:8090/stream-html \
  -H "Content-Type: application/json" \
  -d '{"user_prompt": "Create a registration form with username, email, and password fields"}' \
  -N
```

**Expected Output (SSE format):**
```
data: {"chunk_id": 1, "html": "<!DOCTYPE html>\n<html>...<div class=\"container\">", "done": false}

data: {"chunk_id": 2, "html": "  <div class=\"form-group\">username field</div>", "done": false}

data: {"chunk_id": 3, "html": "  <div class=\"form-group\">email field</div>", "done": false}

data: {"chunk_id": 4, "html": "  <div class=\"form-group\">password field</div>", "done": false}

data: {"chunk_id": 5, "html": "  <button>Register</button>", "done": false}

data: {"chunk_id": 6, "html": "</div></body></html>", "done": false}

data: {"chunk_id": 7, "html": "", "done": true, "total_chunks": 6}
```

#### Interactive Demo

Open the included demo page in your browser:

```bash
# Start the server first
cd examples/html-ui-mcp
export GOOGLE_API_KEY="your-api-key-here"
./start-streaming-server.sh

# In another terminal or browser, open:
open streaming-demo.html
# or: file:///path/to/fluidmcp/examples/html-ui-mcp/streaming-demo.html
```

**Demo Features:**
- 🎨 Live preview of HTML as it streams
- 📦 Visual chunk breakdown showing logical blocks
- ⚡ Real-time progress indicators
- 🎯 Interactive prompt editor
- 🏗️ Parent-first, then-children rendering

#### Streaming Architecture

The chunking algorithm delivers HTML in logical, renderable blocks:

1. **Chunk 1** (Parent Structure):  
   ```html
   <!DOCTYPE html><html><head>...complete styles...</head>
   <body><div class="container">
   ```

2. **Chunks 2-N** (Child Elements):  
   Each form field, button, or component as a complete unit:
   ```html
   <div class="form-group">
     <label>Username</label>
     <input type="text" name="username">
   </div>
   ```

3. **Final Chunk** (Closing Tags):  
   ```html
   </div></body></html>
   ```

This ensures **progressive rendering** - the browser can paint the parent structure immediately, then inject children as they arrive!

#### JavaScript/Fetch Example

```javascript
async function streamHTML(prompt) {
  const response = await fetch('http://localhost:8099/stream-html', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_prompt: prompt })
  });
  
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let accumulatedHTML = '';
  
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    
    const chunk = decoder.decode(value);
    const lines = chunk.split('\n');
    
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        
        if (data.done) {
          console.log('✓ Complete:', data.total_chunks, 'chunks');
          break;
        }
        
        // Progressive rendering
        accumulatedHTML += data.html;
        document.getElementById('preview').srcdoc = accumulatedHTML;
        console.log(`Chunk ${data.chunk_id}:`, data.html.length, 'chars');
      }
    }
  }
}
```

### How Progressive Streaming Works

This server uses Gemini's streaming API internally to generate HTML faster:

#### Technical Details

1. **Gemini Streaming**: Calls `generate_content_stream()` to receive HTML tokens as they're generated
2. **Chunk Collection**: Server collects all chunks internally
3. **Complete Response**: Returns full HTML via standard MCP `tools/call` response

#### Benefits

- **Faster Time-to-First-Token**: Gemini starts generating immediately
- **Reduced Latency**: Overall generation time is faster than non-streaming
- **Better Resource Usage**: Server can process HTML progressively
- **No Client Changes Needed**: Works with any MCP client (Claude Desktop, etc.)

#### Example Request (Standard MCP)

```bash
curl -X POST http://localhost:8099/html-ui/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "modify_ui_or_html",
      "arguments": {
        "user_prompt": "Create a modern dashboard"
      }
    }
  }'
```

The server internally streams from Gemini, but you receive the complete HTML in the response.

**Note**: MCP over stdio doesn't support streaming responses to the client. The streaming benefit is at the LLM API level (Gemini), which makes generation faster overall.

## Claude Desktop Configuration

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "html-ui": {
      "command": "python3",
      "args": [
        "/absolute/path/to/fluidmcp/examples/html-ui-mcp/server.py"
      ],
      "env": {
        "GEMINI_API_KEY": "..."
      }
    }
  }
}
```

Replace `/absolute/path/to/fluidmcp` with your actual path.

## Example Prompts

### Creating New UIs

```
"Create a modern SaaS landing page with hero section, features grid, pricing cards, and footer"

"Generate a dashboard with sidebar navigation, stats cards, and a chart area"

"Build a portfolio page with project cards in a masonry layout"

"Create a pricing table with three tiers and feature comparison"

"Make a contact form with name, email, message fields and nice styling"
```

### Modifying Existing UIs

```
"Add a dark mode toggle and implement dark theme styles"

"Make this layout mobile responsive with a hamburger menu"

"Add smooth scroll animations when sections come into view"

"Convert this table into a grid of cards"

"Improve the color scheme and make it look more modern"

"Add a sticky header that appears on scroll"
```

## Response Format

The tool returns HTML in MCP TextContent format:

```json
{
  "content": [
    {
      "type": "text",
      "text": "<!DOCTYPE html>\n<html>...</html>"
    }
  ]
}
```

Internally, the response includes metadata (type: "html", URI, timestamp) for resource identification, but the primary content is the raw HTML code.

The HTML can be:
- Saved to a file and opened in a browser
- Rendered in an MCP client that supports HTML display
- Further modified with additional prompts

## Building an HTML Preview Client

To display the generated HTML in a web application, use a secure sandbox:

### Secure Iframe Pattern

```html
<iframe 
  sandbox="allow-scripts"
  id="html-preview"
  style="width: 100%; height: 100%; border: none;"
></iframe>

<script>
async function generateAndPreview(prompt) {
  // Call the MCP server
  const response = await fetch('http://localhost:8099/html-ui/mcp', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      jsonrpc: '2.0',
      id: 1,
      method: 'tools/call',
      params: {
        name: 'modify_ui_or_html',
        arguments: { user_prompt: prompt }
      }
    })
  });
  
  const data = await response.json();
  const html = data.result.content[0].text;
  
  // Render in sandboxed iframe
  const iframe = document.getElementById('html-preview');
  const doc = iframe.contentDocument;
  doc.open();
  doc.write(html);
  doc.close();
}
</script>
```

### Security Best Practices

1. **Iframe Sandboxing**:
   - ✅ `allow-scripts` - Enable JavaScript for interactivity
   - ❌ **NO** `allow-same-origin` - Prevents access to parent window's cookies/localStorage
   - ❌ **NO** `allow-forms` - Prevents form submission
   - ❌ **NO** `allow-popups` - Blocks popup windows

2. **Content Security Policy**:
   ```html
   <meta http-equiv="Content-Security-Policy" 
     content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: https:;">
   ```

3. **PostMessage Communication**: Use `window.postMessage()` to safely pass data between parent and iframe.

### Example: Chat UI with Preview

See [demo.html](demo.html) for a complete example showing:
- Split-panel layout (chat + preview)
- Secure iframe rendering
- Simple UI for sending prompts
- Visual demonstration of the concept

```bash
# Open the demo
open examples/html-ui-mcp/demo.html
```

## Generated UI Characteristics

### HTML Structure
- Complete, standalone documents
- Semantic HTML5 elements
- Proper head/body/meta tags
- UTF-8 encoding

### Styling
- **Plain inline CSS** in `<style>` tags
- **NO external frameworks** (no Tailwind, Bootstrap, etc.)
- Simple, readable CSS
- Responsive layouts with CSS media queries
- Modern color schemes
- Professional spacing and typography
- Clean, minimalist designs

### JavaScript
- Vanilla JavaScript only
- No external libraries or frameworks
- No build step needed
- Simple, straightforward code

### Accessibility
- Semantic HTML elements
- ARIA labels where needed
- Keyboard navigation support
- Color contrast compliance
- Screen reader friendly

## Testing & Demo

### Interactive Demo

Open [demo.html](demo.html) in your browser to see a visual demonstration of streaming HTML generation:

```bash
# Open the demo
open examples/html-ui-mcp/demo.html
# or
firefox examples/html-ui-mcp/demo.html
```

The demo shows:
- Split-panel UI (chat + preview)
- Simulated streaming HTML chunks
- Real-time iframe rendering
- Artifact-style live preview

**Note**: This is a UI mockup. For actual streaming, run the MCP server and connect via a compatible client.

### Test Streaming Functionality

Run the included test script to verify streaming works with your Gemini API key:

```bash
cd examples/html-ui-mcp

# Set your API key
export GOOGLE_API_KEY="your-api-key-here"

# Run streaming test
python3 test_streaming.py
```

**Expected Output:**
```
============================================================
HTML UI MCP Server - Streaming Test
============================================================
✓ Gemini API configured

🚀 Testing HTML streaming generation...

Streaming HTML chunks:
------------------------------------------------------------
Chunk  1 [  48 chars]: <!DOCTYPE html>\n<html lang="en">\n<head>\n    ...
Chunk  2 [  52 chars]:     <meta charset="UTF-8">\n    <meta name="v...
Chunk  3 [  65 chars]: iewport" content="width=device-width, initial...
...
------------------------------------------------------------

✓ Streaming complete!
  - Total chunks: 15
  - Total characters: 1247
  - Final HTML length: 1247
  - HTML structure: Valid ✓

First 200 characters of generated HTML:
------------------------------------------------------------
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hello World</title>
...
------------------------------------------------------------

🔄 Testing non-streaming generation (for comparison)...

✓ Non-streaming complete!
  - HTML length: 1247
  - Valid HTML: Yes

============================================================
✅ All tests passed!
============================================================
```

### Manual Testing via FluidMCP

```bash
# Start the server
fluidmcp run examples/html-ui-mcp-config.json --file --start-server

# In another terminal, test the tool
curl -X POST http://localhost:8099/html-ui/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "modify_ui_or_html",
      "arguments": {
        "user_prompt": "Create a colorful landing page"
      }
    }
  }' | jq '.result.content[0].text' -r > output.html

# Open the generated HTML
open output.html
```

## Architecture

### MCP Protocol Compliance

The server strictly follows the Model Context Protocol:

- ✅ Uses official `mcp` package (v1.26.0+)
- ✅ Tools registered via `@app.list_tools()`
- ✅ Tool execution via `@app.call_tool()`
- ✅ Streaming via `@app.create_message()` (sampling/create_message)
- ✅ Returns standard MCP `TextContent`
- ✅ Runs on stdio transport
- ✅ No custom API endpoints
- ✅ No hardcoded UI templates

### Design Principles

1. **No Static Templates:** Server dynamically generates all HTML using AI
2. **LLM-Powered:** Uses Google Gemini with automatic model fallback for reliability
3. **Streaming Support:** Real-time HTML generation via Gemini's streaming API
4. **Simple & Clean:** Plain HTML/CSS without external frameworks or dependencies
5. **Error Handling:** Returns styled error pages as HTML
6. **Production Ready:** Generated code works immediately in any browser

### Generation Parameters

- **Temperature:** 0.3 (balanced between creativity and consistency)
- **Max Output Tokens:** 6144 (supports large, complex pages)
- **Model Fallback:** Automatic retry with alternative models if primary fails
- **Streaming:** Chunks generated progressively via `generate_content_stream()`

### Helper Function: `create_ui_resource`

```python
def create_ui_resource(html_output: str, request_id: Optional[str] = None) -> list[TextContent]:
    """
    Formats HTML output as MCP TextContent with metadata.
    
    Args:
        html_output: Generated HTML code
        request_id: Optional unique identifier (auto-generated if not provided)
        
    Returns:
        MCP-compliant TextContent list
    """
```

This helper ensures consistent response formatting while maintaining MCP protocol compliance. It adds metadata including:
- Resource type (`html`)
- Unique URI for identification (`ui://html-editor/{request_id}`)
- Encoding (UTF-8)
- Generation timestamp (ISO format)

## Troubleshooting

### Server Startup Logging

When the server starts, it logs:
- MCP server initialization status
- Google Gemini SDK availability
- API key configuration status

Look for these messages:
```
INFO:html-ui-mcp:Starting HTML UI MCP Server (Gemini-powered)
INFO:html-ui-mcp:Google Gemini SDK loaded successfully
INFO:html-ui-mcp:Gemini API key configured
```

### "No LLM provider available" Error

**Problem:** No API key configured.

**Solution:** Set your Gemini API key:
```bash
export GEMINI_API_KEY="..."
# or
export GOOGLE_API_KEY="..."
```

### "API key failed" Error

**Problem:** Invalid or expired API key.

**Solution:** 
1. Verify your API key is correct
2. Check your account has available credits/quota
3. Ensure the key has proper permissions

### Error Handling Behavior

The server returns styled HTML error pages for different failure scenarios:

1. **Missing Parameter Error** - Red error page when `user_prompt` is not provided
2. **Configuration Error** - Yellow warning page when no API key is configured (includes setup instructions)
3. **Generation Error** - Red error page with detailed error message when HTML generation fails

**Note:** Error pages use Tailwind CSS via CDN for styling (internal implementation only - generated user content uses plain HTML/CSS as specified in the system prompt).

### Model Fallback Behavior

If the primary Gemini model fails, the server automatically tries alternative models:

1. **gemini-2.5-flash** - Primary model (stable, fast)
2. **gemini-flash-latest** - If primary fails, tries auto-updated version
3. **gemini-2.5-pro** - More powerful fallback for complex requests
4. **gemini-2.0-flash** - Experimental fallback as last resort

Each failure is logged with a warning message. If all models fail, you'll see an error page listing all attempted models and their failure reasons.

### HTML Contains Markdown Code Blocks

**Problem:** LLM wrapped HTML in ```html blocks.

**Solution:** The server automatically strips markdown code blocks from the output. The cleanup logic removes both:
- Triple backticks with `html` language tag: ` ```html `
- Generic triple backticks: ` ``` `

This happens in `generate_html_with_gemini()` after receiving the response from Gemini.

### Import Errors

**Problem:** Missing dependencies.

**Solution:**
```bash
pip install -r requirements.txt
```

### Server Won't Start

**Problem:** Python version or dependency issues.

**Solution:**
1. Ensure Python 3.8+: `python3 --version`
2. Reinstall dependencies: `pip install --force-reinstall -r requirements.txt`
3. Check logs for specific errors

## Development

### Project Structure

```
html-ui-mcp/
├── server.py           # Main MCP server implementation
├── requirements.txt    # Python dependencies
├── metadata.json       # MCP server metadata
└── README.md          # This file
```

### Code Organization

**server.py sections:**
1. Imports and configuration
2. System prompt for HTML generation (enforces plain HTML/CSS, no frameworks)
3. Helper: `create_ui_resource()` - formats HTML as MCP TextContent
4. `generate_html_with_gemini()` - Gemini API integration
5. `generate_html()` - main logic with model fallback chain
6. MCP tool registration and handlers
7. Server initialization and main()

### System Prompt Design

The server uses a carefully designed system prompt that enforces:
- Plain HTML with inline CSS only
- No external frameworks (Tailwind, Bootstrap, etc.)
- Simple, readable code
- Responsive design with basic CSS media queries
- Clean output (HTML only, no markdown wrapping)

### Prompt Construction

The prompt sent to Gemini varies based on the operation:

**For new HTML generation:**
```
{SYSTEM_PROMPT}

Create: {user_prompt}

Return the complete HTML document.
```

**For modifying existing HTML:**
```
{SYSTEM_PROMPT}

Modify this HTML:
{html_code}

Change: {user_prompt}

Return the complete modified HTML.
```

This ensures the AI receives full context while maintaining consistent output format.

### Extending the Server

To add new capabilities:

1. **Modify the system prompt** (`HTML_GENERATION_SYSTEM_PROMPT`) to include new requirements
2. **Add new tool parameters** in the `inputSchema`
3. **Update the generation logic** in `generate_html_with_gemini()`
4. **Test with example prompts**

Example: Adding a "style_preference" parameter:

```python
{
    "style_preference": {
        "type": "string",
        "enum": ["minimal", "colorful", "dark", "professional"],
        "description": "Visual style preference for generated UI"
    }
}
```

### Model Configuration

To modify the Gemini model fallback chain, edit the `models_to_try` list in `generate_html()`:

```python
models_to_try = [
    "gemini-2.5-flash",      # Primary model
    "gemini-flash-latest",   # Auto-updated alternative
    "gemini-2.5-pro",        # More powerful fallback
    "gemini-2.0-flash"       # Experimental fallback
]
```

## License

MIT - See repository LICENSE file

## Support

For issues, questions, or contributions:
- Repository: https://github.com/Fluid-AI/fluidmcp
- Issues: https://github.com/Fluid-AI/fluidmcp/issues

## Changelog

### v1.0.0 (2024)
- Initial release
- Google Gemini integration with multi-model fallback
- MCP protocol compliance
- Dynamic HTML generation without templates or frameworks
- Plain HTML/CSS approach (no external dependencies)
- Responsive design with CSS media queries
- Production-ready code generation
- Automatic model fallback for reliability
- Configurable generation parameters (temp: 0.3, tokens: 6144)
