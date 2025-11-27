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

# --- AUTOMATIC DIRECTORY SETUP ---
# Creates 'Input' and 'Output' folders in the same directory as this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "Input")
OUTPUT_DIR = os.path.join(BASE_DIR, "Output")

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

logger.info(f"Server Ready. Drop files in: {INPUT_DIR}")

# CSS for Professional PDF Generation
PDF_CSS = """
@page { margin: 2.5cm; }
body { font-family: "Helvetica", sans-serif; font-size: 11pt; line-height: 1.6; color: #333; }
h1, h2, h3 { color: #2c3e50; border-bottom: 1px solid #eee; margin-top: 1.5em; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 10pt; }
th, td { border: 1px solid #e0e0e0; padding: 8px 12px; text-align: left; }
th { background-color: #f8f9fa; font-weight: bold; }
pre { background-color: #f5f5f5; padding: 15px; border-radius: 5px; font-family: monospace; overflow-x: auto; }
code { background-color: #f5f5f5; padding: 2px 5px; border-radius: 3px; font-family: monospace; }
"""

def resolve_paths(raw_input, raw_output):
    """
    Smart path resolver:
    - If filename given, looks in Input/. If not found, checks Output/ (for chaining).
    - If absolute path given, uses it directly.
    - Always saves output to Output/ folder.
    """
    # Resolve Input
    if os.path.isabs(raw_input) and os.path.exists(raw_input):
        input_path = raw_input
    else:
        # Default: Check Input directory
        input_filename = os.path.basename(raw_input)
        input_path = os.path.join(INPUT_DIR, input_filename)
        
        # Fallback: Check Output directory (allows using previous results as input)
        if not os.path.exists(input_path):
            fallback_path = os.path.join(OUTPUT_DIR, input_filename)
            if os.path.exists(fallback_path):
                input_path = fallback_path

    # Resolve Output - Force strict structure to avoid directory errors
    # We ignore the directory part of raw_output and force it into our OUTPUT_DIR
    output_path = os.path.join(OUTPUT_DIR, os.path.basename(raw_output))
    
    return input_path, output_path

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="pdf_to_markdown",
            description="Convert PDF to Markdown. Preserves tables and layout.",
            inputSchema={
                "type": "object",
                "properties": {
                    "input_path": {"type": "string", "description": "Filename in Input folder (e.g. 'report.pdf')"},
                    "output_path": {"type": "string", "description": "Filename for Output folder (e.g. 'report.md')"}
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
            description="Convert Markdown to PDF with professional styling.",
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

    raw_input = arguments.get("input_path")
    raw_output = arguments.get("output_path")

    if not raw_input or not raw_output:
        return [types.TextContent(type="text", text="Error: input_path and output_path are required.")]

    input_path, output_path = resolve_paths(raw_input, raw_output)

    if not os.path.exists(input_path):
        return [types.TextContent(type="text", text=f"Error: File '{os.path.basename(input_path)}' not found in Input or Output directory.")]

    try:
        if name == "pdf_to_markdown":
            md_text = pymupdf4llm.to_markdown(input_path)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(md_text)
            return [types.TextContent(type="text", text=f"Success: Created {os.path.basename(output_path)}")]

        elif name == "docx_to_markdown":
            pypandoc.convert_file(input_path, 'md', outputfile=output_path)
            return [types.TextContent(type="text", text=f"Success: Created {os.path.basename(output_path)}")]

        elif name == "markdown_to_pdf":
            with open(input_path, 'r', encoding='utf-8') as f:
                md_content = f.read()
            
            html_content = markdown.markdown(md_content, extensions=['tables', 'fenced_code', 'toc'])
            html = HTML(string=html_content, base_url=os.path.dirname(input_path))
            css = CSS(string=PDF_CSS)
            html.write_pdf(output_path, stylesheets=[css])
            
            return [types.TextContent(type="text", text=f"Success: Created {os.path.basename(output_path)}")]

        elif name == "markdown_to_docx":
            pypandoc.convert_file(input_path, 'docx', outputfile=output_path)
            return [types.TextContent(type="text", text=f"Success: Created {os.path.basename(output_path)}")]

    except Exception as e:
        logger.error(f"Error executing {name}: {str(e)}")
        return [types.TextContent(type="text", text=f"Conversion Error: {str(e)}")]

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