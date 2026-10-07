# Request ID routing: stdio and Streamable HTTP

This documents the transport fix on branch `e2e-fluidmcp`, based on development
commit `8db4a07`. The current fixed flows appear first. The original HTTP
collision diagrams are retained below and explicitly labeled as before the fix.

`{server_name}` is the configured MCP server name. The JSON examples use an
illustrative `echo` tool accepting a `token` argument. A and B represent separate
callers, each with its own waiting HTTP request. Internal IDs `101` and `102`
are illustrative; the stdio router allocates them from a per-router counter.

## Endpoints and source files

| Component | File | Function or class |
| --- | --- | --- |
| `POST /{server_name}/mcp` | [package_launcher.py](../fluidmcp/cli/services/package_launcher.py) | `create_dynamic_router()` -> `proxy_jsonrpc()` |
| `POST /{server_name}/mcp/tools/call` | [package_launcher.py](../fluidmcp/cli/services/package_launcher.py) | `create_dynamic_router()` -> `call_tool()` |
| Stdio ID allocation and response matching | [stdio_jsonrpc.py](../fluidmcp/cli/services/stdio_jsonrpc.py) | `get_stdio_router()`, `StdioJsonRpcRouter.start()`, `_handle_response()` |
| Stdio original-ID restoration | [stdio_jsonrpc.py](../fluidmcp/cli/services/stdio_jsonrpc.py) | `PendingRequest.wait()`, `_restore_id()` |
| Upstream Streamable HTTP forwarding | [package_launcher.py](../fluidmcp/cli/services/package_launcher.py) | `_proxy_to_http_server()` |
| Shared upstream HTTP session and client | [network_handle.py](../fluidmcp/cli/services/network_handle.py) | `NetworkSubprocessHandle.session_id`, `.http_client` |
| Upstream HTTP startup handshake | [server_manager.py](../fluidmcp/cli/services/server_manager.py) | `ServerManager._handshake_http_subprocess()` |

## Current fixed network flows

Both `POST /{server_name}/mcp` and `POST /{server_name}/mcp/tools/call`
now use the same safe network forwarding helpers. The convenience endpoint
still constructs a client-facing envelope with ID `2`, but that ID is replaced
before it reaches the upstream server.

### Streamable HTTP

```text
Caller A: POST /{server_name}/mcp      Caller B: POST /{server_name}/mcp
{"jsonrpc":"2.0","id":1,              {"jsonrpc":"2.0","id":1,
 "method":"tools/call",                "method":"tools/call",
 "params":{"name":"echo",             "params":{"name":"echo",
   "arguments":{"token":"A"}}}         "arguments":{"token":"B"}}}
                  |                              |
                  v                              v
package_launcher.py :: proxy_jsonrpc() -- separate HTTP request handlers
                  |                              |
                  v                              v
package_launcher.py :: _proxy_to_http_server()
A's invocation: original=1            B's invocation: original=1
outgoing id=<UUID-A>                  outgoing id=<UUID-B>
                  |                              |
                  v                              v
Upstream POST /mcp                   Upstream POST /mcp
Mcp-Session-Id: S                    Mcp-Session-Id: S
{"id":"<UUID-A>", ...token:A...}     {"id":"<UUID-B>", ...token:B...}
                  |                              |
                  +---------------+--------------+
                                  |
                                  v
                    Upstream MCP server session S
                    Distinct request IDs: no collision
                                  |
                  +---------------+--------------+
                  |                              |
                  v                              v
A's upstream HTTP response           B's upstream HTTP response
{"id":"<UUID-A>","result":...A...}  {"id":"<UUID-B>","result":...B...}
                  |                              |
                  v                              v
_proxy_to_http_server()              _proxy_to_http_server()
Check id == UUID-A                   Check id == UUID-B
Restore original id=1               Restore original id=1
                  |                              |
                  v                              v
Return to A's HTTP request           Return to B's HTTP request
{"id":1,"result":...A...}            {"id":1,"result":...B...}

If the upstream ID is wrong: HTTP 502, without returning the foreign payload.
For /{server_name}/mcp/tools/call: the same flow restores client-facing id=2.
```

UUID labels and abbreviated messages in this diagram are schematic. Actual
requests retain the full JSON-RPC envelope and tool parameters. Each helper
invocation keeps its own original/upstream IDs; there is no shared lookup using
a restored client ID. JSON responses and SSE-framed HTTP responses are both
validated. JSON-RPC error responses have their IDs restored in the same way.

### Standard SSE upstream

The session owner lives in
[sse_client.py](../fluidmcp/cli/services/sse_client.py).

```text
server_manager.py :: _handshake_sse_subprocess()
    -> network_handle.py :: NetworkSubprocessHandle.sse_client
    -> sse_client.py :: SseJsonRpcClient.start()
        -> owner task opens GET /sse using the MCP SDK
        -> receives the advertised session-specific message endpoint
        -> initializes ClientSession once
        -> keeps the event stream open until the handle closes

Both public endpoints -> package_launcher.py :: _proxy_to_sse_server()
                                  |
                                  v
sse_client.py :: SseJsonRpcClient.request()
    Caller A's original id=1         Caller B's original id=1
                  |                              |
                  v                              v
    SDK allocates id=11              SDK allocates id=12
    SDK registers waiter A           SDK registers waiter B
                  |                              |
                  +---------------+--------------+
                                  |
                   POST to advertised message endpoint
                   Responses arrive on the open GET /sse stream
                                  |
                   SDK matches 11 -> A, 12 -> B
                                  |
                  +---------------+--------------+
                  v                              v
    Build A's envelope with id=1     Build B's envelope with id=1
    Return to A's HTTP handler       Return to B's HTTP handler
```

The SDK assigns internal IDs; `11` and `12` are examples. The owner task enters
and exits the SDK's async contexts in the same task, even when other tasks
request startup/shutdown. Local timeout or cancellation removes the SDK waiter.
Unscoped downstream `notifications/cancelled` messages are ignored on this SSE
path: forwarding the original ID could cancel another caller's internal ID.
Other notifications remain one-way messages.

## 1. Incoming raw JSON-RPC requests

For tool calls through `POST /{server_name}/mcp`, the client supplies the full
JSON-RPC envelope. This flow assumes MCP initialization has already completed.
Two independent client sessions can choose the same request ID:

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
                 |                         |
                 +------------+------------+
                              |
                              v
              fluidmcp/cli/services/package_launcher.py
              create_dynamic_router() -> proxy_jsonrpc()
                              |
                 +------------+------------+
                 |                         |
                 v                         v
            Stdio process        NetworkSubprocessHandle
                                 transport == "http"
```

The `id` is in the JSON-RPC envelope, not inside `params.arguments`. The token
is tool input used to check that the correct caller receives the result.

## 2. Stdio: match the unique ID before restoring the original ID

```text
package_launcher.py :: proxy_jsonrpc()
    A: {"jsonrpc":"2.0","id":1,"method":"tools/call",
        "params":{"name":"echo","arguments":{"token":"A"}}}
    B: {"jsonrpc":"2.0","id":1,"method":"tools/call",
        "params":{"name":"echo","arguments":{"token":"B"}}}
                              |
                              v
stdio_jsonrpc.py :: get_stdio_router(process, server_name).request(...)
                              |
                              v
StdioJsonRpcRouter.start()
    Allocate unique internal IDs and register waiters BEFORE writing:

    _pending[101] -> future A
    _pending[102] -> future B

    PendingRequest A: original_id=1, internal_id=101, future=future A
    PendingRequest B: original_id=1, internal_id=102, future=future B
                              |
                              v
StdioJsonRpcRouter._write() -> subprocess stdin
    {"jsonrpc":"2.0","id":101,"method":"tools/call",
     "params":{"name":"echo","arguments":{"token":"A"}}}
    {"jsonrpc":"2.0","id":102,"method":"tools/call",
     "params":{"name":"echo","arguments":{"token":"B"}}}
                              |
                              v
                     MCP subprocess executes
                              |
                              v
subprocess stdout -- B may finish before A:
    {"jsonrpc":"2.0","id":102,
     "result":{"content":[{"type":"text","text":"B"}]}}
    {"jsonrpc":"2.0","id":101,
     "result":{"content":[{"type":"text","text":"A"}]}}
                              |
                              v
StdioJsonRpcRouter._reader_loop()         [ONE stdout reader]
    -> _dispatch_line() -> _dispatch_message() -> _handle_response()

    Response 102: _pending.pop(102) -> future B.set_result(response)
    Response 101: _pending.pop(101) -> future A.set_result(response)
                              |
                 +------------+------------+
                 |                         |
                 v                         v
PendingRequest A.wait()             PendingRequest B.wait()
    Receives only response 101         Receives only response 102
    _restore_id(): 101 -> 1            _restore_id(): 102 -> 1
                 |                         |
                 v                         v
package_launcher.py                package_launcher.py
proxy_jsonrpc() for A               proxy_jsonrpc() for B
    JSONResponse(response_data)        JSONResponse(response_data)
                 |                         |
                 v                         v
A's existing HTTP response         B's existing HTTP response
{"jsonrpc":"2.0","id":1,           {"jsonrpc":"2.0","id":1,
 "result":{"content":[             "result":{"content":[
   {"type":"text","text":"A"}         {"type":"text","text":"B"}
 ]}}                                ]}}
```

The router selects the correct waiting request using the internal ID. Only
after that selection does the request's own `PendingRequest` restore its
original ID. The restored ID is never used for another shared routing lookup.
Both HTTP responses can therefore contain `id: 1` without being mixed up.

On timeout or cancellation, the internal ID is removed from the pending
registry. Late or unknown responses are dropped rather than assigned to
another waiting caller.

## 3. Before the fix: Streamable HTTP preserved duplicate IDs

```text
package_launcher.py :: proxy_jsonrpc()
    A's incoming JSON-RPC id=1       B's incoming JSON-RPC id=1
                 |                         |
                 +------------+------------+
                              |
                              v
NetworkSubprocessHandle              [network_handle.py]
    process.base_url    = upstream server address
    process.session_id  = S          [one shared upstream MCP session]
    process.http_client = shared HTTP connection pool
                              |
                              v
package_launcher.py :: _proxy_to_http_server(
    process.base_url, request,
    session_id=process.session_id, client=process.http_client
)
    Keeps the client's JSON-RPC id unchanged.
                 |                         |
                 v                         v
Upstream POST /mcp                  Upstream POST /mcp
Mcp-Session-Id: S                   Mcp-Session-Id: S
{"jsonrpc":"2.0",                  {"jsonrpc":"2.0",
 "id":1,                            "id":1,
 "method":"tools/call",             "method":"tools/call",
 "params":{"name":"echo",           "params":{"name":"echo",
   "arguments":{"token":"A"}}}       "arguments":{"token":"B"}}}
                 |                         |
                 +------------+------------+
                              |
                              v
Stateful upstream MCP SDK server
    Response streams indexed by request ID within session S:

    (session S, request id 1) <- A's request
    (session S, request id 1) <- B's request
                              |
                              v
                         ID COLLISION
                              |
                              v
    A result may reach the wrong upstream HTTP response stream;
    other HTTP requests can remain waiting and eventually time out.
                              |
                              v
package_launcher.py :: _proxy_to_http_server()
    Parses upstream JSON or the SSE response envelope.
    Returns the response without unique-ID remapping.
                              |
                              v
proxy_jsonrpc() -> JSONResponse(response)
    Can deliver another caller's tool result to the waiting client.
```

`Mcp-Session-Id: S` identifies an MCP session; it is not a JSON-RPC request ID.
Separate incoming gateway sessions currently share this upstream session for
the same HTTP subprocess. The collision happens in the shared upstream session,
not because HTTP connection pooling itself mixes up responses.

The E2E tests reproduced this with the stateful MCP SDK server. Which caller
receives the incorrect result depends on scheduling. Unique incoming IDs pass
the tested HTTP load cases.

## 4. Before the fix: convenience endpoint with no caller-supplied ID

```text
Caller A                                  Caller B
POST /{server_name}/mcp/tools/call          POST /{server_name}/mcp/tools/call
{"name":"echo",                           {"name":"echo",
 "arguments":{"token":"A"}}               "arguments":{"token":"B"}}
                 |                         |
                 +------------+------------+
                              |
                              v
fluidmcp/cli/services/package_launcher.py
create_dynamic_router() -> call_tool()
    Builds the JSON-RPC envelope itself, with a fixed id=2:

    A: {"jsonrpc":"2.0","id":2,"method":"tools/call",
        "params":{"name":"echo","arguments":{"token":"A"}}}
    B: {"jsonrpc":"2.0","id":2,"method":"tools/call",
        "params":{"name":"echo","arguments":{"token":"B"}}}
                              |
                 +------------+------------+
                 |                         |
                 v                         v
STDIO                              STREAMABLE HTTP
stdio_jsonrpc.py                    package_launcher.py
get_stdio_router().request()        _proxy_to_http_server()
    A: 2 -> unique internal ID         A: keeps id=2
    B: 2 -> unique internal ID         B: keeps id=2
                 |                         |
                 v                         v
Match response by internal ID      Upstream POST /mcp, same session S
Restore id=2 in each caller's       Two simultaneous requests with id=2
own PendingRequest                         |
                 |                         v
                 v                    ID COLLISION
call_tool() returns the correct     Wrong-user results and timeouts
result to each HTTP caller          reproduced in E2E tests
```

The convenience API needs no client MCP handshake. FluidMCP initializes the
upstream subprocess during startup. Its HTTP collision can occur even when
none of the callers supplies an ID: FluidMCP introduces the repeated ID itself.

## 5. Raw JSON-RPC without an ID

An absent `id` in a raw JSON-RPC message means a notification, which does not
expect a JSON-RPC response. For example:

```text
POST /{server_name}/mcp
{"jsonrpc":"2.0","method":"notifications/initialized"}
                              |
                              v
package_launcher.py :: proxy_jsonrpc()
    Special-cases notifications/initialized -> HTTP 204, no response body

Other supported notifications without an id:
    stdio -> StdioJsonRpcRouter.notify(); no response waiter is registered
    HTTP  -> _proxy_to_http_server(); no JSON-RPC response body is expected
```

Omitting `id` from a raw tool message is not the same API flow as sending
`name` and `arguments` to `/mcp/tools/call`. The latter constructs an ordinary
JSON-RPC request with an ID on the caller's behalf.

## Regression coverage

[test_response_isolation.py](../tests_e2e/test_response_isolation.py) tests both
endpoints at 50 and 100 concurrent callers per server, with stdio, Streamable
HTTP, and SSE subprocesses running simultaneously. The fake servers delay
responses by 1-5 seconds and echo unique caller/request tokens, so an unchanged
or duplicated JSON-RPC ID cannot conceal a wrong-user response.

See [the test README](../tests_e2e/README.md) for commands and
[the baseline findings](../tests_e2e/BASELINE.md) for the observed results.
