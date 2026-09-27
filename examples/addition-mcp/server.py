"""
Addition MCP Server
Accepts two numbers and returns their sum.
Runs over HTTP Streamable transport.
"""

from dotenv import load_dotenv
from fastmcp import FastMCP
import os

load_dotenv()

MCP_PORT = int(os.getenv("MCP_PORT"))
TRANSPORT_TYPE = os.getenv("TRANSPORT_TYPE", "http")

mcp = FastMCP("Addition-MCP")

@mcp.tool()
def add_numbers(a: float, b: float) -> str:
    """
    Add two numbers together and return their sum.

    Args:
        a: First number
        b: Second number

    Returns:
        The sum of a and b
    """
    return str(a + b)

if __name__ == "__main__":
    mcp.run(transport=TRANSPORT_TYPE, port=MCP_PORT)
