# Sandboxed YOLO Agent MCP Server - Complete Implementation Plan

## Executive Summary

Create a **sandbox-mcp** server that enables non-technical users to run AI coding agents (Claude Code, OpenCode) in safe, isolated environments with auto-approval ("yolo mode"). The agent executes file processing, data analysis, and automation tasks without requiring programming knowledge.

---

## Final Decisions (Locked ✅)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **YOLO Level** | Level 3 (Files + Network + Limited System) | Enables real work while maintaining safety |
| **Primary Agent** | Claude Code | More mature, better long-horizon planning |
| **Secondary Agent** | OpenCode | Add after Claude Code is stable |
| **Sandbox Backend** | AgentBox (Phase 1) → Arrakis/MicroVM (Phase 2) | Proven solution, swappable architecture |
| **Resource Profile** | Moderate (2 CPU, 4GB RAM, 10min timeout) | Handles real tasks, prevents abuse |
| **Target Users** | Non-programmers doing business tasks | File processing, data analysis, automation |

---

## Architecture

### High-Level Flow

```
User Request
    ↓
FluidMCP Gateway (HTTP/MCP)
    ↓
sandbox-mcp Server (MCP stdin/stdout)
    ↓
YOLO Agent Orchestrator
    ↓
Docker Sandbox (AgentBox-based)
    ↓
Claude Code / OpenCode (YOLO mode enabled)
    ↓
Isolated Workspace (/workspace)
    ↓
Results returned to user
```

### Component Breakdown

```
/workspaces/fluidmcp/
├── sandbox_server.py                    # Main MCP server
├── fluidmcp/cli/services/
│   ├── sandbox_orchestrator.py         # Agent lifecycle management
│   ├── docker_sandbox.py               # Docker container management
│   └── agentbox_backend.py             # AgentBox integration (Phase 1)
├── docker/
│   ├── Dockerfile.claude-code          # Claude Code sandbox image
│   └── Dockerfile.opencode             # OpenCode sandbox image (Phase 2)
├── examples/
│   └── sandbox-config.json             # Sample configuration
└── docs/
    └── SANDBOX.md                      # Complete documentation
```

---

## Files to Create Summary

This implementation requires creating approximately **10 new files** totaling ~2,500 lines of code:

### Core Files (Required for MVP)
1. **sandbox_server.py** (~500 lines) - Main MCP server
2. **fluidmcp/cli/services/sandbox_orchestrator.py** (~300 lines) - Agent lifecycle
3. **fluidmcp/cli/services/docker_sandbox.py** (~400 lines) - Docker management
4. **fluidmcp/cli/services/yolo_policy.py** (~200 lines) - YOLO level enforcement
5. **docker/Dockerfile.claude-code** (~50 lines) - Claude Code image
6. **docker/entrypoint.sh** (~80 lines) - Container entrypoint
7. **examples/sandbox-config.json** (~50 lines) - Sample config
8. **docs/SANDBOX.md** (~500 lines) - Documentation

### Phase 2 Files
9. **fluidmcp/cli/services/agentbox_backend.py** (~150 lines) - AgentBox wrapper
10. **docker/Dockerfile.opencode** (~50 lines) - OpenCode image

### Test Files
11. **tests/test_sandbox_orchestrator.py** (~300 lines)
12. **tests/test_sandbox_security.py** (~200 lines)

---

## Detailed Technical Design

### 1. MCP Server: `sandbox_server.py`

**Purpose**: Expose sandbox execution as MCP tools via stdin/stdout JSON-RPC

**MCP Tools Exposed**:

#### Tool 1: `execute_task`
```json
{
  "name": "execute_task",
  "description": "Execute a task using AI agent in sandboxed environment. The agent will autonomously perform file operations, data processing, and automation with auto-approval enabled.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "task_description": {
        "type": "string",
        "description": "Natural language description of what to accomplish. Example: 'Analyze this CSV file and create a summary report'"
      },
      "agent": {
        "type": "string",
        "enum": ["claude-code", "opencode"],
        "default": "claude-code",
        "description": "Which AI coding agent to use"
      },
      "files": {
        "type": "array",
        "description": "Files to upload to sandbox workspace before execution",
        "items": {
          "type": "object",
          "properties": {
            "path": {
              "type": "string",
              "description": "Relative path in workspace (e.g., 'data.csv')"
            },
            "content": {
              "type": "string",
              "description": "Base64-encoded file content"
            }
          },
          "required": ["path", "content"]
        }
      },
      "working_directory": {
        "type": "string",
        "description": "Working directory path (relative to /workspace)",
        "default": "."
      },
      "timeout": {
        "type": "integer",
        "description": "Maximum execution time in seconds",
        "default": 600,
        "minimum": 60,
        "maximum": 1800
      },
      "yolo_level": {
        "type": "integer",
        "description": "Auto-approval level (3 = recommended)",
        "default": 3,
        "enum": [1, 2, 3, 4]
      }
    },
    "required": ["task_description"]
  }
}
```

**Response Format**:
```json
{
  "session_id": "sandbox-abc123",
  "status": "completed|failed|timeout",
  "output": "Agent execution log and results",
  "files_created": ["report.pdf", "summary.txt"],
  "duration_seconds": 45.2,
  "error": null
}
```

#### Tool 2: `get_sandbox_status`
Check status of a running or completed sandbox execution

#### Tool 3: `download_files`
Download files created by the agent during task execution

#### Tool 4: `cleanup_sandbox`
Clean up sandbox resources and delete workspace

---

### 2. Sandbox Orchestrator: `sandbox_orchestrator.py`

**Purpose**: Manage agent lifecycle, workspace, and execution flow

**Key Responsibilities**:
1. Create isolated workspace directory
2. Upload user files to workspace
3. Launch Docker container with appropriate config
4. Monitor execution (timeout, resource usage)
5. Capture agent output/logs
6. Handle cleanup on completion/failure

**Class Structure**:
```python
class SandboxOrchestrator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.docker_manager = DockerSandboxManager(config)
        self.active_sessions: Dict[str, SandboxSession] = {}

    async def execute_task(
        self,
        task_description: str,
        agent: str,
        files: List[Dict],
        timeout: int,
        yolo_level: int
    ) -> Dict[str, Any]:
        """Execute task in sandboxed environment"""
        # 1. Create session
        session_id = self._generate_session_id()
        workspace = self._create_workspace(session_id)

        # 2. Upload files
        self._upload_files(workspace, files)

        # 3. Launch sandbox
        container = await self.docker_manager.launch_sandbox(
            agent=agent,
            workspace=workspace,
            task=task_description,
            timeout=timeout,
            yolo_level=yolo_level
        )

        # 4. Monitor execution
        result = await self._monitor_execution(container, timeout)

        # 5. Extract results
        output_files = self._list_workspace_files(workspace)

        return {
            "session_id": session_id,
            "status": result.status,
            "output": result.logs,
            "files_created": output_files,
            "duration_seconds": result.duration
        }

    async def get_status(self, session_id: str) -> Dict[str, Any]:
        """Get sandbox execution status"""
        # Implementation details...

    def download_files(self, session_id: str, paths: List[str]) -> List[Dict[str, Any]]:
        """Download files from workspace"""
        # Implementation details...

    def cleanup(self, session_id: str):
        """Clean up sandbox resources"""
        # Implementation details...
```

---

### 3. Docker Sandbox Manager: `docker_sandbox.py`

**Purpose**: Manage Docker containers for isolated execution

**Key Features**:
- Launch containers with resource limits
- Mount workspace as volume
- Configure network isolation
- Monitor container health
- Graceful shutdown

**Class Structure**:
```python
import docker
from docker.types import Resources

class DockerSandboxManager:
    def __init__(self, config: Dict[str, Any]):
        self.client = docker.from_env()
        self.config = config

    async def launch_sandbox(
        self,
        agent: str,
        workspace: Path,
        task: str,
        timeout: int,
        yolo_level: int
    ) -> Container:
        """Launch sandboxed container"""

        # Select appropriate Docker image
        image = self._get_agent_image(agent)

        # Configure resource limits
        resources = Resources(
            mem_limit=self.config.get("memory_limit", "4g"),
            cpu_quota=self.config.get("cpu_quota", 200000),  # 2 CPUs
            pids_limit=self.config.get("pids_limit", 100)
        )

        # Configure environment
        env = {
            "TASK_DESCRIPTION": task,
            "YOLO_MODE": "true",
            "YOLO_LEVEL": str(yolo_level),
            "ANTHROPIC_API_KEY": self.config.get("anthropic_api_key"),
            "TIMEOUT": str(timeout)
        }

        # Launch container
        container = self.client.containers.run(
            image=image,
            command=self._build_command(agent, task),
            volumes={
                str(workspace): {"bind": "/workspace", "mode": "rw"}
            },
            environment=env,
            network_mode=self._get_network_mode(),
            detach=True,
            auto_remove=False,
            resources=resources,
            security_opt=["no-new-privileges"],
            read_only=False,  # /workspace needs write access
            tmpfs={"/tmp": "size=1g"},
            user="sandbox:sandbox"  # Non-root user
        )

        return container

    def _get_agent_image(self, agent: str) -> str:
        """Get Docker image for agent"""
        images = {
            "claude-code": "fluidmcp/claude-code-sandbox:latest",
            "opencode": "fluidmcp/opencode-sandbox:latest"
        }
        return images.get(agent, images["claude-code"])

    def _build_command(self, agent: str, task: str) -> List[str]:
        """Build container entrypoint command"""
        if agent == "claude-code":
            return [
                "claude-code",
                "--yolo",
                "--workspace", "/workspace",
                "--task", task
            ]
        elif agent == "opencode":
            return [
                "opencode",
                "--auto-approve",
                "--workspace", "/workspace",
                "--task", task
            ]
```

---

### 4. Docker Images

#### Dockerfile.claude-code

```dockerfile
FROM ubuntu:22.04

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    python3.11 \
    python3-pip \
    nodejs \
    npm \
    ffmpeg \
    imagemagick \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
RUN curl -fsSL https://claude.ai/install.sh | bash

# Install common Python packages for data tasks
RUN pip3 install --no-cache-dir \
    pandas \
    numpy \
    matplotlib \
    openpyxl \
    requests \
    beautifulsoup4 \
    pillow \
    pypdf2

# Create non-root user
RUN useradd -m -s /bin/bash -u 1000 sandbox && \
    mkdir -p /workspace && \
    chown -R sandbox:sandbox /workspace

# Set up workspace
WORKDIR /workspace
USER sandbox

# Default environment
ENV PYTHONUNBUFFERED=1
ENV YOLO_MODE=true

# Entrypoint
COPY entrypoint.sh /usr/local/bin/
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
```

#### entrypoint.sh

```bash
#!/bin/bash
set -e

# Parse environment variables
TASK="${TASK_DESCRIPTION:-}"
YOLO_LEVEL="${YOLO_LEVEL:-3}"
TIMEOUT="${TIMEOUT:-600}"

# Configure YOLO mode based on level
case "$YOLO_LEVEL" in
  1)
    YOLO_FLAGS="--auto-approve-read --auto-approve-write"
    ;;
  2)
    YOLO_FLAGS="--auto-approve-read --auto-approve-write --auto-approve-network"
    ;;
  3)
    YOLO_FLAGS="--auto-approve-all --restrict-privileged"
    ;;
  4)
    YOLO_FLAGS="--auto-approve-all"
    ;;
  *)
    echo "Invalid YOLO_LEVEL: $YOLO_LEVEL"
    exit 1
    ;;
esac

# Execute Claude Code with timeout
timeout "$TIMEOUT" claude-code $YOLO_FLAGS --workspace /workspace "$TASK" 2>&1

EXIT_CODE=$?

# Handle timeout
if [ $EXIT_CODE -eq 124 ]; then
  echo "Task execution timed out after ${TIMEOUT} seconds"
  exit 124
fi

exit $EXIT_CODE
```

---

### 5. Configuration: `examples/sandbox-config.json`

```json
{
  "mcpServers": {
    "sandbox-agent": {
      "command": "python",
      "args": ["sandbox_server.py"],
      "env": {
        "SANDBOX_TYPE": "docker",
        "DEFAULT_AGENT": "claude-code",
        "DOCKER_IMAGE_CLAUDE": "fluidmcp/claude-code-sandbox:latest",
        "DOCKER_IMAGE_OPENCODE": "fluidmcp/opencode-sandbox:latest",

        "RESOURCE_CPU_CORES": "2",
        "RESOURCE_MEMORY_GB": "4",
        "RESOURCE_TIMEOUT_SECONDS": "600",
        "RESOURCE_MAX_PROCESSES": "100",
        "RESOURCE_MAX_DISK_GB": "10",

        "NETWORK_MODE": "restricted",
        "YOLO_DEFAULT_LEVEL": "3",

        "WORKSPACE_BASE_DIR": "/tmp/fluidmcp-sandboxes",
        "WORKSPACE_CLEANUP_AFTER_HOURS": "24",

        "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}",

        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

---

## Security Model

### Defense Layers

#### 1. Container Isolation
- ✅ Separate namespace (PID, network, mount)
- ✅ Read-only root filesystem (except /workspace)
- ✅ No privileged mode
- ✅ Non-root user (UID 1000)
- ✅ Security options: `no-new-privileges`

#### 2. Resource Limits
```python
Resources(
    mem_limit="4g",           # Hard memory limit
    mem_reservation="2g",      # Soft limit
    cpu_quota=200000,          # 2 CPUs (100000 = 1 CPU)
    cpu_period=100000,
    pids_limit=100,            # Max 100 processes
    storage_opt={
        "size": "10G"          # Max 10GB disk
    }
)
```

#### 3. Network Restrictions

**Level 3 Network Policy** (Default):
- ✅ Allow outbound HTTPS (443)
- ✅ Allow outbound HTTP (80)
- ✅ Allow DNS (53)
- ❌ Block inbound connections
- ❌ Block localhost/host access
- ❌ Block private IP ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)

#### 4. Command Allowlist (Level 3)

**Allowed Commands**:
```python
ALLOWED_COMMANDS = {
    # Python
    "python", "python3", "pip", "pip3",

    # Node.js
    "node", "npm", "npx",

    # File operations
    "cat", "ls", "cp", "mv", "rm", "mkdir", "touch",

    # Data processing
    "jq", "grep", "sed", "awk", "cut", "sort", "uniq",

    # Media processing
    "ffmpeg", "convert", "imagemagick",

    # Network
    "curl", "wget",

    # Git (read-only)
    "git clone", "git pull"
}

BLOCKED_COMMANDS = {
    "docker", "kubectl", "ssh", "nc", "netcat",
    "sudo", "su", "chroot",
    "iptables", "systemctl", "service"
}
```

---

## YOLO Level Implementation

### Level 3: Files + Network + Limited System (Default)

**What Gets Auto-Approved**:

```python
class YoloLevel3Policy:
    def should_auto_approve(self, action: Dict[str, Any]) -> bool:
        """Determine if action should be auto-approved"""
        action_type = action["type"]

        # File operations - always approve
        if action_type in ["read_file", "write_file", "delete_file", "list_dir"]:
            return True

        # Network operations - approve with URL validation
        if action_type in ["http_get", "http_post", "download"]:
            url = action["url"]
            return self._is_safe_url(url)

        # Shell commands - approve if in allowlist
        if action_type == "shell":
            command = action["command"]
            return self._is_allowed_command(command)

        # Package installation - approve common packages
        if action_type == "install_package":
            package = action["package"]
            return self._is_safe_package(package)

        # Everything else - reject
        return False

    def _is_safe_url(self, url: str) -> bool:
        """Check if URL is safe to access"""
        parsed = urllib.parse.urlparse(url)

        # Block localhost
        if parsed.hostname in ["localhost", "127.0.0.1", "0.0.0.0"]:
            return False

        # Block private IPs
        if self._is_private_ip(parsed.hostname):
            return False

        # Allow HTTPS and HTTP
        return parsed.scheme in ["http", "https"]
```

---

## Use Case Examples

### Use Case 1: Analyze CSV File

**User Request**:
```json
{
  "task_description": "Analyze sales_data.csv and create a summary report with key insights",
  "files": [
    {
      "path": "sales_data.csv",
      "content": "base64EncodedCSV..."
    }
  ]
}
```

**What Happens**:
1. Sandbox creates workspace: `/tmp/fluidmcp-sandboxes/sandbox-abc123/`
2. Uploads `sales_data.csv` to workspace
3. Launches Docker container with Claude Code
4. Claude Code autonomously:
   - Reads CSV file ✅ (auto-approved)
   - Analyzes data using pandas ✅ (auto-approved)
   - Generates matplotlib charts ✅ (auto-approved)
   - Creates summary.txt ✅ (auto-approved)
5. Returns results with files: `["summary.txt", "sales_chart.png"]`

---

### Use Case 2: Download and Process Web Data

**User Request**:
```json
{
  "task_description": "Download the COVID-19 data from https://api.example.com/covid and create a cleaned CSV"
}
```

**What Happens**:
1. Claude Code downloads data ✅ (auto-approved, URL is safe)
2. Parses JSON response ✅ (auto-approved)
3. Cleans and normalizes data ✅ (auto-approved)
4. Exports to clean_covid_data.csv ✅ (auto-approved)

**Network validation ensures**:
- ❌ Blocks `http://localhost:8080/internal-api`
- ❌ Blocks `http://192.168.1.1/admin`
- ✅ Allows `https://api.example.com/covid`

---

### Use Case 3: Batch Image Processing

**User Request**:
```json
{
  "task_description": "Resize all uploaded images to 800x600 and convert to WebP format",
  "files": [
    {"path": "img1.jpg", "content": "..."},
    {"path": "img2.png", "content": "..."},
    {"path": "img3.jpg", "content": "..."}
  ]
}
```

**What Happens**:
1. Claude Code identifies image processing task
2. Installs Pillow if needed ✅ (auto-approved, safe package)
3. Loops through images ✅ (auto-approved)
4. Resizes each ✅ (auto-approved)
5. Converts to WebP ✅ (auto-approved)
6. Returns processed images

---

## Implementation Timeline

### Phase 1: Core Functionality (Week 1)

**Day 1-2: Infrastructure** (12-16 hours)
- ✅ Create `sandbox_server.py` with MCP protocol
- ✅ Implement `SandboxOrchestrator` class
- ✅ Implement `DockerSandboxManager` class
- ✅ Basic workspace management

**Day 3-4: Docker Images** (12-16 hours)
- ✅ Create Dockerfile.claude-code
- ✅ Create entrypoint.sh with YOLO levels
- ✅ Build and test image locally
- ✅ Verify Claude Code works in container

**Day 5: Integration & Testing** (8 hours)
- ✅ Integrate with FluidMCP gateway
- ✅ Test execute_task end-to-end
- ✅ Test file upload/download
- ✅ Test resource limits

---

### Phase 2: Security & Polish (Week 2)

**Day 6-7: Security Hardening** (12 hours)
- ✅ Implement network restrictions
- ✅ Add command allowlist validation
- ✅ Add URL safety checks
- ✅ Test security boundaries

**Day 8: Monitoring & Observability** (8 hours)
- ✅ Add execution monitoring
- ✅ Add resource usage logging
- ✅ Integrate with metrics.py
- ✅ Add timeout handling

**Day 9-10: Documentation** (12 hours)
- ✅ Create docs/SANDBOX.md
- ✅ Add architecture diagrams
- ✅ Document all YOLO levels
- ✅ Add troubleshooting guide

---

### Phase 3: OpenCode & Advanced Features (Week 3)

**Day 11-12: OpenCode Integration** (12 hours)
- ✅ Create Dockerfile.opencode
- ✅ Add OpenCode to agent selection
- ✅ Test OpenCode sandbox execution

**Day 13-14: Advanced Features** (12 hours)
- ✅ Add streaming output support
- ✅ Add progress updates
- ✅ Add multi-file task support

**Day 15: Polish & Optimization** (8 hours)
- ✅ Performance optimization
- ✅ Error handling improvements
- ✅ Final testing

---

## AgentBox Integration (Phase 1)

### Integration Strategy

**Phase 1 Approach:**
- Use AgentBox as sandbox backend
- Wrap AgentBox in `agentbox_backend.py`
- Map AgentBox API to our `SandboxOrchestrator` interface
- FluidMCP handles MCP protocol, AgentBox handles execution

**Why This Works:**
- AgentBox is implementation detail
- MCP interface remains stable
- Easy to swap backends later (Arrakis/Firecracker)
- No vendor lock-in

**File Structure:**
```python
# fluidmcp/cli/services/agentbox_backend.py

class AgentBoxBackend:
    """Wrapper for AgentBox integration"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        # Initialize AgentBox client

    async def execute_in_sandbox(
        self,
        agent: str,
        task: str,
        workspace: Path,
        timeout: int
    ) -> ExecutionResult:
        """Execute agent task using AgentBox"""
        # Map to AgentBox API
        # Handle workspace mounting
        # Monitor execution
        # Return results
```

---

## Success Criteria

### MVP Success Metrics
- ✅ Execute task end-to-end in < 30 seconds (for simple tasks)
- ✅ 99%+ security policy enforcement (no false approvals)
- ✅ Handle 10 concurrent sandboxes on single host
- ✅ < 1% task failure rate due to infrastructure
- ✅ Complete documentation with 5+ use case examples
- ✅ 3 beta users successfully using the system

### Phase 1 Completion Criteria
- ✅ Claude Code sandbox working
- ✅ All 4 MCP tools implemented
- ✅ CSV analysis use case working
- ✅ Security tests passing
- ✅ Documentation complete

---

## Dependencies

### Required Python Packages
```
docker>=7.0.0
asyncio
aiofiles
fastapi>=0.104.0
uvicorn>=0.24.0
httpx>=0.25.0
pydantic>=2.5.0
prometheus-client>=0.19.0
```

### System Requirements
- Docker Engine 24.0+
- Python 3.11+
- 16GB+ RAM (for host + sandboxes)
- 100GB+ disk space
- Linux host (Ubuntu 22.04 recommended)

### External Services
- Anthropic API (for Claude Code)
- Docker Hub (for pulling images)

---

## Status

**Plan Status**: ✅ COMPLETE AND READY FOR IMPLEMENTATION

**Waiting For**: Your approval to begin Phase 1 coding

**Total Implementation Effort**: ~2-3 weeks for production-ready MVP

---

**End of Complete Implementation Plan**
