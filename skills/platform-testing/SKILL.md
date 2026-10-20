---
name: platform-testing
description: Test FluidMCP changes through the real source CLI, gateway HTTP endpoints, and MCP subprocesses. Use for local API verification, transport routing, response isolation under concurrent load, and end-to-end PR validation with recorded evidence.
---

# FluidMCP Platform Testing

Use `skills/platform-testing/` from the repository root. Choose tests based on the changed behavior; report transport and endpoint coverage precisely.

## Existing regression suite

Read `tests_e2e/README.md` and the affected tests first. The existing suite launches a real Streamable HTTP MCP server with delayed echoes, runs 50 and 100 concurrent requests, and checks response ownership. It covers both `POST /{server}/mcp` (unique and reused JSON-RPC IDs) and `POST /{server}/mcp/tools/call` (gateway-generated IDs).

```bash
python3 -m venv /tmp/fluidmcp-test-venv
/tmp/fluidmcp-test-venv/bin/pip install -r tests_e2e/requirements.txt
/tmp/fluidmcp-test-venv/bin/python -m pytest -c tests_e2e/pytest.ini tests_e2e -s
```

Use an existing environment only after checking it satisfies the checkout's dependency constraints. Run focused tests in `tests/` for affected behavior too. Root pytest discovery excludes `tests_e2e`; invoking only root pytest does not run the load suite. These tests currently cover HTTP, not stdio or SSE. Add real fixtures for additional transports when the task requires them; do not infer coverage from shared code.

## Interactive HTTP evidence

The helper starts the current checkout's CLI in `run --file --start-server` mode with an isolated, randomly named fake HTTP MCP server. It requires the E2E dependencies above, curl, and Python 3. The gateway uses its normal `0.0.0.0` bind and secure mode is off; run on a development host with appropriate network access controls. No MongoDB, Azure credentials, or GPT Engine login is used. This does not exercise management `serve` mode.

```bash
export PYTHON=/tmp/fluidmcp-test-venv/bin/python
export PORT=8099                 # choose a free port
S=skills/platform-testing/scripts
bash "$S/start_local_server.sh"
RUN_DIR=$(cat "${TMPDIR:-/tmp}/fluidmcp-local-server-$PORT/current_run")
SERVER_NAME=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["server_name"])' "$RUN_DIR/run.json")
bash "$S/api_call.sh" health GET /health
bash "$S/api_call.sh" echo POST "/$SERVER_NAME/mcp/tools/call" \
  -H 'Content-Type: application/json' \
  -d '{"name":"echo","arguments":{"user_id":"alice","response_id":"alice-1","batch":"smoke","delay":1}}'
bash "$S/check.sh" echo-owner alice-1 \
  'python3 -c '\''import glob,json,os; body=json.load(open(glob.glob(os.environ["RUN_DIR"]+"/calls/*-echo.body")[0])); print(json.loads(body["result"]["content"][0]["text"])["response_id"])'\'''
bash "$S/stop_local_server.sh"
python3 "$S/verify_run.py" "$RUN_DIR"
```

Check the actual response shape before writing assertions. Raw JSON-RPC calls use `{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"echo","arguments":{...}}}` at `/$SERVER_NAME/mcp`; notifications omit `id`. Assert both restored JSON-RPC IDs and unique echo fields. An ID by itself cannot prove response ownership when different callers intentionally reuse it.

All manual API evidence goes through `api_call.sh`; checks go through `check.sh`. Use separate labels for concurrent calls. Set `REQUEST_TIMEOUT` for longer requests (default 60 seconds). `verify_run.py` cross-checks calls against gateway access logs, hashes bodies, and recomputes recorded check outcomes including command exit status. It is a consistency check, not proof of coverage or tamper resistance. Keep artifacts and report the actual verifier result and run directory, including failures.

Always stop the helper after testing, including failed checks. It tracks process creation time before stopping the gateway and its children, and retains logs, dependencies, calls, and checks outside the repository. Use the same `PORT`, `TMPDIR`, and `PYTHON` for start/calls/stop. Startup refuses checkout `.env` files because CLI dotenv loading overrides the isolated environment; use a clean worktree rather than modifying personal configuration.

## Tests beyond the default fixture

For authentication or management changes, inspect `fluidmcp/cli/auth.py`, `server.py`, and route dependencies; construct a dedicated fixture for the actual mode/backend. Secure mode uses a configured bearer token, not an email/password JWT login. `api_call.sh` can read a test token from the state directory's `token` file (create with mode 600); `NO_AUTH=1` omits it. The default helper always starts without authentication, so it cannot establish secure-mode behavior.

For concurrency changes, compare each caller's `user_id`, `response_id`, and batch marker against the response and independent upstream execution journal. Include overlapping calls, reused JSON-RPC IDs, upstream errors, timeout/cancellation cleanup, and transport/session boundaries as relevant. Report exactly what ran and any untested paths; a health check alone does not establish isolation.
