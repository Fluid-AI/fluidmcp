# Sandboxed YOLO Agent MCP Server - Implementation Plan

## Executive Summary

Create a **sandbox-mcp** server that enables non-technical users to run AI coding agents (Claude Code, OpenCode) in safe, isolated Docker environments with auto-approval ("YOLO mode"). Each user request spawns a dedicated sandbox container, providing complete workspace isolation, resource limits, and safe execution.

**Design Philosophy**: Simple, isolated, debuggable. One container per session.

---

## Problem Statement

### Current Limitation
AI coding agents require:
1. Manual approval for each action (safe but slow)
2. Technical knowledge to set up and configure
3. Direct access to user's file system (security risk)
4. Understanding of programming concepts

### Desired State
Non-technical users should be able to:
1. Ask AI to "analyze this CSV file" without knowing how
2. Request "download data from this website" without coding
3. Perform file operations through natural language
4. Have actions execute automatically (YOLO mode) within safe boundaries

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
Docker Container (one per session)
    ↓
Claude Code (YOLO mode)
    ↓
Isolated /workspace
    ↓
Results returned to user
```

**Note**: v1 uses plain Docker + Claude Code. Future versions can swap to AgentBox or Firecracker without changing the MCP API.

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Container Model** | One Docker container per session | Simple, isolated, debuggable |
| **YOLO Level** | Level 2 (Files + Network) | Safe for non-programmers |
| **Primary Agent** | Claude Code | More mature, better long-horizon planning |
| **Secondary Agent** | OpenCode (Phase 5) | Add after Claude Code is stable |
| **Backend** | Plain Docker (v1) → AgentBox/Arrakis (later) | Fast to build, swappable later |
| **Resources** | 2 CPU, 4GB RAM, 10min timeout | Handles real tasks, prevents abuse |
| **Session Model** | Stateless + optional reuse | Simple default, multi-step capable |

---

## Proposed File Structure

```
fluidmcp/mcp_servers/
├── sandbox_server.py           # MCP server + session management + lifecycle (~300-350 lines)
├── sandbox_backend.py          # Docker operations + safety policies (~150 lines)
└── docker/
    ├── Dockerfile              # Base image with tools
    └── requirements.txt        # Python packages

examples/
├── sandbox-config.json         # FluidMCP configuration
├── use-case-csv-analysis.json
├── use-case-web-scraping.json
└── use-case-image-processing.json

docs/
└── SANDBOX.md                  # User documentation

tests/
├── unit/
│   ├── test_sandbox_server.py
│   ├── test_sandbox_backend.py
│   └── test_safety_policies.py
├── integration/
│   └── test_end_to_end.py
└── security/
    └── test_escape_attempts.py
```

**Total Estimated Code**: ~500 lines + tests + docs

**Design Note**: For the initial version, session management and MCP handling will live in a single `sandbox_server.py` for simplicity, similar to how the Python REPL MCP server works. The `sandbox_backend.py` provides a thin abstraction layer for Docker operations, allowing future backend swaps (e.g., Firecracker, AgentBox) without changing the MCP API or client behavior. If complexity grows, `sandbox_server.py` can be split later without API changes.

---

## MCP Tools (3 Core Tools)

### 1. `execute_task`
Execute a task in isolated sandbox

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
          "path": {"type": "string"},
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

### 2. `get_files`
Download files created by agent

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "session_id": {"type": "string"},
    "paths": {
      "type": "array",
      "items": {"type": "string"}
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

### 3. `cleanup_session`
Stop container and cleanup workspace

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

---

## Security Model

### Six Layers of Protection

#### Layer 1: Container Isolation
- ✅ Separate PID, network, mount namespaces
- ✅ Non-root user (sandbox:sandbox, UID 1000)
- ✅ No privileged mode
- ✅ Read-only root filesystem (except /workspace)
- ✅ Security options: `no-new-privileges`

#### Layer 2: Resource Limits
```python
Resources(
    mem_limit="4g",           # Hard memory limit
    cpu_quota=200000,         # 2 CPUs (100000 = 1 CPU)
    pids_limit=100,           # Max 100 processes
    storage_opt={"size": "10G"}  # Max 10GB disk
)
```

#### Layer 3: Network Isolation
- ✅ Outbound only (no inbound connections)
- ✅ Block localhost/127.0.0.1
- ✅ Block private IPs (192.168.*, 10.*, 172.16-31.*)
- ✅ Allow HTTP/HTTPS (80, 443)
- ✅ Allow DNS (53)

#### Layer 4: Command Validation
**Allowed**: python, node, npm, curl, git, jq, grep, sed, awk, ffmpeg

**Blocked**: docker, sudo, ssh, nc, netcat, systemctl, iptables, rm -rf /

#### Layer 5: File System Restrictions
- ✅ Only /workspace writable
- ✅ /tmp is tmpfs (in-memory, cleared on exit)
- ✅ Workspace has 10GB quota
- ✅ Auto-cleanup after 30min inactive

#### Layer 6: Execution Monitoring
- ✅ Timeout enforcement
- ✅ Resource usage tracking
- ✅ Abnormal behavior detection
- ✅ Automatic termination on violations

### YOLO Level 2: Files + Network

**What Gets Auto-Approved**:
- ✅ All file operations (read, write, delete within /workspace)
- ✅ Network requests to public URLs (with validation)
- ✅ Safe shell commands (allowlist)
- ✅ Common package installations (pandas, numpy, requests)

**What Gets Blocked**:
- ❌ Privileged operations (sudo, docker)
- ❌ Localhost/private IP access
- ❌ Destructive commands (rm -rf /, format, dd)
- ❌ System service manipulation

---

## Phased Implementation Plan

### Phase 1: Core Infrastructure (1 week)
**Goal**: Working MCP server with Docker containers

**Deliverables**:
- MCP server exposing 3 tools (execute_task, get_files, cleanup_session)
- Container lifecycle management (create, execute, cleanup)
- File upload/download
- Background cleanup task (30min inactive)
- Basic metrics integration

**Success Criteria**:
- ✅ Container spawns and runs
- ✅ Files upload/download work
- ✅ Auto-cleanup after 30min
- ✅ Multiple concurrent sessions
- ✅ Metrics logged

### Phase 2: Real Agent Integration (1 week)
**Goal**: Integrate Claude Code execution in containers

**Deliverables**:
- Claude API integration via Anthropic SDK
- Agent execution within Docker containers
- Streaming output (optional)
- Structured error handling
- Timeout enforcement
- API key management

**Success Criteria**:
- ✅ Real tasks execute (CSV analysis, web scraping, image processing)
- ✅ Error handling graceful
- ✅ Timeout enforced correctly
- ✅ Agent operates autonomously in YOLO mode

### Phase 3: Security Hardening (3 days)
**Goal**: Production-grade security

**Deliverables**:
- Docker security (non-root, read-only root fs)
- Resource limits enforced
- Network restrictions (iptables rules)
- Command validation (allowlist)
- Workspace isolation

**Success Criteria**:
- ✅ Security tests pass (escape attempts fail)
- ✅ Resource limits enforced
- ✅ Network isolation verified

### Phase 4: Monitoring & Observability (2 days)
**Goal**: Production observability

**Deliverables**:
- Metrics integration with existing `metrics.py`
- Structured logging (JSON)
- Health checks
- Container stdout/stderr capture

**Metrics**:
- `sandbox_executions_total` (counter)
- `sandbox_duration_seconds` (histogram)
- `sandbox_active_sessions` (gauge)
- `sandbox_timeouts_total` (counter)
- `sandbox_errors_total` (counter)

### Phase 5: Advanced Features (3 days)
**Goal**: Production polish

**Deliverables**:
- Session reuse for multi-step tasks
- Progress streaming (WebSocket/SSE)
- File management (list, preview)
- OpenCode integration

### Phase 6: Production Readiness (3 days)
**Goal**: Enterprise-grade system

**Deliverables**:
- Complete documentation (SANDBOX.md)
- 90%+ test coverage
- Load testing (100 concurrent sessions)
- CI/CD pipeline integration

---

## Use Case Examples

### Example 1: CSV Analysis
**User Request**:
```json
{
  "task": "Analyze sales.csv and create a summary report",
  "user_id": "user1",
  "files": [{"path": "sales.csv", "content": "base64..."}]
}
```

**What Happens**:
1. Sandbox creates workspace: `/tmp/sandbox_user1_1738195847/`
2. Uploads `sales.csv` to workspace
3. Launches Docker container with Claude Code
4. Claude Code autonomously:
   - Reads CSV file ✅ (auto-approved)
   - Analyzes data using pandas ✅ (auto-approved)
   - Generates matplotlib charts ✅ (auto-approved)
   - Creates summary.txt ✅ (auto-approved)
5. Returns results

**User Receives**:
```json
{
  "session_id": "sandbox_user1_1738195847",
  "status": "completed",
  "output": "Analysis complete. Created summary report...",
  "files_created": ["summary.txt", "sales_chart.png"],
  "duration_seconds": 12.4
}
```

### Example 2: Web Data Fetching
**Task**: "Download COVID-19 data from https://api.example.com/covid and create CSV"

**Network Validation**:
- ❌ Blocks `http://localhost:8080/internal-api`
- ❌ Blocks `http://192.168.1.1/admin`
- ✅ Allows `https://api.example.com/covid`

### Example 3: Image Processing
**Task**: "Resize all images to 800x600 and convert to WebP"

**Auto-approved Actions**:
1. Installs Pillow package ✅
2. Loops through uploaded images ✅
3. Resizes each image ✅
4. Converts to WebP format ✅
5. Returns processed images ✅

---

## Success Criteria

### Functional
- ✅ All 3 MCP tools work correctly
- ✅ Files upload/download reliably
- ✅ Sessions isolated properly
- ✅ Cleanup works (manual + auto)
- ✅ Multiple concurrent users supported

### Performance
- ✅ Simple task completes in <30 seconds
- ✅ Complex task completes in <10 minutes
- ✅ File upload/download: >10MB/s
- ✅ 100 concurrent sessions on single host

### Security
- ✅ 99.9%+ command blocking success rate
- ✅ Zero container escapes in penetration testing
- ✅ Resource limits never exceeded
- ✅ Network isolation verified

### Reliability
- ✅ 99.9% uptime
- ✅ Graceful degradation under load
- ✅ Automatic error recovery
- ✅ Zero data loss

---

## Dependencies

### Python Packages
```
docker>=7.0.0
asyncio
aiofiles
httpx>=0.25.0
pydantic>=2.5.0
prometheus-client>=0.19.0
anthropic>=0.18.0
```

### System Requirements
- Docker Engine 24.0+
- Python 3.11+
- 16GB+ RAM (for host + sandboxes)
- 100GB+ disk space
- Linux host (Ubuntu 22.04 recommended)

### External Services
- Anthropic API (for Claude Code)
- Docker Hub (for pulling base images)

---

## Design Decisions (Locked for v1)

1. **File Structure**: All session lifecycle logic lives in `sandbox_server.py`. Only `sandbox_backend.py` provides backend abstraction. No separate manager layer in v1.

2. **YOLO Level**: Start with Level 2 (Files + Network). This matches the core use cases (CSV analysis, web scraping, data processing) while maintaining safety for non-programmers.

3. **Cleanup Strategy**: Default 30-minute auto-cleanup timeout. Configurable per-user settings deferred to Phase 5+.

4. **Session Reuse**: Stateless by default (one container per request). Optional session reuse via `session_id` parameter for multi-step workflows.

5. **AgentBox Integration**: Start with plain Docker + Claude API for fastest path to working v1. AgentBox integration comes later as a backend swap without API changes.

## Open Questions for Review

1. **Resource Limits**: Are 2 CPU / 4GB RAM / 10GB disk the right defaults, or should these be tunable per-task?

2. **Network Restrictions**: Should we allowlist specific domains, or block only private IPs?

3. **Monitoring**: Beyond the proposed metrics, what observability signals are critical for production deployment?

---

## Timeline

**Total Estimate**: 3 weeks (18 days)

- Phase 1: 1 week (MVP demo ready)
- Phase 2: 1 week (Real agent working)
- Phase 3: 3 days (Security hardened)
- Phase 4: 2 days (Monitoring added)
- Phase 5: 3 days (Advanced features)
- Phase 6: 3 days (Production ready)

**Milestones**:
- Week 1: Phase 1-2 complete, demo working system
- Week 2: Phase 3-4 complete, secure + observable
- Week 3: Phase 5-6 complete, production deployment

---

## Risk Analysis

### Technical Risks
| Risk | Mitigation |
|------|------------|
| Container escape vulnerability | Multiple security layers, penetration testing |
| Resource exhaustion | Hard limits enforced at Docker level |
| Network abuse | URL validation, rate limiting |
| Long-running tasks timeout | 10min hard timeout, progress streaming |

### Operational Risks
| Risk | Mitigation |
|------|------------|
| Container cleanup failure | Background cleanup task + metrics alerting |
| Concurrent session limits | Load testing, horizontal scaling |
| Disk space exhaustion | 10GB per workspace quota, auto-cleanup |

---

## Alternatives Considered

### Why Not: Process-level Isolation
**Rejected**: Weaker isolation, harder to enforce resource limits

### Why Not: VM-based Sandboxing (Firecracker)
**Deferred to Phase 2**: More complex, slower startup. Docker first, then upgrade.

### Why Not: Kubernetes Jobs
**Rejected for Phase 1**: Over-engineering for single-host deployment

### Why Container-per-Session
**Chosen**: Simple, strong isolation, easy to debug, swappable backend

---

## Future Enhancements (Post-MVP)

1. **Stronger Isolation**: Migrate to Firecracker/Arrakis for VM-level isolation
2. **Agent Marketplace**: Pre-configured agents for specific tasks
3. **Cost Tracking**: Per-user usage metrics and billing
4. **Multi-Container Tasks**: Parallel execution across multiple sandboxes
5. **Workspace Snapshots**: Save/restore workspace state
6. **Custom YOLO Policies**: User-defined approval rules

---

**Status**: 🟡 Design Review - Awaiting Approval

**Next Step**: After approval, begin Phase 1 implementation

**Questions?** Please leave inline comments on specific sections.
