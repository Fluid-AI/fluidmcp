# Streamable HTTP ID-collision results

Scope: the Streamable HTTP forwarding helper, both public tool-call endpoints,
and their regression tests. The legacy SSE implementation, server lifecycle,
and stdio router match development; no SSE session changes are included.

## After the fix

Tested on Python 3.12.3 with the repository's dependency constraints:

- **6 E2E tests passed in 110.13 seconds**, covering 450 tool calls.
- **12 HTTP proxy regression tests passed**.
- Every E2E response matched its fake user ID, response token, batch, and delay.
- All six fake HTTP server subprocesses were verified stopped after the run.

| Endpoint | Concurrent callers | Request IDs | Correct responses |
| --- | --- | --- | --- |
| `/mcp` | 50 | Unique | 50/50 |
| `/mcp` | 50 | Reused | 50/50 |
| `/mcp/tools/call` | 50 | Assigned by FluidMCP | 50/50 |
| `/mcp` | 100 | Unique | 100/100 |
| `/mcp` | 100 | Reused | 100/100 |
| `/mcp/tools/call` | 100 | Assigned by FluidMCP | 100/100 |

The shared HTTP helper replaces each upstream request ID with a unique UUID,
checks the response against that UUID, and restores the caller's original ID.
A mismatched upstream response is rejected with HTTP 502 rather than returned
to another user. Notifications remain notifications. JSON and event-stream
response bodies from Streamable HTTP servers both receive ID validation.

Unit tests cover concurrent repeated IDs, original-ID restoration for success
and error responses, notification handling, upstream session headers, rejection
of wrong IDs, and framed responses containing progress events/multiline data.

## Original HTTP failure

Before the fix, on development commit `8db4a07`, the HTTP portion of the original
mixed-transport run produced the following results:

| Endpoint | Concurrent callers | Request IDs | HTTP outcome |
| --- | --- | --- | --- |
| `/mcp` | 50 | Unique | 50 correct |
| `/mcp` | 50 | Reused | 1 wrong user, 49 timeouts |
| `/mcp/tools/call` | 50 | Assigned by FluidMCP | 1 wrong user, 49 timeouts |
| `/mcp` | 100 | Unique | 100 correct |
| `/mcp` | 100 | Reused | 3 wrong users, 97 timeouts |
| `/mcp/tools/call` | 100 | Assigned by FluidMCP | 3 wrong users, 97 timeouts |

The raw endpoint forwarded client IDs unchanged into one shared upstream MCP
session. The convenience endpoint introduced the same problem itself by
assigning every upstream call ID `2`, even though callers supplied no ID.
Unique echo tokens exposed the wrong-user responses despite matching JSON-RPC
IDs. The balance of incorrect responses and timeouts varies with scheduling.

See [README.md](README.md) for run commands and artifact locations, and
[the flow document](../code-flow/request-id-routing.md) for the implementation.
