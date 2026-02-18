#!/usr/bin/env python3
"""
API Client MCP Server - Postman-like HTTP client for making and visualizing API requests
"""

import asyncio
import json
import time
import re
from typing import Any
import httpx
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

# Initialize MCP server
app = Server("api-client")


def highlight_json(json_str: str) -> str:
    """Apply syntax highlighting to JSON string"""
    try:
        parsed = json.loads(json_str)
        formatted = json.dumps(parsed, indent=2)

        # Simple syntax highlighting by wrapping with spans
        highlighted = formatted
        # Highlight keys (strings followed by colon)
        highlighted = re.sub(
            r'"([^"]+)"\s*:',
            r'<span class="json-key">"\1"</span>:',
            highlighted
        )
        # Highlight string values (strings NOT followed by colon)
        highlighted = re.sub(
            r':\s*"([^"]*)"',
            r': <span class="json-string">"\1"</span>',
            highlighted
        )
        # Highlight numbers
        highlighted = re.sub(
            r':\s*(-?\d+\.?\d*)',
            r': <span class="json-number">\1</span>',
            highlighted
        )
        # Highlight booleans
        highlighted = re.sub(
            r'\b(true|false)\b',
            r'<span class="json-boolean">\1</span>',
            highlighted
        )
        # Highlight null
        highlighted = re.sub(
            r'\bnull\b',
            r'<span class="json-null">null</span>',
            highlighted
        )

        return highlighted
    except:
        # If not valid JSON, return as-is
        return json_str


def get_status_color(status_code: int) -> str:
    """Get color class based on HTTP status code"""
    if 200 <= status_code < 300:
        return "text-green-600"
    elif 300 <= status_code < 400:
        return "text-blue-600"
    elif 400 <= status_code < 500:
        return "text-orange-600"
    else:
        return "text-red-600"


def format_size(size_bytes: int) -> str:
    """Format byte size to human-readable format"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


def generate_response_html(response: httpx.Response, duration_ms: float, url: str, method: str) -> str:
    """Generate rich HTML visualization of API response"""
    status_code = response.status_code
    status_text = response.reason_phrase
    status_color = get_status_color(status_code)

    # Get response body
    try:
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            body_content = highlight_json(response.text)
            body_class = "json-content"
        else:
            body_content = response.text[:10000]  # Truncate large responses
            body_class = "text-content"
    except:
        body_content = str(response.content[:10000])
        body_class = "binary-content"

    # Format headers
    headers_html = ""
    for key, value in response.headers.items():
        headers_html += f'<div class="header-item"><span class="header-key">{key}:</span> <span class="header-value">{value}</span></div>\n'

    # Get response size
    response_size = len(response.content)
    size_formatted = format_size(response_size)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>API Response - {status_code} {status_text}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Inter', sans-serif;
            background: #0f0f1e;
            color: #e4e4e7;
            min-height: 100vh;
            padding: 24px;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        .card {{
            background: #1a1a2e;
            border: 1px solid #2a2a3e;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 16px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        }}
        .status-bar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
            padding-bottom: 16px;
            border-bottom: 1px solid #2a2a3e;
        }}
        .status-badge {{
            font-size: 28px;
            font-weight: 700;
            text-shadow: 0 0 20px currentColor;
        }}
        .text-green-600 {{
            color: #10b981;
        }}
        .text-blue-600 {{
            color: #3b82f6;
        }}
        .text-orange-600 {{
            color: #f59e0b;
        }}
        .text-red-600 {{
            color: #ef4444;
        }}
        .metrics {{
            display: flex;
            gap: 32px;
            font-size: 14px;
        }}
        .metric-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            background: #16162a;
            padding: 8px 16px;
            border-radius: 8px;
            border: 1px solid #2a2a3e;
        }}
        .metric-label {{
            font-weight: 600;
            color: #a1a1aa;
        }}
        .metric-value {{
            color: #8b5cf6;
            font-weight: 700;
        }}
        .request-info {{
            font-size: 14px;
            color: #a1a1aa;
            font-family: 'Monaco', 'Courier New', monospace;
            margin-top: 16px;
            padding: 12px;
            background: #16162a;
            border-radius: 8px;
            border: 1px solid #2a2a3e;
        }}
        .method-badge {{
            display: inline-block;
            padding: 6px 14px;
            background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
            color: white;
            border-radius: 6px;
            font-weight: 700;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-right: 12px;
            box-shadow: 0 2px 8px rgba(139, 92, 246, 0.3);
        }}
        details {{
            cursor: pointer;
        }}
        summary {{
            font-size: 18px;
            font-weight: 600;
            color: #e4e4e7;
            padding: 12px 0;
            user-select: none;
            transition: color 0.2s;
        }}
        summary:hover {{
            color: #8b5cf6;
        }}
        .headers-container {{
            margin-top: 16px;
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            max-height: 400px;
            overflow-y: auto;
        }}
        .header-item {{
            padding: 10px 12px;
            background: #16162a;
            border: 1px solid #2a2a3e;
            border-radius: 6px;
            margin-bottom: 6px;
        }}
        .header-key {{
            color: #8b5cf6;
            font-weight: 600;
        }}
        .header-value {{
            color: #a1a1aa;
            margin-left: 8px;
        }}
        .body-container {{
            margin-top: 16px;
        }}
        pre {{
            background: #0a0a14;
            color: #e4e4e7;
            padding: 24px;
            border-radius: 8px;
            border: 1px solid #2a2a3e;
            overflow-x: auto;
            font-family: 'Monaco', 'Courier New', 'Fira Code', monospace;
            font-size: 13px;
            line-height: 1.8;
            max-height: 600px;
            overflow-y: auto;
        }}
        .json-key {{
            color: #60a5fa;
            font-weight: 600;
        }}
        .json-string {{
            color: #34d399;
        }}
        .json-number {{
            color: #fbbf24;
        }}
        .json-boolean {{
            color: #f472b6;
        }}
        .json-null {{
            color: #9ca3af;
        }}
        .section-title {{
            font-size: 18px;
            font-weight: 600;
            color: #e4e4e7;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .copy-button {{
            position: absolute;
            top: 16px;
            right: 16px;
            background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 600;
            transition: all 0.2s;
            box-shadow: 0 2px 8px rgba(139, 92, 246, 0.3);
        }}
        .copy-button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(139, 92, 246, 0.5);
        }}
        .copy-button:active {{
            transform: translateY(0);
        }}
        .body-wrapper {{
            position: relative;
        }}
        /* Scrollbar styling */
        ::-webkit-scrollbar {{
            width: 10px;
            height: 10px;
        }}
        ::-webkit-scrollbar-track {{
            background: #16162a;
            border-radius: 5px;
        }}
        ::-webkit-scrollbar-thumb {{
            background: #8b5cf6;
            border-radius: 5px;
        }}
        ::-webkit-scrollbar-thumb:hover {{
            background: #7c3aed;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Status Bar -->
        <div class="card">
            <div class="status-bar">
                <div>
                    <span class="status-badge {status_color}">{status_code} {status_text}</span>
                </div>
                <div class="metrics">
                    <div class="metric-item">
                        <span class="metric-label">⏱️</span>
                        <span class="metric-value">{duration_ms:.0f}ms</span>
                    </div>
                    <div class="metric-item">
                        <span class="metric-label">📦</span>
                        <span class="metric-value">{size_formatted}</span>
                    </div>
                </div>
            </div>
            <div class="request-info">
                <span class="method-badge">{method}</span>
                <span>{url}</span>
            </div>
        </div>

        <!-- Response Headers -->
        <div class="card">
            <details>
                <summary>📋 Response Headers ({len(response.headers)})</summary>
                <div class="headers-container">
                    {headers_html}
                </div>
            </details>
        </div>

        <!-- Response Body -->
        <div class="card">
            <div class="section-title">📄 Response Body</div>
            <div class="body-wrapper">
                <button class="copy-button" onclick="copyToClipboard()">📋 Copy</button>
                <pre id="responseBody" class="{body_class}">{body_content}</pre>
            </div>
        </div>
    </div>

    <script>
        function copyToClipboard() {{
            const body = document.getElementById('responseBody').innerText;
            navigator.clipboard.writeText(body).then(() => {{
                const btn = document.querySelector('.copy-button');
                const originalText = btn.textContent;
                btn.textContent = '✓ Copied!';
                setTimeout(() => {{
                    btn.textContent = originalText;
                }}, 2000);
            }});
        }}
    </script>
</body>
</html>'''


def generate_error_html(error_message: str, url: str = "", method: str = "GET") -> str:
    """Generate HTML for error messages"""
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>API Request Error</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Inter', sans-serif;
            background: #0f0f1e;
            color: #e4e4e7;
            min-height: 100vh;
            padding: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .container {{
            max-width: 800px;
            width: 100%;
        }}
        .error-card {{
            background: #1a1a2e;
            border: 2px solid #ef4444;
            border-radius: 12px;
            box-shadow: 0 8px 24px rgba(239, 68, 68, 0.2);
            padding: 48px 32px;
        }}
        .error-icon {{
            font-size: 64px;
            text-align: center;
            margin-bottom: 24px;
            filter: drop-shadow(0 0 20px rgba(239, 68, 68, 0.5));
        }}
        .error-title {{
            font-size: 32px;
            font-weight: 700;
            color: #ef4444;
            text-align: center;
            margin-bottom: 16px;
            text-shadow: 0 0 20px rgba(239, 68, 68, 0.3);
        }}
        .error-message {{
            font-size: 16px;
            color: #d4d4d8;
            text-align: center;
            line-height: 1.8;
            margin-bottom: 32px;
            padding: 16px;
            background: #16162a;
            border-radius: 8px;
            border: 1px solid #2a2a3e;
        }}
        .request-details {{
            background: #16162a;
            padding: 16px;
            border-radius: 8px;
            border: 1px solid #2a2a3e;
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 14px;
            color: #a1a1aa;
        }}
        .method-badge {{
            display: inline-block;
            padding: 6px 14px;
            background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
            color: white;
            border-radius: 6px;
            font-weight: 700;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-right: 12px;
            box-shadow: 0 2px 8px rgba(139, 92, 246, 0.3);
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="error-card">
            <div class="error-icon">❌</div>
            <div class="error-title">Request Failed</div>
            <div class="error-message">{error_message}</div>
            {f'<div class="request-details"><span class="method-badge">{method}</span><span>{url}</span></div>' if url else ''}
        </div>
    </div>
</body>
</html>'''


async def make_http_request(
    url: str,
    method: str = "GET",
    headers: list = None,
    query_params: list = None,
    body: str = None,
    body_type: str = "json",
    timeout: int = 30,
    follow_redirects: bool = True
) -> tuple[httpx.Response, float]:
    """
    Make HTTP request with full configuration

    Returns tuple of (response, duration_ms)
    """
    # Convert arrays to dicts
    headers_dict = {}
    if headers and isinstance(headers, list):
        for h in headers:
            if isinstance(h, dict) and "key" in h and "value" in h:
                headers_dict[h["key"]] = h["value"]

    params_dict = {}
    if query_params and isinstance(query_params, list):
        for p in query_params:
            if isinstance(p, dict) and "key" in p and "value" in p:
                params_dict[p["key"]] = p["value"]

    # Prepare request body
    request_body = None
    request_json = None
    request_data = None

    if body and body_type != "none":
        if body_type == "json":
            try:
                request_json = json.loads(body)
                if "Content-Type" not in headers_dict:
                    headers_dict["Content-Type"] = "application/json"
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON body: {str(e)}")
        elif body_type == "text":
            request_data = body
            if "Content-Type" not in headers_dict:
                headers_dict["Content-Type"] = "text/plain"
        elif body_type == "form":
            # Parse form data (key=value&key2=value2)
            try:
                request_data = dict(x.split("=") for x in body.split("&"))
                if "Content-Type" not in headers_dict:
                    headers_dict["Content-Type"] = "application/x-www-form-urlencoded"
            except:
                raise ValueError("Invalid form data format. Expected: key=value&key2=value2")

    # Make request with timing
    start_time = time.time()

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=follow_redirects) as client:
        response = await client.request(
            method=method.upper(),
            url=url,
            headers=headers_dict,
            params=params_dict,
            json=request_json,
            data=request_data
        )

    duration_ms = (time.time() - start_time) * 1000

    return response, duration_ms


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools"""
    return [
        Tool(
            name="make_http_request",
            description="Make HTTP requests with full control over method, headers, query params, and body. Returns a rich HTML visualization of the response with syntax-highlighted JSON, status codes, timing, and headers.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full URL including protocol (e.g., https://api.example.com/users or https://jsonplaceholder.typicode.com/posts)"
                    },
                    "method": {
                        "type": "string",
                        "description": "HTTP method",
                        "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
                        "default": "GET"
                    },
                    "headers": {
                        "type": "array",
                        "description": "HTTP headers as key-value pairs. Example: [{'key': 'Authorization', 'value': 'Bearer token'}, {'key': 'Content-Type', 'value': 'application/json'}]",
                        "items": {
                            "type": "object",
                            "properties": {
                                "key": {"type": "string", "description": "Header name"},
                                "value": {"type": "string", "description": "Header value"}
                            },
                            "required": ["key", "value"]
                        },
                        "default": []
                    },
                    "query_params": {
                        "type": "array",
                        "description": "Query parameters as key-value pairs. Example: [{'key': 'userId', 'value': '1'}, {'key': 'limit', 'value': '10'}]",
                        "items": {
                            "type": "object",
                            "properties": {
                                "key": {"type": "string", "description": "Parameter name"},
                                "value": {"type": "string", "description": "Parameter value"}
                            },
                            "required": ["key", "value"]
                        },
                        "default": []
                    },
                    "body": {
                        "type": "string",
                        "description": "Request body content. For JSON, provide a JSON string. For form data, use key=value&key2=value2 format. For text, provide plain text."
                    },
                    "body_type": {
                        "type": "string",
                        "description": "Body content type",
                        "enum": ["json", "form", "text", "none"],
                        "default": "json"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Request timeout in seconds (default: 30)",
                        "default": 30,
                        "minimum": 1,
                        "maximum": 300
                    },
                    "follow_redirects": {
                        "type": "boolean",
                        "description": "Follow HTTP redirects (default: true)",
                        "default": True
                    }
                },
                "required": ["url"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool execution"""
    if name == "make_http_request":
        try:
            # Extract arguments
            url = arguments.get("url")
            method = arguments.get("method", "GET")
            headers = arguments.get("headers", [])
            query_params = arguments.get("query_params", [])
            body = arguments.get("body")
            body_type = arguments.get("body_type", "json")
            timeout = arguments.get("timeout", 30)
            follow_redirects = arguments.get("follow_redirects", True)

            # Auto-detect POST if body is provided but method is GET
            if body and method == "GET":
                method = "POST"
                print(f"[API Client] Auto-detected POST method due to body presence")

            # Debug logging
            print(f"[API Client] Making {method} request to {url}")
            if body:
                print(f"[API Client] Body type: {body_type}, Body length: {len(body)} chars")

            # Validate required fields
            if not url:
                return [TextContent(
                    type="text",
                    text=generate_error_html("URL is required")
                )]

            # Validate URL format
            if not url.startswith(("http://", "https://")):
                return [TextContent(
                    type="text",
                    text=generate_error_html(
                        "Invalid URL format. URL must start with http:// or https://",
                        url,
                        method
                    )
                )]

            # Make the request
            response, duration_ms = await make_http_request(
                url=url,
                method=method,
                headers=headers,
                query_params=query_params,
                body=body,
                body_type=body_type,
                timeout=timeout,
                follow_redirects=follow_redirects
            )

            # Generate HTML response
            html_output = generate_response_html(response, duration_ms, url, method)

            return [TextContent(type="text", text=html_output)]

        except httpx.TimeoutException:
            return [TextContent(
                type="text",
                text=generate_error_html(
                    f"Request timed out after {arguments.get('timeout', 30)} seconds",
                    arguments.get("url", ""),
                    arguments.get("method", "GET")
                )
            )]
        except httpx.HTTPError as e:
            return [TextContent(
                type="text",
                text=generate_error_html(
                    f"HTTP error: {str(e)}",
                    arguments.get("url", ""),
                    arguments.get("method", "GET")
                )
            )]
        except ValueError as e:
            return [TextContent(
                type="text",
                text=generate_error_html(
                    str(e),
                    arguments.get("url", ""),
                    arguments.get("method", "GET")
                )
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=generate_error_html(
                    f"Unexpected error: {str(e)}",
                    arguments.get("url", ""),
                    arguments.get("method", "GET")
                )
            )]

    return [TextContent(
        type="text",
        text=generate_error_html(f"Unknown tool: {name}")
    )]


async def main():
    """Run the MCP server"""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
