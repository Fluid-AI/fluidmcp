"""
DEPRECATED: Legacy router implementations.

These modules contain the old static per-server router approach used prior to
the unified dynamic router architecture.

DO NOT use these in new code. The single source of truth for routing is:
    fluidmcp.cli.services.package_launcher.create_dynamic_router

All commands (run, github, serve) now use create_dynamic_router(server_manager).
"""
