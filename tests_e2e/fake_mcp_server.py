"""Real MCP SDK server with delayed echoes and an independent execution journal."""

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("http",), required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    port = int(os.environ.get("MCP_PORT", "8000"))
    server = FastMCP(
        f"echo-{args.transport}", host="127.0.0.1", port=port,
        # Exercise the stateful HTTP transport and its SSE response envelopes.
        stateless_http=False, json_response=False,
    )
    journal = args.artifacts / f"{args.transport}.jsonl"

    def record(event, **fields):
        # No await between opening and closing: records cannot interleave in this
        # single-event-loop server. Never print logs on the stdio protocol pipe.
        with journal.open("a") as output:
            output.write(json.dumps({"event": event, "time": time.monotonic(), **fields}) + "\n")

    @server.tool()
    async def echo(user_id: str, response_id: str, batch: str, delay: int) -> str:
        """Return the caller's opaque identity after a real 1–5 second delay."""
        if not 1 <= delay <= 5:
            raise ValueError("delay must be between 1 and 5 seconds")
        payload = {
            "user_id": user_id, "response_id": response_id, "batch": batch,
            "delay": delay, "transport": args.transport,
        }
        record("start", **payload)
        await asyncio.sleep(delay)
        record("finish", **payload)
        return json.dumps(payload)

    (args.artifacts / f"{args.transport}-process.json").write_text(
        json.dumps({"pid": os.getpid(), "port": port})
    )
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
