# API Client MCP Server

A Postman-like HTTP client MCP server that enables making API requests through chat with rich HTML visualization. Perfect for testing APIs, debugging endpoints, and exploring web services.

## Features

- **Full HTTP Method Support**: GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS
- **Rich HTML Visualization**: Syntax-highlighted JSON responses, color-coded status codes, collapsible headers
- **Flexible Configuration**:
  - Custom headers (Authorization, Content-Type, etc.)
  - Query parameters
  - Request body with multiple formats (JSON, form data, text)
  - Timeout control
  - Redirect handling
- **Response Details**:
  - HTTP status code with color coding (green for 2xx, orange for 4xx, red for 5xx)
  - Response time in milliseconds
  - Response size in human-readable format
  - Full response headers
  - Copy-to-clipboard functionality
- **Robust Error Handling**: Network errors, timeouts, invalid JSON, malformed URLs

## Installation

The server is already available in the FluidMCP examples. No additional installation required beyond FluidMCP itself.

## Usage

### Running the Server

Create a configuration file:

```json
{
  "mcpServers": {
    "api-client": {
      "command": "python",
      "args": ["/workspaces/fluidmcp/examples/api-client-mcp/server.py"],
      "env": {}
    }
  }
}
```

Start the server:

```bash
fluidmcp run /path/to/config.json --file --start-server
```

The server will be available at `http://localhost:8099`

### Using via MCP Protocol

The server exposes one tool: `make_http_request`

#### Example 1: Simple GET Request

```json
{
  "url": "https://jsonplaceholder.typicode.com/users"
}
```

Returns: Rich HTML with list of users

#### Example 2: GET with Query Parameters

```json
{
  "url": "https://jsonplaceholder.typicode.com/posts",
  "method": "GET",
  "query_params": [
    {"key": "userId", "value": "1"},
    {"key": "_limit", "value": "5"}
  ]
}
```

Returns: Posts filtered by userId=1, limited to 5 results

#### Example 3: POST with JSON Body

```json
{
  "url": "https://jsonplaceholder.typicode.com/posts",
  "method": "POST",
  "headers": [
    {"key": "Content-Type", "value": "application/json"}
  ],
  "body": "{\"title\": \"My Post\", \"body\": \"Post content\", \"userId\": 1}",
  "body_type": "json"
}
```

Returns: Created post with 201 status

#### Example 4: Authenticated Request (Bearer Token)

```json
{
  "url": "https://api.example.com/protected",
  "method": "GET",
  "headers": [
    {"key": "Authorization", "value": "Bearer YOUR_TOKEN_HERE"}
  ]
}
```

#### Example 5: Form Data Submission

```json
{
  "url": "https://httpbin.org/post",
  "method": "POST",
  "body": "name=John&email=john@example.com",
  "body_type": "form"
}
```

#### Example 6: Custom Timeout

```json
{
  "url": "https://httpbin.org/delay/5",
  "method": "GET",
  "timeout": 10
}
```

### Using via HTTP API

You can also call the MCP server directly via HTTP:

```bash
# List available tools
curl http://localhost:8099/api-client/mcp/tools/list

# Make a request
curl -X POST http://localhost:8099/api-client/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "make_http_request",
    "arguments": {
      "url": "https://jsonplaceholder.typicode.com/users/1",
      "method": "GET"
    }
  }'
```

## Tool Schema

### `make_http_request`

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `url` | string | Yes | - | Full URL including protocol (http:// or https://) |
| `method` | string | No | "GET" | HTTP method: GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS |
| `headers` | array | No | [] | Array of `{key, value}` objects for HTTP headers |
| `query_params` | array | No | [] | Array of `{key, value}` objects for query parameters |
| `body` | string | No | - | Request body content |
| `body_type` | string | No | "json" | Body format: json, form, text, none |
| `timeout` | integer | No | 30 | Request timeout in seconds (1-300) |
| `follow_redirects` | boolean | No | true | Whether to follow HTTP redirects |

**Headers Array Example:**
```json
[
  {"key": "Authorization", "value": "Bearer token123"},
  {"key": "Content-Type", "value": "application/json"},
  {"key": "X-Custom-Header", "value": "custom-value"}
]
```

**Query Params Array Example:**
```json
[
  {"key": "page", "value": "1"},
  {"key": "limit", "value": "10"},
  {"key": "sort", "value": "name"}
]
```

## Testing with Public APIs

### JSONPlaceholder (Free fake REST API)

```json
{
  "url": "https://jsonplaceholder.typicode.com/posts",
  "method": "GET"
}
```

### httpbin.org (HTTP testing service)

```json
{
  "url": "https://httpbin.org/anything",
  "method": "POST",
  "headers": [
    {"key": "X-Test-Header", "value": "test-value"}
  ],
  "body": "{\"test\": \"data\"}",
  "body_type": "json"
}
```

### ReqRes (REST API with authentication simulation)

```json
{
  "url": "https://reqres.in/api/users",
  "method": "GET",
  "query_params": [
    {"key": "page", "value": "2"}
  ]
}
```

## Response Format

The server returns rich HTML with the following sections:

1. **Status Bar**: HTTP status code (color-coded), response time, response size
2. **Request Info**: HTTP method badge and full URL
3. **Response Headers**: Collapsible section with all response headers
4. **Response Body**: Syntax-highlighted content with copy button

### Status Color Coding

- 🟢 **2xx (Success)**: Green
- 🔵 **3xx (Redirect)**: Blue
- 🟠 **4xx (Client Error)**: Orange
- 🔴 **5xx (Server Error)**: Red

### JSON Syntax Highlighting

- Keys: Blue
- Strings: Green
- Numbers: Orange
- Booleans: Pink
- Null: Gray

## Error Handling

The server provides detailed error messages for:

- **Network errors**: Connection refused, DNS resolution failures
- **Timeout errors**: Request exceeds configured timeout
- **Invalid JSON**: Malformed JSON in request body
- **Invalid URLs**: Missing protocol or malformed URL format
- **HTTP errors**: Any httpx-related errors

All errors are displayed in a user-friendly HTML format with the error icon and details.

## Troubleshooting

### Issue: "Request timed out"

**Solution**: Increase the `timeout` parameter:
```json
{
  "url": "https://slow-api.example.com",
  "timeout": 60
}
```

### Issue: "Invalid JSON body"

**Solution**: Ensure your JSON string is properly formatted:
```json
{
  "body": "{\"key\": \"value\"}",  // ✅ Correct (escaped quotes)
  "body": "{'key': 'value'}",      // ❌ Wrong (single quotes)
  "body_type": "json"
}
```

### Issue: "Invalid URL format"

**Solution**: Include the protocol (http:// or https://):
```json
{
  "url": "https://api.example.com",  // ✅ Correct
  "url": "api.example.com"           // ❌ Wrong (missing protocol)
}
```

### Issue: Headers not being sent

**Solution**: Ensure headers are in the correct array format:
```json
{
  "headers": [
    {"key": "Authorization", "value": "Bearer token"}  // ✅ Correct
  ],
  "headers": {"Authorization": "Bearer token"}  // ❌ Wrong (object, not array)
}
```

## curl Equivalents

For reference, here's how MCP requests map to curl commands:

**Simple GET:**
```bash
# MCP
{"url": "https://api.example.com/users"}

# curl
curl https://api.example.com/users
```

**POST with JSON:**
```bash
# MCP
{
  "url": "https://api.example.com/posts",
  "method": "POST",
  "body": "{\"title\": \"Test\"}",
  "body_type": "json"
}

# curl
curl -X POST https://api.example.com/posts \
  -H "Content-Type: application/json" \
  -d '{"title": "Test"}'
```

**With Authentication:**
```bash
# MCP
{
  "url": "https://api.example.com/protected",
  "headers": [{"key": "Authorization", "value": "Bearer token"}]
}

# curl
curl https://api.example.com/protected \
  -H "Authorization: Bearer token"
```

## Development

### File Structure

```
api-client-mcp/
├── server.py       # Main MCP server implementation
├── metadata.json   # FluidMCP package metadata
└── README.md      # This file
```

### Dependencies

- `httpx`: Async HTTP client
- `mcp`: MCP SDK for Python
- Standard library: `json`, `time`, `re`, `asyncio`

### Extending the Server

To add more tools (like save/load request configurations):

1. Add new tool definition in `list_tools()`
2. Implement tool handler in `call_tool()`
3. Update `metadata.json` with new tool info
4. Update this README with usage examples

## Future Enhancements

Potential features for future versions:

- Save/load request configurations
- Request history with timestamps
- Environment variable substitution ({{VAR_NAME}})
- Request collections (group related requests)
- Response assertions and validation
- GraphQL query support
- WebSocket connection support
- Import/export Postman collections
- cURL command export

## License

Part of FluidMCP - see main repository for license information.

## Contributing

Contributions are welcome! Please submit issues and pull requests to the main FluidMCP repository.
