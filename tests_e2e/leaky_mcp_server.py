"""Real MCP SDK server that deliberately leaks dummy credentials to its output.

Used by test_security_redaction.py to prove FluidMCP sanitizes child-process
output before it is logged, persisted or served. Every secret it prints comes
from its own environment (``--leak-env NAME``, repeatable), the value of
``--api-key``, and the lines of ``--leak-file``; the tests pass dummy
credentials only.

Modes:
  crash  print the secrets to stderr and stdout, then exit 3 (startup crash).
  serve  print the secrets to stderr (and, for stdio, a non-JSON stdout line),
         then serve MCP with a ``ping`` tool over ``--transport``. With
         ``--exit-after N`` it leaks again and crashes (exit 3) after N seconds,
         which makes FluidMCP's health monitor record a crash event.
"""

import argparse
import os
import sys
import threading

from mcp.server.fastmcp import FastMCP


def leak_line(args):
    values = [os.environ.get(name, "") for name in args.leak_env] + [args.api_key or ""]
    if args.leak_file:
        # Credentials that never pass through FluidMCP's configuration: only
        # pattern-based detection can catch these.
        with open(args.leak_file) as handle:
            values += [line.rstrip("\n") for line in handle if line.strip()]
    return "auth failed for credentials: " + " | ".join(values)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("crash", "serve"), required=True)
    parser.add_argument("--transport", choices=("http", "stdio"), default="http")
    parser.add_argument("--leak-env", action="append", default=[])
    parser.add_argument("--api-key")
    parser.add_argument("--leak-file")
    parser.add_argument("--exit-after", type=float)
    args = parser.parse_args()

    line = leak_line(args)
    print(line, file=sys.stderr, flush=True)

    if args.mode == "crash":
        print(line, flush=True)
        sys.exit(3)

    if args.transport == "stdio":
        # Non-JSON noise on the protocol pipe, as misbehaving servers do.
        print(line, flush=True)
        server = FastMCP("leaky-stdio")
    else:
        server = FastMCP("leaky-http", host="127.0.0.1", port=int(os.environ.get("MCP_PORT", "8000")),
                         stateless_http=False, json_response=False)

    @server.tool()
    async def ping(message: str) -> str:
        """Echo a message (proves the server is functional after leaking)."""
        return f"pong: {message}"

    if args.exit_after:
        def crash():
            print("fatal: " + line, file=sys.stderr, flush=True)
            os._exit(3)
        threading.Timer(args.exit_after, crash).start()

    server.run(transport="stdio" if args.transport == "stdio" else "streamable-http")


if __name__ == "__main__":
    main()
