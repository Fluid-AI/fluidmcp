#!/usr/bin/env python3
"""
HTML UI MCP Server
Generates and modifies HTML UI using natural language instructions with streaming support
Implements Generative UI pattern with internal Gemini streaming for faster generation
"""

import asyncio
import json
import logging
import os
import sys
import uuid
import re
from datetime import datetime
from typing import Any, Optional, AsyncIterator

from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio as stdio

# FastAPI for HTTP streaming endpoint
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

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
    """Generate or modify HTML using Google Gemini (non-streaming version)"""
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


async def generate_html_stream_with_gemini(
    user_prompt: str, 
    html_code: Optional[str] = None, 
    model: str = "gemini-2.0-flash-exp"
) -> AsyncIterator[str]:
    """
    Generate or modify HTML using Google Gemini with streaming support.
    
    Yields HTML chunks as they're generated, enabling real-time UI updates
    similar to Claude Artifacts.
    
    Args:
        user_prompt: Natural language instruction
        html_code: Optional existing HTML to modify
        model: Gemini model to use
        
    Yields:
        HTML content chunks as strings
    """
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY environment variable not set")
    
    client = genai.Client(api_key=api_key)
    
    # Build the user message
    if html_code:
        full_prompt = f"""{HTML_GENERATION_SYSTEM_PROMPT}

Modify this HTML:\n{html_code}\n\nChange: {user_prompt}\n\nReturn the complete modified HTML."""
    else:
        full_prompt = f"""{HTML_GENERATION_SYSTEM_PROMPT}\n\nCreate: {user_prompt}\n\nReturn the complete HTML document."""
    
    # Use streaming API (returns synchronous iterator)
    # We need to run this in a thread to avoid blocking the event loop
    def _generate():
        stream = client.models.generate_content_stream(
            model=model,
            contents=full_prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=6144
            )
        )
        
        # Collect all text first, then chunk it intelligently
        full_html = ""
        in_code_block = False
        
        # Collect all chunks from Gemini
        for chunk in stream:
            if not chunk.text:
                continue
            full_html += chunk.text
        
        # Strip markdown code blocks if present
        if full_html.strip().startswith("```html"):
            full_html = full_html.strip()[7:]
        elif full_html.strip().startswith("```"):
            full_html = full_html.strip()[3:]
        
        if full_html.strip().endswith("```"):
            full_html = full_html.strip()[:-3]
        
        full_html = full_html.strip()
        
        # Intelligent parent-first chunking for progressive rendering
        # Strategy: Parent structure first, then inject children progressively
        chunks = []
        lines = full_html.split('\n')
        buffer = ""
        parent_structure_complete = False
        in_main_container = False
        
        for line in lines:
            buffer += line + '\n'
            
            # Phase 1: Build complete parent structure first
            # (<!DOCTYPE html><html><head>...</head><body><div class="container">)
            if not parent_structure_complete:
                # After </head>, continue collecting until we find the main container opening
                if '</head>' in line:
                    in_main_container = False
                
                # Look for opening body tag
                if '<body' in line:
                    in_main_container = True
                
                # After finding body, look for first container div
                if in_main_container and '<div' in line and 'class=' in line:
                    # Found main container opening - yield complete parent structure
                    chunks.append(buffer.rstrip())
                    buffer = ""
                    parent_structure_complete = True
                    in_main_container = False
            
            # Phase 2: Yield complete child elements (form-groups, buttons)
            else:
                # Yield after each complete child element
                if '</div>' in line:
                    # Check if this closes a complete child element (like form-group)
                    # Count divs in current buffer only (after last yield)
                    open_divs = buffer.count('<div')
                    close_divs = buffer.count('</div>')
                    
                    # If balanced and it's a child element (has class or contains input/label)
                    if open_divs > 0 and open_divs == close_divs:
                        if 'form-group' in buffer or 'class=' in buffer or '<input' in buffer or '<label' in buffer:
                            chunks.append(buffer.rstrip())
                            buffer = ""
                
                # Yield after complete button
                elif '</button>' in line:
                    chunks.append(buffer.rstrip())
                    buffer = ""
                
                # Yield after complete form
                elif '</form>' in line:
                    chunks.append(buffer.rstrip())
                    buffer = ""
        
        # Final chunk: Any remaining closing tags (</div></body></html>)
        if buffer.strip():
            chunks.append(buffer.strip())
        
        # Fallback: If chunking didn't work well, return whole HTML
        if not chunks or len(chunks) == 1:
            chunks = [full_html]
        
        return chunks
    
    # Run the synchronous generator in a thread pool
    chunks = await asyncio.to_thread(_generate)
    
    # Debug: Log chunk structure AFTER thread returns
    logger.info(f"[HTML-STREAM] Generated {len(chunks)} chunks for streaming")
    for i, chunk in enumerate(chunks):
        preview = chunk[:150].replace('\n', ' ').replace('  ', ' ')
        logger.info(f"  [CHUNK-{i+1}] {preview}...")
    
    # Now yield all the chunks we collected
    for chunk in chunks:
        yield chunk



async def generate_html(user_prompt: str, html_code: Optional[str] = None) -> str:
    """
    Generate or modify HTML using Google Gemini with automatic model fallback.
    Non-streaming version for backward compatibility.
    
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


async def generate_html_stream(
    user_prompt: str, 
    html_code: Optional[str] = None
) -> AsyncIterator[str]:
    """
    Generate or modify HTML using Google Gemini with streaming and automatic model fallback.
    
    Yields HTML chunks as they're generated for real-time UI updates.
    
    Tries multiple Gemini models in order:
    1. gemini-2.5-flash (stable, fast - PRIMARY)  
    2. gemini-flash-latest (auto-updated)
    3. gemini-2.5-pro (more powerful)
    4. gemini-2.0-flash (experimental)
    
    Args:
        user_prompt: Natural language instruction
        html_code: Optional existing HTML to modify
        
    Yields:
        HTML content chunks as strings
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
            logger.info(f"Using Google Gemini ({model}) for streaming HTML generation")
            
            # Yield each chunk from the stream
            async for chunk in generate_html_stream_with_gemini(user_prompt, html_code, model=model):
                yield chunk
            
            # If we successfully streamed, return
            return
            
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
                "Uses Gemini's streaming API internally for faster generation. "
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
                            "'Create a simple portfolio page', "
                            "'Build a dashboard with charts'"
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
            
            # Generate or modify HTML using streaming (internally collects all chunks)
            try:
                # Use streaming generation for faster response
                html_chunks = []
                chunk_count = 0
                
                async for chunk in generate_html_stream(user_prompt, html_code):
                    html_chunks.append(chunk)
                    chunk_count += 1
                    
                    # Log progress every 10 chunks for monitoring
                    if chunk_count % 10 == 0:
                        logger.debug(f"Received {chunk_count} HTML chunks...")
                
                html_output = "".join(html_chunks)
                logger.info(f"HTML generation complete: {chunk_count} chunks, {len(html_output)} characters")
                
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


# ============================================================================
# HTTP STREAMING ENDPOINT (FastAPI)
# ============================================================================

if FASTAPI_AVAILABLE:
    # Create FastAPI app for HTTP streaming
    http_app = FastAPI(title="HTML UI Streaming API")
    
    class StreamHTMLRequest(BaseModel):
        """Request model for streaming HTML generation"""
        user_prompt: str
        html_code: Optional[str] = None
    
    @http_app.post("/stream-html")
    async def stream_html_endpoint(request: StreamHTMLRequest):
        """
        HTTP endpoint that streams HTML chunks using Server-Sent Events (SSE)
        
        This bypasses MCP protocol limitations and provides true streaming
        to clients that can consume SSE.
        
        Example usage:
        ```bash
        curl -X POST http://localhost:8099/stream-html \\
          -H "Content-Type: application/json" \\
          -d '{"user_prompt": "Create a login page"}' \\
          -N
        ```
        """
        if not GEMINI_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Google GenAI SDK not installed. Run: pip install google-genai"
            )
        
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail="GOOGLE_API_KEY or GEMINI_API_KEY environment variable not set"
            )
        
        async def event_generator():
            """Generate SSE events with HTML chunks"""
            try:
                chunk_count = 0
                async for chunk in generate_html_stream(request.user_prompt, request.html_code):
                    chunk_count += 1
                    
                    # SSE format: data: {json}\n\n
                    event_data = json.dumps({
                        "chunk_id": chunk_count,
                        "html": chunk,
                        "done": False
                    })
                    yield f"data: {event_data}\n\n"
                
                # Send final done event
                final_data = json.dumps({
                    "chunk_id": chunk_count + 1,
                    "html": "",
                    "done": True,
                    "total_chunks": chunk_count
                })
                yield f"data: {final_data}\n\n"
                
            except Exception as e:
                error_data = json.dumps({
                    "error": str(e),
                    "done": True
                })
                yield f"data: {error_data}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )
    
    @http_app.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {
            "status": "healthy",
            "gemini_available": GEMINI_AVAILABLE,
            "api_key_configured": bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
        }


# ============================================================================
# MAIN MCP SERVER
# ============================================================================

async def main():
    """Run the MCP server"""
    logger.info("Starting HTML UI MCP Server (Gemini-powered with streaming)")
    
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


async def start_http_server():
    """Start HTTP streaming server on port 8090"""
    if not FASTAPI_AVAILABLE:
        logger.error("FastAPI not available. Install with: pip install fastapi uvicorn")
        return
    
    import uvicorn
    
    logger.info("Starting HTTP streaming server on http://localhost:8090")
    logger.info("Streaming endpoint: POST http://localhost:8090/stream-html")
    logger.info("Health check: GET http://localhost:8090/health")
    
    # Run uvicorn in the current async context
    config = uvicorn.Config(
        http_app,
        host="0.0.0.0",
        port=8090,
        log_level="info",
        access_log=False  # Reduce noise
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    import sys
    
    # Check if running in HTTP-only mode
    if "--http-only" in sys.argv:
        # HTTP streaming server only
        asyncio.run(start_http_server())
    else:
        # Default: MCP stdio server
        # (HTTP streaming available via FluidMCP gateway proxy)
        asyncio.run(main())
