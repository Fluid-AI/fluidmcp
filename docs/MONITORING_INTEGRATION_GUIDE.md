# FluidMCP → Monitoring Integration Guide

**Audience:** `gpt-voice-tester` team (monitoring repo)
**Purpose:** consume FluidMCP's health/event API to monitor a customer's MCP fleet, alert on failures, and report back to that customer's team.

> Customer-agnostic. `gateway_id` scopes every payload, so one monitoring deployment can cover many customers.

> **Availability: everything below is implemented and tested.** The `[phase Pn]`
> markers record which phase each endpoint came from; they are no longer a
> waiting list. Verified by 124 unit/API tests plus an end-to-end suite that
> breaks a real MCP's database and asserts the reported diagnosis
> (`tests/manual/monitoring/live_test.sh`, 33/33 passing).
>
> Two things to know before you start:
> - `success_streak` was added to each server entry (see §4.2).
> - `auto_restart.would_help` is `false` for unreachable dependencies — do not
>   build a retry loop on those (see §4.6).

---

## 1. Mental model

FluidMCP is the MCP process manager. It already detects crashes and restarts servers on its own with exponential backoff. **Your job is not to restart things** — it is to know what happened, decide whether a human needs to care, and tell them.

Three failure classes, and they are genuinely different:

| Class | Example | How FluidMCP sees it | Does auto-restart fix it? |
|---|---|---|---|
| **Process death** | OOM kill, segfault, crash on startup | PID gone → `server.crashed` | Usually yes |
| **Zombie** | Process alive, HTTP hung | ping timeout → `server.zombie` | Usually yes |
| **Dependency failure** | SQL connection broken, expired API key | Process perfectly healthy; **tool calls fail** | **No** — needs a human |

The third class is the one that hurts customers most, and the one that needs *you*. A restarted server with wrong DB credentials is still broken; it just restarted. Alerts for this class must route to a human with the specific remediation, not get swallowed by "FluidMCP restarted it, all good."

---

## 2. Connection

```
Base URL:  https://<fluidmcp-host>            (e.g. https://mcp.customer.example.com)
Auth:      Authorization: Bearer <FMCP_BEARER_TOKEN>
```

`/health` is unauthenticated. Everything under `/api/*` requires the bearer token when `FMCP_SECURE_MODE=true` (it is, in production).

Ask the FluidMCP team for a **read-only monitoring token** rather than the admin token. Until that exists (phase P4), you'll get the admin token — treat it as a secret with restart privileges and keep it out of logs and dashboards.

---

## 3. Recommended collection strategy

Use **both** push and pull. They fail in different ways.

```
Webhook  (push, <1s)  ──►  instant incident creation
Poll /health (30s)    ──►  state reconciliation + "is FluidMCP itself alive?"
Poll /events (30s)    ──►  gap-free event backfill if a webhook was dropped
```

### The rule that matters most

> **If a poll fails or returns stale data, that is your highest-severity alert.**

There are three distinct gateway failure modes and they need different alerts:

| Mode | How you see it | Severity |
|---|---|---|
| Gateway **down** | Poll fails / times out | P1 |
| Gateway **up but misconfigured** | Reachable, `config.errors` non-empty (§4.1b) | P1 |
| Gateway **restarted** | `boot_id` changed | P1 if no deploy was expected |

A total FluidMCP outage sends **zero** webhooks. Silence is indistinguishable from "everything is fine" unless you are actively polling. Alert if:
- `/health` is unreachable for 2 consecutive polls, **or**
- `generated_at` in the response is more than 3× your poll interval old.

---

## 4. Endpoints

### 4.1 `GET /health` — is the gateway up? **[available now]**

Unauthenticated, cheap, safe to hit every 15s.

```json
{
  "status": "healthy",
  "timestamp": "2026-09-01T10:14:02Z",
  "database": { "status": "connected", "persistence_enabled": true },
  "models": { "total": 0, "by_type": { "replicate": 0 } },
  "version": "2.0.0"
}
```

`status`: `healthy` | `degraded` | `starting`. `degraded` means the gateway is serving but MongoDB is unreachable — **crash history and events are being lost**, so raise it as a warning, not just a note.

---

### 4.1b `GET /api/monitoring/gateway` — is FluidMCP itself healthy? **[phase P0]**

`/health` tells you the gateway is *answering*. This tells you whether it is actually **configured correctly and functioning** — the redeploy-with-missing-credentials case.

```json
{
  "gateway_id": "gw-prod-1",
  "boot_id": "boot_01J8X7QK...",
  "boot_count": 47,
  "started_at": "2026-09-01T08:00:11Z",
  "uptime_seconds": 8031,
  "status": "degraded",
  "config": {
    "valid": false,
    "errors": [
      { "key": "FMCP_BEARER_TOKEN", "problem": "not set while FMCP_SECURE_MODE=true",
        "impact": "all /api requests will return 500" }
    ],
    "warnings": [
      { "key": "MONGODB_URI", "problem": "unreachable",
        "impact": "crash history and events are not persisted" }
    ]
  },
  "resources": {
    "memory_rss_bytes": 412386304, "cpu_percent": 6.2,
    "open_fds": 214, "threads": 18, "event_loop_lag_ms": 12
  },
  "servers_managed": 12
}
```

**`boot_id` is the field that matters most.** It is generated once per process start. Compare it against the previous poll:

| Observation | Meaning |
|---|---|
| `boot_id` unchanged | Same process — normal |
| `boot_id` changed | **The gateway restarted.** Deploy, crash, or container reschedule |
| `boot_id` changed + `boot_count` jumped by >1 | **Crash loop** between your polls — P1 |
| Unreachable, then new `boot_id` | It was down and came back; the gap is your outage window |

Without this you cannot distinguish a deploy from a crash, or a network blip from a restart. Store `boot_id` alongside your event cursor and reset the cursor whenever it changes.

**`config.errors` is non-empty → P1, regardless of `status`.** This is the redeploy failure mode: a container that comes up with a missing bearer token answers `/health` fine but returns 500 on every `/api` call. `/health` and this block are readable **without authentication**, which is deliberate — if the token is the thing that is broken, you cannot authenticate to find out.

`event_loop_lag_ms` above ~250 means the gateway is blocked and will start failing everything, including its own health checks. It is the only early warning for a wedged gateway.

---

### 4.2 `GET /api/monitoring/health` — fleet rollup **[phase P0]**

One call, every server. This is your primary polling endpoint.

```json
{
  "gateway_id": "gw-prod-1",
  "boot_id": "boot_01J8X7QK...",
  "generated_at": "2026-09-01T10:14:02.113Z",
  "gateway": { "status": "healthy", "uptime_seconds": 84213,
               "database": "connected", "config_valid": true },
  "summary": {
    "total": 12, "running": 9, "degraded": 1, "failed": 1,
    "stopped": 1, "unstable": 1, "crashes_last_hour": 3
  },
  "servers": [
    {
      "id": "customer-sql",
      "name": "Customer SQL MCP",
      "state": "degraded",
      "pid": 4412,
      "uptime_seconds": 3600,
      "restart_count": 2,
      "stability": "stable",
      "memory_rss_bytes": 268435456,
      "memory_usage_pct": 25.6,
      "memory_trend": "rising",
      "cpu_percent": 3.1,
      "active_requests": 0,
      "error_rate_5m": 0.83,
      "success_streak": 0,
      "failing_tools": [
        { "tool": "execute_query", "error_rate_5m": 0.94, "calls": 34,
          "last_error": "ECONNREFUSED 10.20.1.44:1433" }
      ],
      "config_issues": { "missing_env": [], "placeholder_env": ["API_KEY"] },
      "failure_category": "db_connection_refused",
      "failure_owner": "customer",
      "last_error": "ECONNREFUSED 10.20.1.44:1433",
      "last_crash": {
        "timestamp": "2026-09-01T09:02:11Z",
        "exit_code": 137,
        "exit_label": "oom_killed"
      }
    }
  ]
}
```

**`state`** — the field to drive status colours:

| State | Meaning | Dashboard |
|---|---|---|
| `running` | Alive and serving | 🟢 |
| `degraded` | Alive, but tool calls are failing | 🟠 **alert a human** |
| `restarting` | Mid-restart | 🟡 |
| `failed` | Dead, restart exhausted or failed | 🔴 |
| `stopped` | Intentionally stopped | ⚪ |
| `config_error` | Missing/placeholder env vars or unresolvable command | 🟠 **customer must fix** |
| `not_found` | Configured but never started | ⚪ |

**`stability: "unstable"`** is orthogonal to state — it means ≥5 restarts in 10 minutes. A server can be `running` *and* `unstable`. That combination is a **crash loop**: it looks fine on any single poll and is one of the highest-signal conditions on the whole dashboard. Do not let `running` mask it.

**`failing_tools[]`** — per-tool error rates. A server can sit at 12% overall error rate while one specific tool is at 94% because everything else still works. Drive per-endpoint alerts off this array, not off `error_rate_5m`, or a single broken endpoint inside a busy server will never trip a threshold.

**`last_error`** — the MCP's own error text, with credential-shaped substrings
redacted (URL userinfo, `password=`/`api_key:` values, `Bearer` tokens, JWTs,
`r8_`/`sk_`/`ghp_` prefixes). Classification runs against the raw text, so
accuracy is unaffected. Safe to display and to forward to a customer — with one
exception below.

**`success_streak`** — consecutive successful tool calls at the tail of the
window, across all of the server's tools. A degraded server clears once this
reaches 5 (`FMCP_RECOVERY_STREAK`) *and* no tool is above the error threshold.
Recovery is judged on this streak rather than on the window-wide error rate:
rate-based recovery is pathologically sticky, because historical failures stay
inside the window and keep a demonstrably-working server flagged for minutes.
Treat a rising streak on a degraded server as "recovering".

**`config_issues`** — env vars that are missing or still hold placeholder values (`<YOUR_KEY>`, `your-...`, `xxxx`). Key names only; values are never returned. Non-empty means a human must set something.

**`failure_owner`** — `customer` (the customer must act: credentials, firewall, DB), `fluidmcp` (our bug), `external` (upstream vendor), `unknown`. Use it to route: `customer` → that customer's team, everything else → FluidMCP team.

---

### 4.3 `GET /api/monitoring/events` — incremental feed **[phase P0]**

```
GET /api/monitoring/events?since=10432&limit=100&severity=warning
```

| Param | Notes |
|---|---|
| `since` | Last `seq` you processed. Omit for the most recent `limit` events. |
| `limit` | 1–500, default 100 |
| `severity` | `info` \| `warning` \| `critical` — returns this level and above |
| `server_id` | Filter to one server |
| `type` | Filter by event type |

```json
{
  "gateway_id": "gw-prod-1",
  "generated_at": "2026-09-01T10:14:02Z",
  "latest_seq": 10437,
  "events": [
    {
      "event_id": "evt_01J8X...",
      "seq": 10433,
      "type": "server.crashed",
      "severity": "critical",
      "server_id": "customer-sql",
      "server_name": "Customer SQL MCP",
      "timestamp": "2026-09-01T10:13:58.442Z",
      "data": {
        "exit_code": 137,
        "exit_category": "resource",
        "exit_label": "oom_killed",
        "exit_description": "Killed by OS (likely OOM) — check memory limits",
        "uptime_seconds": 412.5,
        "memory_bytes_at_crash": 1073741824,
        "stderr_tail": "...",
        "failure_category": "oom",
        "failure_owner": "fluidmcp",
        "remediation": "Increase memory_limit_mb or investigate the memory leak."
      }
    }
  ]
}
```

**Persist `latest_seq` after each successful batch.** `seq` is a gap-free monotonic counter per gateway:

- `events[0].seq > your_cursor + 1` → you missed events. They are still in Mongo; re-request from your cursor.
- `latest_seq < your_cursor` → **the gateway restarted and reset its counter.** Reset your cursor to 0 and re-sync. The authoritative signal is a changed `boot_id` (§4.1b) — key your cursor on `(gateway_id, boot_id)` so a restart resets it automatically. Handle this explicitly; otherwise you will silently stop ingesting events after every FluidMCP deploy.

Never use timestamps as a cursor — same-millisecond writes and clock skew cause silent loss.

---

### 4.4 `GET /api/monitoring/stream` — SSE live feed **[phase P1]**

```
GET /api/monitoring/stream?severity=warning
Accept: text/event-stream
```

```
event: server.crashed
data: {"event_id":"evt_01J8X...","seq":10433,...}

: heartbeat
```

Same envelope as `/events`. A `: heartbeat` comment arrives every 15s — if none arrives for 45s, reconnect. Reconnect with exponential backoff, and **on reconnect always backfill via `/events?since=<cursor>`**; the stream does not replay what you missed while disconnected.

Good for a live dashboard. Do not use it as your only ingestion path.

---

### 4.5 Webhooks — push alerts **[phase P1]**

Register once:

```bash
curl -X POST https://<host>/api/monitoring/webhooks \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "url": "https://monitor.internal/hooks/fluidmcp",
    "events": ["server.crashed", "server.unstable", "server.dependency_failed",
               "server.restart_failed", "resource.memory_killed"],
    "secret": "whsec_generate_your_own"
  }'
```

Delivery headers:

```
X-FMCP-Event: server.crashed
X-FMCP-Delivery: dlv_01J8X...
X-FMCP-Timestamp: 1756721642
X-FMCP-Signature: sha256=<hmac_sha256(secret, raw_body)>
```

**Always verify the signature** — the receiver is internet-reachable and this endpoint creates incidents.

```python
import hmac, hashlib, time

def verify(raw_body: bytes, signature: str, timestamp: str, secret: str) -> bool:
    if abs(time.time() - int(timestamp)) > 300:      # replay window
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

Body is a single event object, identical to an `/events` entry.

**Return 2xx fast.** FluidMCP retries 3× with backoff (2s/8s/32s) and auto-disables the receiver after 10 consecutive failures. Enqueue and process asynchronously; never do alert routing inline in the handler.

Deliveries are **at-least-once** — deduplicate on `event_id`.

Test it: `POST /api/monitoring/webhooks/{id}/test`.

---

### 4.6 `GET /api/monitoring/servers/{id}/diagnosis` — why is it down **[phase P2]**

Call this when opening an incident. It is the "what do I tell the customer" endpoint.

```json
{
  "server_id": "customer-sql",
  "state": "degraded",
  "diagnosis": {
    "failure_category": "db_connection_refused",
    "owner": "customer",
    "confidence": "high",
    "summary": "The MCP process is healthy but every tool call fails to reach the SQL server at 10.20.1.44:1433.",
    "remediation": "Verify the SQL Server is running and reachable from the FluidMCP host. Check firewall rules and the DB_HOST/DB_PORT env vars for this server.",
    "evidence": [
      { "source": "tool_error", "tool": "execute_query", "count": 14,
        "sample": "ECONNREFUSED 10.20.1.44:1433" },
      { "source": "stderr", "line": "Error: connect ECONNREFUSED 10.20.1.44:1433" }
    ]
  },
  "error_rate_5m": 0.93,
  "recent_crashes": [],
  "auto_restart": {
    "attempted": false,
    "restart_count": 0,
    "would_help": false,
    "reason": "Restarting will not fix this. The fault is outside the process — a credential, a configuration value, or an unreachable dependency — so FluidMCP does not restart automatically. A restart loop here only hides the cause."
  }
}
```

`summary` + `remediation` are written to be pasted directly into a ticket or a message to the customer.

**`auto_restart.would_help` should gate any retry UI you build.** It is `false`
for credentials, configuration, unreachable dependencies, upstream 5xx and rate
limiting — restarting the MCP changes nothing there, and a restart loop buries
the real cause. It is `true` for genuine process-level faults and for
connection-pool exhaustion, where a restart really does clear the condition. Do
not offer a one-click restart when this is `false`; show the remediation.

---

### 4.7 `GET /api/monitoring/uptime` — SLA reporting **[phase P3]**

```
GET /api/monitoring/uptime?window=24h        # 1h | 24h | 7d | 30d
```

```json
{
  "window": "24h",
  "servers": [
    { "server_id": "customer-sql", "uptime_pct": 97.42, "downtime_seconds": 2228,
      "crash_count": 3, "restart_count": 3, "mttr_seconds": 742,
      "mtbf_seconds": 28800, "degraded_seconds": 1180 }
  ],
  "fleet": { "uptime_pct": 99.1, "total_crashes": 5, "servers_with_incidents": 2 }
}
```

Feeds the weekly customer report. Note `degraded_seconds` is tracked separately from downtime — a server that was up but unusable is not "uptime" as far as the customer is concerned, and reporting it as such will get challenged.

---

### 4.8 Control endpoints **[available now]**

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/servers/{id}/restart` | Manual restart |
| `POST` | `/api/servers/{id}/start` \| `/stop` | |
| `POST` | `/api/servers/start-all` \| `/stop-all` | |
| `GET` | `/api/servers/{id}/stderr?lines=100&contains=error` | Raw log tail — **not redacted**, see note |
| `GET` | `/api/servers/{id}/debug` | Per-server aggregator (status+resources+crashes+stderr) |
| `GET` | `/api/servers/{id}/crashes?limit=20` | Crash history |

> **`/stderr` and `/crashes` return raw, unredacted MCP output.** Everything
> under `/api/monitoring/*` scrubs credential-shaped text before returning it;
> these two older endpoints do not, because they exist to show exactly what the
> process printed. Treat their output as potentially containing secrets: do not
> forward it to a customer channel or store it unfiltered alongside redacted
> data. Prefer `/monitoring/servers/{id}/diagnosis`, whose evidence is redacted.

Expose restart in the dashboard as an **operator-triggered** action only. Do not build an auto-restart loop in the monitoring repo — FluidMCP already has one with backoff and storm detection, and a second uncoordinated loop will fight it and mask the underlying fault.

---

## 5. Building without the monitoring endpoints

Everything in §4.8 plus `/api/servers` exists today. A functional dashboard is buildable right now:

```python
async def poll_fleet(base, token):
    h = {"Authorization": f"Bearer {token}"}
    servers = (await client.get(f"{base}/api/servers", headers=h)).json()
    out = []
    for s in servers:
        d = (await client.get(
            f"{base}/api/servers/{s['id']}/debug?stderr_lines=20", headers=h
        )).json()
        out.append({
            "id": s["id"],
            "state": d["status"]["state"],
            "stability": d["status"].get("stability"),
            "restart_count": d["status"].get("restart_count", 0),
            "crashes_per_hour": d["crashes"]["crashes_per_hour"],
            "memory_trend": d["resources"]["memory_trend"],
            "last_crash": (d["crashes"]["events"] or [None])[0],
            "stderr": d["stderr"]["lines"],
        })
    return out
```

Cost: N+1 requests per cycle. `/api/monitoring/health` (§4.2) does all of this in
one call and adds error rates, failure classification and config issues — prefer
it. This section is kept only as a fallback for a gateway running an older build.

On an older build without `boot_id`, approximate restart detection by watching
for `uptime_seconds` resetting across all servers at once. On a current build,
use `boot_id` (§4.1b) — it is unambiguous.

You can also scrape `GET /metrics` (Prometheus) today — `fluidmcp_server_status`, `fluidmcp_server_restarts_total`, `fluidmcp_server_uptime_seconds`, `fluidmcp_server_memory_rss_bytes`, `fluidmcp_tool_calls_total`, `fluidmcp_errors_total`. See [MONITORING.md](MONITORING.md).

---

## 6. Alert rules

| Condition | Severity | Route | Why |
|---|---|---|---|
| `/health` unreachable ×2, or `generated_at` stale | **P1** | FluidMCP oncall | Total outage; no webhooks will fire |
| `config.errors` non-empty on `/api/monitoring/gateway` | **P1** | FluidMCP oncall | Misconfigured deploy — gateway is up but broken |
| `boot_id` changed unexpectedly (no deploy) | **P1** | FluidMCP oncall | Gateway crashed and restarted |
| `boot_count` jumped >1 between polls | **P1** | FluidMCP oncall | Gateway crash-looping |
| `state: config_error` or `config_issues` non-empty | **P1** | customer team | Missing creds — will never work until set |
| Any `failing_tools[].error_rate_5m > 0.5` | **P2** | route by `failure_owner` | One endpoint broken inside a healthy server |
| `event_loop_lag_ms > 250` sustained | **P2** | FluidMCP oncall | Gateway wedging; will fail everything soon |
| `state: failed` and restart exhausted | **P1** | FluidMCP + customer | Server is down and not coming back |
| `stability: unstable` | **P1** | FluidMCP | Crash loop — collapse per-crash alerts into one incident |
| `failure_owner: customer` | **P1** | **customer team** | Only the customer can fix it; include `remediation` verbatim |
| `state: degraded` > 5 min | **P2** | route by `failure_owner` | Alive but failing calls |
| `database.status != connected` | **P2** | FluidMCP | History is being lost right now |
| `memory_trend: rising` + `memory_usage_pct > 85` | **P3** | FluidMCP | Predicts the next OOM |
| `crashes_last_hour > 3` on one server | **P2** | FluidMCP | Chronic instability |
| Single crash, auto-restart succeeded | **info** | log only | FluidMCP handled it — do not page |

**Suppression rules that will save you from alert fatigue:**
- Suppress `server.crashed` for 10 minutes after `server.unstable` fires for that server — a crash loop is one incident, not fifteen.
- Suppress everything per-server while the gateway itself is down; a gateway outage is one alert.
- Auto-resolve on `server.recovered`.

---

## 7. Dashboard

**Gateway health strip** — always visible, top of every view:
- 🟢/🔴 **FluidMCP is up / down** — driven by poll success, not by any field in the response
- Uptime since `started_at`, `boot_count`, and a marker whenever `boot_id` changes
- Config validity badge — red with the offending key names when `config.errors` is non-empty
- DB connection state, event-loop lag, `generated_at` freshness

Treat gateway-down as a distinct visual state that greys out the whole server grid. A stale grid rendered as if it were live is worse than no grid — it reports every server as last-known-good while the gateway is dead.

**Fleet overview** — the 5-second glance:
- Status tiles: total / running / degraded / config_error / failed / unstable
- Server grid: name, state pill, uptime, restarts (24h), error rate, memory trend arrow
- Live event feed (SSE), severity-coloured

**Server detail** — drill-down on click:
- State timeline (running / degraded / down bands over 24h)
- Memory + CPU sparklines with limit lines
- Per-tool error rates table (`failing_tools`) — sorted by error rate, so a single broken endpoint is obvious
- Config issues panel — missing/placeholder env var names
- Crash table: timestamp, exit label, uptime before crash, stderr excerpt
- Current diagnosis card (`summary` + `remediation` + evidence)
- stderr tail with a filter box
- Restart button (operator action, confirm dialog)

**Customer report view** — weekly, exportable:
- Uptime % per server vs target, with `degraded_seconds` shown separately
- Incident list with cause, owner, and duration
- Failures split by `failure_owner` — this is the chart that ends the "whose fault is it" conversation
- Top recurring `failure_category` values with remediation status

For chart styling, the monitoring repo's existing conventions apply; the important content decision is keeping **degraded** visually distinct from **down** everywhere, since conflating them is what makes uptime numbers get disputed.

---

## 8. Reference

### Event types

| Type | Severity | Meaning |
|---|---|---|
| `server.started` | info | Started successfully |
| `server.stopped` | info | Intentional stop |
| `server.crashed` | critical | Process died unexpectedly |
| `server.restarting` | warning | Restart attempt beginning |
| `server.restarted` | info | Restart succeeded |
| `server.restart_failed` | critical | Restart failed / max restarts reached |
| `server.unstable` | critical | ≥5 restarts in 10 min — crash loop |
| `server.recovered` | info | Back to healthy |
| `server.zombie` | critical | PID alive, HTTP unresponsive |
| `server.degraded` | warning | Tool error rate above threshold |
| `server.dependency_failed` | critical | Downstream (SQL/API) unreachable |
| `resource.memory_warning` | warning | ≥90% of memory limit |
| `resource.memory_killed` | critical | Killed at ≥98% of limit |
| `resource.cpu_stuck` | warning | Pegged CPU for 3 cycles |
| `server.config_invalid` | critical | Missing/placeholder env vars or bad command — customer must fix |
| `gateway.config_invalid` | critical | FluidMCP itself misconfigured (bad Mongo URI, missing token) |
| `gateway.started` / `gateway.stopping` | info | Gateway lifecycle |

### `failure_category` values

`oom` · `segfault` · `command_not_found` · `permission_denied` · `missing_dependency` · `db_connection_refused` · `db_auth_failed` · `db_pool_exhausted` · `tls_failure` · `upstream_auth_failed` · `upstream_5xx` · `upstream_timeout` · `rate_limited` · `missing_credentials` · `invalid_config` · `unknown`

### Exit codes

| Code | Label | Meaning |
|---|---|---|
| 0 | `clean_exit` | Normal |
| 1 | `generic_error` | Unhandled error |
| 126 | `permission_denied` | Not executable |
| 127 | `command_not_found` | Binary missing |
| 137 | `oom_killed` | OS killed it (OOM) |
| 139 | `segfault` | Segmentation fault |
| 143 | `sigterm_container` | Container runtime stop |
| -1 | `killed_by_fluidmcp` | Resource monitor kill |
| -9 | `sigkill` | Force-killed |
| -15 | `sigterm` | Graceful shutdown |

### FluidMCP-side defaults worth knowing

| Setting | Default | Effect on you |
|---|---|---|
| `FMCP_HEALTH_CHECK_INTERVAL` | 30s | Max crash detection latency |
| `FMCP_HTTP_PING_TIMEOUT` | 10s | Zombie detection threshold |
| `FMCP_RESTART_STORM_THRESHOLD` | 5 / 10 min | When `unstable` fires |
| `FMCP_MEMORY_KILL_PCT` | 98% | When FluidMCP kills for memory |
| `FMCP_EVENT_RETENTION_DAYS` | 30 | **Persist events on your side before this expires** |

---

## 9. Acceptance checklist — how to confirm it works

Run through this against a real deployment. Each step names the exact thing to
look at, so a "yes" is unambiguous.

### A. Gateway is being watched at all

```bash
curl -s $BASE/health | jq '{status, boot_id, boot_count, config}'
```

- [ ] `boot_id` present. **Write it down** — you compare against it later.
- [ ] `config.valid` is `true` (or `config.errors` names something you expect).
- [ ] `curl -s -o /dev/null -w '%{http_code}' $BASE/health/ready` returns `200`.

Then **stop the gateway** and confirm your monitoring reacts:

- [ ] Poll fails → your dashboard shows FluidMCP **down**, not "all servers healthy".
- [ ] A **P1** alert fires within two poll intervals.

Restart it and:

- [ ] `boot_id` has **changed** → your collector logged "gateway restarted".
- [ ] `boot_count` incremented.
- [ ] Your event cursor reset (it is keyed on `boot_id`) and no events were double-counted.

> This is the single most important step. Everything else assumes the gateway is
> reachable; only this one covers the case where it is not.

### B. Fleet rollup reflects reality

```bash
curl -s $BASE/api/monitoring/health | jq '{summary, ids: [.servers[].id]}'
```

- [ ] Every MCP you expect appears, with the state you expect.
- [ ] `summary` counts add up to `total`.
- [ ] Response arrives in well under a second.

### C. A real crash is caught, classified, restarted

Kill one MCP's process directly:

```bash
PID=$(curl -s $BASE/api/monitoring/health | jq -r '.servers[0].pid')
kill -9 $PID
```

Within ~2× `FMCP_HEALTH_CHECK_INTERVAL` (default 30s → allow 60s):

- [ ] `server.crashed` in `/api/monitoring/events?severity=critical`, with
      `exit_label: "sigkill"`.
- [ ] `server.restarting` then `server.restarted` follow.
- [ ] The server is back to `running` in the rollup, with `restart_count` incremented.
- [ ] Your webhook receiver got the crash delivery, and the HMAC signature verified.

### D. A broken dependency is caught — the important one

This is the case no process-level check can see, so test it deliberately.
Break the MCP's actual dependency **without touching the process** — block the
database port, revoke the credential, or stop the upstream:

```bash
# example: make the DB unreachable from the FluidMCP host
sudo iptables -A OUTPUT -p tcp --dport 1433 -j REJECT
```

Then call the affected tool 5+ times and wait one monitor cycle:

- [ ] `process_state` is still `running` — proving the process is fine.
- [ ] `state` is `degraded`.
- [ ] `failing_tools` names the specific tool.
- [ ] `failure_category` is a `db_*` / `upstream_*` value, not `unknown`.
- [ ] `failure_owner` is `customer`.
- [ ] `/servers/{id}/diagnosis` gives a `summary` and `remediation` you would
      actually be willing to send to the customer.
- [ ] `auto_restart.would_help` is `false`, and your UI does **not** offer a restart.

Undo the break, call the tool ~6 more times:

- [ ] `success_streak` climbs, then `state` returns to `running`.
- [ ] `server.recovered` is emitted and your incident auto-resolves.

**If `failure_category` comes back `unknown`, that is the one thing to report.**
It means your MCP's error text is not in the pattern catalog. Send the exact
error string and it gets added to
[`failure_patterns.py`](../fluidmcp/cli/services/failure_patterns.py) — or add it
yourself via `FMCP_FAILURE_PATTERNS_FILE`.

### E. Missing credentials are caught before first use

Register an MCP with a deliberately missing or placeholder credential, and start it:

- [ ] `server.config_invalid` event emitted **at start**, not at first tool call.
- [ ] `config_issues.missing_env` / `placeholder_env` name the keys.
- [ ] **No credential *values* appear anywhere** in the response. Grep for the
      real secret to be sure.
- [ ] `failure_owner` is `customer` and the remediation names the keys to set.

### F. Event delivery is lossless

- [ ] Record your cursor, generate 3 events, poll with `since=<cursor>` → exactly 3.
- [ ] Poll again with the new cursor → `returned: 0`. No re-delivery.
- [ ] `seq` values are strictly ascending with no gaps.
- [ ] Stop your receiver, generate events, restart it, backfill via
      `/events?since=<cursor>` → nothing was lost.
- [ ] Send the same `event_id` twice → your store deduplicates.

### G. Alert routing is right

- [ ] A `failure_owner: customer` event reaches the customer path, and includes
      the `remediation` text verbatim.
- [ ] Everything else reaches the FluidMCP path.
- [ ] A flapping server produces **one** `server.unstable` incident, not one
      alert per crash.
- [ ] A single crash that auto-restarted successfully does **not** page anyone.

### What to report back

If something here fails, the useful bundle is:

```bash
curl -s $BASE/api/monitoring/gateway > gateway.json
curl -s $BASE/api/monitoring/health  > fleet.json
curl -s "$BASE/api/monitoring/events?limit=200" > events.json
curl -s $BASE/api/monitoring/servers/<id>/diagnosis > diagnosis.json
curl -s "$BASE/api/servers/<id>/stderr?lines=100" > stderr.json
```

Those five files contain everything needed to diagnose a monitoring gap. Check
`stderr.json` for credentials before sharing it — the others redact by design,
but raw stderr is whatever the MCP printed.

---

## 10. Open questions for the two teams

1. **Probe configuration** — dependency probes (§4.6) need a cheap, side-effect-free tool per MCP (e.g. `SELECT 1`). Who enumerates those per customer, and are they safe to run every 2 minutes against a production DB?
2. **Escalation path** — does `failure_owner: customer` page the customer directly, or land in a queue a FluidMCP engineer triages first?
3. **Multi-deployment** — one FluidMCP gateway per customer, or several? `gateway_id` is in every payload; confirm whether the dashboard needs to aggregate across them.
4. **Retention** — 30 days on the FluidMCP side. How long does the monitoring repo need to keep events for SLA reporting?
5. **Uptime target** — what number is each customer actually being held to, and does `degraded` time count against it? This decides how §4.7 is presented.
