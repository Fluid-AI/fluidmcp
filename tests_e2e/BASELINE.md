# Before and after the transport fix

## Fixed implementation

The same suite now passes **24/24 tests in 136.05 seconds**, including all
1,350 tool calls through both endpoints. Every transport correctly returned
all 50/100 responses for unique, reused, and gateway-assigned IDs. All 18 fake
server subprocesses are checked for cleanup separately after the run.

Streamable HTTP now replaces each request ID with a unique upstream UUID,
validates the returned ID, and restores the original ID in that caller's HTTP
response. Notifications remain notifications. Standard SSE now uses a persistent
initialized MCP SDK session with SDK-managed unique IDs and response waiters.

All **89 focused regression tests pass**, covering concurrent repeated IDs,
error responses, mismatched upstream IDs, SSE response framing, session
lifecycle, failed startup cleanup, stdio routing, and concurrency limiting.
SSE downstream cancellation notifications are ignored because their IDs cannot
be safely matched to SDK IDs without downstream session-scoped cancellation
tracking. Local request timeouts/cancellations still remove their SDK waiters.

## Original baseline

Tested on 2026-10-07 against development commit
`8db4a07ea23b7af57c79546f6dd8dd420bfd5d7b`, on branch `e2e-fluidmcp`,
using Python 3.12.3 and the dependency constraints in the repository's
`requirements.txt` (including MCP SDK 1.26.0).

Before the fix: **14 passed, 10 failed in 315.51 seconds**. Six passing tests are the
direct SSE controls. The load tests attempted 1,350 calls through FluidMCP:

| Endpoint | Callers per server | JSON-RPC IDs | HTTP | stdio | SSE through gateway |
| --- | --- | --- | --- | --- | --- |
| `/mcp` | 50 | Unique | 50 correct | 50 correct | 50 HTTP 400 errors |
| `/mcp` | 50 | Reused | 1 wrong user, 49 timeouts | 50 correct | 50 HTTP 400 errors |
| `/mcp/tools/call` | 50 | Assigned by FluidMCP | 1 wrong user, 49 timeouts | 50 correct | 50 HTTP 400 errors |
| `/mcp` | 100 | Unique | 100 correct | 100 correct | 100 HTTP 400 errors |
| `/mcp` | 100 | Reused | 3 wrong users, 97 timeouts | 100 correct | 100 HTTP 400 errors |
| `/mcp/tools/call` | 100 | Assigned by FluidMCP | 3 wrong users, 97 timeouts | 100 correct | 100 HTTP 400 errors |

Counts of mismatches versus timeouts may vary with scheduling. The requirement
is always zero incorrect, missing, duplicate, or failed responses.

### Streamable HTTP could return another user's response

Independent clients may legitimately choose the same JSON-RPC request ID in
their separate sessions. The reused-ID scenarios initialize separate gateway
sessions, then all clients send ID `1` with different user IDs and opaque tokens.

The test reproduces responses containing a different caller's user ID and token,
alongside read timeouts. The JSON-RPC ID alone cannot detect this because both
clients used ID `1`; comparing the echoed payload exposes the incorrect routing.
Unique-ID HTTP scenarios pass at both load levels.

The `/mcp/tools/call` scenario also reproduces cross-user responses without
clients supplying any JSON-RPC IDs at all. Those clients send only `name` and
`arguments`, with no initialization handshake. FluidMCP itself constructs the
upstream JSON-RPC request using the fixed ID `2` for every tool call, so concurrent
requests collide in the shared upstream HTTP session. This case exercises the
ordinary convenience API independently of client-generated IDs.

Source inspection explains the collision: the HTTP proxy passes the client's
request ID unchanged and sends every request through the subprocess handle's
shared upstream session. The SDK's stateful Streamable HTTP server indexes its
response streams by request ID within that session. The stdio path already
allocates gateway-unique upstream IDs and restores the caller's original ID.

### Standard SSE could not be proxied successfully

Gateway calls to the standard SDK SSE server return HTTP 400. The independent
SDK client control can initialize and call the same server successfully in
each scenario. The failed gateway calls never execute the fake's echo tool.

The gateway's SSE proxy sends JSON-RPC directly to `/messages/`, without an
established SSE session or its session-specific message URL, and expects a JSON
response to the POST. A standard SSE MCP server delivers responses over its
established event stream.

The original failures remain documented here for comparison. The regression
assertions have not been weakened, skipped, or marked `xfail` to obtain the
passing result. See [README.md](README.md) for the full test design, run command,
and artifact locations.
