import asyncio
import os
import sys
import time

from fastmcp import FastMCP

TRANSPORT_TYPE = os.getenv("TRANSPORT_TYPE", "http")

mcp = FastMCP("TestServerB")


@mcp.tool(name="check_env", description="Returns the TEST_SECRET env var to verify env_file loading")
def check_env() -> dict:
    print("[check_env] called", file=sys.stderr, flush=True)
    return {
        "server": "test_b",
        "TEST_SECRET": os.getenv("TEST_SECRET", "NOT_SET"),
        "TEST_LABEL": os.getenv("TEST_LABEL", "NOT_SET"),
    }


@mcp.tool(name="sleep_test", description="Sleeps for 1 second, used for concurrency testing")
async def sleep_test() -> dict:
    req_id = time.monotonic()
    print(f"[sleep_test] START id={req_id:.4f}", file=sys.stderr, flush=True)
    await asyncio.sleep(1)
    elapsed = time.monotonic() - req_id
    print(f"[sleep_test] DONE  id={req_id:.4f} elapsed={elapsed:.3f}s", file=sys.stderr, flush=True)
    return {"server": "test_b", "status": "done"}


if __name__ == "__main__":
    mcp.run(transport=TRANSPORT_TYPE, port=int(os.getenv("MCP_PORT")))
