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

## Key Files to Create

### 1. sandbox_server.py (~500 lines)
Main MCP server exposing sandbox execution via JSON-RPC

### 2. fluidmcp/cli/services/sandbox_orchestrator.py (~300 lines)
Manages agent lifecycle, workspace, execution flow

### 3. fluidmcp/cli/services/docker_sandbox.py (~400 lines)
Docker container management with resource limits

### 4. fluidmcp/cli/services/agentbox_backend.py (~200 lines)
AgentBox integration wrapper

### 5. docker/Dockerfile.claude-code (~50 lines)
Claude Code sandbox Docker image

### 6. docker/Dockerfile.opencode (~50 lines)
OpenCode sandbox Docker image

### 7. docker/entrypoint.sh (~80 lines)
Container entrypoint with YOLO configuration

### 8. examples/sandbox-config.json (~50 lines)
Sample FluidMCP configuration

### 9. docs/SANDBOX.md (~500 lines)
Complete documentation

---

## MCP Tools Exposed

### Tool 1: execute_task
Execute a task using AI agent in sandboxed environment with auto-approval

**Parameters:**
- `task_description` (required): Natural language task description
- `agent` (optional): "claude-code" or "opencode" (default: claude-code)
- `files` (optional): Array of files to upload to workspace
- `timeout` (optional): Max execution time in seconds (default: 600)
- `yolo_level` (optional): Auto-approval level 1-4 (default: 3)

**Returns:**
```json
{
  "session_id": "sandbox-abc123",
  "status": "completed|failed|timeout",
  "output": "Agent execution log and results",
  "files_created": ["report.pdf", "summary.txt"],
  "duration_seconds": 45.2
}
```

### Tool 2: get_sandbox_status
Check status of running/completed sandbox execution

### Tool 3: download_files
Download files created by the agent

### Tool 4: cleanup_sandbox
Clean up sandbox resources and workspace

---

## YOLO Level 3 (Recommended Default)

**What Gets Auto-Approved:**
- ✅ All file operations (read, write, delete)
- ✅ Network requests (with URL safety validation)
- ✅ Allowed shell commands (python, node, curl, etc.)
- ✅ Safe package installations (pandas, numpy, etc.)

**What Gets Blocked:**
- ❌ Privileged operations (sudo, docker)
- ❌ Localhost/private IP access
- ❌ Dangerous commands (rm -rf /, format, etc.)
- ❌ System service manipulation

---

## Security Model

### Container Isolation
- Separate namespaces (PID, network, mount)
- Read-only root filesystem (except /workspace)
- Non-root user (UID 1000)
- Resource limits: 2 CPU, 4GB RAM, 10GB disk

### Network Restrictions
- Allow: Outbound HTTPS/HTTP
- Block: Inbound, localhost, private IPs

### Command Allowlist
```python
ALLOWED = ["python", "node", "npm", "curl", "git", "jq", ...]
BLOCKED = ["docker", "sudo", "ssh", "nc", "systemctl", ...]
```

---

## Implementation Timeline

### Phase 1: Core Functionality (Week 1)
- Days 1-2: Infrastructure (MCP server, orchestrator, Docker manager)
- Days 3-4: Docker images (Claude Code, entrypoint)
- Day 5: Integration & testing

### Phase 2: Security & Polish (Week 2)
- Days 6-7: Security hardening
- Day 8: Monitoring & observability
- Days 9-10: Documentation

### Phase 3: OpenCode & Advanced Features (Week 3)
- Days 11-12: OpenCode integration
- Days 13-14: Advanced features
- Day 15: Polish & optimization

---

## Use Case Examples

### Example 1: CSV Analysis
```json
{
  "task_description": "Analyze sales_data.csv and create summary report",
  "files": [{"path": "sales_data.csv", "content": "base64..."}]
}
```
**Agent autonomously:** Reads CSV → Analyzes with pandas → Creates charts → Generates summary

### Example 2: Web Data Processing
```json
{
  "task_description": "Download COVID data from https://api.example.com and create cleaned CSV"
}
```
**Agent autonomously:** Downloads JSON → Parses → Cleans → Exports CSV

### Example 3: Image Processing
```json
{
  "task_description": "Resize all images to 800x600 and convert to WebP",
  "files": [
    {"path": "img1.jpg", "content": "..."},
    {"path": "img2.png", "content": "..."}
  ]
}
```
**Agent autonomously:** Installs Pillow → Loops through images → Resizes → Converts

---

## AgentBox Integration

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

---

## Success Criteria

### MVP Metrics
- ✅ Execute task end-to-end in < 30 seconds (simple tasks)
- ✅ 99%+ security policy enforcement
- ✅ Handle 10 concurrent sandboxes
- ✅ < 1% infrastructure failure rate
- ✅ Complete documentation with 5+ examples
- ✅ 3 beta users successfully using system

---

## Dependencies

**Python Packages:**
- docker>=7.0.0
- asyncio, aiofiles
- fastapi>=0.104.0
- httpx>=0.25.0
- pydantic>=2.5.0

**System Requirements:**
- Docker Engine 24.0+
- Python 3.11+
- 16GB+ RAM
- 100GB+ disk
- Linux (Ubuntu 22.04 recommended)

**External Services:**
- Anthropic API (for Claude Code)
- Docker Hub (for images)

---

## Status

**Plan Status**: ✅ COMPLETE AND READY FOR IMPLEMENTATION

**Waiting For**: Your review and decision to proceed

---

**Total Implementation Effort**: ~2-3 weeks for production-ready MVP
