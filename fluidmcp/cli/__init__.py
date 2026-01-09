"""
FluidMCP - A CLI tool for orchestrating Model Context Protocol servers.

This package provides a unified interface for managing and running
multiple MCP servers through a single configuration file.
"""

__version__ = "0.1.0"
__author__ = "Fluid AI"
__email__ = "info@fluid.ai"

# Import main function when __init__.py is imported
# This allows: from fluidmcp import main
def main():
    """Entry point for CLI commands."""
    from .cli import main as cli_main
    return cli_main()

__all__ = ["main"]
