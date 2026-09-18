# Spec: MCP Server Startup Should Not Silently Crash-Loop on Missing Env Vars

**Branch:** TBD
**Status:** Draft

---

## 1. Context and Problem Statement

In `fmcp serve` mode (Railway / REST-managed servers), adding and starting an MCP
server does **not** validate that required environment variables are set. The
request appears to succeed — the API returns a PID — but if the underlying
command needs a missing env var, the subprocess dies almost immediately.
FluidMCP then silently auto-restarts it up to `max_restarts` (default 3) times
with exponential backoff, each attempt failing identically, before giving up
and marking the server `"failed"`. The user has to read `last_error` / a raw
stderr trail to figure out that the real cause was a missing API key.

This is not a "should we allow starting without all envs?" question — it
already allows it, just badly. The actual gaps are:

1. No upfront signal that required env vars are missing, at Add time or Start time.
2. No real required/optional distinction in the `fmcp serve` REST path — every
   env key present in a server's config is unconditionally treated as required
   (`fluidmcp/cli/api/management.py:2167`), even though the CLI/package-install
   path (`fluidmcp/cli/services/env_manager.py`) already supports a proper
   per-key `required: bool` in `metadata.json`.
3. Wasted restart cycles: if the failure is caused by an env var we already
   know is missing, retrying 3 times with backoff is pure noise — the outcome
   can't change without user intervention.
4. `last_error` is whatever the subprocess happened to print to stderr, not a
   FluidMCP-generated, actionable message.

## 2. Current Behavior (End-to-End Trace, Verified)

| Step | Code | Behavior |
|---|---|---|
| Add server | `management.py:716` `add_server()` | Only checks `id`/`name` presence (`:753-757`) and runs `validate_server_config()` (injection/security checks). Env values — including empty strings or placeholders like `"YOUR_API_KEY_HERE"` — are accepted and stored as-is. |
| Frontend Add modal | `AddServerModal.tsx:122-180` | Section is explicitly labeled "Environment Variables (optional)". Free-form key/value rows, no required marking, nothing blocks submission. |
| Frontend submit | `AddServerModal.tsx:299-308` | `disabled={connecting}` is the only gate — no field validation. |
| Start server | `management.py:1395` `start_server()` | Checks the server exists and isn't already running/disabled. No env completeness check. |
| Spawn | `server_manager.py:806` `_spawn_mcp_process()`, env merge at `:968-972` | `for key, value in env_vars.items(): if key not in env and value and not self._is_placeholder(value): env[key] = value` — missing/empty/placeholder values are silently **dropped**, never flagged. `subprocess.Popen` is called regardless. |
| Crash | subprocess exits non-zero almost immediately | — |
| Auto-restart | `server_manager.py:1867-1895` (`_handle_process_exit`-style path) and `:2049-2226` (`trigger_restart`) | `restart_policy` defaults to `"on-failure"`, `max_restarts` defaults to `3` (`management.py:945-946`, `server_manager.py:1868`). Retries with exponential backoff, identical failure each time. |
| Final state | — | Server lands in `status: "failed"` with `server.error` populated from whatever the subprocess printed. Already surfaced in the UI at `ServerListPanel.tsx:187-194`, with a "Retry" button at `:210-215` — but the message itself is raw, not diagnosed. |
| Env metadata query | `management.py:2125-2183` `get_server_instance_env()` | Line `2167`: `"required": True,  # All env vars in config are considered required` — hardcoded for every key in `config.get("env", {})`, regardless of whether that key is actually needed by the server at runtime. |
| Contrast: CLI/registry path | `env_manager.py:59-80`, `:228-242` | Registry packages carry structured `env: {KEY: {value, required, description}}` in `metadata.json`, and `edit-env` / install-time prompts already respect a real per-key `required` flag. This richer schema is never passed through the flat `env: {KEY: value}` shape used by the `fmcp serve` REST API. |

## 3. Goals

- Keep servers startable with incomplete env configuration (don't hard-block —
  some tools on a server may not need every key; users often wire up secrets
  incrementally).
- Give the user an honest, upfront signal about which env vars are missing and
  whether they're required, both when adding a server and before/at start.
- Stop burning 3 identical restart attempts when the cause is a known-missing
  required env var.
- Turn `last_error` into something a user can act on without reading raw
  stderr, when the failure is plausibly env-related.

## Non-Goals

- Do not attempt to infer which env vars a given `npx`/arbitrary command
  actually needs from its source — the signal is limited to what's already
  observable (unfilled placeholder values) plus an optional explicit flag.
- Do not change the CLI/registry `metadata.json` required-flag behavior
  (`env_manager.py`) — it already works correctly for that path.
- Not building a generic "MCP server health diagnostics" system — scope is
  limited to the env-completeness signal.

**Note on real-world `metadata.json` data (confirmed 2026-09-18):** cloned
private-repo servers usually look like the image-enhancement-mcp example —
flat `"env": {"REPLICATE_API_TOKEN": "your_replicate_api_token_here"}`, no
`required` field at all. Only some (e.g. the ONGC sql-executor-mcp) use the
structured `{description, required}` form. A design that only reacts to an
explicit `required: true` would do nothing for most real servers. So the
primary signal for 4.1-4.4 is the **placeholder heuristic** (`_is_placeholder()`,
already in `server_manager.py:1592`, matching values like
`"your_..._here"`/empty strings) — it needs zero metadata changes and works
today. An explicit `required` flag, when present, is a stronger override on
top of it (e.g. a required key with a *real-looking* but still wrong value
wouldn't be caught by the placeholder check alone).

## 4. Proposed Design

Each numbered item below is sized to be its own PR. They're ordered so each
one ships independent, verifiable value without waiting on the others —
earlier PRs don't assume later ones exist.

### PR 1 — Fail fast + actionable error, using the existing placeholder check (backend only)

**No schema or API shape changes.** In the crash/auto-restart path
(`server_manager.py`, restart logic at `:1867-1895` and `:2049-2226`), before
scheduling a restart: re-check `env_vars` for the server's config against
`_is_placeholder()` (`:1592`, already handles `"your_..._here"`/empty). If any
config env key is currently unset/placeholder, skip the retry loop entirely —
go straight to `status: "failed"` — and set `last_error` to a
FluidMCP-generated message: `"Server exited immediately; unfilled environment
variable(s): REPLICATE_API_TOKEN, GEMINI_API_KEY — check server config"`.
If no env looks unfilled, keep today's behavior (retry as normal, raw stderr
in `last_error`) — this only changes outcomes for the case we can actually
diagnose.

This is the highest-value, lowest-risk PR: it fixes the exact crash-loop
scenario in the two screenshots (image-enhancement-mcp with untouched
`"your_replicate_api_token_here"` placeholders) without needing anyone to
have annotated anything. **Start here.**

### PR 2 — Surface the same signal at add/start time, not just after a crash

Add a small helper (e.g. `get_unfilled_env(config) -> list[str]`, reusing the
same `_is_placeholder` check from PR 1) and call it from `add_server`
(`management.py:716`) and `start_server` (`:1395`). Include it in both
responses:

```json
{
  "message": "Server 'weather' configured successfully",
  "id": "weather",
  "unfilled_env": ["OPENWEATHER_API_KEY"]
}
```

Non-blocking — server is still added/started either way. This lets the
frontend warn *before* the user hits a failure at all, instead of only after
PR 1's fail-fast kicks in.

### PR 3 — Frontend: surface `unfilled_env` in the Add modal and server list

- `AddServerModal.tsx`: after a successful add, if the response has
  `unfilled_env`, show an inline warning ("2 env vars still need real
  values: ..., ...") instead of just closing the modal.
- `ServerListPanel.tsx`: add an amber "needs config" badge (distinct from the
  red `"failed"` state at `:187-194`) driven by the same field, fetched via
  `GET /servers/{id}/instance/env` or a lightweight status field — whichever
  is cheaper to wire up given how `servers` state is already loaded.

Depends on PR 2 for the data; no backend changes of its own.

### PR 4 — Optional explicit `required` flag as a stronger override

Only worth doing once PR 1-3 are in and it's clear the placeholder heuristic
isn't catching everything (e.g. a required key gets a real-looking but wrong
value). Extend `env` values to optionally be
`{value, required, description}` objects (plain strings still mean
"unknown/optional", matching today), fix `get_server_instance_env()`
(`management.py:2167`) to read the real flag instead of hardcoding `True`,
and add the "Required" toggle to `AddServerModal.tsx` (`:143-174`) and
`ServerEnvForm.tsx` (`:64` already has the right conditional, it just needs
real data). Since most cloned `metadata.json` won't set this, treat its
absence as "unknown" (no warning), not "required."

## 5. API Changes Summary

| Endpoint | Change | PR |
|---|---|---|
| Crash/restart internals | Fail-fast + diagnosed `last_error` when placeholder env detected | 1 |
| `POST /api/servers` (`add_server`) | Response includes `unfilled_env: string[]` | 2 |
| `POST /api/servers/{id}/start` (`start_server`) | Response includes `unfilled_env: string[]` | 2 |
| `POST /api/servers` — request body | Accept `env` values as `string \| {value, required?, description?}` | 4 |
| `GET /api/servers/{id}/instance/env` | `required` reflects the stored flag instead of hardcoded `True` | 4 |

## 6. Open Questions (need a decision before implementation)

- **Should PR 1's fail-fast apply retroactively** to servers already in a
  crash-loop, or only to newly-started ones? (Probably: the check runs at
  restart-decision time regardless of when the server was added, so it
  applies immediately — flag if that's not desired.)
- **Should a hard-block mode exist at all** (e.g. an opt-in strict setting for
  production deployments that refuses to start with unfilled env)? This spec
  assumes soft-warn-only throughout; flag if that's wrong for the Railway
  deployment case specifically.
- For PR 4: is the explicit `required` flag worth building at all given how
  rarely real `metadata.json` files set it, or should effort instead go into
  a better placeholder-pattern list (e.g. catching more template conventions
  than just `your_..._here`)?

## 7. Acceptance Criteria

**PR 1:** A server whose config env contains only placeholder/empty values
fails immediately on first crash (no 3x retry/backoff) with a `last_error`
naming the specific unfilled key(s). A server whose env looks filled in but
still crashes retains today's retry behavior and raw-stderr `last_error`.

**PR 2:** `add_server` and `start_server` responses include `unfilled_env`
matching PR 1's detection logic; existing callers ignoring the new field are
unaffected.

**PR 3:** The Add-server flow and server list visibly flag unfilled env vars
without blocking add/start.

**PR 4:** `GET /servers/{id}/instance/env` reflects a real per-key `required`
value when declared; keys without it behave as before (no regression for the
common no-`required` case confirmed in the screenshots above).

## 8. Out of Scope

- CLI (`fluidmcp install` / `edit-env`) — already correct via `env_manager.py`,
  untouched.
- Automatic detection of which env vars a command needs beyond placeholder
  pattern matching.
- Any change to `restart_policy`/`max_restarts` semantics for crashes that
  aren't diagnosed as env-related.
