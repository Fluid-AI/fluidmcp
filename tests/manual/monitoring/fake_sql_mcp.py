#!/usr/bin/env python3
"""A stdio MCP server that simulates a database-backed MCP, for monitoring tests.

Its behaviour is driven by the presence of flag files so a test can flip it
between healthy and broken WITHOUT restarting the process. That is the entire
point of the exercise: a broken database connection does not kill the process,
so no process-level health check can see it.

Flags (paths overridable via env):
  FAKESQL_BREAK_FLAG    execute_query returns isError with an ECONNREFUSED message
                        (a 200 OK JSON-RPC *result* — how real MCPs report this)
  FAKESQL_AUTHFAIL_FLAG execute_query returns a JSON-RPC error (login failed)
  FAKESQL_CRASH_FLAG    process exits immediately with the exit code in the file

Usage:
    python3 fake_sql_mcp.py            # speaks MCP over stdio
    touch /tmp/_fakesql_broken         # break the "database"
    rm /tmp/_fakesql_broken            # heal it
"""
import json
import os
import sys

BREAK_FLAG = os.environ.get("FAKESQL_BREAK_FLAG", "/tmp/_fakesql_broken")
AUTHFAIL_FLAG = os.environ.get("FAKESQL_AUTHFAIL_FLAG", "/tmp/_fakesql_authfail")
CRASH_FLAG = os.environ.get("FAKESQL_CRASH_FLAG", "/tmp/_fakesql_crash")

TOOLS = [
    {
        "name": "execute_query",
        "description": "Run a SQL query against the configured database",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "list_tables",
        "description": "List tables (never touches the database)",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def reply(msg_id, result=None, error=None):
    payload = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def warn(message):
    sys.stderr.write(message + "\n")
    sys.stderr.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        if os.path.exists(CRASH_FLAG):
            try:
                with open(CRASH_FLAG) as f:
                    code = int(f.read().strip() or "1")
            except (ValueError, OSError):
                code = 1
            warn("FATAL: simulated crash")
            os._exit(code)

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = request.get("method")
        msg_id = request.get("id")

        # Notifications carry no id and must not be answered.
        if msg_id is None:
            continue

        if method == "initialize":
            reply(msg_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-sql", "version": "1.0.0"},
            })
        elif method == "tools/list":
            reply(msg_id, {"tools": TOOLS})
        elif method == "ping":
            reply(msg_id, {})
        elif method == "tools/call":
            name = (request.get("params") or {}).get("name")
            if name == "execute_query":
                if os.path.exists(AUTHFAIL_FLAG):
                    # Transport-level failure: a real JSON-RPC error.
                    reply(msg_id, error={
                        "code": -32603,
                        "message": "Login failed for user 'sa'.",
                    })
                    warn("Login failed for user 'sa'.")
                elif os.path.exists(BREAK_FLAG):
                    # The important case: a *successful* JSON-RPC result whose
                    # payload says isError. Invisible to process health checks.
                    reply(msg_id, {
                        "content": [{
                            "type": "text",
                            "text": "Error: connect ECONNREFUSED 10.20.1.44:1433",
                        }],
                        "isError": True,
                    })
                    warn("Error: connect ECONNREFUSED 10.20.1.44:1433")
                else:
                    reply(msg_id, {
                        "content": [{"type": "text", "text": "1 row: [1]"}],
                        "isError": False,
                    })
            elif name == "list_tables":
                reply(msg_id, {
                    "content": [{"type": "text", "text": "users, orders"}],
                    "isError": False,
                })
            else:
                reply(msg_id, error={"code": -32601, "message": f"Unknown tool: {name}"})
        else:
            reply(msg_id, error={"code": -32601, "message": f"Unknown method: {method}"})


if __name__ == "__main__":
    main()
