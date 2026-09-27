"""
Echo MCP Server
Returns the input message unchanged. Useful for connectivity smoke-tests.
Runs over HTTP Streamable transport.
"""

from dotenv import load_dotenv
from fastmcp import FastMCP
import os

load_dotenv()

MCP_PORT = int(os.getenv("MCP_PORT"))
TRANSPORT_TYPE = os.getenv("TRANSPORT_TYPE", "http")

mcp = FastMCP("Echo-MCP")


@mcp.tool()
def echo(message: str) -> str:
    """
    Return the input message unchanged.

    Args:
        message: Any string to echo back

    Returns:
        The same string that was passed in
    """
    return message


if __name__ == "__main__":
    mcp.run(transport=TRANSPORT_TYPE, port=MCP_PORT)
