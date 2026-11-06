# E2E tests

- `test_response_isolation.py` - Streamable HTTP response isolation (below).
- `test_security_redaction.py` - credential redaction and API authentication
  (PR #967); see [Security redaction suite](#security-redaction-suite).

# Streamable HTTP response-isolation E2E tests

From the repository root:

```bash
python3 -m venv /tmp/fluidmcp-e2e-venv
/tmp/fluidmcp-e2e-venv/bin/python -m pip install -r tests_e2e/requirements.txt
/tmp/fluidmcp-e2e-venv/bin/python -m pytest -c tests_e2e/pytest.ini tests_e2e -s
```

Dependencies use the repository's `requirements.txt` as version constraints.
The separate pytest configuration keeps these process/network load tests out of
the default unit-test run. No registry packages, database, cloud services, or
credentials are needed. Run one suite at a time; FluidMCP assigns upstream HTTP
ports from its shared 8500–8599 range. The gateway uses an available local port.
The CLI loads repository `.env` files if present, so run in a checkout without
those files to avoid overriding the fixture's isolated configuration.

## Scope

The actual source CLI starts FluidMCP and a real MCP SDK `FastMCP` subprocess
using stateful Streamable HTTP. The fake uses event-stream response bodies,
which are part of Streamable HTTP. Legacy SSE transport and stdio are outside
this suite's scope.

Both public endpoints are exercised:

- `POST /{server}/mcp`: full JSON-RPC requests after MCP initialization.
- `POST /{server}/mcp/tools/call`: only `{"name":"echo","arguments":{...}}`,
  with no caller-supplied JSON-RPC ID, envelope, session header, or handshake.

Each batch starts fresh gateway and fake-server processes so hanging requests
or failures cannot contaminate another scenario.

| Endpoint | Concurrent callers | JSON-RPC IDs |
| --- | --- | --- |
| `/mcp` | 50 | Unique |
| `/mcp` | 50 | Every caller uses `1` |
| `/mcp/tools/call` | 50 | Assigned by FluidMCP |
| `/mcp` | 100 | Unique |
| `/mcp` | 100 | Every caller uses `1` |
| `/mcp/tools/call` | 100 | Assigned by FluidMCP |

There are six tests and 450 tool calls. Each call supplies a unique fake user ID,
response token, batch ID, and a deterministic 1–5 second delay. A common barrier
releases all callers together. Varying delays produce out-of-order completion.
The fake returns the exact input and its transport identity.

Raw MCP callers establish separate sessions and supply their session headers.
HTTP connection pools have capacity for the entire offered load. Initialization
connections are not reused for load requests. User identities are simulated;
this tests response routing, not authentication or authorization.

## Assertions and artifacts

Every response must contain the exact expected echo payload. Raw JSON-RPC
responses must preserve the caller's ID. The convenience endpoint must return
a JSON-RPC envelope, but the test does not require a specific gateway-assigned
ID. HTTP/protocol/tool errors, timeouts, missing or duplicate responses, and
cross-user responses all fail.

An independent server journal verifies exactly one execution per request,
actual delays, overlapping execution, and out-of-order completion. Client
in-flight concurrency must equal 50 or 100. Backend peak is reported separately
because gateway scheduling may reduce it.

The printed pytest temporary directory contains the gateway log, config,
process metadata, execution journal, and JSON reports with each URL, submitted
body, expected/actual payload, and error. Use `--basetemp=/path/to/dedicated-temp`
for a predictable location; pytest clears it on the next run. Cleanup stops the
gateway and fake server even when assertions fail. FluidMCP's subprocess stderr
logs are under `~/.fluidmcp/logs/`, keyed by unique test server names.

Append `-k jsonrpc` or `-k tools-call` to select an endpoint. Tests do not skip,
accept, or mark known failures `xfail`. See [BASELINE.md](BASELINE.md) for the
original HTTP failure and the verification results after the fix.

# Security redaction suite

```bash
/tmp/fluidmcp-e2e-venv/bin/python -m pytest -c tests_e2e/pytest.ini tests_e2e/test_security_redaction.py -s
```

Additionally requires **Docker** and **openssl**: a throwaway MongoDB container
(`mongo:7.0`, override with `FMCP_E2E_MONGO_IMAGE`) runs with TLS from a
test-only CA, because FluidMCP always connects with TLS and validates
certificates. The root password deliberately contains `@ : / # %`. The
container is removed after the run. No real credentials or network access to
GitHub are used: every credential is a per-run dummy value, and
`mock_github.py` serves real git Smart HTTP (via `git http-backend`) on
localhost with GitHub-style token auth, redirected with `url.insteadOf`.

Helpers: `leaky_mcp_server.py` (real MCP server that prints dummy secrets and
optionally crashes), `logging_harness.py` (production logging/Sentry setup in
a fresh process), `mock_github.py`.

Covered end to end with the real source CLI (`serve`, `run`, `github`):
GitHub clone/auto-reclone/from-github auth via `GITHUB_TOKEN` (wire-level
credential checks, git argv, `.git/config`); MongoDB URI masking and
fail-fast startup; bearer token handling across restarts; authentication of
every documented route; sanitization of MCP child output in logs, APIs and
MongoDB records (including legacy raw records); all credential categories in
loguru, stdlib logging, tracebacks, API errors and Sentry envelopes; and
regressions for normal MCP traffic, metrics and `run --secure`. A final test
sweeps every captured artifact for any secret.

Known, documented exception: per-server stderr files under
`~/.fluidmcp/logs/` are written directly by the child process and stay raw on
disk (owner-only `0600`); every reader sanitizes them.

Run against `development` without PR #967, 27 of the 30 tests fail; the 3
that pass are regression checks.
