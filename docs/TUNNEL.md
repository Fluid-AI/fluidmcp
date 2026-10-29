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
   - both sides prove their identity with key pairs; FluidMCP's private key never leaves the client's server;
   - every message is encrypted and signed with session keys that are new for each connection and replaced every hour.
4. **Allowlist**: only servers in `FMCP_TUNNEL_ALLOWED_SERVERS` can be called.
5. **Gateway auth**: with `--secure` (or `FMCP_SECURE_MODE=true`), forwarded calls carry `FMCP_BEARER_TOKEN` like any other caller.

Request and response bodies are never logged by the tunnel.

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

- **Reconnects** automatically: backoff from 1 s up to 60 s; 60 s after a rejected token or failed handshake.
- **One connection** at a time. Requests in flight when it drops are cancelled; GPT Engine reports them as failed
  and does not retry them.
- **Local timeout**: a call slower than `FMCP_TUNNEL_REQUEST_TIMEOUT` returns `local_timeout`.
- If the local gateway is not yet listening (right after startup), a forwarded call waits up to 10 s for it.

## Monitoring

`/health` includes a `tunnel` field for information only; it never changes the health status code.

`/metrics`:

| Metric | Type |
|---|---|
| `fluidmcp_tunnel_connected` | Gauge (1 = connected) |
| `fluidmcp_tunnel_requests_total{server,result}` | Counter (`result` is the HTTP status or an error code) |
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
