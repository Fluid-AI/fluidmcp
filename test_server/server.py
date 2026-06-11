import asyncio
import os
import sys
import time

from fastmcp import FastMCP

mcp = FastMCP("test-server")


@mcp.tool()
def sleep_test_sync() -> dict:
    req_id = time.monotonic()
    print(f"[sleep_test_sync] START id={req_id:.4f}", file=sys.stderr, flush=True)
    time.sleep(1)
    elapsed = time.monotonic() - req_id
    print(f"[sleep_test_sync] DONE  id={req_id:.4f} elapsed={elapsed:.3f}s", file=sys.stderr, flush=True)
    return {"status": "done", "type": "sync"}


@mcp.tool()
async def sleep_test_async() -> dict:
    req_id = time.monotonic()
    print(f"[sleep_test_async] START id={req_id:.4f}", file=sys.stderr, flush=True)
    await asyncio.sleep(1)
    elapsed = time.monotonic() - req_id
    print(f"[sleep_test_async] DONE  id={req_id:.4f} elapsed={elapsed:.3f}s", file=sys.stderr, flush=True)
    return {"status": "done", "type": "async"}


@mcp.tool()
async def hang_forever() -> dict:
    """Hangs indefinitely — used to trigger a 504 and test immediate restart."""
    print("[hang_forever] START — sleeping forever", file=sys.stderr, flush=True)
    await asyncio.sleep(9999)
    return {"status": "done"}


if __name__ == "__main__":
    transport = os.environ.get("TRANSPORT_TYPE", "http")
    port = int(os.environ.get("MCP_PORT", "8500"))
    mcp.run(transport=transport, port=port)
