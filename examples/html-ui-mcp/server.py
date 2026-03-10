#!/usr/bin/env python3
"""
HTML UI MCP Server
Generates and modifies HTML UI using natural language instructions
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime
from typing import Any, Optional

from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio as stdio

# Import Google Gemini
try:
    from google import genai
    from google.genai import types as genai_types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    raise ImportError("Google GenAI SDK not installed. Run: pip install google-genai")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("html-ui-mcp")

# Initialize MCP server
app = Server("html-ui")

# System prompt for HTML generation
HTML_GENERATION_SYSTEM_PROMPT = """You are an HTML/CSS/JavaScript developer. Generate clean, simple web pages.

REQUIREMENTS:
- Use plain HTML with inline CSS in <style> tags
- NO frameworks (no Tailwind, Bootstrap, etc.)
- Keep code simple and readable
- Make it responsive with basic CSS media queries
- Return ONLY the HTML code (no markdown, no explanations)

STYLE:
- Clean, professional designs
- Good spacing and typography
- Simple color schemes
- Responsive for mobile

OUTPUT:
Return just the HTML document, nothing else."""


def create_ui_resource(html_output: str, request_id: Optional[str] = None) -> list[TextContent]:
    """
    Create a UI resource response in MCP format.
    
    This helper function formats HTML output as an MCP TextContent response
    with metadata indicating it's HTML content that can be rendered.
    
    Args:
        html_output: The generated HTML code
        request_id: Optional unique identifier for this UI resource
        
    Returns:
        List of TextContent formatted for MCP protocol
    """
    if request_id is None:
        request_id = str(uuid.uuid4())
    
    # Format the response with metadata for the MCP client
    # The HTML is wrapped in a structured format that indicates:
    # 1. This is HTML content (not plain text)
    # 2. It should be rendered, not displayed as code
    # 3. A unique URI for resource identification
    
    response_metadata = {
        "type": "html",
        "uri": f"ui://html-editor/{request_id}",
        "encoding": "utf-8",
        "generated_at": datetime.utcnow().isoformat()
    }
    
    # Return MCP-compliant TextContent with HTML
    # The HTML is returned as-is so it can be extracted and rendered
    return [
        TextContent(
            type="text",
            text=html_output
        )
    ]


async def generate_html_with_gemini(user_prompt: str, html_code: Optional[str] = None, model: str = "gemini-2.0-flash-exp") -> str:
    """Generate or modify HTML using Google Gemini"""
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY environment variable not set")
    
    client = genai.Client(api_key=api_key)
    
    # Build the user message
    if html_code:
        # For modifications, keep it concise
        full_prompt = f"""{HTML_GENERATION_SYSTEM_PROMPT}

Modify this HTML:\n{html_code}\n\nChange: {user_prompt}\n\nReturn the complete modified HTML."""
    else:
        # For new generation
        full_prompt = f"""{HTML_GENERATION_SYSTEM_PROMPT}\n\nCreate: {user_prompt}\n\nReturn the complete HTML document."""
    
    response = client.models.generate_content(
        model=model,
        contents=full_prompt,
        config=genai_types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=6144
        )
    )
    
    html_output = response.text.strip()
    
    # Clean up markdown code blocks if present
    if html_output.startswith("```html"):
        html_output = html_output[7:]
    elif html_output.startswith("```"):
        html_output = html_output[3:]
    
    if html_output.endswith("```"):
        html_output = html_output[:-3]
    
    return html_output.strip()


async def generate_html(user_prompt: str, html_code: Optional[str] = None) -> str:
    """
    Generate or modify HTML using Google Gemini with automatic model fallback.
    
    Tries multiple Gemini models in order:
    1. gemini-2.5-flash (stable, fast - PRIMARY)
    2. gemini-flash-latest (auto-updated)
    3. gemini-2.5-pro (more powerful)
    4. gemini-2.0-flash (experimental)
    """
    if not GEMINI_AVAILABLE:
        raise ValueError("Google GenAI SDK not installed. Run: pip install google-genai")
    
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable required")
    
    # Try multiple models with fallback
    models_to_try = [
        "gemini-2.5-flash",
        "gemini-flash-latest",
        "gemini-2.5-pro",
        "gemini-2.0-flash"
    ]
    
    errors = []
    for model in models_to_try:
        try:
            logger.info(f"Using Google Gemini ({model}) for HTML generation")
            return await generate_html_with_gemini(user_prompt, html_code, model=model)
        except Exception as e:
            error_msg = f"{model} failed: {str(e)}"
            logger.warning(error_msg)
            errors.append(error_msg)
            # Continue to next model
    
    # If all models failed
    error_message = "All Gemini models failed. Please try again later.\n\n"
    error_message += "Errors:\n" + "\n".join(errors)
    raise ValueError(error_message)


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available HTML UI generation tools"""
    return [
        Tool(
            name="modify_ui_or_html",
            description=(
                "Generate or modify HTML using natural language instructions. "
                "Creates simple, clean HTML pages with inline CSS styling. "
                "Can create new HTML from scratch or modify existing HTML code. "
                "Generates responsive, easy-to-understand HTML/CSS/JavaScript."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_prompt": {
                        "type": "string",
                        "description": (
                            "Natural language instruction describing what to create. "
                            "Examples: 'Create a login page', "
                            "'Add a navigation menu', "
                            "'Make this responsive', "
                            "'Add a contact form', "
                            "'Create a simple portfolio page'"
                        )
                    },
                    "html_code": {
                        "type": "string",
                        "description": (
                            "Optional existing HTML code to modify. "
                            "If provided, the tool will modify this HTML according to the user_prompt. "
                            "If not provided, a completely new HTML document will be generated."
                        )
                    }
                },
                "required": ["user_prompt"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls"""
    try:
        if arguments is None:
            arguments = {}
        
        if name == "modify_ui_or_html":
            user_prompt = arguments.get("user_prompt")
            html_code = arguments.get("html_code")
            
            # Validate required parameter
            if not user_prompt:
                error_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Error</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 flex items-center justify-center min-h-screen p-4">
    <div class="bg-red-900 border border-red-700 text-red-100 px-6 py-4 rounded-lg max-w-md">
        <h2 class="text-xl font-bold mb-2">⚠️ Error</h2>
        <p>The <code class="bg-red-950 px-2 py-1 rounded">user_prompt</code> parameter is required.</p>
        <p class="mt-2 text-sm">Please provide a natural language instruction describing the UI you want to create or modify.</p>
    </div>
</body>
</html>"""
                return create_ui_resource(error_html)
            
            logger.info(f"Generating HTML for prompt: {user_prompt[:100]}...")
            
            # Generate or modify HTML
            try:
                html_output = await generate_html(user_prompt, html_code)
                logger.info("HTML generation successful")
                return create_ui_resource(html_output)
            
            except ValueError as e:
                # Configuration error (no API keys)
                error_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Configuration Error</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 flex items-center justify-center min-h-screen p-4">
    <div class="bg-yellow-900 border border-yellow-700 text-yellow-100 px-6 py-4 rounded-lg max-w-2xl">
        <h2 class="text-xl font-bold mb-3">⚙️ Configuration Required</h2>
        <p class="mb-3">{str(e)}</p>
        <div class="bg-yellow-950 p-3 rounded text-sm">
            <p class="font-semibold mb-2">Setup Instructions:</p>
            <ol class="list-decimal list-inside space-y-1">
                <li>Get an API key from one of the supported providers</li>
                <li>Set the environment variable before running the server</li>
                <li>Restart the MCP server</li>
            </ol>
        </div>
    </div>
</body>
</html>"""
                return create_ui_resource(error_html)
            
            except Exception as e:
                # Generation error
                logger.error(f"HTML generation error: {str(e)}")
                error_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Generation Error</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 flex items-center justify-center min-h-screen p-4">
    <div class="bg-red-900 border border-red-700 text-red-100 px-6 py-4 rounded-lg max-w-lg">
        <h2 class="text-xl font-bold mb-2">❌ Generation Error</h2>
        <p class="mb-2">Failed to generate HTML:</p>
        <pre class="bg-red-950 p-3 rounded text-sm overflow-x-auto">{str(e)}</pre>
    </div>
</body>
</html>"""
                return create_ui_resource(error_html)
        
        else:
            return [TextContent(
                type="text",
                text=f"Unknown tool: {name}"
            )]
    
    except Exception as e:
        logger.error(f"Error executing {name}: {str(e)}")
        return [TextContent(
            type="text",
            text=f"Error: {str(e)}"
        )]


async def main():
    """Run the MCP server"""
    logger.info("Starting HTML UI MCP Server (Gemini-powered)")
    
    # Check Gemini availability
    if GEMINI_AVAILABLE:
        logger.info("Google Gemini SDK loaded successfully")
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if api_key:
            logger.info("Gemini API key configured")
        else:
            logger.warning("GOOGLE_API_KEY or GEMINI_API_KEY not set")
    else:
        logger.error("Google GenAI SDK not installed. Run: pip install google-genai")
    
    # Run stdio transport
    async with stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
