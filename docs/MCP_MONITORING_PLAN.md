# MCP Fleet Monitoring — Implementation Plan (FluidMCP side)

**Status:** P0–P2 implemented (see §13 for what shipped)
**Owner:** FluidMCP team
**Consumer:** `gpt-voice-tester` (monitoring/alerting repo)
**Driver:** customer deployments where MCP servers go down repeatedly — need detection, auto-recovery, root-cause attribution, and reporting back to the customer's own team.

> Written to be customer-agnostic. Any deployment running a fleet of MCP servers has these needs; nothing here is specific to one account.

---

## 1. Short answer: yes, this is very doable

FluidMCP already **detects** and **auto-restarts** dead MCP servers. Most of the hard runtime work exists. What is missing is a **monitoring-facing contract**: a fleet-level rollup, an incremental event feed, push notification, and classification of *dependency* failures (the "SQL connection broken" case).

Rough split:

| Layer | State |
|---|---|
| Crash detection (PID death, zombie HTTP) | ✅ Built |
| Auto-restart with backoff + storm detection | ✅ Built |
| Exit-code classification | ✅ Built |
| Crash history persistence (MongoDB) | ✅ Built |
| Per-server stderr capture + tail API | ✅ Built |
| Prometheus metrics | ✅ Built |
| Per-server debug aggregator API | ✅ Built |
| **Fleet-wide health rollup (one call)** | ❌ Missing |
| **Incremental event feed (`since` cursor)** | ❌ Missing |
| **Push (webhook / SSE) on crash** | ❌ Missing |
| **Dependency-failure detection (SQL/API down)** | ❌ Missing — most important gap |
| **`degraded` state + tool error-rate tracking** | ❌ Missing |
| **Uptime / SLA history for reporting** | ❌ Missing |
| **Missing-env / placeholder-cred detection** | ⚠️ Partial — [`_is_placeholder`](../fluidmcp/cli/services/server_manager.py#L1592) detects them but only silently skips injection; nothing warns |
| **Per-tool error rates** | ⚠️ Partial — `record_tool_call` exists but only feeds Prometheus, not state |
| **Gateway self-monitoring (boot identity, config validity)** | ❌ Missing |

---

## 2. What already exists (verified in code)

### 2.1 The watchdog

[`MCPHealthMonitor`](../fluidmcp/cli/services/server_manager.py#L1909) runs a background loop every `FMCP_HEALTH_CHECK_INTERVAL` seconds (default 30) over every process in `ServerManager.processes`:

- **PID liveness** via [`HealthChecker.check_process_alive`](../fluidmcp/cli/services/health_checker.py#L23) (`psutil`; catches zombie/dead states).
- **Zombie detection** for HTTP-transport servers — [`_check_http_ping`](../fluidmcp/cli/services/server_manager.py#L1995) POSTs `tools/list` with a `FMCP_HTTP_PING_TIMEOUT` (default 10s). PID alive + no HTTP response = treated as dead.
- **Resource snapshot** per cycle (RSS, CPU%, active requests) with a 3-sample memory ring buffer for trend.
- **Threshold enforcement** — [`_check_resource_thresholds`](../fluidmcp/cli/services/server_manager.py#L2318): kills at `FMCP_MEMORY_KILL_PCT` (98%), warns at `FMCP_MEMORY_WARN_PCT` (90%), restarts after `FMCP_CPU_KILL_CYCLES` (3) consecutive cycles above `FMCP_CPU_WARN_PCT` (90%). 60s kill cooldown per server.
- **Restart under policy** with exponential backoff (`5s * 2^min(count,5)`), capped by the server's `max_restarts`.
- **Restart-storm detection** — [`_check_stability`](../fluidmcp/cli/services/server_manager.py#L2441): ≥`FMCP_RESTART_STORM_THRESHOLD` (5) restarts in 10 minutes flips the instance to `stability: "unstable"` in the DB. Cleared after 5 minutes healthy.
- **Fast-path restart** — [`trigger_restart`](../fluidmcp/cli/services/server_manager.py#L2028) is called by the gateway on a 504, skipping backoff.

### 2.2 Crash forensics

[`_cleanup_server`](../fluidmcp/cli/services/server_manager.py#L1476) persists a crash event on every non-intentional exit:

```json
{
  "server_id": "customer-sql",
  "server_name": "Customer SQL MCP",
  "exit_code": 137,
  "exit_category": "resource",
  "exit_label": "oom_killed",
  "exit_description": "Killed by OS (likely OOM) — check memory limits",
  "stderr_tail": "...last 2KB of stderr...",
  "uptime_seconds": 412.5,
  "memory_bytes_at_crash": 1073741824,
  "cpu_percent_at_crash": 12.4,
  "active_requests_at_crash": 3,
  "timestamp": "2026-09-01T10:14:02Z"
}
```

[`classify_exit_code`](../fluidmcp/cli/services/server_manager.py#L46) maps exit codes to `(category, label, description)` — `oom_killed`, `segfault`, `command_not_found`, `permission_denied`, `sigterm_container`, etc.

### 2.3 Existing HTTP surface

| Endpoint | Purpose |
|---|---|
| `GET /health` | Gateway + MongoDB health (unauthenticated) |
| `GET /metrics` | Prometheus exposition |
| `GET /api/servers` | All servers with nested `status` |
| `GET /api/servers/{id}/status` | State, pid, uptime, restart_count, stability |
| `GET /api/servers/{id}/resources` | RSS, CPU, FDs, memory trend |
| `GET /api/servers/{id}/crashes` | Crash history + `crashes_last_hour` |
| `GET /api/servers/{id}/stderr` | Tail with `contains` filter |
| `GET /api/servers/{id}/debug` | Aggregator: status + resources + concurrency + crashes + stderr |
| `POST /api/servers/{id}/restart` | Manual restart |
| `POST /api/servers/start-all` \| `stop-all` | Fleet control |

All `/api/*` routes are bearer-token gated when `FMCP_SECURE_MODE=true`.

### 2.4 Structured logging (commit `ff4d580`)

Per-request trace IDs (`X-Trace-ID`), JSON log sink, and proxy-path tags: `[mcp.call]`, `[mcp.ok]`, `[mcp.slow]`, `[mcp.timeout]`, `[mcp.error_response]`, `[mcp.error]`. Per-tool metrics via `record_tool_call(tool, status, duration)`.

---

## 3. The gap that actually matters

> **A broken SQL connection does not kill the process.**

Every detection mechanism above answers *"is the process alive and serving HTTP?"* For an MCP whose database credentials expired, whose connection pool is exhausted, or whose upstream API is 503-ing, the answer is **yes** — PID alive, HTTP responds, `tools/list` works. The watchdog sees a perfectly healthy server. The customer sees every tool call failing.

That failure is only visible in three places, none of which currently drive state:

1. **Tool results** — JSON-RPC `error`, or a `result` with `isError: true` and a message like `ECONNREFUSED 10.x.x.x:1433` / `Login failed for user`.
2. **stderr** — the MCP's own logs.
3. **Latency** — pool exhaustion shows up as timeouts before it shows up as errors.

So the plan needs three new detection mechanisms alongside the existing process watchdog:

- **Passive**: track tool-call outcomes per server in a rolling window; cross a threshold → `degraded`.
- **Active**: optional per-server `health_probe` that calls a cheap tool on an interval (e.g. a `SELECT 1` tool). This is the *only* way to catch a broken dependency on an **idle** server — which is exactly the 3am case.
- **Classification**: regex catalog over tool errors + stderr that names the failure (`db_connection_refused`, `db_auth_failed`, `upstream_5xx`, `rate_limited`) and, critically, assigns an **owner** — is this FluidMCP's problem or the customer's problem? That is what gets reported back to the customer.

---

## 4. Architecture

```
┌─────────────────────────── FluidMCP gateway ───────────────────────────┐
│                                                                        │
│  MCPHealthMonitor ──┐                                                  │
│  ToolErrorTracker ──┼──► EventBus ──┬──► Mongo (mcp_events, TTL 30d)   │
│  DependencyProbe  ──┤               ├──► SSE  /api/monitoring/stream   │
│  ResourceMonitor  ──┘               └──► WebhookDispatcher (HMAC)      │
│                                                                        │
│  FailureClassifier ──► failure_category + owner + remediation          │
│                                                                        │
│  /api/monitoring/{health,events,uptime,servers/{id}/diagnosis}         │
└────────────────────────────────────────────────────────────────────────┘
            │ push (webhook, instant)      ▲ pull (poll 30s, backstop)
            ▼                              │
┌──────────────────────── gpt-voice-tester ──────────────────────────────┐
│  Collector → State store → Alert engine → Dashboards + customer reports │
└────────────────────────────────────────────────────────────────────────┘
```

**Both directions are required.** Webhooks give sub-second crash alerts. Polling is the backstop — if FluidMCP itself dies, no webhook will ever fire, and only a missed poll reveals it. The monitoring repo must treat "poll failed / stale" as its own highest-severity alert.

**Division of responsibility:**

- **FluidMCP** owns: process state, restart policy, failure classification, event emission. It is the *source of truth*, and it self-heals.
- **gpt-voice-tester** owns: history beyond the retention window, alert routing (Slack/email/PagerDuty to the customer), dashboards, SLA reports, cross-deployment aggregation.

FluidMCP does **not** send emails or Slack messages. It emits typed events; the monitoring repo decides who hears about them.

---

## 5. New components

All new code under `fluidmcp/cli/services/`, new router at `fluidmcp/cli/api/monitoring.py` mounted at `/api/monitoring`.

### 5.1 `event_bus.py`

In-process pub/sub. `emit(event)` → in-memory ring buffer (last 1000) + async Mongo write + fan-out to SSE subscribers and the webhook dispatcher. Never blocks or raises into the caller — a monitoring failure must not take down a server restart.

Event envelope:

```json
{
  "event_id": "evt_01J...",
  "seq": 10432,
  "type": "server.crashed",
  "severity": "critical",
  "server_id": "customer-sql",
  "server_name": "Customer SQL MCP",
  "timestamp": "2026-09-01T10:14:02.113Z",
  "data": { }
}
```

`seq` is a monotonic per-gateway counter — it is the cursor for the incremental feed and makes gap detection trivial on the consumer side.

Event types:

| Type | Severity | Emitted from |
|---|---|---|
| `server.started` | info | `_start_server_unlocked` |
| `server.stopped` | info | `_stop_server_unlocked` |
| `server.crashed` | critical | `_cleanup_server` |
| `server.restarting` | warning | `_restart_under_policy` |
| `server.restarted` | info | `_restart_under_policy` |
| `server.restart_failed` | critical | `_restart_under_policy` |
| `server.unstable` | critical | `_check_stability` |
| `server.recovered` | info | `_clear_stability` |
| `server.zombie` | critical | `_check_http_ping` |
| `server.degraded` | warning | `ToolErrorTracker` |
| `server.dependency_failed` | critical | `DependencyProbe` / classifier |
| `resource.memory_warning` | warning | `_check_resource_thresholds` |
| `resource.memory_killed` | critical | `_check_resource_thresholds` |
| `resource.cpu_stuck` | warning | `_check_resource_thresholds` |
| `gateway.started` / `gateway.stopping` | info | lifespan hooks |

### 5.2 `failure_classifier.py`

Two inputs, one output.

- **Exit codes** → reuse `classify_exit_code`.
- **Text** (stderr tail + tool error messages) → ordered regex catalog.

```python
PATTERNS = [
    (r"ECONNREFUSED|could not connect to server|connection refused",
     "db_connection_refused", "customer",
     "MCP cannot reach its database host. Verify DB host/port reachability and firewall rules."),
    (r"Login failed for user|password authentication failed|Access denied for user",
     "db_auth_failed", "customer",
     "Database credentials rejected. Rotate/update the DB password in the server's env vars."),
    (r"too many connections|connection pool exhausted|QueuePool limit",
     "db_pool_exhausted", "customer",
     "Connection pool exhausted. Increase pool size or fix connection leaks in the MCP."),
    (r"SSL.*(handshake|certificate).*(fail|expired)",
     "tls_failure", "customer", "TLS/certificate problem reaching the upstream."),
    (r"401 Unauthorized|403 Forbidden|invalid api key",
     "upstream_auth_failed", "customer", "Upstream API rejected credentials."),
    (r"429|rate limit", "rate_limited", "customer", "Upstream rate limit hit."),
    (r"50[0234] |Bad Gateway|Service Unavailable",
     "upstream_5xx", "external", "Upstream service is failing."),
    (r"ETIMEDOUT|timed out|timeout", "upstream_timeout", "unknown",
     "Requests to the dependency are timing out."),
    (r"MODULE_NOT_FOUND|ImportError|No module named",
     "missing_dependency", "fluidmcp", "MCP package is missing a dependency — reinstall."),
    (r"ENOENT|command not found", "bad_command", "fluidmcp",
     "Configured command not found on PATH."),
]
```

The `owner` field (`customer` | `fluidmcp` | `external` | `unknown`) is what makes the customer-facing report actionable — it separates "the customer must rotate a password" from "we shipped a bad build".

Catalog lives in `fluidmcp/cli/services/failure_patterns.py` so it can be extended without touching logic, and is overridable via `FMCP_FAILURE_PATTERNS_FILE` (JSON) for deployment-specific error strings.

### 5.3 `tool_error_tracker.py`

Per-server rolling window (default 5 min / 200 samples) of tool-call outcomes. Records from **both** call paths:

- `run_tool` in [`management.py`](../fluidmcp/cli/api/management.py#L2352) — already calls `record_tool_call`.
- The gateway proxy in [`package_launcher.py`](../fluidmcp/cli/services/package_launcher.py) — currently only logs `[mcp.error_response]`; must also feed the tracker.

**Must also inspect successful responses for `result.isError == true`.** MCP servers report tool-level failures inside a 200 OK JSON-RPC *result*, not as a JSON-RPC error. Missing this is the single easiest way to under-report the customer's actual failures.

Tracked **per (server, tool)**, not only per server. A single broken tool inside an otherwise-busy server dilutes to nothing in a server-wide average and never crosses the threshold — which is exactly the "one endpoint suddenly started failing" case. The rollup exposes both:

```json
"error_rate_5m": 0.12,
"failing_tools": [
  { "tool": "execute_query", "error_rate_5m": 0.94, "calls": 34,
    "last_error": "ECONNREFUSED 10.20.1.44:1433" }
]
```

Transition rules:
- any single tool's error rate ≥ `FMCP_DEGRADED_ERROR_RATE` over ≥ `FMCP_DEGRADED_MIN_SAMPLES` → emit `server.degraded` naming that tool
- error rate ≥ `FMCP_DEGRADED_ERROR_RATE` (default 0.5) over ≥ `FMCP_DEGRADED_MIN_SAMPLES` (default 5) → emit `server.degraded`, set state `degraded`.
- error rate < 0.1 over a full window → emit `server.recovered`.

### 5.4 `dependency_probe.py`

Opt-in per server:

```json
{
  "id": "customer-sql",
  "command": "npx",
  "args": ["-y", "@acme/mcp-sql"],
  "health_probe": {
    "tool": "execute_query",
    "args": { "query": "SELECT 1" },
    "interval_seconds": 120,
    "timeout_seconds": 15,
    "failure_threshold": 2
  }
}
```

Runs inside the existing `MCPHealthMonitor` loop (no second scheduler). After `failure_threshold` consecutive failures → `server.dependency_failed` with the classifier's verdict attached. Recovery emits `server.recovered`.

Restart policy interaction: dependency failure **does not** trigger a restart by default (restarting rarely fixes wrong credentials, and a restart loop makes diagnosis harder). Opt in per server with `"restart_on_dependency_failure": true` — appropriate for connection-pool leaks, where a restart genuinely does help.

### 5.5 `webhook_dispatcher.py`

Registered receivers (persisted in Mongo):

```json
{
  "url": "https://monitor.internal/hooks/fluidmcp",
  "secret": "whsec_...",
  "events": ["server.crashed", "server.unstable", "server.dependency_failed"],
  "enabled": true
}
```

- `X-FMCP-Signature: sha256=<hmac(secret, raw_body)>`, `X-FMCP-Event`, `X-FMCP-Delivery`, `X-FMCP-Timestamp`.
- Retry 3× with backoff (2s/8s/32s); 10 consecutive failures auto-disables and logs loudly.
- **SSRF guard**: reject non-HTTPS in production and block link-local/metadata ranges (`169.254.0.0/16`) unless `FMCP_WEBHOOK_ALLOW_INSECURE=true`. Optional `FMCP_WEBHOOK_ALLOWLIST` of host patterns.
- Delivery is fire-and-forget on a bounded queue — a slow receiver must never back-pressure the health monitor.

### 5.6 `config_validator.py` — pre-flight config checks

Catches the **missing env var / missing credential** case *before* the server is launched, instead of waiting for it to crash or fail at first tool call.

At `_start_server_unlocked`, before spawning:

- **Declared-required check** — if the server's `metadata.json` or config declares `required_env`, verify every key is present and non-empty.
- **Placeholder check** — reuse [`_is_placeholder`](../fluidmcp/cli/services/server_manager.py#L1592), which already detects `<YOUR_KEY>`, `xxxx`, `your-`, `placeholder`. Today it *silently skips* injecting such values; it should also raise a finding.
- **Unresolved interpolation** — a value still containing `${...}` means an expected environment variable was never set.
- **Command reachability** — `shutil.which(command)` before spawn, so `command_not_found` is reported as config error rather than exit 127.

Result → `server.config_invalid` event (severity `critical`, `failure_owner: customer`) and state `config_error`, with the offending keys listed **by name only — never values**:

```json
{
  "type": "server.config_invalid",
  "server_id": "customer-sql",
  "data": {
    "failure_category": "missing_credentials",
    "failure_owner": "customer",
    "missing_env": ["DB_PASSWORD"],
    "placeholder_env": ["API_KEY"],
    "remediation": "Set DB_PASSWORD and replace the placeholder value for API_KEY via PUT /api/servers/customer-sql/instance/env"
  }
}
```

Default behaviour is **warn-and-start**, not block — a server may legitimately read credentials from a mounted file rather than env. Set `"strict_config": true` per server to refuse to start instead. This distinction matters: blocking by default would turn a monitoring feature into an outage.

### 5.7 Gateway self-monitoring

Everything above monitors the MCP servers. This monitors **FluidMCP itself** — the case where the container is redeployed with a bad Mongo URI or a missing bearer token.

**a. Boot identity.** Every monitoring payload carries:

```json
{ "gateway_id": "gw-prod-1", "boot_id": "boot_01J8X...", "boot_count": 47, "started_at": "..." }
```

`boot_id` is generated once at process start. A changed `boot_id` between two polls is unambiguous proof the gateway restarted — this is what separates "a deploy happened" from "the network blipped", which is otherwise undiagnosable from the outside. It is also the authoritative signal for the `seq` counter reset described in the integration guide.

**b. Readiness vs liveness.** `/health` currently reports `starting` when the DB is down but no models are loaded, which conflates "booting normally" with "misconfigured". Split it:

- `GET /health` — **liveness**. Always 200 if the process is serving. Must bind and answer *even when config is broken*, otherwise a misconfigured container is indistinguishable from a dead one.
- `GET /health/ready` — **readiness**. 503 until dependencies are actually usable.

Add a `config` block to `/health` reporting boot-time validation:

```json
{
  "status": "degraded",
  "boot_id": "boot_01J8X...",
  "config": {
    "valid": false,
    "errors": [
      { "key": "FMCP_BEARER_TOKEN", "problem": "not set while FMCP_SECURE_MODE=true",
        "impact": "all /api requests will return 500" }
    ],
    "warnings": [
      { "key": "MONGODB_URI", "problem": "unreachable", "impact": "crash history and events are not persisted" }
    ]
  }
}
```

This directly fixes the redeploy case: a container that comes up with a missing bearer token currently returns opaque 500s from [`auth.py`](../fluidmcp/cli/auth.py#L38) on every `/api` call, with nothing saying why. Reporting it on the unauthenticated `/health` is the only way monitoring can see it — by definition it cannot authenticate to find out.

**c. Gateway resource self-report.** Surface FluidMCP's own RSS, CPU, open FDs, thread count, and asyncio event-loop lag. Event-loop lag is the highest-signal one: a blocked loop means the gateway stops responding to *everything*, including its own health checks, and it is invisible in every other metric. The values already exist as `fluidmcp_process_memory_bytes` / `fluidmcp_process_cpu_percent` in the Prometheus registry — they just are not in the JSON rollup.

**d. Crash-loop visibility.** If the gateway crash-loops on boot (bad Mongo URI with `--require-persistence`), it never serves `/health` at all, so the *only* external evidence is unreachability. Two mitigations:

- Write a boot record (`boot_id`, `boot_count`, `timestamp`, `config_errors`) to Mongo as the *first* action after DB connect, before any fail-fast exit. Once Mongo is reachable again, the history explains the gap.
- Emit `gateway.config_invalid` before exiting, if the event sink is available at all.

Neither closes the gap fully. When the container is gone, absence of heartbeat is the only signal — which is why the monitoring repo's stale-poll alert is load-bearing and must be treated as P1.

---

## 6. New endpoints

Full request/response contracts live in [MONITORING_INTEGRATION_GUIDE.md](MONITORING_INTEGRATION_GUIDE.md); this is the build list.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/monitoring/health` | Fleet rollup — summary + every server in one call |
| `GET` | `/api/monitoring/events` | Incremental feed, `?since=<seq>&limit=&severity=&server_id=` |
| `GET` | `/api/monitoring/stream` | SSE live event push |
| `GET` | `/api/monitoring/servers/{id}/diagnosis` | Why is it down — classification + evidence + remediation |
| `GET` | `/api/monitoring/gateway` | FluidMCP's own health: boot_id, config validity, self-resources, event-loop lag |
| `GET` | `/health/ready` | Readiness (503 until dependencies usable) — distinct from liveness `/health` |
| `GET` | `/api/monitoring/uptime` | Per-server uptime %, MTTR, crash count over a window |
| `POST` | `/api/monitoring/webhooks` | Register receiver |
| `GET` | `/api/monitoring/webhooks` | List receivers (secrets redacted) |
| `DELETE` | `/api/monitoring/webhooks/{id}` | Remove receiver |
| `POST` | `/api/monitoring/webhooks/{id}/test` | Send a synthetic event |

Design constraints:

- `/health` (fleet) must serve entirely from in-memory state + one Mongo read. Target < 100ms with 50 servers. It will be polled every 30s forever.
- `/events` is cursor-based on `seq`, never timestamp-based — clock skew and same-millisecond writes cause silent event loss with timestamp cursors.
- Every response carries `gateway_id` and `generated_at` so the monitoring repo can aggregate multiple FluidMCP deployments and detect staleness.

---

## 7. Data model

New collection `mcp_events`:

```
{ _id, seq, event_id, type, severity, server_id, server_name, timestamp, data }
```
Indexes: `{seq: 1}` (unique), `{server_id: 1, timestamp: -1}`, `{timestamp: 1}` with `expireAfterSeconds = FMCP_EVENT_RETENTION_DAYS * 86400` (default 30).

New collection `mcp_state_transitions` (for uptime/SLA):

```
{ _id, server_id, from_state, to_state, timestamp, reason, failure_category }
```
Uptime % over a window = time in `running`/`healthy` ÷ window length, computed from transitions.

New collection `monitoring_webhooks`: as in §5.5.

**Persistence caveat:** all of this requires MongoDB. With the in-memory repository ([`memory.py`](../fluidmcp/cli/repositories/memory.py)) events are lost on restart and uptime history is meaningless. For any production customer deployment, run with `--require-persistence`.

---

## 8. Wiring points in existing code

| File | Change |
|---|---|
| [`server_manager.py`](../fluidmcp/cli/services/server_manager.py) | `emit()` in `_cleanup_server`, `_restart_under_policy`, `_check_stability`, `_clear_stability`, `_check_resource_thresholds`, `_check_http_ping`, `_start_server_unlocked`, `_stop_server_unlocked` |
| `server_manager.py` | `get_server_status` returns `degraded` + `failure_category` + `last_error` |
| `MCPHealthMonitor` | run `DependencyProbe` inside the existing cycle |
| [`package_launcher.py`](../fluidmcp/cli/services/package_launcher.py) | feed `ToolErrorTracker` from the proxy path; inspect `result.isError` |
| [`management.py`](../fluidmcp/cli/api/management.py) | feed `ToolErrorTracker` from `run_tool` |
| [`server.py`](../fluidmcp/cli/server.py) | mount monitoring router; start/stop dispatcher; emit gateway events |
| [`base.py`](../fluidmcp/cli/repositories/base.py) + `database.py` + `memory.py` | `save_event`, `list_events_since`, `save_state_transition`, `get_uptime_stats`, webhook CRUD |
| [`models/server_status.py`](../fluidmcp/cli/models/server_status.py) | wire up the already-defined `UNHEALTHY`; add `DEGRADED`, `CONFIG_ERROR` |
| `server_manager.py` | run `config_validator` in `_start_server_unlocked` before spawn |
| [`server.py`](../fluidmcp/cli/server.py) | generate `boot_id` at startup; add `config` block + `boot_id` to `/health`; add `/health/ready`; write boot record to Mongo before any fail-fast exit |
| [`auth.py`](../fluidmcp/cli/auth.py) | on missing `FMCP_BEARER_TOKEN` in secure mode, surface the misconfiguration on `/health` rather than only 500-ing per request |

---

## 9. Phasing

Each phase ships independently and is separately useful.

### P0 — Pull-based fleet visibility + gateway self-monitoring (~3 days)
`GET /api/monitoring/health`, `GET /api/monitoring/events` (backed by existing crash events), `GET /api/monitoring/gateway`, `failure_classifier.py`, `config_validator.py`, `boot_id`/`boot_count`, `config` block on `/health`, liveness/readiness split, `mcp_events` collection + emission from `_cleanup_server`.

Gateway self-monitoring is in P0 deliberately, not later: a misconfigured redeploy is both the most likely failure and the one that is currently hardest to diagnose from outside.

**Unblocks the monitoring repo completely** — they can build the entire dashboard and alerting on polling alone. Everything after this reduces detection latency and adds depth.

### P1 — Push (~2 days)
`event_bus.py`, `webhook_dispatcher.py`, SSE stream, webhook CRUD + test endpoint, emission wired into all lifecycle points.

Crash-to-alert latency drops from ≤30s (poll interval) to < 1s.

### P2 — Dependency failure detection (~2–3 days) ← the core ask
`tool_error_tracker.py` (per-tool granularity), `dependency_probe.py`, `degraded` state, `server.degraded` / `server.dependency_failed` events, `/servers/{id}/diagnosis`.

This is what catches "SQL connection broken". Highest value, most design risk — thresholds will need tuning against real customer traffic, so ship it with everything configurable per server and default to alert-only (no auto-restart).

### P3 — Reporting (~1–2 days)
`mcp_state_transitions`, `/api/monitoring/uptime`, MTTR/MTBF, weekly customer report data.

### P4 — Hardening
Read-only monitoring token separate from the admin bearer token, rate limiting on monitoring routes, load test with 50 servers, chaos test (kill -9 loops, DB blackhole, receiver returning 500s).

---

## 10. Configuration

```bash
# Detection
FMCP_HEALTH_CHECK_INTERVAL=30        # existing — watchdog cycle
FMCP_HTTP_PING_TIMEOUT=10            # existing — zombie detection
FMCP_RESTART_STORM_THRESHOLD=5       # existing — restarts/10min → unstable

# New: degradation
FMCP_DEGRADED_ERROR_RATE=0.5        # per-tool error rate that trips degraded
FMCP_DEGRADED_MIN_SAMPLES=5         # minimum calls before the rate is trusted
FMCP_ERROR_WINDOW_SECONDS=300       # rolling window for error-rate maths
FMCP_RECOVERY_STREAK=5              # consecutive successes required to clear degraded
FMCP_RECOVERY_ERROR_RATE=0.1        # legacy rate floor (streak is now authoritative)

# New: events
FMCP_EVENT_RETENTION_DAYS=30
FMCP_EVENT_BUFFER_SIZE=1000

# New: webhooks
FMCP_WEBHOOK_TIMEOUT=10
FMCP_WEBHOOK_MAX_RETRIES=3
FMCP_WEBHOOK_ALLOWLIST=monitor.internal,*.customer.example.com
FMCP_WEBHOOK_ALLOW_INSECURE=false

# New: classifier
FMCP_FAILURE_PATTERNS_FILE=/etc/fluidmcp/customer-patterns.json

# New: gateway self-monitoring
FMCP_GATEWAY_ID=gw-prod-1           # names this deployment in every payload
FMCP_STRICT_CONFIG=false            # true = refuse to start servers with invalid config
FMCP_EVENT_LOOP_LAG_WARN_MS=250     # log a warning above this lag
FMCP_REQUIRE_PERSISTENCE=false      # /health/ready returns 503 if DB is down
```

---

## 11. Testing

- **Unit** — classifier against a corpus of real customer stderr samples; `ToolErrorTracker` window math; `seq` monotonicity and gap-free ordering under concurrent emission; HMAC signature correctness.
- **Integration** — kill an MCP with `SIGKILL` → assert `server.crashed` in `/events` with `exit_label: sigkill` and a webhook delivered; block the MCP's DB port → assert transition to `degraded` with `failure_category: db_connection_refused`; restart-storm → `server.unstable`.
- **Config scenarios** — start a server with a missing required env var → `server.config_invalid` with the key named and no value leaked; start with `<YOUR_KEY>` placeholder → flagged; boot the gateway with `FMCP_SECURE_MODE=true` and no token → `/health` reports the error unauthenticated while `/api` 500s; boot with a bad Mongo URI → boot record written or `gateway.config_invalid` emitted before exit.
- **Restart identity** — restart the gateway → `boot_id` changes, `boot_count` increments, `seq` resets, and a consumer keyed on `(gateway_id, boot_id)` re-syncs without gaps or duplicates.
- **Per-tool isolation** — one tool failing at 95% inside a server whose other tools are healthy → `failing_tools[]` names it and `server.degraded` fires, even though server-wide error rate stays low.
- **Failure-injection** — webhook receiver returning 500 (retries, then auto-disable); Mongo unreachable mid-run (events buffered/dropped without killing the health monitor); 50 servers crashing simultaneously (dispatcher queue bounded, no unbounded memory growth).

---

## 12. Risks

| Risk | Mitigation |
|---|---|
| Monitoring code crashes the watchdog | All `emit()`/dispatch wrapped in try/except; bounded queues; never `await` a webhook inside the monitor loop |
| Event collection grows unbounded | TTL index; capped `limit` on `/events`; bounded in-memory ring |
| Alert fatigue from a flapping server | `server.unstable` is a distinct event type — monitoring repo should collapse per-crash alerts into one "unstable" incident |
| Degradation thresholds too sensitive → false alarms | Ship alert-only, per-server tunable; tune against real traffic before enabling any auto-action |
| Webhook URLs as SSRF vector | HTTPS-only + host allowlist + metadata-range block |
| No Mongo → no history | Document `--require-persistence` as mandatory for production |
| Gateway itself dies (no webhook fires) | Monitoring repo's stale-poll alert is the only backstop — call this out explicitly in the integration guide |
| Misconfigured redeploy returns opaque 500s | `config` block on unauthenticated `/health`; `boot_id` change proves a restart happened |
| Blocking start on config validation causes an outage | Warn-and-start by default; `strict_config` is opt-in per server |
| Single failing tool hidden by server-wide error average | Track error rate per (server, tool); surface `failing_tools[]` in the rollup |

---

## 13. Implementation status

P0, P1 and P2 are implemented and tested. P3 (reporting) is partially in: the
uptime endpoint and state-transition recording exist; the weekly-report shaping
does not.

### Shipped modules

| File | Purpose |
|---|---|
| [`models/events.py`](../fluidmcp/cli/models/events.py) | Event enum, severity, envelope, wire format |
| [`services/event_bus.py`](../fluidmcp/cli/services/event_bus.py) | seq assignment, ring buffer, async persistence, SSE fan-out |
| [`services/failure_patterns.py`](../fluidmcp/cli/services/failure_patterns.py) | Regex catalog + owner attribution (data only) |
| [`services/failure_classifier.py`](../fluidmcp/cli/services/failure_classifier.py) | `classify_text`, `classify_exit`, `diagnose` |
| [`services/config_validator.py`](../fluidmcp/cli/services/config_validator.py) | Pre-flight missing/placeholder credential detection |
| [`services/tool_error_tracker.py`](../fluidmcp/cli/services/tool_error_tracker.py) | Per-(server, tool) rolling error rates, degraded/recovered |
| [`services/dependency_probe.py`](../fluidmcp/cli/services/dependency_probe.py) | Active `health_probe` calls for idle servers |
| [`services/webhook_dispatcher.py`](../fluidmcp/cli/services/webhook_dispatcher.py) | HMAC-signed delivery, retry, SSRF guards, auto-disable |
| [`services/gateway_info.py`](../fluidmcp/cli/services/gateway_info.py) | boot_id/boot_count, config validation, self-resources, loop lag |
| [`api/monitoring.py`](../fluidmcp/cli/api/monitoring.py) | All 12 `/api/monitoring/*` endpoints |

### Tests

- [`tests/test_monitoring.py`](../tests/test_monitoring.py) — 78 unit tests
- [`tests/test_monitoring_api.py`](../tests/test_monitoring_api.py) — 23 API integration tests
- [`tests/manual/monitoring/fake_sql_mcp.py`](../tests/manual/monitoring/fake_sql_mcp.py) — an MCP whose "database" can be broken via flag files **without restarting the process**
- [`tests/manual/monitoring/live_test.sh`](../tests/manual/monitoring/live_test.sh) — end-to-end against a real gateway

```bash
# 124 unit + API tests
pytest tests/test_monitoring.py tests/test_monitoring_api.py -q

# End-to-end: starts a real gateway, breaks a real MCP's database, asserts the
# reported diagnosis. Takes ~100s. 33 assertions.
bash tests/manual/monitoring/live_test.sh 8123
```

Full-suite status: **8 failed, 982 passed, 33 skipped, 1 error** — identical to
a clean checkout. All 8 failures and the 1 error are pre-existing and unrelated
to monitoring (§14.4).
`test_debug_aggregator.py` went from 3 failing to 0 — see §14.4.

### Verified live

With a real gateway and a real MCP subprocess, after breaking the simulated
database while leaving the process untouched:

```
process_state    : running          ← PID alive, HTTP 200, MCP responding
state            : degraded         ← monitoring overlay caught it
error_rate_5m    : 0.6
failure_category : db_connection_refused
failure_owner    : customer
failing_tools    : [{"tool": "execute_query", "error_rate_5m": 1.0, "errors": 6}]
```

This is the case the process watchdog structurally cannot see, and it is now
detected, classified, attributed to an owner, and pushed as an event.

---

## 14. Findings from implementation

Issues discovered while building, worth acting on separately.

### 14.1 Bugs the live test caught (fixed)

Both were invisible to unit tests and only surfaced against a real gateway with
a real subprocess. Worth recording because they justify keeping the live suite.

**Monitoring code aborted server restarts.** `_restart_under_policy` called
`self.record_transition(...)`, but that method lives on `ServerManager`, not on
`MCPHealthMonitor`. The resulting `AttributeError` was swallowed by the restart
path's broad `except Exception`, so **crashed servers silently stopped being
restarted** — the exact opposite of what a monitoring feature should do:

```
ERROR  Error restarting MCP server 'customer-sql':
       'MCPHealthMonitor' object has no attribute 'record_transition'
```

Fixed by using `self._sm.record_transition`, and hardened by routing all
in-restart-path bookkeeping through a new `_safe_transition()` that cannot raise.
Guarded by three tests, including one that AST-parses `MCPHealthMonitor` and
fails if `self.record_transition` reappears — verified to fail when the bug is
deliberately reintroduced.

**Degraded state was pathologically sticky.** Recovery required the *window-wide*
error rate to fall below 0.1, but the historical failures stay inside the 5-minute
window — so a server that was demonstrably working again kept reporting
`degraded` for minutes, and in the live test never recovered at all. It was also
asymmetric: degradation triggered per-tool, recovery was judged server-wide.

Replaced with a trailing-success-streak rule: recovered once no tool is above the
error threshold **and** `FMCP_RECOVERY_STREAK` (default 5) consecutive successes
have followed, merged across all of the server's tools so a streak on one tool
cannot mask another still failing. Recovery went from ~200 calls to 7.

### 14.2 Secret redaction (added during review)

An adversarial pass found that tool-error text flowed unmodified from an MCP
server into the event feed, the fleet rollup's `last_error`, webhook payloads and
diagnosis evidence. MCP servers routinely echo their own connection strings
("could not connect to `postgres://app:hunter2@db:5432/prod`"), so a credential
could have reached the customer's monitoring store, a Slack channel, or an
incident ticket.

Added [`redact_secrets()`](../fluidmcp/cli/utils/error_utils.py), applied at every
publication point: URL userinfo, `key=value` / `key: value` / JSON
`"key": "value"` for credential-named keys, provider prefixes (`r8_`, `sk_`,
`ghp_`), `Bearer`/`Basic` values, and JWTs.

Two details that matter:

- **Classify raw, publish redacted.** Redaction is lossy and can remove the very
  token a failure pattern matches on. Classification runs against the original
  text; only the stored and emitted copy is scrubbed. A test asserts every
  pattern still classifies correctly after redaction.
- **Redacted JSON stays parseable.** Quoting is preserved
  (`{"api_key":"***REDACTED***"}`), because a mangled payload is nearly as
  unhelpful to a responder as a leaked one. Writing that test is what exposed a
  bug where JSON-quoted keys were not matched at all.

Note the pre-existing `GET /api/servers/{id}/stderr` and `/crashes` endpoints
still return raw stderr — unchanged here, and flagged in the integration guide's
acceptance checklist.

### 14.3 Fixed as part of this work

**Restart attribution for dependency failures.** `db_connection_refused`,
`upstream_5xx` and `rate_limited` were initially reported as
`restart_would_help: true`. They are not: if the dependency is down or
throttling, restarting the MCP client changes nothing and a restart loop only
buries the cause. Now in `RESTART_WONT_HELP`. `db_pool_exhausted` is
deliberately excluded — a restart genuinely clears a leaked pool.

**`--in-memory` flag was unreachable.** [`server.py`](../fluidmcp/cli/server.py)
read `args.in_memory`, but the argument parser never defined it, so the
in-memory branch could not be selected from the CLI. Flag added — required for
local testing without MongoDB.

### 14.4 Found running the real customer MCPs — HIGH PRIORITY

Both surfaced only when the real PIDS and IFS servers ran under FluidMCP with
real credentials. Neither is a monitoring bug; both are core orchestration bugs
that monitoring made visible.

#### Per-server `env` is silently ignored when the gateway has the same variable

[`server_manager.py:1052`](../fluidmcp/cli/services/server_manager.py#L1052):

```python
# Merge environment variables (shell env takes precedence)
env = dict(os.environ)
for key, value in env_vars.items():
    if key not in env and value and not self._is_placeholder(value):
        env[key] = value
```

`if key not in env` means **the gateway process's own environment wins over
per-server configuration**. Observed directly: a server registered with
`DB_HOST=unreachable-db.invalid` received `DB_HOST=fluidgpt-sql-server...`
because the gateway had been started with `.env` sourced. The configured value
was accepted by the API, stored in the database, and returned by
`GET /api/servers/{id}` — then discarded at spawn time. Silently.

Consequences:

- **Two MCPs cannot use different values for the same variable.** For a product
  whose purpose is orchestrating many MCP servers, each with its own database,
  this defeats the core use case.
- **Every MCP subprocess inherits the whole gateway environment**, including
  other servers' secrets and the gateway's own `FMCP_BEARER_TOKEN`.
- **Configuration silently does not apply** — the API reports success and the
  behaviour is wrong, which is the hardest failure mode to debug.

The comment says the precedence is deliberate, so this is a product decision
rather than an obvious typo — but the current default contradicts the API
contract. Recommended: per-server config wins, with the gateway environment as a
fallback only for variables the server does not define. That is a behaviour
change, so it wants an explicit decision, not a silent fix.

Workaround until then: do not export an MCP's variables into the gateway's own
environment; start the gateway with them unset.

#### `GET /api/servers/{id}` returns credentials in plaintext

The response includes the full `env` map with real secret values — database
passwords, API keys — unredacted. Any holder of the bearer token can read every
MCP's credentials, and the values land in any log or terminal that captures the
response.

`GET /api/servers/{id}/instance/env` already handles this correctly (returning
`{"present": true, "masked": ...}` rather than values). The main config endpoint
should mask the same way. Not changed here because other consumers may depend on
the current response shape.

### 14.5 Pre-existing, not fixed — needs a decision

**FluidMCP cannot connect to a non-TLS MongoDB.**
[`database.py`](../fluidmcp/cli/repositories/database.py) always passes
`tlsAllowInvalidCertificates` to `AsyncIOMotorClient`. In this PyMongo version
passing any `tls*` option implies `tls=True`, so the client attempts a TLS
handshake against a plain MongoDB and fails. Reproduced against `mongo:7`:

```
mongod: "SSL handshake received but server is started without SSL support"
fluidmcp: "SSL handshake failed: [SSL: UNEXPECTED_EOF_WHILE_READING]"
```

Managed MongoDB (Railway, Atlas) uses TLS, so production is unaffected — but
local development against a plain `mongod` is impossible. Fix: only pass the
`tls*` kwargs when TLS is actually intended (e.g. gate on the URI scheme or an
explicit `FMCP_MONGODB_TLS` flag). Left alone here because it touches the
production database path and is outside the monitoring scope.

**`POST /api/servers` payload in CLAUDE.md is wrong.** The documented shape is
`{"server_id": ..., "config": {...}}`; the endpoint actually accepts a flat
object with `id`. Posting the documented form returns
`{"detail":"Server id is required"}`.

**Pre-existing test collection error.** `tests/test_validators.py` fails to
import (`NameError: AddServerFromGitHubRequest`) on a clean checkout, before any
change in this work.

**`tests/test_serve_api.py` and `tests/test_serve_e2e.py` hang.** Both time out
on a clean checkout as well; they appear to start a real server and never
terminate. Excluded from suite runs here.

**Two crash-endpoint tests fail on a clean checkout.**
`test_debug_api_crashes_stderr.py::test_empty_crashes_for_known_server` and
`::test_crashes_per_hour_counts_recent` fail before any change here. Not
investigated — outside scope.

### 14.6 Test hygiene fixed in passing

`test_debug_aggregator.py` and `test_debug_api_crashes_stderr.py` used the
deprecated `asyncio.get_event_loop()` pattern, which only works when an earlier
test happens to leave a current event loop on the main thread. Adding async tests
made that latent dependency manifest — though the same failure reproduces on a
clean checkout by running any pre-existing async test file first, e.g.:

```bash
pytest tests/test_crash_root_cause.py tests/test_debug_aggregator.py
# RuntimeError: There is no current event loop in thread 'MainThread'
```

Replaced five call sites with `asyncio.run()`, which creates its own loop and
carries no ordering dependency.
