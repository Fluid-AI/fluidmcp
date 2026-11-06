# REST Proxy Servers

A REST proxy is a plain HTTP pass-through hosted by FluidMCP. It has no tools and does not speak JSON-RPC. FluidMCP forwards every request under `/{name}/` to a configured target and returns the upstream response unchanged.

Use it when a system can only reach the FluidMCP gateway, for example a customer network that whitelists only the gateway URL, and needs to call an external API such as WhatsApp (Gupshup) through it.

```
caller ──▶ https://<gateway>/gupshup-chat/wa/api/v1/msg?x=1
                 │  FluidMCP REST proxy
                 ▼
           https://media.gupshup.com/wa/api/v1/msg?x=1  ──▶ response returned as-is
```

## Configuration

### With a config file (`fmcp run`)

Add a `restServers` section. It can sit next to `mcpServers` and `llmModels`, or be the only section.

```json
{
  "mcpServers": {},
  "restServers": {
    "gupshup-chat": {
      "type": "rest-proxy",
      "target-rest-endpoint": "media.gupshup.com"
    }
  }
}
```

```bash
fmcp validate examples/rest-proxy-config.json --file
fmcp run examples/rest-proxy-config.json --file --start-server --secure --token "$FMCP_BEARER_TOKEN"
```

| Field | Required | Description |
|---|---|---|
| key (`gupshup-chat`) | yes | The first path segment, `/{name}/`. 1–64 letters, digits, `_` or `-`, starting with a letter or digit. |
| `type` | yes | Must be `"rest-proxy"`. |
| `target-rest-endpoint` | yes | Target host or URL. A bare host (`media.gupshup.com`) means `https://`. A base path is allowed (`https://api.example.com/v1`). No username/password, query string or fragment. |

No other fields are accepted.

**Names that can't be used:**
- names reserved by FluidMCP: `api`, `ui`, `llm`, `health`, `metrics`, `docs`, `redoc`, `status`, `servers`, `documentation`, `inspector`, plus the first path segment of any other route the running gateway serves. At startup, a proxy that would hide one of those routes is logged as an error and not started;
- any name already used by an MCP server. REST proxy routes are matched first, so the MCP server would become unreachable.

### On the hosted gateway (`fmcp serve`)

`fmcp serve` has no config file. Manage REST proxies with the management API, using the admin token in `Authorization`. They are stored in MongoDB (collection `fluidmcp_rest_servers`) and reloaded on restart. A change takes effect on the next request; there is no start or stop step.

```bash
# Add
curl -X POST https://<gateway>/api/rest-servers \
  -H "Authorization: Bearer $FMCP_BEARER_TOKEN" -H "Content-Type: application/json" \
  -d '{"id": "gupshup-chat", "type": "rest-proxy", "target-rest-endpoint": "media.gupshup.com"}'

# List / get
curl https://<gateway>/api/rest-servers -H "Authorization: Bearer $FMCP_BEARER_TOKEN"
curl https://<gateway>/api/rest-servers/gupshup-chat -H "Authorization: Bearer $FMCP_BEARER_TOKEN"

# Change the target
curl -X PUT https://<gateway>/api/rest-servers/gupshup-chat \
  -H "Authorization: Bearer $FMCP_BEARER_TOKEN" -H "Content-Type: application/json" \
  -d '{"type": "rest-proxy", "target-rest-endpoint": "https://media.gupshup.com"}'

# Delete
curl -X DELETE https://<gateway>/api/rest-servers/gupshup-chat -H "Authorization: Bearer $FMCP_BEARER_TOKEN"
```

The same endpoints exist under `fmcp run`, backed by memory only. They are lost on restart.

How the API behaves:
- Responses include `persisted`. It is `true` only when the proxy will be reloaded after a restart (MongoDB); with the in-memory backend it is `false`.
- On MongoDB, a failed save or delete returns 500 and leaves the live proxy unchanged, so the gateway and the database never disagree.
- A stored proxy that failed validation at startup (it is logged and not started) can be replaced with `PUT` or `POST`, or removed with `DELETE`.
- Changes are serialized: two simultaneous adds of the same id give one 200 and one 409.
- Every add, update and delete is written to the audit log.

## Calling a REST proxy

Call the gateway exactly as you would call the target, with `/{name}` in front of the path:

```bash
curl -X POST "https://<gateway>/gupshup-chat/wa/api/v1/msg" \
  -H "FluidMCP-Authorization: Bearer $FMCP_BEARER_TOKEN" \
  -H "apikey: <gupshup api key>" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "channel=whatsapp&source=...&destination=...&message=..."
```

### Authentication (secure mode)

In secure mode (`--secure`), every proxy call needs FluidMCP's token in `FluidMCP-Authorization`.
- Both `Bearer <token>` and the bare token are accepted.
- `FluidMCP-Authorization` is never forwarded.
- The caller's `Authorization` header goes to the upstream untouched.
- A FluidMCP token sent only in `Authorization` does not authorize the call, because that header belongs to the upstream.

Without secure mode, proxy routes are open to anyone who can reach the gateway.

The token is the gateway's single bearer token. Anyone who holds it can also use the management API.

### What is forwarded

| | Behaviour |
|---|---|
| Method | Any method (GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS, …) |
| Path | Everything after `/{name}`, still percent-encoded, appended to the target. Bare `/{name}` maps to the target root. |
| Query string | Byte for byte |
| Headers | All, except `Host` (set from the target), hop-by-hop headers (`Connection` and the headers it lists, `Keep-Alive`, `TE`, `Trailer`, `Transfer-Encoding`, `Upgrade`, `Proxy-*`) and any `FluidMCP-*` header. Nothing is added: no `User-Agent`, no `Accept-Encoding`, no `X-Forwarded-*`. |
| Body | Streamed as-is. `Content-Length` is kept when the caller sent one. |
| Response | Status, headers (including repeated `Set-Cookie`) and raw body, streamed back unchanged. Compressed bodies stay compressed. Redirects are returned to the caller, not followed. |

Headers the gateway itself adds to every response:
- `Date` and `Server`. Uvicorn always adds its own, so the upstream's copies are dropped rather than sent twice.
- `Vary: Origin`, added by the CORS middleware. It only affects caching.
- `X-Trace-ID`, under `fmcp serve` only.

### Errors from FluidMCP

Errors from the upstream (its 4xx and 5xx responses) are passed through unchanged. Errors produced by FluidMCP itself carry an `X-FluidMCP-Error` header and a JSON body `{"error": "<code>", "message": "..."}`. Any `X-FluidMCP-*` or `FluidMCP-*` header sent by the upstream is removed, so an upstream error can't pass itself off as one from FluidMCP.

| Status | `X-FluidMCP-Error` | Cause |
|---|---|---|
| 401 | `unauthorized` | Secure mode and a missing or wrong `FluidMCP-Authorization` |
| 500 | `misconfigured` | Secure mode but no `FMCP_BEARER_TOKEN` on the gateway |
| 400 | `bad_path` | A `.` or `..` path segment, however it is encoded: `%2e%2e`, double-encoded `%252e%252e`, or hidden behind an encoded slash or backslash (`..%2F`, `..%5C`, `\`) |
| 502 | `upstream_unreachable` | DNS failure, connection refused, TLS error, … |
| 504 | `upstream_timeout` | No response within the timeout |

## Settings

| Variable | Default | Description |
|---|---|---|
| `FMCP_REST_PROXY_TIMEOUT` | `60` | Seconds to wait for the upstream (read/write). Connecting is limited to 10 s. |
| `MCP_ROOT_PATH` | empty | Prefix for proxy routes as well as MCP routes: `/{root}/{name}/...` |
| `MAX_REQUEST_SIZE_MB` | `10` | `fmcp serve` only: request bodies larger than this (by `Content-Length`) get 413, including proxy uploads. |
| `HTTPS_PROXY` / `HTTP_PROXY` | — | Respected for outbound calls, for networks that need a corporate proxy. |

## Logging

Each call logs one line: `[rest.ok] proxy=<name> method=<M> path=<path> status=<s> elapsed=<ms>`. Other outcomes are logged as `[rest.unauthorized]`, `[rest.bad_path]`, `[rest.unreachable]`, `[rest.timeout]` or `[rest.stream_error]`.

Headers, query strings and bodies are never logged, because they carry API keys, phone numbers and message text. Uvicorn's access log keeps a line per request, but for REST proxy paths the query string is replaced with `?REDACTED`, for example `"GET /gupshup-chat/users?REDACTED HTTP/1.1" 200`. Lines for other routes are unchanged.

Metrics are recorded under the server id `rest:<name>`.

`GET /health` under `fmcp run` reports `rest_servers`. A gateway configured with only REST proxies is healthy. A gateway configured with MCP servers is degraded when none of them is running, including when they all failed to start.

## Limits

- Outbound only. Inbound webhooks (for example WhatsApp delivery receipts) are not handled.
- Not reachable through the GPT Engine tunnel, which only carries JSON-RPC to `/{server}/mcp`.
- WebSocket upgrades are not proxied.
- One gateway token for every proxy; there are no per-proxy tokens.

## Implementation

- [fluidmcp/cli/services/rest_proxy.py](../fluidmcp/cli/services/rest_proxy.py): validation, registry, route and forwarder.
- [fluidmcp/cli/auth.py](../fluidmcp/cli/auth.py): `verify_proxy_token`.
- [fluidmcp/cli/api/management.py](../fluidmcp/cli/api/management.py): `/api/rest-servers`.
- Tests:
  - [tests/test_rest_proxy.py](../tests/test_rest_proxy.py)
  - [tests/test_rest_proxy_config.py](../tests/test_rest_proxy_config.py)
  - [tests/test_rest_proxy_api.py](../tests/test_rest_proxy_api.py)
