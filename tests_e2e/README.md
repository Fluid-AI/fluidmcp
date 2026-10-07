# Concurrent response-isolation E2E tests

From the repository root:

```bash
python3 -m venv /tmp/fluidmcp-e2e-venv
/tmp/fluidmcp-e2e-venv/bin/python -m pip install -r tests_e2e/requirements.txt
/tmp/fluidmcp-e2e-venv/bin/python -m pytest -c tests_e2e/pytest.ini tests_e2e -s
```

Dependencies use the repository's `requirements.txt` as version constraints.
The separate pytest configuration keeps these process/network load tests out of
the default unit-test run. No registry packages, cloud services, database, or
credentials are needed. Run one suite at a time; FluidMCP assigns upstream HTTP
ports from its shared 8500–8599 range. A free port is chosen for the gateway.
The CLI loads repository `.env` files if present, so run in a checkout without
those files to avoid overriding the fixture's isolated configuration.

## What runs

The source checkout's actual CLI starts one FluidMCP gateway and three separate
MCP SDK `FastMCP` subprocesses: stateful Streamable HTTP (SSE response bodies),
stdio, and legacy SSE. The load test covers both gateway endpoints:

- `POST /{server}/mcp`: full JSON-RPC `tools/call` requests, after MCP initialization.
- `POST /{server}/mcp/tools/call`: only `{"name": "echo", "arguments": {...}}`,
  without a client-supplied JSON-RPC ID, envelope, session header, or handshake.

The fake servers use the SDK's real transports;
the test does not mock routing or provide a nonstandard SSE endpoint.

Six mixed-transport batches run, each with a fresh gateway and subprocesses so
failures or hanging requests cannot contaminate the next batch:

| Endpoint | Callers per server | Total simultaneous calls | JSON-RPC IDs |
| --- | --- | --- | --- |
| `/mcp` | 50 | 150 | Unique |
| `/mcp` | 50 | 150 | Every client uses `1` |
| `/mcp/tools/call` | 50 | 150 | Assigned by FluidMCP |
| `/mcp` | 100 | 300 | Unique |
| `/mcp` | 100 | 300 | Every client uses `1` |
| `/mcp/tools/call` | 100 | 300 | Assigned by FluidMCP |

For `/mcp`, each simulated user initializes a separate gateway MCP session.
The convenience endpoint is called directly, as an ordinary HTTP API. A common
start barrier releases all tool calls in each batch. Every call sends a unique opaque response
token, user identifier, batch identifier, and a deterministic delay of 1–5 seconds.
Delays deliberately vary to produce out-of-order completion. The server echoes
those values and its transport identity. The users share a sufficiently large
TCP connection pool; raw MCP clients supply their own session headers on every request.
These are simulated user identities, not separate authenticated accounts; this
suite checks response routing rather than access control.

Every response must contain exactly the expected echo payload. Raw MCP responses
must also preserve the caller's JSON-RPC ID. Convenience-endpoint responses must
have a JSON-RPC envelope, but the test does not require a particular gateway-assigned ID.
HTTP/protocol/tool errors, timeouts, missing or duplicate responses,
wrong-server responses, and cross-user responses all fail. Reused JSON-RPC IDs
test independent clients that happen to choose the same ID; opaque tokens still
distinguish their responses.

The server journals starts and finishes independently. Successful cases also
verify each request executed exactly once, the configured delays actually
elapsed, execution overlapped, and completion order differed from arrival order.
Client in-flight concurrency must equal the requested 50 or 100 per server;
backend peak concurrency is reported separately because scheduling can reduce it.

A separate control connects directly to the SSE fake using the official SDK and
checks an echo. This confirms the fake implements standard SSE even if the
gateway cannot proxy it. This control is not counted as gateway load coverage.

## Failures and artifacts

The suite prints its pytest temporary artifact directory. It contains the gateway
log, generated config, fake-server process metadata, execution journals, and a
JSON report for every batch with the endpoint, exact submitted body,
expected/actual payload, and error for each request. Use
`--basetemp=/path/to/dedicated-e2e-temp` for a predictable location (pytest clears
that directory on the next run). Fixture cleanup stops the gateway and children
even when assertions fail. FluidMCP also writes its usual subprocess stderr logs
under `~/.fluidmcp/logs/`, keyed by the unique test server names.

Transport assertions are separate, but always consume a shared mixed-transport
batch: an SSE failure does not hide HTTP or stdio results. Known product failures
are intentionally not skipped, accepted as successes, or marked `xfail`.

The transport fix passes all 24 tests. See [BASELINE.md](BASELINE.md) for the
before/after results and implementation notes.

To run one endpoint's cases, append `-k jsonrpc` or `-k tools-call` to the command.
