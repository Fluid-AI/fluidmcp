Enable non-programmers to use AI coding agents (Claude Code, OpenCode) in YOLO mode without manual approvals, safely isolated in Docker containers.

**Origin**: Abhinav's request to run OpenCode and Claude Code as MCP servers in sandboxed environments for non-programming tasks.

---

## Architecture Decision

### ✅ Chosen Approach: Simple MCP Server (Not Complex Orchestrator)

**Mental Model**: Python REPL MCP server, but with Docker containers instead of in-process execution.

```
User Request
  → FluidMCP Gateway
    → sandbox-mcp (MCP server with 3 tools)
      → SandboxManager (Python class, ~200 lines)
        → docker run (container per session)
```

**Key Insight**: `SandboxManager` is a **helper class**, NOT a separate microservice.

### ❌ Rejected Approach: Separate Orchestrator Service
- Too complex for MVP
- Premature abstraction
- More moving parts than needed
- Would use Arrakis/AgentBox as separate services (overkill)

---

## Research Completed

### Sandbox Solutions Evaluated

1. **Arrakis** (https://github.com/abshkbh/arrakis)
   - 747 stars
   - MicroVM isolation (cloud-hypervisor)
   - REST API + Python SDK (`py-arrakis`)
   - Snapshot/restore support
   - **Status**: Researched but too complex for initial implementation

2. **agentbox** (https://github.com/Michaelliv/agentbox)
   - 34 stars
   - Python-based
   - Simpler than Arrakis
   - **Status**: Could be used later, not in MVP

3. **SWE-ReX** (https://github.com/SWE-agent/SWE-ReX)
   - 411 stars
   - Massively parallel
   - Powers SWE-agent
   - **Status**: Evaluated but not needed for MVP

---

## Implementation Plan

### File Structure (~400-500 lines total)

```
fluidmcp/mcp_servers/
├── sandbox_server.py      # MCP server with 3 tools (~150 lines)
├── sandbox_manager.py     # Docker wrapper class (~200 lines)
├── docker_backend.py      # Docker SDK operations (~100 lines)
└── safety_policies.py     # YOLO Level 2 validations (~50 lines)

docker/
└── sandbox/
    └── Dockerfile         # Claude Code + common tools

examples/
└── sandbox-config.json    # FluidMCP configuration

docs/
└── SANDBOX_MCP_USAGE.md   # User documentation
```

### MCP Tools (3 Total)

1. **`execute_task`**
   - Description: Execute AI coding task in isolated container
   - Inputs: `task` (string), `session_id` (optional), `agent` (claude-code|opencode)
   - Output: `session_id`, `status`, `result`

2. **`get_files`**
   - Description: Download files from sandbox workspace
   - Inputs: `session_id` (string), `paths` (list of strings)
   - Output: Base64-encoded file contents or zip

3. **`cleanup_session`**
   - Description: Stop and remove container
   - Inputs: `session_id` (string)
   - Output: `status`, `message`

### Session Model (Hybrid - Option C)

- **Default**: Stateless (new container per task)
  - Simple, no tracking needed
  - Good for one-shot tasks

- **Optional**: Stateful (pass `session_id` to reuse container)
  - Enables multi-step workflows
  - Container persists between calls
  - Files remain in `/workspace`

- **Cleanup**:
  - Auto-cleanup after 30 minutes of inactivity
  - Manual cleanup via `cleanup_session` tool
  - Background task checks inactive containers every 60 seconds

### Safety Boundaries (YOLO Mode Level 2)

**Allowed Operations**:
- ✅ File read/write/delete (in `/workspace` only)
- ✅ Network requests (external APIs, no private networks)
- ✅ Data processing (pandas, CSV, JSON, etc.)
- ✅ Code execution (Python, Node.js, etc.)

**Blocked Operations**:
- ❌ Destructive commands (`rm -rf /`, `mkfs`, `format`, fork bombs)
- ❌ Privilege escalation (`sudo`, `chmod 777`, `chown root`)
- ❌ Private network access (localhost, 192.168.*, 10.*, 172.16-31.*)
- ❌ System modification (outside `/workspace`)

**Resource Limits**:
- Max execution time: 5 minutes per command
- Max file size: 10MB per file
- Max workspace size: 1GB total
- Memory: 4GB per container
- CPU: 2 cores per container

**Allowed File Types**:
```
.txt, .md, .csv, .json, .pdf, .xlsx, .xls,
.py, .js, .ts, .html, .css, .xml, .yaml, .yml
```

---

## Implementation Steps (Todo List)

1. ⏳ Create Dockerfile with Claude Code and common tools
2. ⏳ Build docker_backend.py (Docker SDK wrapper)
3. ⏳ Build sandbox_manager.py (session + container lifecycle)
4. ⏳ Build sandbox_server.py (MCP server with 3 tools)
5. ⏳ Add safety_policies.py (YOLO Level 2 validations)
6. ⏳ Create FluidMCP config example
7. ⏳ Test with sample task end-to-end
8. ⏳ Write README with usage examples

---

## Critical Decisions Needed Before Implementation

### Decision 1: Claude Code Installation in Docker

**Problem**: How do we get Claude Code CLI inside the Docker image?

**Options**:
- A) Use official Claude Code Docker image (if exists)
- B) Install from npm: `npm install -g @anthropic/claude-code`
- C) Bundle the CLI binary
- D) Use Python SDK/API instead of CLI

**Status**: ⚠️ PENDING - Need to decide

---

### Decision 2: Agent Execution Method

**Problem**: How does the agent execute tasks inside the container?

**Options**:
- A) Shell command: `claude code --yolo "analyze data.csv"`
- B) Python API: `from claude import Client; client.run_task(...)`
- C) AgentBox interface (need to research)
- D) Direct Anthropic API calls with custom prompting

**Status**: ⚠️ PENDING - Need to decide

---

### Decision 3: Agent Support Scope

**Problem**: Which agents to support initially?

**Options**:
- A) Claude Code only (simpler, faster MVP)
- B) Claude Code + OpenCode (Abhinav mentioned both)
- C) Extensible design for multiple agents

**Recommendation**: Start with A, design for C

**Status**: ⚠️ PENDING - Need to decide

---

### Decision 4: AgentBox Integration

**Problem**: Should we use AgentBox or build custom?

**Research Findings**:
- AgentBox is "a computer for your agent"
- 34 stars, Python-based
- Need to understand its interface/API

**Options**:
- A) Research and use AgentBox (Abhinav mentioned it)
- B) Skip AgentBox, use direct Docker
- C) Support both (AgentBox + custom)

**Status**: ⚠️ PENDING - Need to decide

---

### Decision 5: File Exchange Mechanism

**Problem**: How do files get in/out of containers?

**Current Plan**:
- **IN**: Mount host directory as `/workspace` volume
- **OUT**: `docker cp` to extract files, return via MCP

**Options**:
- A) Volume mounts (simple, performant)
- B) Docker cp (current plan)
- C) Network file transfer (HTTP upload/download)
- D) Shared volume with FluidMCP

**Status**: ⚠️ PENDING - Need to confirm approach

---

## Code Skeletons

### Dockerfile (Base Image)
```dockerfile
FROM python:3.11-slim

# Install common tools for non-programmers
RUN pip install \
    pandas openpyxl requests beautifulsoup4 \
    python-docx pillow matplotlib seaborn \
    jupyter notebook

# Install Node.js for npm packages
RUN apt-get update && apt-get install -y nodejs npm

# TODO: Install Claude Code CLI
# Option B: RUN npm install -g @anthropic/claude-code

# Create workspace
WORKDIR /workspace

# Default command (wait for instructions)
CMD ["sleep", "infinity"]
```

### docker_backend.py
```python
import docker
from typing import List, Optional

class DockerBackend:
    """Wrapper around Docker SDK for container operations"""

    def __init__(self, image_name: str = "fluidmcp/sandbox:latest"):
        self.client = docker.from_env()
        self.image_name = image_name

    def create_container(self, session_id: str) -> docker.models.containers.Container:
        """Create and start a new container"""
        pass

    def exec_command(self, container_id: str, command: str, timeout: int = 300) -> str:
        """Execute command in container and return output"""
        pass

    def copy_files_from(self, container_id: str, paths: List[str]) -> bytes:
        """Copy files from container (returns tar archive)"""
        pass

    def remove_container(self, container_id: str, force: bool = True) -> None:
        """Stop and remove container"""
        pass

    def list_containers(self, filters: dict = None) -> List[docker.models.containers.Container]:
        """List containers with optional filters"""
        pass

    def get_container_stats(self, container_id: str) -> dict:
        """Get container resource usage stats"""
        pass
```

### sandbox_manager.py
```python
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from docker_backend import DockerBackend

class SandboxSession:
    """Represents a user sandbox session"""
    def __init__(self, session_id: str, container_id: str, user_id: str):
        self.session_id = session_id
        self.container_id = container_id
        self.user_id = user_id
        self.created_at = datetime.now()
        self.last_activity = datetime.now()

class SandboxManager:
    """Manages sandbox lifecycle and session tracking"""

    def __init__(self, docker_backend: DockerBackend, cleanup_interval: int = 30):
        self.docker = docker_backend
        self.sessions: Dict[str, SandboxSession] = {}
        self.cleanup_interval_minutes = cleanup_interval
        self._cleanup_task = None

    async def initialize(self):
        """Start background cleanup task"""
        self._cleanup_task = asyncio.create_task(self._auto_cleanup_loop())

    async def shutdown(self):
        """Cleanup all sessions and stop background tasks"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
        for session_id in list(self.sessions.keys()):
            await self.cleanup_session(session_id)

    async def execute_task(
        self,
        task: str,
        user_id: str,
        session_id: Optional[str] = None,
        agent: str = "claude-code"
    ) -> dict:
        """Execute task in container (create new or reuse existing)"""
        pass

    async def get_files(self, session_id: str, paths: List[str]) -> bytes:
        """Download files from sandbox workspace"""
        pass

    async def cleanup_session(self, session_id: str) -> dict:
        """Destroy container and cleanup session"""
        pass

    async def get_session_status(self, session_id: str) -> dict:
        """Get session information"""
        pass

    async def _auto_cleanup_loop(self):
        """Background task to cleanup inactive sessions"""
        while True:
            await asyncio.sleep(60)  # Check every minute
            await self._cleanup_inactive_sessions()

    async def _cleanup_inactive_sessions(self):
        """Remove sessions inactive for > cleanup_interval_minutes"""
        pass
```

### sandbox_server.py
```python
#!/usr/bin/env python3
"""
Sandboxed AI Agent MCP Server

Simple MCP server that spawns Docker containers for AI agent execution.
"""

import asyncio
import json
import logging
from typing import List

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from sandbox_manager import SandboxManager
from docker_backend import DockerBackend

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('sandbox-mcp')

# Initialize components
docker_backend = DockerBackend()
sandbox_manager = SandboxManager(docker_backend)

# Create MCP server
app = Server("sandbox-mcp")

@app.list_tools()
async def list_tools() -> List[types.Tool]:
    """List available MCP tools"""
    return [
        types.Tool(
            name="execute_task",
            description="Execute AI coding task in isolated Docker container",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Natural language task description"},
                    "user_id": {"type": "string", "description": "User identifier"},
                    "session_id": {"type": "string", "description": "Optional: reuse existing session"},
                    "agent": {"type": "string", "enum": ["claude-code", "opencode"], "default": "claude-code"}
                },
                "required": ["task", "user_id"]
            }
        ),
        types.Tool(
            name="get_files",
            description="Download files from sandbox workspace",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "paths": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["session_id", "paths"]
            }
        ),
        types.Tool(
            name="cleanup_session",
            description="Stop and remove sandbox container",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"}
                },
                "required": ["session_id"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> List[types.TextContent]:
    """Handle MCP tool calls"""
    try:
        if name == "execute_task":
            result = await sandbox_manager.execute_task(
                task=arguments["task"],
                user_id=arguments["user_id"],
                session_id=arguments.get("session_id"),
                agent=arguments.get("agent", "claude-code")
            )
        elif name == "get_files":
            result = await sandbox_manager.get_files(
                session_id=arguments["session_id"],
                paths=arguments["paths"]
            )
        elif name == "cleanup_session":
            result = await sandbox_manager.cleanup_session(
                session_id=arguments["session_id"]
            )
        else:
            result = {"status": "error", "error": f"Unknown tool: {name}"}

        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        logger.error(f"Error in tool {name}: {e}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"status": "error", "error": str(e)}, indent=2)
        )]

async def main():
    """Main entry point"""
    logger.info("Starting Sandbox MCP Server")

    await sandbox_manager.initialize()

    try:
        async with stdio_server() as streams:
            await app.run(streams[0], streams[1], app.create_initialization_options())
    finally:
        await sandbox_manager.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
```

### safety_policies.py
```python
"""
Safety policies for YOLO Mode Level 2
"""

import re
from typing import Tuple

BLOCKED_COMMANDS = {
    'rm -rf /', 'dd if=', 'mkfs', 'format', ':(){:|:&};:',  # Destructive
    'chmod 777', 'chown root', 'sudo su',  # Privilege escalation
}

RESTRICTED_NETWORK_PATTERNS = [
    r'127\.0\.0\.1', r'localhost', r'0\.0\.0\.0',
    r'192\.168\.', r'10\.', r'172\.(1[6-9]|2[0-9]|3[0-1])\.',
]

ALLOWED_FILE_EXTENSIONS = {
    '.txt', '.md', '.csv', '.json', '.pdf', '.xlsx', '.xls',
    '.py', '.js', '.ts', '.html', '.css', '.xml', '.yaml', '.yml'
}

def validate_command(command: str) -> Tuple[bool, str]:
    """Validate command against safety policies"""
    command_lower = command.lower()
    for blocked in BLOCKED_COMMANDS:
        if blocked in command_lower:
            return False, f"Blocked command pattern: {blocked}"
    return True, ""

def validate_network_access(url: str) -> Tuple[bool, str]:
    """Validate network access against safety policies"""
    for pattern in RESTRICTED_NETWORK_PATTERNS:
        if re.search(pattern, url):
            return False, f"Access to private/local networks is restricted"
    return True, ""

def validate_file_path(path: str) -> Tuple[bool, str]:
    """Validate file operation against safety policies"""
    # Check extension
    ext = path[path.rfind('.'):] if '.' in path else ''
    if ext and ext.lower() not in ALLOWED_FILE_EXTENSIONS:
        return False, f"File type {ext} not allowed"

    # Check for path traversal
    if '..' in path or path.startswith('/'):
        return False, "Path traversal not allowed"

    return True, ""
```

### FluidMCP Configuration Example
```json
{
  "mcpServers": {
    "sandbox": {
      "command": "python",
      "args": ["-m", "fluidmcp.mcp_servers.sandbox_server"],
      "env": {
        "DOCKER_IMAGE": "fluidmcp/sandbox:latest",
        "AUTO_CLEANUP_MINUTES": "30",
        "YOLO_LEVEL": "2",
        "MAX_EXECUTION_TIME": "300",
        "MAX_FILE_SIZE_MB": "10"
      }
    }
  }
}
```

---

## Testing Plan

### Test 1: Basic Execution
```bash
# Start FluidMCP
fluidmcp run examples/sandbox-config.json --file --start-server

# Test via MCP
curl -X POST http://localhost:8099/sandbox/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "params": {
      "name": "execute_task",
      "arguments": {
        "task": "Create a CSV file with 10 random numbers",
        "user_id": "test-user",
        "agent": "claude-code"
      }
    }
  }'
```

### Test 2: Multi-Step Session
```bash
# Step 1: Create and analyze data
curl ... -d '{"name": "execute_task", "arguments": {"task": "Create data.csv", ...}}'
# Returns: {"session_id": "abc123", ...}

# Step 2: Reuse session to process data
curl ... -d '{"name": "execute_task", "arguments": {"task": "Process data.csv", "session_id": "abc123", ...}}'

# Step 3: Download files
curl ... -d '{"name": "get_files", "arguments": {"session_id": "abc123", "paths": ["/workspace/data.csv"]}}'

# Step 4: Cleanup
curl ... -d '{"name": "cleanup_session", "arguments": {"session_id": "abc123"}}'
```

### Test 3: Safety Boundaries
```bash
# Should be blocked
curl ... -d '{"name": "execute_task", "arguments": {"task": "Run: rm -rf /", ...}}'
# Expected: {"status": "blocked", "error": "Blocked command pattern: rm -rf /"}
```

---

## Future Enhancements (Not in MVP)

1. **Multiple Agent Support**: OpenCode, Cursor, Windsurf
2. **Arrakis Integration**: MicroVM isolation for production
3. **AgentBox Integration**: If beneficial after research
4. **Snapshot/Restore**: Save and restore sandbox state
5. **Resource Monitoring**: Track CPU/memory usage
6. **Persistent Workspaces**: Optional data persistence
7. **Multi-tenant Isolation**: Stronger user separation
8. **API Rate Limiting**: Per-user quotas
9. **Audit Logging**: Track all operations
10. **Web UI**: Visual interface for non-technical users

---

## References

- **Original Discussion**: Conversation with Abhinav about YOLO mode + sandbox
- **Research Agent**: Task ID `a4d31a5` (Arrakis research)
- **Plan File**: `/home/codespace/.claude/plans/quizzical-swinging-russell.md`
- **Arrakis Repo**: https://github.com/abshkbh/arrakis
- **AgentBox Repo**: https://github.com/Michaelliv/agentbox
- **SWE-ReX Repo**: https://github.com/SWE-agent/SWE-ReX

---

## Next Steps When Resuming

1. **Answer 5 critical decisions** (marked with ⚠️ above)
2. **Start with Dockerfile** (build base image)
3. **Implement docker_backend.py** (test Docker SDK operations)
4. **Implement sandbox_manager.py** (test session management)
5. **Implement sandbox_server.py** (test MCP tools)
6. **End-to-end testing** with FluidMCP

---

**Status**: Ready to implement once decisions are made.

**Estimated Time**: 2-4 hours for MVP implementation.
