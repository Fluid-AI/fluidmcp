import os
import asyncio
import logging
import markdown
import pypandoc
import pymupdf4llm
from weasyprint import HTML, CSS
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("doc-converter")

server = Server("doc-converter")

# Professional CSS for PDF generation
PDF_CSS = """
@page { margin: 2.5cm; }
body { font-family: "Helvetica", sans-serif; font-size: 11pt; line-height: 1.6; }
h1, h2 { color: #2c3e50; border-bottom: 1px solid #eee; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
th, td { border: 1px solid #e0e0e0; padding: 8px 12px; }
th { background-color: #f8f9fa; font-weight: bold; }
pre { background-color: #f5f5f5; padding: 10px; border-radius: 5px; font-family: monospace; }
"""

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="pdf_to_markdown",
            description="Convert PDF to Markdown.",
            inputSchema={
                "type": "object",
                "properties": {
                    "input_path": {"type": "string"},
                    "output_path": {"type": "string"}
                },
                "required": ["input_path", "output_path"]
            }
        ),
        types.Tool(
            name="docx_to_markdown",
            description="Convert DOCX to Markdown.",
            inputSchema={
                "type": "object",
                "properties": {
                    "input_path": {"type": "string"},
                    "output_path": {"type": "string"}
                },
                "required": ["input_path", "output_path"]
            }
        ),
        types.Tool(
            name="markdown_to_pdf",
            description="Convert Markdown to PDF.",
            inputSchema={
                "type": "object",
                "properties": {
                    "input_path": {"type": "string"},
                    "output_path": {"type": "string"}
                },
                "required": ["input_path", "output_path"]
            }
        ),
        types.Tool(
            name="markdown_to_docx",
            description="Convert Markdown to DOCX.",
            inputSchema={
                "type": "object",
                "properties": {
                    "input_path": {"type": "string"},
                    "output_path": {"type": "string"}
                },
                "required": ["input_path", "output_path"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if not arguments:
        raise ValueError("Missing arguments")

    input_path = arguments.get("input_path")
    output_path = arguments.get("output_path")

    # Basic Validation
    if not input_path or not output_path:
        return [types.TextContent(type="text", text="Error: input_path and output_path are required.")]
    
    if not os.path.exists(input_path):
        return [types.TextContent(type="text", text=f"Error: Input file not found at {input_path}")]

    try:
        if name == "pdf_to_markdown":
            md_text = pymupdf4llm.to_markdown(input_path)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(md_text)
            return [types.TextContent(type="text", text=f"Success: {output_path}")]

        elif name == "docx_to_markdown":
            pypandoc.convert_file(input_path, 'md', outputfile=output_path)
            return [types.TextContent(type="text", text=f"Success: {output_path}")]

        elif name == "markdown_to_pdf":
            # READ THE FILE CONTENT (This was missing in your old version)
            with open(input_path, 'r', encoding='utf-8') as f:
                md_content = f.read()
            
            html_content = markdown.markdown(md_content, extensions=['tables', 'fenced_code'])
            
            html = HTML(string=html_content, base_url=os.path.dirname(input_path))
            css = CSS(string=PDF_CSS)
            html.write_pdf(output_path, stylesheets=[css])
            
            return [types.TextContent(type="text", text=f"Success: {output_path}")]

        elif name == "markdown_to_docx":
            pypandoc.convert_file(input_path, 'docx', outputfile=output_path)
            return [types.TextContent(type="text", text=f"Success: {output_path}")]

    except Exception as e:
        logger.error(f"Error executing {name}: {str(e)}")
        return [types.TextContent(type="text", text=f"Conversion Failed: {str(e)}")]
    
    return [types.TextContent(type="text", text="Tool not found")]

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="doc-converter",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())