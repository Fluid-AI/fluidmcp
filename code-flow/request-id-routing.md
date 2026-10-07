# Request ID routing: Streamable HTTP and stdio

This documents the Streamable HTTP ID-collision fix on `e2e-fluidmcp`, based on
development commit `8db4a07`. The existing stdio behavior is shown for comparison.
The legacy SSE transport is not changed by this PR.

## Endpoints and files

| Component | File | Function or class |
| --- | --- | --- |
| `POST /{server_name}/mcp` | [package_launcher.py](../fluidmcp/cli/services/package_launcher.py) | `create_dynamic_router()` -> `proxy_jsonrpc()` |
| `POST /{server_name}/mcp/tools/call` | [package_launcher.py](../fluidmcp/cli/services/package_launcher.py) | `create_dynamic_router()` -> `call_tool()` |
| Streamable HTTP forwarding | [package_launcher.py](../fluidmcp/cli/services/package_launcher.py) | `_proxy_to_http_server()` |
| Shared upstream HTTP session | [network_handle.py](../fluidmcp/cli/services/network_handle.py) | `NetworkSubprocessHandle.session_id`, `.http_client` |
| Existing stdio correlation | [stdio_jsonrpc.py](../fluidmcp/cli/services/stdio_jsonrpc.py) | `StdioJsonRpcRouter.start()`, `_handle_response()`, `PendingRequest._restore_id()` |

## Incoming JSON-RPC format

After MCP initialization, separate callers can choose the same JSON-RPC ID:

```text
Caller A                                  Caller B
POST /{server_name}/mcp                    POST /{server_name}/mcp
{                                         {
  "jsonrpc": "2.0",                         "jsonrpc": "2.0",
  "id": 1,                                 "id": 1,
  "method": "tools/call",                   "method": "tools/call",
  "params": {                              "params": {
    "name": "echo",                          "name": "echo",
    "arguments": {"token": "A"}              "arguments": {"token": "B"}
  }                                        }
}                                         }
                  |                        |
                  v                        v
package_launcher.py :: proxy_jsonrpc() -- separate waiting HTTP requests
```

The examples use an illustrative echo tool. The request ID is in the JSON-RPC
envelope; the token is tool input that identifies the caller's expected result.

## Streamable HTTP: fixed flow

```text
package_launcher.py :: proxy_jsonrpc()
    Caller A: id=1, token=A            Caller B: id=1, token=B
                  |                              |
                  v                              v
package_launcher.py :: _proxy_to_http_server()
    A's invocation saves original=1   B's invocation saves original=1
    Assigns upstream id=<UUID-A>      Assigns upstream id=<UUID-B>
                  |                              |
                  v                              v
Upstream POST /mcp                   Upstream POST /mcp
Mcp-Session-Id: S                    Mcp-Session-Id: S
{"jsonrpc":"2.0",                   {"jsonrpc":"2.0",
 "id":"<UUID-A>",                    "id":"<UUID-B>",
 "method":"tools/call",              "method":"tools/call",
 "params":{"name":"echo",            "params":{"name":"echo",
   "arguments":{"token":"A"}}}        "arguments":{"token":"B"}}}
                  |                              |
                  +---------------+--------------+
                                  |
                                  v
                 Upstream server's shared MCP session S
                 Distinct IDs identify distinct responses
                                  |
                  +---------------+--------------+
                  |                              |
                  v                              v
A's upstream HTTP response           B's upstream HTTP response
{"id":"<UUID-A>","result":...A...}  {"id":"<UUID-B>","result":...B...}
                  |                              |
                  v                              v
_proxy_to_http_server()              _proxy_to_http_server()
    Verify returned id == UUID-A        Verify returned id == UUID-B
    Restore original id=1               Restore original id=1
                  |                              |
                  v                              v
A's existing HTTP response           B's existing HTTP response
{"id":1,"result":...A...}            {"id":1,"result":...B...}
```

Abbreviated responses retain the full JSON-RPC envelope in actual traffic.
`Mcp-Session-Id: S` is a session identifier, distinct from a request ID.
The helper keeps the original and upstream IDs in each invocation; it never
uses a restored ID for another shared routing lookup. A mismatched upstream ID
produces HTTP 502 without returning the foreign payload. Error responses also
have their original IDs restored.

Streamable HTTP can return JSON or event-stream bodies. Both formats receive
the same ID validation. Event-stream framing here does not involve a legacy
SSE session, `/sse` connection, or `/messages/` endpoint.

Before the fix, both upstream requests retained `id=1` in session S. Those IDs
collided in the stateful MCP server's response routing, producing wrong-user
responses and timeouts. HTTP connection pooling itself was not the collision.

## Stdio: existing flow for comparison

```text
package_launcher.py :: proxy_jsonrpc()
    A: id=1, token=A                   B: id=1, token=B
                  |                              |
                  +---------------+--------------+
                                  |
                                  v
stdio_jsonrpc.py :: get_stdio_router(process).request()
    -> StdioJsonRpcRouter.start()
       Allocate unique internal IDs and register BEFORE writing:
         _pending[101] -> future A; PendingRequest A keeps original_id=1
         _pending[102] -> future B; PendingRequest B keeps original_id=1
                                  |
                                  v
Subprocess stdin: {"id":101,...token:A...}, {"id":102,...token:B...}
                                  |
                           MCP server executes
                                  |
                                  v
Subprocess stdout, possibly out of order:
    {"id":102,"result":...B...}
    {"id":101,"result":...A...}
                                  |
                                  v
StdioJsonRpcRouter._reader_loop() -> _dispatch_line()
    -> _dispatch_message() -> _handle_response()
       _pending.pop(102) -> future B.set_result(response)
       _pending.pop(101) -> future A.set_result(response)
                                  |
                  +---------------+--------------+
                  v                              v
PendingRequest A.wait()              PendingRequest B.wait()
    _restore_id(): 101 -> 1              _restore_id(): 102 -> 1
                  |                              |
                  v                              v
A's existing HTTP response           B's existing HTTP response
{"id":1,"result":...A...}            {"id":1,"result":...B...}
```

Internal IDs `101` and `102` are examples. Restoration occurs after selecting
the correct waiter. Late responses whose internal IDs were removed after a
timeout are dropped. The original ID therefore cannot redirect a result to
another caller during restoration.

## Convenience endpoint: no caller-supplied JSON-RPC ID

```text
Caller A                                  Caller B
POST /{server_name}/mcp/tools/call          POST /{server_name}/mcp/tools/call
{"name":"echo",                           {"name":"echo",
 "arguments":{"token":"A"}}               "arguments":{"token":"B"}}
                  |                        |
                  +------------+-----------+
                               |
                               v
package_launcher.py :: call_tool()
    Builds a JSON-RPC request for each caller:
    {"jsonrpc":"2.0","id":2,"method":"tools/call",
     "params": <the caller's name and arguments>}
                               |
                  +------------+-----------+
                  v                        v
Streamable HTTP, fixed             Stdio, existing behavior
_proxy_to_http_server()             get_stdio_router().request()
    2 -> unique UUID                   2 -> unique internal integer
    Verify response ID                 Match response to its waiter
    Restore id=2                       Restore id=2
                  |                        |
                  v                        v
    Return the result to the correct caller's waiting HTTP request
```

Before the HTTP fix, the generated `id=2` was forwarded unchanged, causing
collisions even when no user supplied an ID. The convenience endpoint needs
no client MCP handshake; FluidMCP initializes the upstream server at startup.

## Raw messages without an ID

An absent `id` in a raw JSON-RPC message denotes a notification, which expects
no JSON-RPC response. For example:

```text
POST /{server_name}/mcp
{"jsonrpc":"2.0","method":"notifications/initialized"}
    -> package_launcher.py :: proxy_jsonrpc()
    -> HTTP 204, no response body (handled locally)

Other supported notifications forwarded by _proxy_to_http_server():
    no unique request ID is added; no JSON-RPC response body is parsed.
```

This differs from `/mcp/tools/call`, which creates a request envelope for the
caller. See [the E2E README](../tests_e2e/README.md) for the two-endpoint load
tests and [the results](../tests_e2e/BASELINE.md) for before/after evidence.
