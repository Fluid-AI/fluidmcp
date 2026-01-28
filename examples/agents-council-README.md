# Agents Council Integration with FluidMCP

## Overview

This directory contains configuration files for integrating [agents-council](https://github.com/MrLesk/agents-council) with FluidMCP. Agents Council is a multi-agent collaboration platform that enables AI agents (Claude Code, Codex, Gemini, Cursor) to work together on complex tasks through a unified MCP server.

## What is Agents Council?

Agents Council provides centralized agent communication via an MCP stdio server. It allows multiple AI agents to:
- Start collaborative sessions with complex requests
- Join ongoing discussions and provide feedback
- Poll for updates and responses from other agents
- Close sessions with conclusions
- Summon Claude or Codex agents into active councils

All council state is stored locally at `~/.agents-council/state.json`, enabling persistent collaboration across agent sessions.

## Configuration Files

### 1. agents-council-config.json
Basic configuration for a single agents-council server.

```json
{
  "mcpServers": {
    "agents-council": {
      "command": "npx",
      "args": ["-y", "agents-council@latest", "mcp"],
      "env": {}
    }
  }
}
```

**Use case**: Single agent acting as a council participant or coordinator.

### 2. agents-council-named.json
Configuration for multiple named agents that can collaborate.

```json
{
  "mcpServers": {
    "agents-council-opus": {
      "command": "npx",
      "args": ["-y", "agents-council@latest", "mcp", "-n", "Opus"],
      "env": {}
    },
    "agents-council-codex": {
      "command": "npx",
      "args": ["-y", "agents-council@latest", "mcp", "-n", "Codex"],
      "env": {}
    },
    "agents-council-gemini": {
      "command": "npx",
      "args": ["-y", "agents-council@latest", "mcp", "-n", "Gemini"],
      "env": {}
    }
  }
}
```

**Use case**: Multiple distinct agents collaborating on the same task, each with a unique name for identification in the council.

## Available MCP Tools

Agents Council provides 6 MCP tools:

### 1. start_council
Opens a new council session with a request for collaboration.

**Input Schema**:
```json
{
  "request": "string (required) - The complex problem or task to discuss"
}
```

**Example**:
```json
{
  "request": "Help me design a scalable microservices architecture for a real-time chat application with 100k+ concurrent users"
}
```

### 2. join_council
Allows an agent to join an existing council session.

**Input Schema**:
```json
{}
```

**Returns**: The current council request and all existing responses.

### 3. get_current_session_data
Polls for new responses and updates in the active council session.

**Input Schema**:
```json
{
  "cursor": "string (optional) - Pagination cursor for fetching updates"
}
```

**Returns**: New responses since the last poll.

### 4. send_response
Submits feedback or a response to the active council.

**Input Schema**:
```json
{
  "response": "string (required) - The agent's feedback or contribution"
}
```

**Example**:
```json
{
  "response": "I recommend using event-driven architecture with Apache Kafka for message queuing and Redis for session management."
}
```

### 5. close_council
Ends the council session with a final conclusion.

**Input Schema**:
```json
{
  "conclusion": "string (required) - Summary of the council's decisions"
}
```

**Example**:
```json
{
  "conclusion": "Agreed on using Kafka for message queuing, Redis for sessions, WebSockets for real-time communication, and Kubernetes for orchestration."
}
```

### 6. summon_agent
Summons Claude or Codex into the current council session.

**Input Schema**:
```json
{
  "agent": "string (required) - Agent to summon: 'claude' or 'codex'"
}
```

**Requirements**:
- Claude: Requires Claude Code installed and authenticated
- Codex: Requires Codex CLI authenticated (`codex login`)

## Quick Start Guide

### Step 1: Start FluidMCP Backend

```bash
# Start backend + frontend on port 8099
fmcp serve
```

Access points:
- Frontend UI: http://localhost:8099/ui
- Swagger API: http://localhost:8099/docs
- API Base: http://localhost:8099/api

### Step 2: Add Agents Council Server via API

**Option A: Using curl**

```bash
curl -X POST http://localhost:8099/api/servers \
  -H "Content-Type: application/json" \
  -d '{
    "id": "agents-council",
    "name": "Agents Council",
    "description": "Multi-agent collaboration platform",
    "command": "npx",
    "args": ["-y", "agents-council@latest", "mcp"],
    "env": {}
  }'
```

**Option B: Using Swagger UI**

1. Navigate to http://localhost:8099/docs
2. Find `POST /api/servers`
3. Click "Try it out"
4. Paste the JSON body
5. Click "Execute"

**Option C: Run from config file**

```bash
# From project root
fmcp run examples/agents-council-config.json --file --start-server
```

### Step 3: Start the Server

**Via curl**:
```bash
curl -X POST http://localhost:8099/api/servers/agents-council/start
```

**Via Swagger UI**:
- Navigate to `POST /api/servers/{id}/start`
- Enter `agents-council` as the server ID
- Execute

**Via Frontend**:
- Go to http://localhost:8099/ui
- Find "Agents Council" server card
- Click "Start" button

### Step 4: Verify Tools Discovered

```bash
curl -X POST http://localhost:8099/agents-council/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

Expected response includes 6 tools:
- start_council
- join_council
- get_current_session_data
- send_response
- close_council
- summon_agent

## Testing Workflow

### Scenario 1: Single Agent Council Session

**1. Start a council**:
```bash
curl -X POST http://localhost:8099/api/servers/agents-council/tools/start_council/run \
  -H "Content-Type: application/json" \
  -d '{
    "arguments": {
      "request": "Design a caching strategy for a high-traffic e-commerce API"
    }
  }'
```

**2. Send a response**:
```bash
curl -X POST http://localhost:8099/api/servers/agents-council/tools/send_response/run \
  -H "Content-Type: application/json" \
  -d '{
    "arguments": {
      "response": "Use multi-layer caching: Redis for session data, CDN for static assets, and in-memory cache for frequently accessed product data."
    }
  }'
```

**3. Get session data**:
```bash
curl -X POST http://localhost:8099/api/servers/agents-council/tools/get_current_session_data/run \
  -H "Content-Type: application/json" \
  -d '{
    "arguments": {}
  }'
```

**4. Close the council**:
```bash
curl -X POST http://localhost:8099/api/servers/agents-council/tools/close_council/run \
  -H "Content-Type: application/json" \
  -d '{
    "arguments": {
      "conclusion": "Implement multi-layer caching with Redis, CDN, and in-memory cache. Monitor cache hit rates and adjust TTLs based on usage patterns."
    }
  }'
```

### Scenario 2: Multi-Agent Collaboration

**1. Add multiple named agents**:

```bash
# Add Opus agent
curl -X POST http://localhost:8099/api/servers \
  -H "Content-Type: application/json" \
  -d '{
    "id": "council-opus",
    "name": "Council Agent - Opus",
    "command": "npx",
    "args": ["-y", "agents-council@latest", "mcp", "-n", "Opus"],
    "env": {}
  }'

# Add Codex agent
curl -X POST http://localhost:8099/api/servers \
  -H "Content-Type: application/json" \
  -d '{
    "id": "council-codex",
    "name": "Council Agent - Codex",
    "command": "npx",
    "args": ["-y", "agents-council@latest", "mcp", "-n", "Codex"],
    "env": {}
  }'
```

**2. Start both agents**:

```bash
curl -X POST http://localhost:8099/api/servers/council-opus/start
curl -X POST http://localhost:8099/api/servers/council-codex/start
```

**3. Opus starts the council**:

```bash
curl -X POST http://localhost:8099/api/servers/council-opus/tools/start_council/run \
  -H "Content-Type: application/json" \
  -d '{
    "arguments": {
      "request": "What is the best approach for implementing real-time notifications in a mobile app?"
    }
  }'
```

**4. Codex joins and responds**:

```bash
# Join the council
curl -X POST http://localhost:8099/api/servers/council-codex/tools/join_council/run \
  -H "Content-Type: application/json" \
  -d '{
    "arguments": {}
  }'

# Send response
curl -X POST http://localhost:8099/api/servers/council-codex/tools/send_response/run \
  -H "Content-Type: application/json" \
  -d '{
    "arguments": {
      "response": "I recommend using Firebase Cloud Messaging (FCM) for cross-platform support, with WebSocket fallback for real-time updates when the app is active."
    }
  }'
```

**5. Opus checks for updates and closes**:

```bash
# Get updates
curl -X POST http://localhost:8099/api/servers/council-opus/tools/get_current_session_data/run \
  -H "Content-Type: application/json" \
  -d '{
    "arguments": {}
  }'

# Close council
curl -X POST http://localhost:8099/api/servers/council-opus/tools/close_council/run \
  -H "Content-Type: application/json" \
  -d '{
    "arguments": {
      "conclusion": "Use FCM for push notifications with WebSocket fallback for in-app real-time updates."
    }
  }'
```

## Frontend UI Usage

### Dashboard View
1. Navigate to http://localhost:8099/ui
2. See all council agents listed with status
3. Start/Stop agents using action buttons
4. Tool count badge shows 6 tools per agent

### Server Details & Tool Runner
1. Click "Details" on any council agent card
2. View all available tools
3. Click on any tool (e.g., "start_council")
4. Fill in the dynamic form with required arguments
5. Click "Run Tool"
6. View results in the output panel
7. Execution history saved automatically

### Environment Variables
Agents Council doesn't require any environment variables by default. All configuration is handled through command-line arguments (`-n` for agent name).

## Using JSON-RPC Directly

For advanced users, you can communicate directly with the MCP server using JSON-RPC:

```bash
curl -X POST http://localhost:8099/agents-council/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "start_council",
      "arguments": {
        "request": "Your complex task here"
      }
    }
  }'
```

All 6 tools can be called this way by changing the `name` and `arguments` fields.

## State Management

- **State File**: `~/.agents-council/state.json`
- **Shared State**: All agents using agents-council share the same state file
- **Persistence**: Council sessions persist across server restarts
- **Clean State**: Delete `~/.agents-council/state.json` to start fresh

## MongoDB Storage

FluidMCP automatically stores:
- **Server Config**: In `fluidmcp_servers` collection
- **Runtime State**: In `fluidmcp_server_instances` collection
- **Server Logs**: In `fluidmcp_server_logs` collection (capped at 100MB)
- **Discovered Tools**: Cached in server config for quick access

Query MongoDB to see your council configuration:

```javascript
// Connect to MongoDB
use fluidmcp

// View council servers
db.fluidmcp_servers.find({"id": "agents-council"}).pretty()

// View runtime instances
db.fluidmcp_server_instances.find({"server_id": "agents-council"}).pretty()

// View logs
db.fluidmcp_server_logs.find({"server_name": "agents-council"}).sort({"timestamp": -1}).limit(50)
```

## Troubleshooting

### Issue: npx takes too long to start
**Solution**: Pre-install the package globally:
```bash
npm install -g agents-council
```

Then update config to use `agents-council` instead of `npx`:
```json
{
  "command": "agents-council",
  "args": ["mcp"]
}
```

### Issue: Tools not discovered after start
**Solution**: Check server logs for errors:
```bash
curl http://localhost:8099/api/servers/agents-council/logs
```

Verify MCP handshake completed successfully.

### Issue: Multiple agents showing same responses
**Expected behavior**: All agents share the same state file (`~/.agents-council/state.json`) for collaboration. Different named agents (`-n Opus`, `-n Codex`) will show distinct names in the council but access the same session data.

### Issue: Council session persists across restarts
**Expected behavior**: State is stored locally. To start fresh:
```bash
rm ~/.agents-council/state.json
```

### Issue: Frontend form not rendering
**Solution**: Verify tool inputSchema is valid JSON Schema. Check browser console for errors. Ensure server is running and tools were discovered.

## Advanced Configuration

### Custom Agent Names
Use the `-n` flag to set custom agent names:

```json
{
  "command": "npx",
  "args": ["-y", "agents-council@latest", "mcp", "-n", "CustomAgentName"]
}
```

Agent names appear in council responses for identification.

### Integration with Other MCP Servers
Agents Council can run alongside other MCP servers in FluidMCP:

```json
{
  "mcpServers": {
    "agents-council": {
      "command": "npx",
      "args": ["-y", "agents-council@latest", "mcp"],
      "env": {}
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
      "env": {}
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"],
      "env": {}
    }
  }
}
```

All servers run independently on the same FluidMCP gateway (port 8099).

## Security Considerations

- **Local State**: Council state is stored locally at `~/.agents-council/state.json`
- **No Authentication**: Agents Council doesn't require API keys
- **Shared State**: All local agents share the same state file
- **Process Isolation**: Each MCP server runs in its own subprocess
- **FluidMCP Security**: Use `--secure` flag with bearer token for API authentication:

```bash
fmcp serve --secure --token mySecretToken123
```

Then include token in all API requests:
```bash
curl -H "Authorization: Bearer mySecretToken123" ...
```

## References

- **Agents Council Repository**: https://github.com/MrLesk/agents-council
- **MCP Protocol**: https://modelcontextprotocol.io
- **FluidMCP Documentation**: https://github.com/yourusername/fluidmcp
- **Inspiration**: https://github.com/karpathy/llm-council

## Support

For issues related to:
- **Agents Council**: https://github.com/MrLesk/agents-council/issues
- **FluidMCP Integration**: https://github.com/yourusername/fluidmcp/issues

## License

Agents Council is licensed under MIT. FluidMCP integration examples are provided as-is for educational purposes.
