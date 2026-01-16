# Sandboxed YOLO Agent MCP Server - Implementation Plan

**Status**: Ready for Implementation
**Created**: 2026-01-29
**Target**: Non-programmers using AI agents for automation tasks

---

## Executive Summary

Create a **sandbox-mcp** server that enables non-technical users to run AI coding agents (Claude Code, OpenCode) in safe, isolated Docker environments with auto-approval ("YOLO mode"). Users describe tasks in natural language, and the agent autonomously executes file processing, data analysis, and automation without requiring programming knowledge.

---

## Key Decisions (Finalized ✅)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Architecture** | Simple MCP Server (not orchestrator) | Python REPL pattern, ~400 lines total |
| **Sandbox Backend** | Plain Docker (Phase 1) | Fast to build, swap to Arrakis later |
| **Primary Agent** | Mock Agent (Phase 1) | Prove infrastructure works first |
| **Real Agent** | Claude API (Phase 2) | Use Anthropic SDK, not CLI |
| **File Exchange** | Volume mounts + docker cp | Flexible for input/output |
| **Session Model** | Hybrid (stateless + optional reuse) | Simple default, multi-step capable |
| **YOLO Level** | Level 2 (Files + Network) | Safe for non-programmers |

---

## Architecture

### High-Level Flow

```
User Request (Natural Language Task)
    ↓
FluidMCP Gateway (HTTP/MCP)
    ↓
sandbox-mcp Server (MCP stdio)
    ↓
SandboxManager (Python class)
    ↓
Docker Container (isolated workspace)
    ↓
Agent Execution (mock → Claude API later)
    ↓
Results returned to user
```

### Component Diagram

```
fluidmcp/mcp_servers/
├── sandbox_server.py         # MCP server (~150 lines)
├── sandbox_manager.py        # Session management (~200 lines)
├── docker_backend.py         # Docker operations (~100 lines)
└── safety_policies.py        # YOLO Level 2 rules (~50 lines)

docker/sandbox/
└── Dockerfile                # Base image with tools

examples/
└── sandbox-config.json       # FluidMCP config
```

**Total Code**: ~500 lines

---

## MCP Tools (3 Total)

### Tool 1: `execute_task`

**Purpose**: Execute a task in isolated sandbox

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "task": {
      "type": "string",
      "description": "Natural language task description",
      "example": "Analyze this CSV and create a summary"
    },
    "user_id": {
      "type": "string",
      "description": "User identifier for isolation"
    },
    "session_id": {
      "type": "string",
      "description": "Optional: reuse existing container"
    },
    "files": {
      "type": "array",
      "description": "Files to upload to workspace",
      "items": {
        "type": "object",
        "properties": {
          "path": {"type": "string", "example": "data.csv"},
          "content": {"type": "string", "description": "Base64-encoded"}
        }
      }
    },
    "timeout": {
      "type": "integer",
      "default": 300,
      "description": "Max execution time (seconds)"
    }
  },
  "required": ["task", "user_id"]
}
```

**Response**:
```json
{
  "session_id": "sandbox_user123_1738195847",
  "status": "completed|failed|timeout",
  "output": "Task completed. Created summary.txt",
  "files_created": ["summary.txt", "chart.png"],
  "duration_seconds": 23.4,
  "error": null
}
```

---

### Tool 2: `get_files`

**Purpose**: Download files created by agent

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "session_id": {"type": "string"},
    "paths": {
      "type": "array",
      "items": {"type": "string"},
      "example": ["summary.txt", "chart.png"]
    }
  },
  "required": ["session_id", "paths"]
}
```

**Response**:
```json
{
  "files": [
    {
      "path": "summary.txt",
      "content": "base64EncodedContent...",
      "size_bytes": 1234,
      "mime_type": "text/plain"
    }
  ]
}
```

---

### Tool 3: `cleanup_session`

**Purpose**: Stop container and cleanup workspace

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "session_id": {"type": "string"}
  },
  "required": ["session_id"]
}
```

**Response**:
```json
{
  "status": "success",
  "message": "Session cleaned up",
  "session_id": "sandbox_user123_1738195847"
}
```

---

## Implementation Details

### Phase 1: Infrastructure (Mock Agent)

**Goal**: Build working MCP server with Docker containers, prove architecture

#### File 1: `sandbox_server.py` (~150 lines)

**Purpose**: MCP server exposing 3 tools via stdin/stdout

```python
#!/usr/bin/env python3
"""
Sandbox MCP Server

Simple MCP server that spawns Docker containers for isolated task execution.
Phase 1: Uses mock agent to prove infrastructure.
Phase 2: Replace with Claude API.
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('sandbox-mcp')

# Initialize
docker_backend = DockerBackend(image_name="fluidmcp/sandbox:latest")
sandbox_manager = SandboxManager(docker_backend)

app = Server("sandbox-mcp")

@app.list_tools()
async def list_tools() -> List[types.Tool]:
    return [
        types.Tool(
            name="execute_task",
            description="Execute task in isolated Docker container with auto-approval",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Task description"},
                    "user_id": {"type": "string", "description": "User ID"},
                    "session_id": {"type": "string", "description": "Optional session ID"},
                    "files": {"type": "array", "items": {"type": "object"}},
                    "timeout": {"type": "integer", "default": 300}
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
            description="Clean up sandbox resources",
            inputSchema={
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> List[types.TextContent]:
    try:
        if name == "execute_task":
            result = await sandbox_manager.execute_task(
                task=arguments["task"],
                user_id=arguments["user_id"],
                session_id=arguments.get("session_id"),
                files=arguments.get("files", []),
                timeout=arguments.get("timeout", 300)
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
        logger.error(f"Error in {name}: {e}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"status": "error", "error": str(e)}, indent=2)
        )]

async def main():
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

---

#### File 2: `sandbox_manager.py` (~200 lines)

**Purpose**: Manage container lifecycle, sessions, cleanup

```python
"""
Sandbox Manager

Manages Docker container sessions, workspace, and cleanup.
"""

import asyncio
import base64
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import shutil

from docker_backend import DockerBackend

logger = logging.getLogger('sandbox-mcp')

class SandboxSession:
    """Represents an active sandbox session"""
    def __init__(self, session_id: str, container_id: str, user_id: str, workspace: Path):
        self.session_id = session_id
        self.container_id = container_id
        self.user_id = user_id
        self.workspace = workspace
        self.created_at = datetime.now()
        self.last_activity = datetime.now()

class SandboxManager:
    """Manages sandbox lifecycle and sessions"""

    def __init__(self, docker_backend: DockerBackend):
        self.docker = docker_backend
        self.sessions: Dict[str, SandboxSession] = {}
        self.workspace_base = Path("/tmp/fluidmcp-sandboxes")
        self.cleanup_interval_minutes = 30
        self._cleanup_task = None

    async def initialize(self):
        """Start background cleanup task"""
        self.workspace_base.mkdir(parents=True, exist_ok=True)
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Sandbox manager initialized")

    async def shutdown(self):
        """Cleanup all sessions"""
        logger.info("Shutting down sandbox manager...")
        if self._cleanup_task:
            self._cleanup_task.cancel()
        for session_id in list(self.sessions.keys()):
            await self.cleanup_session(session_id)

    async def execute_task(
        self,
        task: str,
        user_id: str,
        session_id: Optional[str],
        files: List[Dict],
        timeout: int
    ) -> Dict:
        """Execute task in container"""
        try:
            # Create or reuse session
            if session_id and session_id in self.sessions:
                session = self.sessions[session_id]
                session.last_activity = datetime.now()
                logger.info(f"Reusing session {session_id}")
            else:
                session = await self._create_session(user_id)
                session_id = session.session_id
                logger.info(f"Created new session {session_id}")

            # Upload files to workspace
            await self._upload_files(session.workspace, files)

            # Execute task in container
            result = await self.docker.exec_command(
                container_id=session.container_id,
                command=self._build_command(task),
                timeout=timeout
            )

            # List created files
            created_files = self._list_workspace_files(session.workspace)

            return {
                "session_id": session_id,
                "status": "completed",
                "output": result,
                "files_created": created_files,
                "duration_seconds": timeout  # TODO: track actual duration
            }

        except asyncio.TimeoutError:
            return {
                "session_id": session_id,
                "status": "timeout",
                "error": f"Task exceeded {timeout}s timeout"
            }
        except Exception as e:
            logger.error(f"Error executing task: {e}")
            return {
                "session_id": session_id,
                "status": "failed",
                "error": str(e)
            }

    async def get_files(self, session_id: str, paths: List[str]) -> Dict:
        """Download files from workspace"""
        if session_id not in self.sessions:
            raise ValueError(f"Session not found: {session_id}")

        session = self.sessions[session_id]
        session.last_activity = datetime.now()

        files = []
        for path in paths:
            file_path = session.workspace / path
            if file_path.exists():
                content = base64.b64encode(file_path.read_bytes()).decode()
                files.append({
                    "path": path,
                    "content": content,
                    "size_bytes": file_path.stat().st_size,
                    "mime_type": self._detect_mime(file_path)
                })

        return {"files": files}

    async def cleanup_session(self, session_id: str) -> Dict:
        """Cleanup session resources"""
        if session_id not in self.sessions:
            return {"status": "error", "error": "Session not found"}

        session = self.sessions[session_id]

        # Stop container
        await self.docker.remove_container(session.container_id)

        # Delete workspace
        if session.workspace.exists():
            shutil.rmtree(session.workspace)

        # Remove from sessions
        del self.sessions[session_id]

        logger.info(f"Cleaned up session {session_id}")
        return {"status": "success", "message": "Session cleaned up"}

    async def _create_session(self, user_id: str) -> SandboxSession:
        """Create new sandbox session"""
        session_id = f"sandbox_{user_id}_{int(time.time())}"
        workspace = self.workspace_base / session_id
        workspace.mkdir(parents=True, exist_ok=True)

        # Create container
        container_id = await self.docker.create_container(
            session_id=session_id,
            workspace=workspace
        )

        session = SandboxSession(session_id, container_id, user_id, workspace)
        self.sessions[session_id] = session

        return session

    async def _upload_files(self, workspace: Path, files: List[Dict]):
        """Upload files to workspace"""
        for file_info in files:
            path = workspace / file_info["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            content = base64.b64decode(file_info["content"])
            path.write_bytes(content)

    def _build_command(self, task: str) -> str:
        """Build command to execute (mock agent in Phase 1)"""
        # Phase 1: Mock agent that creates dummy output
        return f'echo "Mock agent executing: {task}" > /workspace/output.txt'

    def _list_workspace_files(self, workspace: Path) -> List[str]:
        """List all files in workspace"""
        if not workspace.exists():
            return []
        return [str(f.relative_to(workspace)) for f in workspace.rglob('*') if f.is_file()]

    def _detect_mime(self, path: Path) -> str:
        """Detect MIME type from extension"""
        ext = path.suffix.lower()
        mime_types = {
            '.txt': 'text/plain',
            '.csv': 'text/csv',
            '.json': 'application/json',
            '.pdf': 'application/pdf',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
        }
        return mime_types.get(ext, 'application/octet-stream')

    async def _cleanup_loop(self):
        """Background cleanup task"""
        while True:
            try:
                await asyncio.sleep(60)
                await self._cleanup_inactive()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

    async def _cleanup_inactive(self):
        """Cleanup inactive sessions"""
        timeout = timedelta(minutes=self.cleanup_interval_minutes)
        now = datetime.now()

        for session_id, session in list(self.sessions.items()):
            if now - session.last_activity > timeout:
                logger.info(f"Cleaning up inactive session {session_id}")
                await self.cleanup_session(session_id)
```

---

#### File 3: `docker_backend.py` (~100 lines)

**Purpose**: Docker SDK wrapper for container operations

```python
"""
Docker Backend

Wrapper around Docker SDK for container lifecycle management.
"""

import asyncio
import docker
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger('sandbox-mcp')

class DockerBackend:
    """Docker container management"""

    def __init__(self, image_name: str = "fluidmcp/sandbox:latest"):
        self.client = docker.from_env()
        self.image_name = image_name

    async def create_container(self, session_id: str, workspace: Path) -> str:
        """Create and start container"""
        try:
            # Ensure image exists
            await asyncio.to_thread(self._ensure_image)

            # Create container
            container = await asyncio.to_thread(
                self.client.containers.run,
                self.image_name,
                command="sleep infinity",  # Keep alive
                volumes={str(workspace): {'bind': '/workspace', 'mode': 'rw'}},
                detach=True,
                name=session_id,
                mem_limit="4g",
                cpu_quota=200000,  # 2 CPUs
                network_mode="bridge",
                remove=False
            )

            logger.info(f"Created container {container.id[:12]} for {session_id}")
            return container.id

        except Exception as e:
            logger.error(f"Failed to create container: {e}")
            raise

    async def exec_command(self, container_id: str, command: str, timeout: int) -> str:
        """Execute command in container"""
        try:
            container = self.client.containers.get(container_id)

            # Execute with timeout
            exec_result = await asyncio.wait_for(
                asyncio.to_thread(container.exec_run, command, workdir="/workspace"),
                timeout=timeout
            )

            output = exec_result.output.decode('utf-8')
            return output

        except asyncio.TimeoutError:
            logger.warning(f"Command timeout after {timeout}s")
            raise
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            raise

    async def remove_container(self, container_id: str):
        """Stop and remove container"""
        try:
            container = self.client.containers.get(container_id)
            await asyncio.to_thread(container.stop, timeout=5)
            await asyncio.to_thread(container.remove)
            logger.info(f"Removed container {container_id[:12]}")
        except docker.errors.NotFound:
            pass
        except Exception as e:
            logger.error(f"Failed to remove container: {e}")

    def _ensure_image(self):
        """Ensure Docker image exists"""
        try:
            self.client.images.get(self.image_name)
        except docker.errors.ImageNotFound:
            logger.info(f"Pulling image {self.image_name}...")
            self.client.images.pull(self.image_name)
```

---

#### File 4: `safety_policies.py` (~50 lines)

**Purpose**: YOLO Level 2 validation rules

```python
"""
Safety Policies

YOLO Mode Level 2: Files + Network operations with restrictions
"""

import re
from typing import Tuple

# Blocked command patterns
BLOCKED_COMMANDS = {
    'rm -rf /', 'dd if=', 'mkfs', 'format',
    'chmod 777', 'sudo', 'su'
}

# Blocked network patterns
BLOCKED_NETWORKS = [
    r'127\.0\.0\.1', r'localhost', r'0\.0\.0\.0',
    r'192\.168\.', r'10\.', r'172\.(1[6-9]|2[0-9]|3[0-1])\.'
]

def validate_command(command: str) -> Tuple[bool, str]:
    """Check if command is safe"""
    cmd_lower = command.lower()
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return False, f"Blocked: {blocked}"
    return True, ""

def validate_url(url: str) -> Tuple[bool, str]:
    """Check if URL is safe"""
    for pattern in BLOCKED_NETWORKS:
        if re.search(pattern, url):
            return False, "Private network access blocked"
    return True, ""
```

---

#### File 5: `Dockerfile` (~30 lines)

**Purpose**: Base sandbox image with common tools

```dockerfile
FROM python:3.11-slim

# Install common tools for non-programmers
RUN apt-get update && apt-get install -y \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages for data tasks
RUN pip install --no-cache-dir \
    pandas \
    openpyxl \
    requests \
    matplotlib

# Create non-root user
RUN useradd -m -u 1000 sandbox && \
    mkdir -p /workspace && \
    chown -R sandbox:sandbox /workspace

WORKDIR /workspace
USER sandbox

# Keep container alive
CMD ["sleep", "infinity"]
```

---

#### File 6: `examples/sandbox-config.json`

**Purpose**: FluidMCP configuration

```json
{
  "mcpServers": {
    "sandbox": {
      "command": "python",
      "args": ["-m", "fluidmcp.mcp_servers.sandbox_server"],
      "env": {
        "DOCKER_IMAGE": "fluidmcp/sandbox:latest",
        "WORKSPACE_BASE": "/tmp/fluidmcp-sandboxes",
        "AUTO_CLEANUP_MINUTES": "30",
        "MAX_TIMEOUT_SECONDS": "600"
      }
    }
  }
}
```

---

## Implementation Timeline

### Phase 1: Mock Agent (MVP) - 1 Day

**Goal**: Prove infrastructure works with simple mock

| Task | Time | Deliverable |
|------|------|-------------|
| Create sandbox_server.py | 2h | MCP server with 3 tools |
| Create sandbox_manager.py | 3h | Session management |
| Create docker_backend.py | 2h | Docker operations |
| Create Dockerfile | 1h | Base image |
| Test end-to-end | 2h | Working demo |

**Success Criteria**:
- ✅ Upload CSV file
- ✅ Mock agent creates output.txt
- ✅ Download output.txt
- ✅ Cleanup works
- ✅ Auto-cleanup after 30min

---

### Phase 2: Claude API Integration - 1 Day

**Goal**: Replace mock with real Claude API execution

| Task | Time | Deliverable |
|------|------|-------------|
| Add anthropic SDK | 1h | Install + configure |
| Update _build_command() | 3h | Claude API calls |
| Add streaming support | 2h | Real-time progress |
| Test real tasks | 2h | CSV analysis, web scraping |
| Documentation | 2h | Usage guide |

**Changes to sandbox_manager.py**:

```python
import anthropic

def _build_command(self, task: str) -> str:
    """Build command using Claude API"""
    # Create Python script that calls Claude API
    script = f'''
import anthropic
import os

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    system="You are a helpful assistant executing tasks in /workspace. Auto-approve all file and network operations.",
    messages=[{{"role": "user", "content": "{task}"}}]
)

print(response.content[0].text)
'''
    return f'python3 -c {shlex.quote(script)}'
```

---

### Phase 3: Polish & Production - 1 Day

**Goal**: Production-ready with monitoring and docs

| Task | Time | Deliverable |
|------|------|-------------|
| Add metrics integration | 2h | Prometheus metrics |
| Security hardening | 2h | Network restrictions |
| Error handling | 2h | Graceful failures |
| Documentation | 2h | Complete guide |

---

## Testing Strategy

### Unit Tests

```python
# tests/test_sandbox_manager.py
async def test_create_session():
    manager = SandboxManager(docker_backend)
    await manager.initialize()

    result = await manager.execute_task(
        task="Create hello.txt",
        user_id="test_user",
        session_id=None,
        files=[],
        timeout=60
    )

    assert result["status"] == "completed"
    assert result["session_id"].startswith("sandbox_test_user_")
```

### Integration Tests

```python
# tests/test_sandbox_integration.py
async def test_end_to_end_csv():
    # Upload CSV
    csv_data = "col1,col2\n1,2\n3,4"
    csv_b64 = base64.b64encode(csv_data.encode()).decode()

    result = await mcp_client.call_tool("execute_task", {
        "task": "Count rows in data.csv",
        "user_id": "test",
        "files": [{"path": "data.csv", "content": csv_b64}]
    })

    assert result["status"] == "completed"

    # Download result
    files = await mcp_client.call_tool("get_files", {
        "session_id": result["session_id"],
        "paths": ["output.txt"]
    })

    assert len(files["files"]) == 1
```

---

## Metrics

Track these metrics via FluidMCP's existing metrics system:

```python
from fluidmcp.cli.services.metrics import MetricsCollector

# In sandbox_manager.py
collector = MetricsCollector("sandbox")

collector.record_execution(
    status="completed",
    duration_seconds=23.4,
    user_id="user123"
)
```

**Key Metrics**:
- `sandbox_executions_total` (counter)
- `sandbox_duration_seconds` (histogram)
- `sandbox_active_sessions` (gauge)
- `sandbox_timeouts_total` (counter)
- `sandbox_errors_total` (counter)

---

## Security Checklist

### Container Isolation ✅
- [x] Non-root user (UID 1000)
- [x] Resource limits (2 CPU, 4GB RAM)
- [x] Network: bridge mode (outbound only)
- [x] Volume: workspace only

### Safety Policies ✅
- [x] Block destructive commands
- [x] Block private network access
- [x] Timeout enforcement
- [x] Auto-cleanup inactive sessions

### Data Protection ✅
- [x] Per-user workspace isolation
- [x] Workspace deleted after cleanup
- [x] No persistent data outside workspace

---

## Documentation

### User Guide (docs/SANDBOX.md)

```markdown
# Sandbox MCP Server

## Quick Start

1. Configure FluidMCP:
```json
{
  "mcpServers": {
    "sandbox": {
      "command": "python",
      "args": ["-m", "fluidmcp.mcp_servers.sandbox_server"]
    }
  }
}
```

2. Start FluidMCP:
```bash
fluidmcp run examples/sandbox-config.json --file --start-server
```

3. Execute task:
```bash
curl -X POST http://localhost:8099/sandbox/mcp \
  -d '{"method": "tools/call", "params": {"name": "execute_task", "arguments": {"task": "Analyze data.csv", "user_id": "user1"}}}'
```

## Use Cases

### CSV Analysis
```json
{
  "task": "Analyze sales.csv and create summary report",
  "files": [{"path": "sales.csv", "content": "base64..."}]
}
```

### Web Scraping
```json
{
  "task": "Download COVID-19 data from https://api.example.com/covid and create CSV"
}
```

### Image Processing
```json
{
  "task": "Resize all images to 800x600",
  "files": [{"path": "img1.jpg", "content": "base64..."}]
}
```
```

---

## Success Criteria

### Phase 1 (Mock Agent) ✅
- [ ] MCP server responds to all 3 tools
- [ ] Container creates and runs
- [ ] Files upload/download works
- [ ] Cleanup works
- [ ] Auto-cleanup after 30min
- [ ] No memory leaks after 100 sessions

### Phase 2 (Claude API) ✅
- [ ] Real tasks execute successfully
- [ ] CSV analysis works
- [ ] Web scraping works
- [ ] Error handling graceful
- [ ] Timeout enforced correctly

### Phase 3 (Production) ✅
- [ ] Metrics integrated
- [ ] Security hardened
- [ ] Documentation complete
- [ ] Ready for beta users

---

## Next Steps

**To start implementation**, run:

```bash
# 1. Create MCP server skeleton
cd /workspaces/fluidmcp/fluidmcp/mcp_servers
touch sandbox_server.py sandbox_manager.py docker_backend.py safety_policies.py

# 2. Create Docker image
mkdir -p docker/sandbox
cd docker/sandbox
touch Dockerfile

# 3. Create config example
mkdir -p examples
touch examples/sandbox-config.json

# 4. Start coding Phase 1 (Mock Agent)
```

**Estimated Total Time**: 3 days (8 hours/day)
- Day 1: Phase 1 (Mock Agent MVP)
- Day 2: Phase 2 (Claude API Integration)
- Day 3: Phase 3 (Polish & Production)

---

**Status**: Ready to implement
**Approval**: Pending your go-ahead

**Say "start phase 1" when ready to begin implementation.**
