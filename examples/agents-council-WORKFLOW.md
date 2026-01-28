# agents-council Workflow & Architecture

## What is agents-council?

**agents-council is a message broker/coordination platform for AI agent sessions, NOT an automatic AI orchestrator.**

Think of it like:
- ✅ Slack for AI agents (message passing)
- ✅ GitHub for code discussions (collaboration hub)
- ❌ NOT AutoGPT (doesn't spawn AI agents automatically)
- ❌ NOT a multi-LLM caller (doesn't call OpenAI/Anthropic APIs)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    agents-council MCP Server                │
│                                                              │
│  - Stores session state in ~/.agents-council/state.json    │
│  - Provides MCP tools for coordination                      │
│  - Broadcasts messages between connected agents             │
│  - Does NOT call LLM APIs                                   │
└─────────────────────────────────────────────────────────────┘
         ↑                    ↑                    ↑
         │                    │                    │
    ┌────┴────┐          ┌────┴────┐          ┌────┴────┐
    │ Agent 1 │          │ Agent 2 │          │ Agent 3 │
    │ (Human  │          │ (Human  │          │ (Human  │
    │  using  │          │  using  │          │  using  │
    │ Claude  │          │  Codex  │          │ Gemini  │
    │  Code)  │          │   CLI)  │          │   CLI)  │
    └─────────┘          └─────────┘          └─────────┘
```

## Two Usage Models

### Model 1: Manual Multi-Agent Collaboration (Primary Use Case)

**Scenario**: You want multiple AI sessions (Claude Code, Codex, Gemini) to collaborate on a complex problem.

**Example Workflow**:

1. **Developer A (using Claude Code)** starts a council:
   ```bash
   # In Claude Code terminal
   > Use the start_council tool to ask: "Design a caching strategy for our API"
   ```

2. **Developer B (using Codex)** joins the council:
   ```bash
   # In Codex terminal
   > Use the join_council tool to see the request
   > Use send_response tool to reply: "I recommend Redis with LRU eviction"
   ```

3. **Developer A** checks for updates:
   ```bash
   # Back in Claude Code
   > Use get_current_session_data tool to see Codex's response
   > Use send_response to add: "Good idea! Let's also add Memcached for query caching"
   ```

4. **Developer B** sees the update and closes:
   ```bash
   # In Codex
   > Use get_current_session_data to see Claude's response
   > Use close_council with conclusion: "Agreed on Redis + Memcached architecture"
   ```

**Key Point**: Each agent session is controlled by a human developer using their AI assistant. agents-council just passes messages between them.

### Model 2: Automated Summoning (Requires Local CLI Tools)

**Scenario**: You want to automatically invoke Claude or Codex to respond to your question.

**Prerequisites**:
- **Claude**: Claude Code CLI installed (`npm install -g @anthropics/claude-code`) and authenticated
- **Codex**: Codex SDK/CLI authenticated

**Example Workflow**:

1. **Start a council**:
   ```bash
   curl -X POST http://localhost:8099/api/servers/agents-council/tools/start_council/run \
     -H "Content-Type: application/json" \
     -d '{
       "request": "How should we handle database migrations in production?",
       "agent_name": "DevOps-Lead"
     }'
   ```

2. **Summon Claude to respond**:
   ```bash
   curl -X POST http://localhost:8099/api/servers/agents-council/tools/summon_agent/run \
     -H "Content-Type: application/json" \
     -d '{"agent": "Claude"}'
   ```

   **What happens**:
   - agents-council spawns Claude Code CLI as a subprocess
   - Passes the request: "How should we handle database migrations in production?"
   - Claude reads the request, thinks, and posts a response
   - Response is stored in the council session

3. **Check for Claude's response**:
   ```bash
   curl -X POST http://localhost:8099/api/servers/agents-council/tools/get_current_session_data/run \
     -H "Content-Type: application/json" \
     -d '{}'
   ```

**Limitations**:
- Requires local Claude Code or Codex CLI installation
- Uses your local authentication (API keys, tokens)
- Summoned agents run with read-only access by default

---

## Why No Automatic Responses?

### What You Experienced

```
You: start_council("How to optimize queries?", agent_name="TestAgent")
     → Council created ✅

You: send_response("Use indexes and query caching")
     → Your response stored ✅

You: get_current_session_data()
     → Returns: Only YOUR response (TestAgent's response)
     → No other agents have joined! ❌
```

### Why?

Because agents-council is a **passive coordinator**, not an **active AI caller**:

- ✅ It stores your question
- ✅ It stores your response
- ✅ It makes the data available to OTHER agents
- ❌ It does NOT call OpenAI/Anthropic/Gemini APIs
- ❌ It does NOT spawn AI agents automatically (unless summoned)
- ❌ It does NOT generate responses on its own

### To Get Responses

You need ONE of these:

**Option 1**: Add another agent instance (named agent) and manually send responses:
```bash
# Add a second agent
curl -X POST http://localhost:8099/api/servers \
  -d '{
    "id": "council-agent2",
    "name": "Council Agent 2",
    "command": "npx",
    "args": ["-y", "agents-council@latest", "mcp", "-n", "Agent2"],
    "env": {}
  }'

# Start it
curl -X POST http://localhost:8099/api/servers/council-agent2/start

# Join the council
curl -X POST http://localhost:8099/api/servers/council-agent2/tools/join_council/run \
  -d '{"agent_name": "Agent2"}'

# Send response as Agent2
curl -X POST http://localhost:8099/api/servers/council-agent2/tools/send_response/run \
  -d '{"content": "I suggest using connection pooling and prepared statements"}'
```

**Option 2**: Use summon_agent (requires local CLI tools):
```bash
curl -X POST http://localhost:8099/api/servers/agents-council/tools/summon_agent/run \
  -d '{"agent": "Claude"}'
```

**Option 3**: Connect multiple human developers, each using their own AI assistant (Claude Code, Codex, etc.)

---

## Real-World Use Cases

### Use Case 1: Code Review Collaboration

**Scenario**: You want Claude Code and Codex to review your pull request together.

**Setup**:
1. You (using Claude Code) start a council with the PR description
2. Your colleague (using Codex) joins the council
3. Both AI assistants analyze the code and provide feedback
4. You consolidate the feedback and close the council

**Value**: Get diverse perspectives from different AI models without manually copying context between sessions.

### Use Case 2: Architecture Decision

**Scenario**: Deciding between microservices vs monolith architecture.

**Setup**:
1. Developer A (Claude Code) starts council: "Microservices vs monolith for our app?"
2. Developer B (Gemini CLI) joins and argues for microservices
3. Developer C (Codex) joins and argues for monolith
4. All agents see each other's responses in real-time
5. Team closes with consensus decision

**Value**: Async collaboration with persistent state - agents can join/leave without losing context.

### Use Case 3: Automated Expert Summoning

**Scenario**: You need quick feedback from Claude and Codex simultaneously.

**Setup**:
1. Start council with complex question
2. Summon Claude: `summon_agent("Claude")`
3. Summon Codex: `summon_agent("Codex")`
4. Both AI agents automatically respond
5. Close council with synthesized answer

**Value**: Get multiple AI perspectives without manual back-and-forth.

---

## State Persistence

All session data is stored in `~/.agents-council/state.json`:

```json
{
  "version": 1,
  "session": {
    "id": "session-uuid",
    "status": "active",
    "current_request_id": "request-uuid"
  },
  "requests": [
    {
      "id": "request-uuid",
      "content": "How to optimize queries?",
      "created_by": "TestAgent",
      "status": "open"
    }
  ],
  "feedback": [
    {
      "id": "feedback-uuid",
      "author": "TestAgent",
      "content": "Use indexes and caching",
      "created_at": "2026-01-28T..."
    }
  ],
  "participants": [
    {
      "agent_name": "TestAgent",
      "last_seen": "2026-01-28T..."
    }
  ]
}
```

**Key Benefits**:
- Sessions survive server restarts
- All agents share the same state file
- Can resume councils at any time

---

## Comparison with Other Tools

| Feature | agents-council | AutoGPT | LangChain Agents | ai-council |
|---------|---------------|---------|------------------|------------|
| **Purpose** | Agent coordination | Autonomous AI | Agent framework | Multi-LLM consensus |
| **Calls LLM APIs** | ❌ (only via summon) | ✅ | ✅ | ✅ |
| **Requires API Keys** | ❌ (unless summon) | ✅ | ✅ | ✅ |
| **Message Passing** | ✅ | ❌ | ❌ | ❌ |
| **Multi-Agent Collab** | ✅ | ❌ | Partial | ❌ |
| **State Persistence** | ✅ | ✅ | Partial | ❌ |
| **Human-in-Loop** | ✅ | ❌ | Partial | ❌ |

---

## Summary

**agents-council is a coordination platform, not an AI caller.**

### What it DOES:
- ✅ Provides a shared message bus for AI agent sessions
- ✅ Stores session state persistently
- ✅ Enables async collaboration between developers using different AI tools
- ✅ Supports manual message passing and automated summoning

### What it DOES NOT do:
- ❌ Automatically spawn AI agents to answer questions
- ❌ Call OpenAI/Anthropic/Gemini APIs directly
- ❌ Generate responses without human involvement (except summon)
- ❌ Require API keys for basic operation

### To Get AI Responses:
1. **Multiple agents**: Add named agents and send responses from each
2. **Summon feature**: Use summon_agent if Claude Code/Codex CLI installed
3. **Multi-developer**: Have multiple humans using different AI assistants collaborate

The power of agents-council is **coordination and persistence**, not **automatic AI orchestration**.
