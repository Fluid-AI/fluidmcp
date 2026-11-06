# GPT Engine: Tunnel Build Brief

What GPT Engine needs so that FluidMCP deployments on client servers can serve MCP tools through an outbound tunnel,
without the client opening any port or whitelisting anything. The FluidMCP side is done; see [TUNNEL.md](TUNNEL.md).

## Goal

A FluidMCP site opens **one outbound WebSocket** to its GPT Engine deployment. GPT Engine sends MCP requests down it
and gets the results back. GPT Engine needs:

- a WebSocket endpoint that accepts and authenticates tunnels;
- a local HTTP **bridge** that the existing MCP client calls like any MCP server;
- two small fixes in the MCP client.

Rules:

- Off unless `MCP_TUNNEL_ENABLED=true`. Deployments without it are unchanged.
- One process (1 replica, `UVICORN_WORKERS=1`). Tunnel state is in memory; no Redis.
- A `tools/call` that may have reached the site is **never retried automatically** (tools can send OTPs or write data).
- Tunnel code never calls Mongo and never does synchronous I/O on the event loop.
- Everything is per connector (one per site); nothing is specific to one client.

## Request flow

```
agent / voice / Temporal run (same process)
  └─ existing MCP client: POST http://localhost:<PORT>/mcp-tunnel/<connector>/<server>/mcp   (bridge)
       └─ registry: find the connector's tunnel (wait up to 10 s) → encrypt "request" → send
            └─ /ws/mcp-tunnel ◄══ wss (opened by FluidMCP) ══► FluidMCP → local gateway → MCP server
       ◄─ "response" decrypted → future resolved → HTTP reply to the MCP client
```

## What FluidMCP provides

| File (FluidMCP repo) | Copy to GPT Engine | Notes |
|---|---|---|
| `fluidmcp/cli/tunnel/protocol.py` | `services/mcp_tunnel_protocol.py` | **Byte-identical; do not edit locally.** Pure Python, uses `cryptography` (already a dependency) |
| `tests/tunnel_test_vectors.json` | `tests/tunnel_test_vectors.json` | Shared reference; regenerate only together with the protocol |
| `tests/test_tunnel_protocol.py` | `tests/test_mcp_tunnel_protocol.py` | Change only the import lines |
| `tests/tunnel_fake_server.py` | (reference only) | A working server-side wrapper to copy patterns from |
| `docs/TUNNEL_PROTOCOL.md` | (reference) | Full wire specification |

Server-side API:

```python
from services.mcp_tunnel_protocol import (
    ServerHandshake, SecureChannel, ControlMessage, ProtocolError,
    generate_identity_key, private_key_from_b64, private_key_to_b64, public_key_to_b64, parse_public_key_list)

handshake = ServerHandshake(identity_key, client_public_keys, connector_id)   # starts the 10 s clock
await ws.send_bytes(handshake.receive_client_hello(await ws.receive_bytes()))
channel = handshake.receive_client_finish(await ws.receive_bytes())
frame = channel.encrypt(json_bytes)      # DATA record
result = channel.decrypt(frame)          # bytes (JSON), or ControlMessage for a re-key
channel.check_timers()                   # every 5 s; raises ProtocolError when a timer expires
```

- Every `encrypt`/`decrypt` **and** the send of its result happen under one `asyncio.Lock` per connection.
  A `ControlMessage.reply` is sent immediately, under the same lock.
- Never retry a failed send; close the connection.
- On `ProtocolError` or a text frame: close with **1008**, empty reason. Log `err.code` locally only.

## Messages inside the channel (UTF-8 JSON)

| Direction | Message |
|---|---|
| FluidMCP → GPT Engine (first) | `{"type":"hello","protocol":1,"version":"x.y.z","connector":"<id>","servers":["<name>", ...]}` |
| GPT Engine → FluidMCP | `{"type":"request","id":"<uuid4>","server":"<name>","body":{<JSON-RPC 2.0 request>}}` |
| FluidMCP → GPT Engine | `{"type":"response","id":"<uuid4>","status":<int>,"body":<json, text or null>}` |
| FluidMCP → GPT Engine | `{"type":"error","id":"<uuid4>","code":"server_not_allowed\|bad_request\|local_timeout\|local_call_failed\|response_too_large"}` |

Limits: 10 MiB per WebSocket message, binary frames only. Re-keying is handled inside the protocol module.

## Tasks

### G1. Protocol module and tests
Add the three files from the table above and run the vector test in CI.

### G2. Configuration (read once at startup)

```
MCP_TUNNEL_ENABLED=false|true
MCP_TUNNEL_CONNECTORS={"<connector>": {"token_sha256": "<hex sha256 of the tunnel token>",
                                       "public_keys": ["<site public key, base64>"],
                                       "servers": ["<server>", "..."]}}
MCP_TUNNEL_SERVER_PRIVATE_KEY=<base64 Ed25519 private key>     # Railway secret or Key Vault
MCP_TUNNEL_BRIDGE_TOKEN=<random, at least 32 bytes>
```

- `public_keys` holds 1–2 keys (two only during a site key rotation).
- Validate at startup. On invalid configuration, log an error and leave the tunnel disabled; do not crash.
- Log the server **public** key (`public_key_to_b64`) at startup; it is given to each site.
- Provide a one-off command to generate the server key pair (`generate_identity_key`, `private_key_to_b64`).

### G3. Registry: `services/mcp_tunnel.py`
- `TunnelConn`: `ws`, `channel`, `lock`, `connector`, `hello`, `connected_at`.
- `connectors: dict[str, TunnelConn]`, `pending: dict[str, asyncio.Future]`.
- `register(conn)`: close any existing connection for the same connector with 1012, then store the new one.
- `send_request(connector, server, body, timeout=55)`:
  - wait up to 10 s for a connection, else raise `NotDelivered`;
  - create the future, then encrypt and send under the lock; if the send fails, raise `NotDelivered`;
  - wait for the reply; on timeout raise `TunnelTimeout`.
- On disconnect, fail that connector's pending futures with `TunnelLost`.
- At startup, warn if `UVICORN_WORKERS` is above 1.

### G4. WebSocket endpoint `/ws/mcp-tunnel` on `ws_app`
1. Before `accept()`: read `Authorization: Bearer <token>` and `X-Connector-Id`; the connector must exist and
   `hmac.compare_digest(sha256(token), token_sha256)` must pass. Otherwise close before accepting (client sees HTTP 403).
2. Accept, then within `asyncio.wait_for(..., 10)`: receive CLIENT_HELLO, send SERVER_HELLO, receive CLIENT_FINISH.
3. Decrypt the first message (`hello`); its `connector` must equal the header. Then `register()`.
4. Receive loop: decrypt under the lock; `response`/`error` → resolve `pending[id]` (ignore unknown ids);
   `ControlMessage` → send its `reply` under the lock.
5. Ticker task: `channel.check_timers()` every 5 s.
6. On exit: unregister, fail pending futures, cancel the ticker.

### G5. Bridge route `POST /mcp-tunnel/{connector}/{server}/mcp`
- Mounted outside the global auth dependencies (like `ws_app`).
- `Authorization: Bearer` must match `MCP_TUNNEL_BRIDGE_TOKEN` (`hmac.compare_digest`), else 401.
- `connector` must exist and `server` must be in its list, else 404.
- Pass the JSON-RPC body to `send_request()`; return FluidMCP's `body` as JSON with its `status`.
- The route is reachable through the public domain; the bridge token is its only protection.

### G6. Bridge error mapping

| Condition | Response |
|---|---|
| `NotDelivered` | **503** with header `X-Tunnel-Not-Delivered: 1` |
| `TunnelTimeout`, or FluidMCP `local_timeout` | **504** |
| `TunnelLost`, or any other FluidMCP `error` | **502** with `{"error": "<code>"}` |

Error bodies must never contain the text `No valid session ID` (it switches the client to its session fallback).

### G7. No retry after possible delivery (`retry_utils.py`, `mcp_server_handler.py`)
- Add `class NonRetryableToolCallError(Exception)`; `_retry_common` re-raises it immediately, as it does
  `MCPResponseParsingError`.
- In `call_tool_request`, when the URL path starts with `/mcp-tunnel/`: wrap **every** failure, including
  `httpx.ReadTimeout`, 502, 504 and any non-2xx, in `NonRetryableToolCallError`, **except** 503 with
  `X-Tunnel-Not-Delivered: 1`, which keeps the normal retry.
- Other URLs and `tools/list` are unchanged.

### G8. Header-leak fix in `fetch_all_mcp_tools`
Reset `mcp_headers = {}` at the start of each server's loop iteration. Today it is set once outside the loop, so one
server's headers (including tokens) can be sent to another. This affects all tenants; check workflows with more than
one MCP server before release.

### G9. Shutdown
In the shutdown hook, close every tunnel with 1012 and fail pending futures with `TunnelLost`.

### G10. Health and alerting
- Add `"mcp_tunnel": {"enabled": ..., "connectors": {"<connector>": {"connected": ..., "since": ..., "key_no": ...}}}`
  to the health response, for information only (never fails the check).
- Alert when a connector has been disconnected for 60 s (OTel, Sentry or an uptime monitor).

### G11. Member data
Apply the agreed redaction to `log_tool_execution`, the `Tool kwargs` / `Tool response` logs, the `Arguments:` and
`result from MCP server` logs, and `log_llm_interaction`, per the client's compliance decision.

### G12. Workflow configuration (no code)
For each tunnelled server add an `mcp_servers` entry:

- `url: http://localhost:<PORT>/mcp-tunnel/<connector>/<server>/mcp` (use `localhost`; the URL validator rejects `127.0.0.1`)
- `auth_bearer_token: <MCP_TUNNEL_BRIDGE_TOKEN>`

## Acceptance tests

Unit:
- Wrong token or unknown connector → 403 before accept.
- Handshake with an unregistered site key → closed with 1008. Text frame → 1008.
- A new connection for the same connector replaces the old one.
- Bridge with no tunnel → 503 with the header after 10 s; timeout → 504; disconnect → 502 and pending calls fail.
- `call_tool_request` on a bridge URL does not retry on `ReadTimeout`/502/504 and does retry on the not-delivered 503;
  other URLs keep today's behaviour.
- Headers are reset between servers (G8). A `localhost` bridge URL passes `mcpServerUrlValidator`.
- With `MCP_TUNNEL_ENABLED=false` the routes do not exist.
- Protocol vectors pass.

Staging (1 replica × 1 worker, event-loop watchdog on):
- A real FluidMCP connects; `tools/list` and `tools/call` work through the bridge, including from a voice call.
- Re-key under load (shorten the interval in staging); nothing fails.
- Kill the connection mid-call: the tool runs exactly once and is not retried.
- Redeploy with and without overlap; measure how long calls fail.

## Production settings to confirm (Railway access)

- 1 replica and `UVICORN_WORKERS=1`.
- `RAILWAY_DEPLOYMENT_OVERLAP_SECONDS` and `RAILWAY_DEPLOYMENT_DRAINING_SECONDS`.
- No other service runs this image.
- Idle timeout and maximum WebSocket lifetime on any proxy (e.g. Cloudflare) in front of the domain.
- Where `MCP_TUNNEL_SERVER_PRIVATE_KEY` is stored and who can read it.
- Who registers and rotates site keys.
