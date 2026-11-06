"""
Tunnel Test MCP Server

Standard-library-only MCP server over stdio for end-to-end tunnel tests.

Tools:
- echo: returns the message (read-only)
- sleep: waits N seconds, logging each start and finish to TUNNEL_TEST_LOG
  (default /tmp/tunnel-test-mcp.log) so tests can count how many times it ran
"""

import json
import os
import sys
import threading
import time
from datetime import datetime, timezone

LOG_PATH = os.environ.get("TUNNEL_TEST_LOG", "/tmp/tunnel-test-mcp.log")
MAX_SLEEP = 120

TOOLS = [
    {
        "name": "echo",
        "description": "Return the message unchanged. Read-only.",
        "inputSchema": {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    },
    {
        "name": "sleep",
        "description": f"Wait the given number of seconds (max {MAX_SLEEP}), then return. "
                       f"Each start and finish is appended to {LOG_PATH}.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "seconds": {"type": "number"},
                "label": {"type": "string", "description": "Written to the log to identify the call"},
            },
            "required": ["seconds"],
        },
    },
]

_write_lock = threading.Lock()


def _send(message: dict) -> None:
    with _write_lock:
        sys.stdout.write(json.dumps(message) + "\n")
        sys.stdout.flush()


def _log_run(event: str, label: str, seconds: float) -> None:
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()} {event} label={label} seconds={seconds}\n")


def _text(text: str, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _call_tool(name: str, arguments: dict) -> dict:
    if name == "echo":
        return _text(str(arguments.get("message", "")))
    if name == "sleep":
        seconds = min(max(float(arguments.get("seconds", 0)), 0), MAX_SLEEP)
        label = str(arguments.get("label", "-"))
        _log_run("start", label, seconds)
        time.sleep(seconds)
        _log_run("finish", label, seconds)
        return _text(f"slept {seconds}s (label={label})")
    return _text(f"Unknown tool: {name}", is_error=True)


def _handle(request: dict) -> None:
    method, request_id = request.get("method"), request.get("id")
    if request_id is None:
        return  # notification
    params = request.get("params") or {}
    if method == "initialize":
        result = {
            "protocolVersion": params.get("protocolVersion", "2025-03-26"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "tunnel-test-mcp", "version": "1.0.0"},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        result = _call_tool(params.get("name", ""), params.get("arguments") or {})
    else:
        _send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}})
        return
    _send({"jsonrpc": "2.0", "id": request_id, "result": result})


def main() -> None:
    # One thread per request so echo still answers while a sleep call is running.
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            continue
        threading.Thread(target=_handle, args=(request,), daemon=True).start()


if __name__ == "__main__":
    main()
