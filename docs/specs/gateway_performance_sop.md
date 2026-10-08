# Spec: Gateway Performance, Isolation and Cleanup SOP

**Branch:** `docs/gateway-performance-sop`
**Status:** Draft
**Audited at:** `6210e7d` (development). All line references below are at this commit.

---

## 1. Context and Problem Statement

FluidMCP runs **many MCP servers as subprocesses inside one container**, behind one FastAPI
gateway. That topology is fixed. The goal is a gateway that is never the bottleneck: the only
limit left should be the infrastructure (CPU, RAM, network). One slow, stuck, crashing or noisy
MCP server must not degrade any other.

This document does three things:

- Records a full audit of the request path, server lifecycle, background loops, MCP protocol
  handling, management API, container setup and code structure.
- Defines the invariants all gateway code must keep from now on (the SOP, §5).
- Lays out an ordered roadmap of small, independently testable PRs (§6).

This PR is documentation only. Each roadmap slice ships as its own PR.

---

## 2. How a Request Flows Today

```
client ──HTTP──▶ uvicorn (1 worker, loop="asyncio")
  └─ BaseHTTPMiddleware: limit_request_size   (server.py:227)
     └─ BaseHTTPMiddleware: trace_id          (server.py:198)
        └─ CORSMiddleware                      (server.py:186)
           └─ POST /{server_name}/mcp          (package_launcher.py:569, async def)
              ├─ Depends(get_token)            sync def → anyio threadpool hop (:290)
              ├─ RequestTimer (metrics)        (:644)
              ├─ auto_start_stopped_server     fast path: dict get + poll() (:539)
              ├─ "initialize" answered locally with hardcoded caps (:671-685)
              ├─ optional per-server Semaphore → 429 when full (:694-704)
              ├─ stdio:  StdioJsonRpcRouter.start()  ── stdin.write+flush ON THE LOOP (stdio_jsonrpc.py:298)
              │          reader thread ── readline → match by id → Future.set_result
              │          await wrap_future(…, 45s)
              ├─ http:   pooled httpx client → upstream /mcp (uuid id rewrite) (:184-272)
              ├─ await server_manager.update_last_used()  ── MongoDB w=majority upsert (:817)
              └─ JSONResponse
```

**Key facts:**

- **No LLM "router agent" decides where MCP requests go.** Dispatch is
  `server_manager.processes[server_name]`, a dict lookup. The only LLM agent is the Inspector UI
  helper (`services/inspector_agent.py`), and it only *suggests* a tool; it never executes one.
- **`StdioJsonRpcRouter` is the right design.** It has one reader thread per process and matches
  responses by JSON-RPC ID (#912/#913). There is no global or per-server I/O lock, so a slow
  tool does not serialize other calls to the same server.
- **There is one uvicorn worker with one asyncio loop.** This is unavoidable because the Popen
  handles live in memory. Anything that blocks the loop, or serializes background work, is
  therefore a container-wide bottleneck. That is the organising principle of this SOP.
- **Three launch paths exist:** `serve` (ServerManager), `run` (`run_servers.py`) and `github`
  (`cli.py` + legacy launcher). They share the router but not the lifecycle, so fixes must reach
  all three.
- **No test CI runs today.** `.github/workflows/` contains only a Claude review and a Docker push.

---

## 3. Findings Register

Severity scale:

- **P0:** security exposure.
- **P1:** one server can stall the whole container.
- **P2:** per-request latency or correctness on the hot path.
- **P3:** MCP protocol fidelity.
- **P4:** fan-out, polling and state.
- **P5:** container and image.
- **P6:** structural debt.

### 3.1 P0: Security (fix first)

| ID | Finding | Location |
|---|---|---|
| SEC-1 | **`GET /api/servers` has no auth** and returns each stdio server's raw `env` (API keys, tokens). The router has no auth dependency at all. Also unauthenticated: `/servers/{id}/status`, `/logs`, `/instance/env` (key names only), `/tools`. | `api/management.py:1093, 1733, 1754, 2128, 2325`; `server_manager.py:752-757`; `server.py:300` |
| SEC-2 | Every MCP child gets the **full gateway environment**: `FMCP_BEARER_TOKEN`, `MONGODB_URI`, GitHub/S3 credentials, Sentry DSN. Gateway values also *override* per-server env, so a child cannot set its own `PORT`, `HOME` or `NODE_OPTIONS`. The LLM launcher and the inspector already filter with an allowlist. | `server_manager.py:969-972`; `package_launcher.py:366`; compare `llm_launcher.py:35, 187` |
| SEC-3 | Two copied `get_token` functions compare with plain `!=` (not constant-time) and re-read env vars on every call. | `management.py:411-418`; `package_launcher.py:290-297` (vs `auth.py:89`, which uses `compare_digest`) |
| SEC-4 | `GET /servers/{id}/logs?lines=0` passes 0 to Mongo `.limit()`, which means no limit, so the whole logs collection comes back. | `management.py:1754`; `database.py:921` |
| SEC-5 | `git clone` puts the GitHub token in the URL, so it is saved in the clone's `.git/config`. | `github_utils.py:99-115` |
| SEC-6 | The rate-limit key trusts a spoofable `X-Forwarded-For`. In `run` and `github` modes CORS sets `allow_origins=["*"]` together with `allow_credentials=True`. | `management.py:194-227`; `run_servers.py:266`; `cli.py:562` |

### 3.2 P1: Container-wide stalls (one server hurts all)

| ID | Finding | Location |
|---|---|---|
| LOOP-1 | The stdin `write()`+`flush()` runs **on the event loop** under a `threading.Lock`. If one child stops reading stdin and its 64 KB pipe fills, the **entire gateway freezes**. `_on_timeout` also writes `notifications/cancelled` from the loop. | `stdio_jsonrpc.py:154-200, 277-302` |
| LOOP-2 | Other synchronous blocking calls on the loop: `process.wait(5)`; `raw_proc.wait()` with no timeout; a synchronous `git clone` with no timeout, run inside the operation lock; LLM `stop()` `wait(10)`; `time.sleep(0.5)` plus a synchronous Popen; synchronous log-file reads (the LLM log tail is O(n²)); a log-dir scan on every spawn. | `server_manager.py:1486, 2067, 916, 1607`; `llm_launcher.py:473, 796`; `management.py:2096, 2776-2828` |
| LOOP-3 | The JSON log sink runs at **DEBUG**, writes with a synchronous `print(..., flush=True)` and has no `enqueue`. That is about 5 lines per request, plus one debug line for every stderr line of every subprocess, all behind one handler lock that the reader threads also use. | `cli/server.py:80-98`; `package_launcher.py:75` |
| BG-1 | `MCPHealthMonitor` checks servers **one after another**. Restart backoff (up to 160 s) and the restart itself (up to 60 s) are awaited inline, and the HTTP ping opens a new client with a 10 s timeout. One sick server freezes monitoring for every server. The LLM health monitor follows the same pattern. | `server_manager.py:1960-1970, 1995, 2198-2225`; `llm_launcher.py:740-754, 894-958` |
| BG-2 | One default executor (`min(32, host_cpus+4)`, sized from host CPUs rather than the cgroup quota) is shared by server init (`to_thread(initialize_mcp_server)`, up to 30 s each), stops (`to_thread(wait)`) and inspector LLM calls. Starting many servers at once exhausts it. | `server_manager.py:402, 1098`; `inspector_agent.py:166, 221` |
| PROC-1 | **No process group.** Popen has no `start_new_session`, and kills only reach the `npx` wrapper. The `node` grandchild is orphaned and keeps the stdout pipe open, so the router reader thread never sees EOF and leaks. The psutil CPU/RSS kill policy measures the wrapper, not the server. | `server_manager.py:1042-1052, 393-409, 1484, 2065, 2247-2255` |
| PROC-2 | **A spawn timeout leaks the process and its port.** The outer `wait_for(30)` is shorter than the inner budget (0.5 s + 30 s init + 5/10 s tools), and the `CancelledError` handler only closes the stderr log. | `server_manager.py:250-253, 1122-1124` |
| PROC-3 | There is no init process (tini or dumb-init); PID 1 is bash. | `Dockerfile:93`; `entrypoint.sh` |

### 3.3 P2: Hot-path latency and correctness

| ID | Finding | Location |
|---|---|---|
| HOT-1 | `await update_last_used()` does a Mongo `w=majority` upsert **before every response** on stdio `/mcp`, `tools/call` and `/sse`. HTTP/SSE servers never call it, so the idle reaper stops network servers that are busy. | `package_launcher.py:817, 869, 1271`; `server_manager.py:1801-1838` |
| HOT-2 | Two `BaseHTTPMiddleware` layers wrap every request and every stream. `limit_request_size` raises `HTTPException` outside the exception handler, so clients get 500 without CORS headers. It only checks `Content-Length`, so chunked bodies bypass it. | `cli/server.py:198, 227-270` |
| HOT-3 | The synchronous `def get_token` costs a threadpool hop per request. Settings are re-read from env on every request (`FMCP_BEARER_TOKEN`, `FMCP_SECURE_MODE`, `FMCP_SLOW_REQUEST_MS`, `FMCP_HTTP_PROXY_TIMEOUT`, …). | `package_launcher.py:290, 712, 796`; `auth.py:89` |
| HOT-4 | **Cold-start herd.** `start_server` fails fast when the lock is held, so concurrent first requests to a stopped server get 503. | `server_manager.py:344-347`; `package_launcher.py:565-567` |
| HOT-5 | Any 504 from an HTTP-transport server (a call over 60 s, **or** an httpx `PoolTimeout` above 200 in flight) calls `trigger_restart`. That kills every in-flight call on the server, with no backoff, so one slow tool can use up `max_restarts`. | `package_launcher.py:710-722`; `server_manager.py:2016-2080` |
| HOT-6 | Client disconnects and client `notifications/cancelled` never reach the upstream. The waiter is dropped, but the upstream keeps working and the semaphore slot stays held. The client's cancel carries its own ID, which the gateway has rewritten, so it matches nothing upstream. | `stdio_jsonrpc.py:78-94, 283-292`; `package_launcher.py:762, 1105` |
| HOT-7 | `/sse` leaks a semaphore slot if the client disconnects before the generator starts. The generator's `except` path can raise `UnboundLocalError` on an early failure. | `package_launcher.py:887, 1112, 1119` |
| HOT-8 | `trace_id` in `/mcp` logs is always empty, because `locals().get("http_request")` refers to a parameter that does not exist. | `package_launcher.py:640` |
| HOT-9 | The `tools/call` timeout path writes to the DB without a guard, so a DB failure turns the 504 into a 500. | `package_launcher.py:1263` |
| HOT-10 | Uvicorn config: `loop="asyncio"` is forced, `uvicorn[standard]` is not installed (no uvloop/httptools), and there is no `timeout_keep_alive`, `backlog` or `timeout_graceful_shutdown`. | `cli/server.py:739-749`; `run_servers.py:1376`; `requirements.txt:51` |
| HOT-11 | Metric labels come straight from the URL and request body (`server_id`, `method`, `tool_name`). Requests that return 404 still create series, so memory grows without bound. | `package_launcher.py:644-650`; `management.py:2417-2434` |

### 3.4 P3: MCP protocol fidelity

| ID | Finding | Location |
|---|---|---|
| MCP-1 | The gateway answers `initialize` with **fake** capabilities and serverInfo, and echoes the client's protocolVersion back. The real upstream result is thrown away. It hands out a random `mcp-session-id` that is never tracked. | `package_launcher.py:465, 496, 671-685`; `server_manager.py:1376` |
| MCP-2 | The gateway advertises `roots`/`sampling` support to upstreams but answers those requests with -32601. Server→client requests arriving inside HTTP SSE responses are never answered, so the upstream hangs. | `package_launcher.py:261, 466`; `stdio_jsonrpc.py:446-468` |
| MCP-3 | All clients share **one upstream HTTP session**. When the upstream session expires, its 404 is passed through; the client re-initializes against the fake `initialize` and loops. The gateway never re-handshakes. | `server_manager.py:1375`; `package_launcher.py:223, 268-272, 713` |
| MCP-4 | Tools cache: `notifications/tools/list_changed` is dropped, so the cache is never invalidated. Stateless HTTP servers are misdetected as SSE, so their tools are never cached. `PUT /servers/{id}` wipes the cached tools. `tools/list` is always forwarded upstream. | `stdio_jsonrpc.py:433-438`; `server_manager.py:1417`; `management.py:1275-1288` |
| MCP-5 | Progress notifications are lost: upstream SSE responses are fully buffered, and stdio `/mcp` registers no progress callback. Progress only reaches the client on `/sse`. | `package_launcher.py:243-263, 768` |
| MCP-6 | The legacy SSE transport is broken. It sends no `session_id`, POSTs before opening the GET, omits the trailing slash, drops the query string and creates a new client per request. `SseSubprocessHandle` is never instantiated. | `package_launcher.py:149-182, 925-980`; `management.py:1593-1668`; `sse_handle.py` |
| MCP-7 | `run_tool` calls `get_stdio_router` on HTTP/SSE handles, which returns a 500. It also takes no concurrency semaphore, never updates last-used, and uses a 30 s timeout where `/mcp` uses 45 s. | `management.py:2354-2436` |
| MCP-8 | Other protocol gaps:<br>• A JSON-RPC batch gets a FastAPI 422.<br>• Errors are returned as FastAPI `{"detail"}` instead of a JSON-RPC `error`.<br>• `/sse` errors arrive as HTTP 200 with `data:{"error"}`.<br>• Notifications get a mix of 204 and 202.<br>• There is no `GET`/`DELETE /{server}/mcp`.<br>• There is no response-size cap. | `package_launcher.py:572, 685, 697-703, 737`; `stdio_jsonrpc.py:313` |

### 3.5 P4: Fan-out, polling and state

| ID | Finding | Location |
|---|---|---|
| FAN-1 | `list_servers` makes N+1 serial Mongo reads with no projection and no pagination. The GET can also **spawn** crashed servers without taking the lock. A `$or` query runs on the unindexed `server_name`. | `server_manager.py:581, 614-661, 705-786, 1886`; `database.py:715` |
| FAN-2 | `start-all`, `stop-all`, `shutdown_all` and `_cleanup_on_exit` all handle servers one at a time. `start-all` also starts disabled servers. | `management.py:1684`; `server_manager.py:131-200, 790` |
| FAN-3 | `GET /api/llm/models` probes each model live, one after another. **UI polling increments `consecutive_health_failures`, which can trigger model restarts.** The frontend polls at 1 s, 2 s, 10 s and 30 s, with no `document.hidden` pause and no in-flight guard. | `management.py:2448-2467`; `llm_launcher.py:531-563, 706`; `frontend/src/hooks/usePolling.ts:95`; `pages/LLMModelDetails.tsx:61`; `pages/LLMPlayground.tsx:33`; `pages/MCPInspector.tsx:791` |
| FAN-4 | Run mode spawns servers one after another at startup with no outer timeout. Uvicorn isn't listening until all of them finish, so the 40 s Docker `start-period` can be exceeded. `_server_processes` goes stale after a restart. | `run_servers.py:73, 291-336` |
| FAN-5 | Every 2 s poll of the inspector logs returns the full buffer, and the client's offset drifts. | `api/inspector.py:249`; `inspector_session.py:185` |
| STATE-1 | The app sets both `lifespan=` and `@app.on_event`, so the on_event hooks **never run**: inspector `cleanup_sessions()`, the HTTP client close and the Redis close. | `cli/server.py:164, 429-451` |
| STATE-2 | Shutdown runs in the wrong order:<br>• Uvicorn waits on SSE streams with no graceful timeout.<br>• The lifespan **disconnects Mongo before** `shutdown_all()`.<br>• Stops run one at a time (10 s each) under a 10 s total cap.<br>• The synchronous fallback then takes about 7 s per server. | `cli/server.py:137-143, 782-787`; `server_manager.py:131-200` |
| STATE-3 | State-handling bugs:<br>• `env_file` is popped out of the cached config.<br>• The memory backend overwrites instance state.<br>• The logs collection is never capped.<br>• The stderr PIPE fallback has no drainer.<br>• Stderr logs rotate only at spawn.<br>• Per-server locks and semaphores are never pruned.<br>• `get_stderr_tail` returns empty in serve/run modes. | `server_manager.py:829, 1014, 1629`; `memory.py:105`; `database.py:343-382` |
| STATE-4 | `/health` pings Mongo on every call, always returns 200, and ignores MCP processes. | `cli/server.py:320-379` |
| STATE-5 | One bad row (a naive vs aware datetime comparison) aborts idle cleanup for every server. `_validate_server_with_manager` leaks its temporary config. The instance-env rollback always logs CRITICAL, even when it succeeds. | `server_manager.py:1810-1821`; `management.py:797-859, 2261` |

### 3.6 P5: Container and image

| ID | Finding | Location |
|---|---|---|
| IMG-1 | The npm/uv cache is ephemeral and is cleared in the image. Unversioned `npx -y` re-resolves against the registry on every (re)start, so the first request after a deploy or an idle stop pays the full download. | `Dockerfile:30-35, 74` |
| IMG-2 | No `RLIMIT_NOFILE` handling. The `RLIMIT_AS` memory cap breaks V8, and there is no `NODE_OPTIONS`/`--max-old-space-size` alternative. | `server_manager.py:1016-1032, 1727-1740` |
| IMG-3 | Only 99 ports are available for HTTP/SSE servers (`8500-8599`, end exclusive), and the bind-then-close check races. | `network_utils.py:69-87` |
| IMG-4 | Image and build issues:<br>• The Python version is 3.10 in Docker, `>=3.12` in `uv.lock` and `>=3.6` in `setup.py`.<br>• `COPY . .` comes before the pip and frontend layers, so every code change busts those caches.<br>• The container runs as root.<br>• The build uses `npm install`, not `npm ci`. | `Dockerfile:1, 46-55`; `uv.lock:3`; `setup.py:55` |

### 3.7 P6: Structural debt and dead code

- **God modules:**
  - `api/management.py` has 4,700 lines, 71 functions and 42 lazy imports.
  - `services/server_manager.py` has 2,467 lines.
  - `create_dynamic_router` is a single 770-line closure.
  - Import cycle: `run_servers` ↔ `management`.
  - `services/__init__.py` eagerly imports the whole LLM stack.
- **Duplicates:**
  - 3× `get_token`.
  - 3× `validate_server_config` (the local copies shadow the imports and use different env-name rules).
  - 3 rate limiters.
  - About 8 sanitizers.
  - 2× `get_stderr_tail`.
  - 4 health-check implementations.
  - About 10 ad-hoc `httpx.AsyncClient(...)` creations.
  - 3 CORS setups.
- **Dead code:**
  - `services/restart_manager.py`.
  - `services/sse_handle.py` and its branches.
  - `deprecated/router/legacy_router.py`.
  - The HTTP checks in `health_checker.py`.
  - `StdioJsonRpcRouter._send`.
  - `ServerManager._loop` and `_metrics_registry` (always `None`, so the active-requests gauge always reads 0).
  - The duplicate `server.run()` argparse.
  - The dead env-restart block in `update_server`.
- **Stale docs:**
  - `CONTRIBUTING.md` says there are no automated tests.
  - The `pr_review.yml` prompt says "NO TESTS EXIST".
  - `CONTRIBUTING.md` points to a PR template that does not exist.

---

## 4. Target Architecture

```
client ──▶ uvicorn (uvloop/httptools, 1 worker)
  └─ pure-ASGI: size limit (streamed) → trace ContextVar → CORS
     └─ /{server}/mcp   async auth (settings loaded once)
        ├─ ensure_started()  ── coalesced start future (no 503 herd)
        ├─ per-server semaphore (acquired inside stream generators)
        ├─ stdio: enqueue → per-server WRITER thread → stdin
        │         per-server READER thread → Future     (loop never touches pipes)
        ├─ http:  per-server pooled client, real upstream session, re-handshake on 404
        ├─ manager.touch(server)  ── in-memory, O(1)
        └─ response
Background (each per-server or bounded-concurrent, never inline restarts):
  health task/server · last-used flusher · log flusher · idle reaper · LLM health task/model
Blocking work: dedicated bounded executors (lifecycle / io), every call with a timeout
Children: own process group (killpg), least-privilege env, tini as PID 1
```

---

## 5. SOP: Invariants for All Gateway Code

Reviewers should reject changes that break any of these.

1. **The loop is I/O-only.**
   - No synchronous file, pipe, process-wait, sleep or subprocess call inside `async def`.
   - Blocking work goes to a dedicated bounded executor: `FMCP_LIFECYCLE_WORKERS` for init, wait and git; `FMCP_IO_WORKERS` for file reads.
2. **Per-server isolation.**
   - Each server has its own writer thread, reader thread, semaphore and health task.
   - No shared resource may be held by one server for an unbounded time.
3. **The hot path does zero DB I/O.** The DB is written only by background flushers: last-used, logs and metrics.
4. **Background loops never await restarts or backoffs inline.** They run per server, or bounded-concurrent with a semaphore.
5. **Every wait has a timeout,** and every outer timeout is larger than the sum of the inner budgets.
6. **Every spawned process tree is owned.** Spawn with `start_new_session=True`, stop with `os.killpg` (SIGTERM, then SIGKILL), and run tini as PID 1.
7. **Children get a least-privilege environment:** an allowlist plus explicit per-server env, with per-server values taking precedence.
8. **Reads have no side effects.** GET endpoints never start or restart servers and never change health counters.
9. **Everything is bounded:** metric labels, caches, log reads, response sizes, and in-memory registries (pruned when a server is deleted).
10. **One implementation per concern:** one auth, one validator, one httpx client factory, one stderr tail, one health-monitor pattern.
11. **Settings are read once.** Environment variables are parsed into a settings object at startup, never inside request handlers.
12. **All management routes require auth by default.** Public routes are an explicit allowlist (`/health`, and `/metrics` when configured).
13. **Every gateway PR includes a regression test** for the finding it fixes, and does not regress the load-harness numbers (§7).

---

## 6. Roadmap: Vertical Slices, One PR Each

Every slice follows the same steps:

1. Write a failing test that reproduces the finding.
2. Make the minimal fix.
3. Run the targeted tests, then the full `pytest`.
4. Run the load harness and compare against the baseline.

### Phase 0: Safety Net

| Slice | Fixes | Design |
|---|---|---|
| 0.1 pytest CI | none | • Add `.github/workflows/tests.yml`: Python 3.12 (align the Dockerfile with it), `pip install -e .`, `pytest -m "not slow"` with a Mongo service container.<br>• Mark `tests/test_e2e.py::TestE2ERealMCPServers` as `slow`, because it is network-dependent. |
| 0.2 Load harness and baseline | none | • Add `tests/manual/load_multi_mcp.py` with about 20 fake servers: fast, slow, stdin-stall, stderr-spam, crash-loop and HTTP.<br>• Drive 500 concurrent calls.<br>• Record event-loop lag, p50/p99 per server class, 503 count, leaked PIDs, threads and ports, and the `/metrics` series count.<br>• Commit the numbers to `tests/manual/BASELINE.md`. |

### Phase 1: Security

| Slice | Fixes | Design |
|---|---|---|
| 1.1 | SEC-1, 3, 4 | • Router-level `dependencies=[Depends(auth.get_token)]` on the management router, with an explicit public allowlist.<br>• Redact `env` values in the list and get responses.<br>• Delete the duplicate `get_token` functions.<br>• Bound `lines` to `1..5000`. |
| 1.2 | SEC-2 | • Add `build_child_env(config)`: an allowlist (`PATH`, `HOME`, `LANG`, `LC_*`, `TMPDIR`, `NODE_*`, `NPM_CONFIG_*`, `UV_*`, `PYTHON*`, `SSL_CERT_*`, proxy vars), extendable with `FMCP_CHILD_ENV_PASSTHROUGH`. Per-server env takes precedence. Reuse `llm_launcher.filter_safe_env_vars`.<br>• **Behaviour change:** add `FMCP_CHILD_ENV_INHERIT_ALL=1` as an escape hatch and call it out in the release notes. |
| 1.3 | SEC-5, 6 | • Pass the git token through `GIT_ASKPASS` or an `http.extraHeader` env var, never in the URL.<br>• Add `FMCP_TRUST_PROXY_HEADERS` and only read `X-Forwarded-For` when it is set.<br>• Stop pairing `*` origins with credentials. |

### Phase 2: Keep the Event Loop Free

| Slice | Fixes | Design |
|---|---|---|
| 2.1 | LOOP-1 | • Add a per-router writer thread fed by a bounded queue.<br>• When the queue is full, raise `StdioBackpressure`, which maps to 503 + `Retry-After`.<br>• Send `notify`, `_on_timeout` and `_safe_write` through the queue.<br>• Remove `_write_lock` and `_send`. |
| 2.2 | LOOP-3, HOT-8 | • Add `FMCP_LOG_LEVEL` (default `INFO`).<br>• Use loguru `enqueue=True` and stop flushing on every line.<br>• Move per-line drainer logs to TRACE.<br>• Carry `trace_id` in a `ContextVar` set by the middleware. |
| 2.3 | LOOP-2, BG-2 | • Add dedicated bounded executors.<br>• Wrap every wait, git, file read and LLM stop/start in `to_thread` with a timeout.<br>• Replace the O(n²) log tail with a `deque`-based reverse read. |
| 2.4 | HOT-2, HOT-3 | • Rewrite the trace and size middleware as pure ASGI. The size limit counts streamed bytes, so chunked bodies are covered, and error responses keep CORS headers.<br>• Make auth `async`.<br>• Load a `Settings` object once at startup. |

### Phase 3: Hot Path

| Slice | Fixes | Design |
|---|---|---|
| 3.1 | HOT-1 | • Add `ServerManager.touch(server_id)`: in memory, called for **all** transports.<br>• Flush to the DB in the background every `FMCP_LAST_USED_FLUSH_S` (30 s) with `w=1`.<br>• The idle reaper reads the in-memory value. |
| 3.2 | HOT-4 | Add `ensure_started()`: concurrent first requests share one shielded start future. Explicit start/restart APIs stay fail-fast. |
| 3.3 | HOT-5 | • Restart only after `FMCP_HTTP_RESTART_THRESHOLD` consecutive connect or protocol errors.<br>• A read timeout returns 504 and a pool timeout returns 503; neither restarts the server.<br>• Make the pool limits configurable. |
| 3.4 | HOT-6, HOT-7 | • When a waiter is cancelled, send `notifications/cancelled` upstream using the **internal** ID.<br>• Map client cancellations from the client ID to the internal ID.<br>• Acquire the `/sse` semaphore inside the generator. |
| 3.5 | HOT-9, HOT-11 | • Make DB logging fire-and-forget.<br>• Take metric labels only from an allowlist.<br>• Move `RequestTimer` after the 404 check. |
| 3.6 | HOT-10 | Use `uvicorn[standard]`, `loop="auto"`, a keep-alive setting, `backlog` and `timeout_graceful_shutdown`, identically in all three modes. |

### Phase 4: Background Work and Process Ownership

| Slice | Fixes | Design |
|---|---|---|
| 4.1 | BG-1 | • Run one supervised task per server, bounded by a health-concurrency semaphore.<br>• Run restarts as detached tasks.<br>• Reuse the handle's client for pings.<br>• Apply the same pattern to the LLM health monitor. |
| 4.2 | PROC-1, PROC-3 | • Spawn with `start_new_session=True` and stop with `os.killpg` everywhere.<br>• Sum psutil metrics over child processes.<br>• Add tini to the Dockerfile. |
| 4.3 | PROC-2 | • Make spawning cancel-safe: on cancel, kill the process group, release the port and unregister the server.<br>• Set the outer timeout to the inner budget plus a margin. |
| 4.4 | STATE-1, STATE-2 | • Move the `on_event` bodies into the lifespan.<br>• Stop servers before the DB disconnects.<br>• Stop servers in parallel with `gather`, under a total budget shorter than the Docker grace period.<br>• Document `stop_grace_period`. |

### Phase 5: Fan-out and Read Endpoints

| Slice | Fixes | Design |
|---|---|---|
| 5.1 | FAN-1, FAN-2 | • `list_servers`: a single `$in` query with a projection and pagination.<br>• GET endpoints never spawn servers.<br>• Fix the index for the `server_name` query.<br>• Run start-all and stop-all in parallel under a semaphore, honouring `enabled_only`. |
| 5.2 | FAN-3, FAN-5 | • GET LLM endpoints return cached health and stay read-only.<br>• Frontend polling: pause when `document.hidden`, add an in-flight guard, back off from 1 s.<br>• Inspector logs: return only new entries via a `?since=` cursor. |
| 5.3 | FAN-4 | • Run mode: start uvicorn first, then spawn servers concurrently in the background.<br>• `/health` reports `starting` meanwhile.<br>• `_server_processes` becomes a view over `server_manager.processes`. |

### Phase 6: MCP Protocol Fidelity

| Slice | Fixes | Design |
|---|---|---|
| 6.1 | MCP-1, MCP-3 | • Cache the real upstream `initialize` result per server and return it, with the negotiated protocolVersion.<br>• Map each gateway session to an upstream session.<br>• On an upstream 404, re-handshake once and retry. |
| 6.2 | MCP-2, MCP-5 | • Stop advertising capabilities the gateway can't serve, or proxy `roots`/`sampling`.<br>• Stream upstream SSE with `client.stream`.<br>• Forward progress on `/mcp` when the client accepts `text/event-stream`. |
| 6.3 | MCP-4 | • Keep an in-memory tools cache in `ServerManager`, invalidated on `list_changed`.<br>• Fix stateless-HTTP detection.<br>• Keep `tools` on `PUT`. |
| 6.4 | MCP-7, MCP-8 | • `run_tool` uses the same transport-dispatch helper as `/mcp`.<br>• Return JSON-RPC error envelopes.<br>• Support batches, or return a proper -32600.<br>• Return 202 for notifications.<br>• Add a response-size cap. |
| 6.5 | MCP-6 | **Product decision needed:** either fix legacy SSE properly (session-aware GET-then-POST) or drop the `sse` transport. |

### Phase 7: Container and State Hygiene

| Slice | Fixes | Design |
|---|---|---|
| 7.1 | IMG-1 | • Move `NPM_CONFIG_CACHE`/`UV_CACHE_DIR` to a persistent volume.<br>• Add optional `FMCP_PREWARM=1`, which runs `npm cache add` for configured packages at boot.<br>• Recommend pinned package versions in docs. |
| 7.2 | IMG-2, 3, 4 | • Raise `RLIMIT_NOFILE` at startup.<br>• Cap node memory with `NODE_OPTIONS` instead of `RLIMIT_AS`.<br>• Make the port range configurable.<br>• Align the Python version, reorder Docker layers, run as a non-root user and use `npm ci`. |
| 7.3 | STATE-3, 4, 5 | • Copy configs instead of mutating them.<br>• Make the memory backend merge instead of overwrite.<br>• Cap the logs collection.<br>• Rotate stderr logs while servers run.<br>• Prune locks when a server is deleted.<br>• Keep a single `get_stderr_tail`.<br>• `/health` uses a cached DB status plus an MCP process summary.<br>• Wrap each row of idle cleanup in its own try. |

### Phase 8: Cleanup

| Slice | Fixes | Design |
|---|---|---|
| 8.1 | P6 dead code | • Delete the listed modules and branches once `grep` across `fluidmcp/ tests/ docs/` shows no references.<br>• Update `CLAUDE.md`, `CONTRIBUTING.md` and the `pr_review.yml` prompt. |
| 8.2 | P6 structure | • Split `management.py` into `api/servers.py`, `api/llm.py`, `api/inference.py` and `api/diagnostics.py`.<br>• Split `create_dynamic_router` into per-transport dispatchers.<br>• Break the `run_servers` ↔ `management` import cycle.<br>• Consolidate validators, sanitizers and the httpx client factory.<br>• *Pure moves only, no behaviour change.* |

### Task Ordering and Dependencies

```
0.1 → 0.2 → 1.x (security, can ship immediately after 0.1)
            → 2.1 → 2.2 → 2.3 → 2.4
            → 3.1 → 3.2 → 3.3 → 3.4 → 3.5 → 3.6
            → 4.2 → 4.3 → 4.1 → 4.4
            → 5.x, 6.x, 7.x (independent of each other)
            → 8.1 → 8.2 (last, once behaviour is pinned by tests)
```

---

## 7. Acceptance Criteria

The criteria below define "the only bottleneck is the infrastructure". They are measured with
the load harness from slice 0.2:

- [ ] With one server's stdin stalled and another spamming stderr:
  - event-loop lag p99 stays **under 20 ms**;
  - fast-server p99 stays within **10 %** of the fast-only baseline.
- [ ] **Zero 503s** when 50 concurrent cold-start requests hit one stopped server.
- [ ] A server in crash-loop backoff delays no other server's health check by more than one interval.
- [ ] No orphan `node` processes, leaked router threads or leaked ports after 100 start/stop/timeout cycles.
- [ ] The `/metrics` series count stays constant under 10k random-path 404s.
- [ ] **No MongoDB call on the MCP request path.** Assert this with a DB mock that raises.
- [ ] Container stop with 30 servers finishes within the grace period, and the final state writes succeed.
- [ ] `GET /api/servers` returns 401 without a token.
- [ ] No secret values appear in any API response.
- [ ] MCP children do not see `FMCP_BEARER_TOKEN` or `MONGODB_URI`.
- [ ] CI runs `pytest` on every PR.

---

## 8. Out of Scope

- Running more than one uvicorn worker, or splitting servers across containers (the topology is fixed).
- Replacing the custom metrics module with `prometheus-client`.
- Rewriting the Inspector agent. Two known follow-ups:
  - its "streaming" collects the whole reply before sending;
  - concurrent stdout reads on its stdio session are unsafe.
- Merging the `run`/`github` launch paths into `ServerManager`.
