# HTML UI MCP Server

An AI-powered Model Context Protocol (MCP) server that generates and modifies HTML user interfaces using natural language instructions.

## Overview

This MCP server acts as an intelligent HTML/CSS/JavaScript generator that can:

- ✨ Generate complete HTML UIs from natural language descriptions
- 🎨 Modify existing HTML code based on instructions
- 📱 Create responsive, mobile-friendly layouts
- 🌓 Support dark and light themes
- ⚡ Use plain HTML with inline CSS (no external frameworks)
- ♿ Follow accessibility best practices
- 🚀 Produce simple, clean, production-ready code

## Features

### Single Tool: `modify_ui_or_html`

**Purpose:** Generate or modify HTML UI using natural language instructions. Creates simple, clean HTML pages with inline CSS styling.

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

## Architecture

### MCP Protocol Compliance

The server strictly follows the Model Context Protocol:

- ✅ Uses official `mcp` package
- ✅ Tools registered via `@app.list_tools()`
- ✅ Tool execution via `@app.call_tool()`
- ✅ Returns standard MCP `TextContent`
- ✅ Runs on stdio transport
- ✅ No custom API endpoints
- ✅ No hardcoded UI templates

### Design Principles

1. **No Static Templates:** Server dynamically generates all HTML using AI
2. **LLM-Powered:** Uses Google Gemini with automatic model fallback for reliability
3. **Simple & Clean:** Plain HTML/CSS without external frameworks or dependencies
4. **Error Handling:** Returns styled error pages as HTML
5. **Production Ready:** Generated code works immediately in any browser

### Generation Parameters

- **Temperature:** 0.3 (balanced between creativity and consistency)
- **Max Output Tokens:** 6144 (supports large, complex pages)
- **Model Fallback:** Automatic retry with alternative models if primary fails

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
