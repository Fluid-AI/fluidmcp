# GPT Engine Tunnel

The tunnel lets GPT Engine call MCP servers running on a client's own server without opening any port or adding
firewall rules there. FluidMCP opens one outbound WebSocket (`wss://`, port 443) to the client's GPT Engine
deployment; GPT Engine sends MCP requests down it, and FluidMCP forwards them to its own gateway
(`/{server}/mcp` on `127.0.0.1`).

It is built into `fmcp run` and is off unless `FMCP_TUNNEL_URL` is set.

```
GPT Engine  ◄══ wss:// opened by FluidMCP ══  FluidMCP tunnel client ──► 127.0.0.1:<port>/<root>/{server}/mcp
```

## Security

1. **TLS** (`wss://`). Plain `ws://` is accepted only for `localhost`, for testing.
2. **Tunnel token**, checked by GPT Engine before it accepts the connection.
3. **fmcp-tunnel/1** inside the connection ([TUNNEL_PROTOCOL.md](TUNNEL_PROTOCOL.md)):
   - both sides prove their identity with Ed25519 key pairs (each side pins the other's public key); FluidMCP's
     private key never leaves the client's server;
   - every message is encrypted and authenticated (AES-256-GCM) with session keys that are new for each connection
     and replaced every hour.
4. **Allowlist**: only servers in `FMCP_TUNNEL_ALLOWED_SERVERS` can be called.
5. **Gateway auth**: with `--secure` (or `FMCP_SECURE_MODE=true`), forwarded calls carry `FMCP_BEARER_TOKEN` like any other caller.

Request and response bodies, tokens and keys are never logged by the tunnel.

### What this protects against

| Threat | Protected? |
|---|---|
| Someone who has the tunnel URL and token, but not the site's private key | Yes. The token only gets past the HTTP check; the handshake then fails (`unknown_client_key` / `bad_signature`) |
| A recorded handshake or message replayed later | Yes. CLIENT_FINISH signs the server's fresh values, and records carry strict sequence numbers under per-connection keys |
| Changed, reordered, dropped or injected messages | Yes. Any of these closes the connection (code 1008); nothing is forwarded |
| A TLS-inspecting proxy or a rogue certificate in front of GPT Engine | Yes. The proxy can't produce GPT Engine's pinned signature, so FluidMCP aborts the handshake. It can still see the token in the upgrade request |
| Session keys exposed later | Limited to that connection and key period (ephemeral X25519 per connection and per re-key) |
| Someone with the token **and** the site's `identity.key` file | **No.** They can connect as the site. Keep the key file at mode 0600 on a private volume, and rotate it (below) if the server may be compromised |
| Someone with GPT Engine's server private key | **No.** They can act as GPT Engine and call every allowlisted server |
| Data GPT Engine stores or logs after it decrypts a reply | Out of scope; GPT Engine decides that |
| Denial of service against GPT Engine's endpoint, traffic analysis (message sizes and timing) | No |

No key or secret is built into the code: the site key comes from `fmcp tunnel keygen`, GPT Engine's public key and the
token come from configuration. The fixed keys in `tests/tunnel_test_vectors.json` are published test data; never
use them for a real deployment.

## Settings

| Variable | Required | Default | Description |
|---|---|---|---|
| `FMCP_TUNNEL_URL` | yes | | GPT Engine endpoint, e.g. `wss://<gpt-engine-domain>/ws/mcp-tunnel`. Setting it turns the tunnel on |
| `FMCP_TUNNEL_TOKEN` | yes | | Tunnel token issued by GPT Engine |
| `FMCP_TUNNEL_CONNECTOR_ID` | yes | | Name of this site in GPT Engine (letters, digits, `. _ : -`) |
| `FMCP_TUNNEL_ALLOWED_SERVERS` | yes | | Comma-separated MCP server names GPT Engine may call |
| `FMCP_TUNNEL_SERVER_PUBLIC_KEYS` | yes | | GPT Engine's public key (two, comma-separated, during a rotation) |
| `FMCP_TUNNEL_KEY_PATH` | no | `~/.fmcp/tunnel/identity.key` | This site's private key |
| `FMCP_TUNNEL_MAX_CONCURRENCY` | no | `20` | Requests forwarded at the same time |
| `FMCP_TUNNEL_REQUEST_TIMEOUT` | no | `45` | Seconds to wait for the local gateway |

If a setting is missing or invalid, FluidMCP logs `Tunnel disabled: ...` and runs without the tunnel.

## Setting up a site

1. Create this site's key (once). In Docker, mount a volume on the key directory first so it survives upgrades
   (the image sets `HOME=/app`, so the default is `/app/.fmcp/tunnel`):

   ```bash
   fmcp tunnel keygen
   ```

   Send the printed **public** key to the GPT Engine team. The private key stays in `identity.key` (mode 0600).

2. From the GPT Engine team, get the tunnel URL, token and GPT Engine's public key.

3. Set the variables above and start FluidMCP as usual:

   ```bash
   fmcp run config.json --file --start-server --secure
   ```

4. Check the connection:

   ```bash
   curl -s http://localhost:<port>/health
   # "tunnel": {"enabled": true, "connected": true, "last_connected_at": "...", "key_no": 1}
   ```

The server clock must be synchronised (`timedatectl`); the handshake rejects clocks more than 60 s off.

### In Docker (on-premise, `ON_PREMISE=true`)

`entrypoint.sh` runs `fmcp run "$FMCP_CONFIG_PATH" --file --start-server` on `$PORT`, and the tunnel starts from that
command. Besides the settings above:

- **Persist the key.** The image sets `HOME=/app`, so the key is `/app/.fmcp/tunnel/identity.key`. Mount a volume
  there (or set `FMCP_TUNNEL_KEY_PATH` to a mounted path). Without it, the key is lost on every image upgrade and the
  tunnel stays off until a new key is registered with GPT Engine.
- **Create the key before turning the tunnel on**, e.g. `docker compose run --rm <service> fmcp tunnel keygen`, then
  send the public key to the GPT Engine team. If the key is missing, the gateway starts and logs
  `Tunnel disabled: no identity key`.
- **Set `FMCP_TUNNEL_SERVER_PUBLIC_KEYS`.** It's required; without it the tunnel is disabled.
- **The gateway port can be published on localhost only** (`"127.0.0.1:8499:8499"`). The tunnel calls the gateway
  from inside the container on `127.0.0.1:$PORT$MCP_ROOT_PATH`, so it doesn't need the published port.
- To turn the tunnel off, remove `FMCP_TUNNEL_URL` and restart. Nothing else changes.

Before setting up a new site, check from inside the FluidMCP container that outbound WebSockets work:

```bash
curl -si --http1.1 --max-time 5 -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' https://echo.websocket.org/ | head -1
# HTTP/1.1 101 Switching Protocols
```

## Rotating the site key

```bash
fmcp tunnel keygen --rotate      # creates identity.next.key, prints its public key
# GPT Engine adds the new public key (it accepts both for now)
fmcp tunnel activate-new-key     # makes the new key active
# restart FluidMCP, then GPT Engine removes the old public key
```

`fmcp tunnel show-key` prints the active (and any pending) public key.

When GPT Engine rotates its own key, set both of its public keys in `FMCP_TUNNEL_SERVER_PUBLIC_KEYS` until the
rotation is complete.

## Behaviour

- **Reconnects** automatically: backoff from 1 s up to 60 s; 60 s after a rejected token or failed handshake. The
  backoff resets only after a connection has stayed up for 30 s, so several drops in a row (for example two GPT
  Engine restarts within a minute) reconnect after 1–2 s, then 2–3 s, 4–5 s, and so on.
- **One connection** at a time. If it drops, replies that were waiting to be sent on it are lost, and GPT Engine
  reports those calls as failed and does not retry them. The calls themselves keep running until they finish or reach
  their deadline, so a re-sent request with the same id gets their outcome (see below).
- **Concurrency**: at most `FMCP_TUNNEL_MAX_CONCURRENCY` calls run at once; further calls wait for a slot.
- If the local gateway is not yet listening (right after startup), a forwarded call keeps retrying the connection for
  up to 10 s, within its deadline. Only a refused connection is retried, because then the request was never sent.

### Deadline

Each request has one deadline of `FMCP_TUNNEL_REQUEST_TIMEOUT` seconds (default 45). It starts when FluidMCP accepts
the request and covers both the wait for a concurrency slot and the call to the gateway. Getting a slot doesn't
restart the clock: the call gets only the time left.

- If the deadline passes while the request is still waiting for a slot, it is never sent to the gateway, not even
  later when a slot frees. FluidMCP answers `not_delivered` (`reason: queue_timeout`).
- If a slot frees with less than 0.5 s left (or less than half the timeout, if the timeout is under 1 s), the request
  isn't sent either. Starting it then would almost certainly end with an unknown outcome.
- If the deadline passes while the gateway is handling the call, FluidMCP answers `local_timeout`. It stops waiting,
  but the call is **not** cancelled on the gateway and the tool may still finish. A late answer from the gateway is
  discarded and never causes a second call.

### Duplicate request ids

GPT Engine gives every request a unique `id` (a UUID string). FluidMCP remembers ids so that a request is never run
twice, even if GPT Engine sends it again:

- **Key:** the tunnel `id`, compared exactly (case and whitespace matter). It must be a string of 1–128 characters;
  other requests are ignored. The JSON-RPC `id` inside `body` is passed to the gateway unchanged and is not used for
  this, because GPT Engine may reuse it across calls.
- **While the call is running**, every copy of the request waits for the same call and gets the same answer. Copies
  don't extend its deadline. If one copy's reply can't be sent (for example its connection dropped), the call and
  the other copies are not affected.
- **After the call finished**, a copy gets the original answer without calling the gateway again. This includes
  errors and timeouts.
- **Same id, different request** (other `server` or `body`): nothing is run. FluidMCP answers `duplicate_request`
  (`reason: payload_mismatch`).

Limits (in memory, per FluidMCP process):

| Limit | Value | When it is reached |
|---|---|---|
| How long a finished id is remembered | 10 minutes | The id is forgotten; a request with it after that runs as new |
| Ids remembered (running + finished in the last 10 minutes) | 50 000 | New ids are refused with `not_delivered` (`reason: dedup_capacity`) and not run. Remembered ids are never dropped early |
| Stored answers | 64 MiB | The oldest answers are dropped, but their ids are kept. A copy then gets `duplicate_request` (`reason: outcome_expired`) and is not run |

What this does **not** cover:

- **Restarts.** The memory is lost when FluidMCP restarts, so an id seen before a restart can run again after it.
  In the GPT Engine design ([GPT_ENGINE_TUNNEL_BUILD.md](GPT_ENGINE_TUNNEL_BUILD.md), G3) every call gets a new id
  and a dropped connection fails the call rather than re-sending it, so this only matters if that changes.
- **More than one FluidMCP process** serving the same connector. The design is one FluidMCP and one GPT Engine
  process per site.
- **Ids older than 10 minutes.** GPT Engine waits at most 55 s for an answer, so a legitimate copy arrives well
  within that window.

Answers stay in memory for up to 10 minutes so copies can be answered. They may contain member data; they are never
logged or written to disk.

### At-most-once calls

FluidMCP sends each accepted request id to the gateway at most once (within the limits above). Whether a failed call
can be retried is decided on the GPT Engine side ([GPT_ENGINE_TUNNEL_BUILD.md](GPT_ENGINE_TUNNEL_BUILD.md), G6–G7):

| What GPT Engine sees | Did the tool run? | Retry? |
|---|---|---|
| No tunnel connected, or the send failed (503 `X-Tunnel-Not-Delivered: 1`) | No | Yes |
| `not_delivered` (`queue_timeout`, `gateway_unreachable`, `dedup_capacity`) | No: the gateway never received it | Yes (as a new request) |
| `server_not_allowed`, `bad_request` | No | No (it won't succeed) |
| `duplicate_request` | Not by this message; the original call may have | No |
| `local_call_failed` | Maybe (the gateway connection failed after the request was sent) | No |
| `local_timeout`, bridge timeout, connection lost mid-call | Maybe | No |
| `response`, including 4xx/5xx from the gateway | Yes, or the gateway refused it | No |

`not_delivered` and `duplicate_request` replies also carry a `reason` field. A GPT Engine build that doesn't know
these codes treats them as an ordinary error (502, not retried), which is safe.

### Single GPT Engine instance

GPT Engine keeps tunnel state (the connection, pending requests and request/response matching) in memory in one
process, so it must run as one replica with one worker. FluidMCP holds one connection; a new one replaces the old.

## Monitoring

`/health` includes a `tunnel` field for information only; it never changes the health status code.

`/metrics`:

| Metric | Type |
|---|---|
| `fluidmcp_tunnel_connected` | Gauge (1 = connected) |
| `fluidmcp_tunnel_requests_total{server,result}` | Counter (`result` is the HTTP status, an error code, or `duplicate` for a copy answered from the original call) |
| `fluidmcp_tunnel_request_seconds{server}` | Histogram |
| `fluidmcp_tunnel_handshake_failures_total` | Counter |

## Troubleshooting

| Log message | Cause |
|---|---|
| `Tunnel disabled: no identity key at ...` | Run `fmcp tunnel keygen`, or mount the key directory |
| `Tunnel disabled: cannot use identity key ... (chmod 600)` | The key file is readable by other users |
| `Tunnel rejected: HTTP 403` | Wrong token or connector ID |
| `Tunnel rejected: handshake failed (...)` | Key not registered in GPT Engine, wrong `FMCP_TUNNEL_SERVER_PUBLIC_KEYS`, or clock skew |
| `Tunnel protocol error (...); reconnecting` | The connection was corrupted or a timer expired; it reconnects with a fresh handshake |
| `Rejected tunnel request for server not in allowlist` | GPT Engine asked for a server missing from `FMCP_TUNNEL_ALLOWED_SERVERS` |
| `Duplicate tunnel request ...: waiting for the original call` / `returning the original outcome` | GPT Engine sent the same request id again; it was answered without running the tool again |
| `Tunnel request ... not executed: id already used (payload_mismatch)` | GPT Engine reused an id for a different request; check GPT Engine's id generation |
| `Tunnel request ... refused: duplicate-protection capacity reached` | More than 50 000 request ids in 10 minutes; new requests are refused until older ids expire |
| `Local call to '...' failed: gateway not reachable` | The local gateway refused the connection for 10 s (or until the deadline); the request was not sent |

## Local testing

`tests/tunnel_fake_server.py` is a minimal GPT Engine endpoint:

```bash
fmcp tunnel keygen
PYTHONPATH=. python tests/tunnel_fake_server.py --token test --client-public-key "<public key>" --connector site-a
# prints FMCP_TUNNEL_SERVER_PUBLIC_KEYS=...

FMCP_TUNNEL_URL=ws://127.0.0.1:8765 FMCP_TUNNEL_TOKEN=test FMCP_TUNNEL_CONNECTOR_ID=site-a \
FMCP_TUNNEL_ALLOWED_SERVERS=filesystem,memory FMCP_TUNNEL_SERVER_PUBLIC_KEYS=<printed key> \
fmcp run examples/sample-config.json --file --start-server
```

The fake server sends `tools/list` to every allowed server once connected and prints the results.

Tests: `pytest tests/test_tunnel_protocol.py tests/test_tunnel_client.py`.
