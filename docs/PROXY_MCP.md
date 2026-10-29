# Proxy MCP Servers

A proxy MCP server exposes an HTTP endpoint as an MCP tool. It has no server code of its own: FluidMCP answers `tools/list` from the config, and on `tools/call` it sends the tool arguments to the endpoint and returns the response as the tool result.

Use it to make an existing API, such as OpenAI's chat completions, callable from FluidGPT or any other MCP client without writing a `server.py`.

## Configuration

```json
{
  "mcpServers": {
    "openai-chat": {
      "type": "proxy",
      "endpoint": "https://api.openai.com/v1/chat/completions",
      "headers": { "Authorization": "Bearer ${OPENAI_API_KEY}" },
      "response_path": "choices.0.message.content",
      "tool": {
        "name": "chat_completion",
        "description": "...",
        "inputSchema": { "type": "object", "properties": { "...": {} } }
      }
    }
  }
}
```

The full OpenAI example is in [examples/openai-proxy-config.json](../examples/openai-proxy-config.json).

| Field | Required | Description |
|---|---|---|
| `type` | yes | Must be `"proxy"`. |
| `endpoint` | yes | `http://` or `https://` URL the tool call is sent to. |
| `tool.name` | yes | 1–64 letters, digits, `_` or `-`. |
| `tool.inputSchema` | yes | JSON schema with `"type": "object"`. |
| `tool.description` | no | Shown to the client's LLM. |
| `method` | no | `POST` (default), `PUT`, `PATCH`, `GET` or `DELETE`. `GET` and `DELETE` send the arguments as query parameters; the others send them as the JSON body. |
| `headers` | no | Sent with every upstream request. `${VAR}` is replaced when the server starts. |
| `timeout` | no | Upstream timeout in seconds. Default `50`. |
| `response_path` | no | Dotted path into the JSON response, for example `choices.0.message.content`. Without it, the full response body is returned. |

### Header variables

`${VAR}` in a header value is looked up in this order:

1. The FluidMCP process environment.
2. The server's instance env (`PUT /api/servers/{id}/instance/env`).
3. The server's `env` block.

If a variable is missing, the server fails to start and the log names the variable. Header values are never logged. `GET /api/servers` leaves headers out, and `GET /api/servers/{id}` shows each value as `****`.

## Running it

With a config file:

```bash
export OPENAI_API_KEY=sk-...
fluidmcp validate examples/openai-proxy-config.json --file
fluidmcp run examples/openai-proxy-config.json --file --start-server
```

With `fmcp serve` (Railway), send the same fields to the management API:

```bash
curl -X POST https://your-app/api/servers \
  -H "Authorization: Bearer $FMCP_BEARER_TOKEN" -H "Content-Type: application/json" \
  -d '{"id": "openai-chat", "name": "OpenAI Chat", "type": "proxy", "endpoint": "...", "headers": {...}, "tool": {...}}'
curl -X POST https://your-app/api/servers/openai-chat/start -H "Authorization: Bearer $FMCP_BEARER_TOKEN"
```

Calling the tool:

```bash
curl -X POST http://localhost:8099/openai-chat/mcp -H "Content-Type: application/json" -d '{
  "jsonrpc": "2.0", "id": 1, "method": "tools/call",
  "params": {"name": "chat_completion",
             "arguments": {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Hi"}]}}}'
```

```json
{"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "Hello! How can I help?"}], "isError": false}}
```

## Errors

Upstream failures (HTTP 4xx/5xx, timeout, connection error, missing `response_path`) come back as a normal tool result with `isError: true` and a message, for example `Upstream returned HTTP 401: {...}`. They are not HTTP or JSON-RPC errors, because FluidGPT retries those and would send the same request upstream again.

## Using it from FluidGPT

- Point the workflow's MCP server URL at `https://<fluidmcp>/<server-id>/mcp`, not `/sse`. FluidGPT sends no auth headers on `/sse` URLs.
- Put the FluidMCP bearer token in `auth_bearer_token`.
- FluidGPT drops any argument that is not declared in `inputSchema.properties`, so declare every field the upstream needs, including optional ones such as `temperature`.
- FluidGPT describes array arguments to its LLM only as "array of objects". Spell out the item format in `tool.description`, as the OpenAI example does for `messages`.
- FluidGPT gives up after 60 seconds (`MCP_REQUEST_TIMEOUT`). Keep `timeout` below that.
- FluidGPT reads only `content[0].text`. Use `response_path` to return just the part the LLM needs.
- FluidGPT caches tool lists, so a schema change may take a while to show up.

## Limits

- One tool per proxy server.
- No streaming. An upstream `stream: true` response is returned as raw text once it completes.
- Every caller shares the API key in the proxy's headers. Incoming request headers are never forwarded upstream.
