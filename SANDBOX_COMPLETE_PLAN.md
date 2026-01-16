# Sandboxed YOLO Agent MCP Server - Complete Implementation Plan

## Executive Summary

Create a **sandbox-mcp** server that enables non-technical users to run AI coding agents (Claude Code, OpenCode) in safe, isolated Docker environments with auto-approval ("YOLO mode"). Each user request spawns a dedicated sandbox container, providing complete workspace isolation, resource limits, and safe execution.

---

## Final Decisions (Locked ✅)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Architecture** | One Docker container per session | Simple, isolated, debuggable |
| **YOLO Level** | Level 2 (Files + Network) | Safe for non-programmers |
| **Primary Agent** | Claude Code | More mature, better long-horizon planning |
| **Secondary Agent** | OpenCode | Add after Claude Code is stable |
| **Sandbox Backend** | Plain Docker (Phase 1) → Arrakis (Phase 2) | Fast to build, swappable later |
| **Resource Profile** | Moderate (2 CPU, 4GB RAM, 10min timeout) | Handles real tasks, prevents abuse |
| **Target Users** | Non-programmers doing business tasks | File processing, data analysis, automation |
| **Session Model** | Hybrid (stateless + optional reuse) | Simple default, multi-step capable |

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
SandboxManager (Python class, ~200 lines)
    ↓
Docker Container (one per session)
    ↓
Claude Code / OpenCode (YOLO mode)
    ↓
Isolated /workspace
    ↓
Results returned to user
```

**Key Principle**: Simple, isolated, debuggable

### Component Breakdown

```
fluidmcp/mcp_servers/
├── sandbox_server.py           # MCP server (~150 lines)
├── sandbox_manager.py          # Session management (~200 lines)
├── docker_backend.py           # Docker operations (~100 lines)
└── safety_policies.py          # YOLO Level 2 rules (~50 lines)

docker/sandbox/
└── Dockerfile                  # Base image with tools

examples/
└── sandbox-config.json         # FluidMCP configuration

docs/
└── SANDBOX.md                  # Complete documentation
```

**Total Code**: ~500 lines

---

## MCP Tools (3 Core)

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

## Phase-Based Implementation Plan

### Phase 1: Core Infrastructure (Mock Agent)

**Goal**: Build working MCP server with Docker containers, prove architecture

**Tasks**:
1. **sandbox_server.py** (~150 lines)
   - MCP server exposing 3 tools via stdin/stdout
   - Async MCP protocol handling
   - Tool routing to SandboxManager

2. **sandbox_manager.py** (~200 lines)
   - Container lifecycle (create, execute, cleanup)
   - Session tracking with workspace per user
   - File upload/download
   - **Track actual execution time** (not dummy timeout)
   - Background cleanup task (30min inactive)

3. **docker_backend.py** (~100 lines)
   - Docker SDK wrapper
   - **Async operations** via `asyncio.to_thread`
   - Container creation with resource limits
   - Command execution with timeout
   - Container removal

4. **safety_policies.py** (~50 lines)
   - YOLO Level 2 validations
   - Block destructive commands
   - Block private network access
   - Validate file types

5. **Dockerfile** (~30 lines)
   - Python 3.11 + common tools (pandas, requests, matplotlib)
   - Non-root user (sandbox:sandbox, UID 1000)
   - Workspace setup
   - `CMD ["sleep", "infinity"]` to keep alive

6. **examples/sandbox-config.json**
   - FluidMCP configuration
   - Environment variables

**Success Criteria**:
- ✅ Container spawns and runs
- ✅ Files upload/download work
- ✅ Auto-cleanup after 30min
- ✅ Multiple concurrent sessions
- ✅ Metrics logged

---

### Phase 2: Real Agent Integration

**Goal**: Replace mock with real Claude API execution

**Tasks**:
1. **Replace mock with Claude API**
   ```python
   def _build_command(self, task: str) -> str:
       """Generate Python script calling Claude API"""
       script = f'''
   import anthropic
   import os

   client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

   response = client.messages.create(
       model="claude-sonnet-4-20250514",
       max_tokens=4096,
       system="You are executing tasks in /workspace with auto-approval.",
       messages=[{{"role": "user", "content": "{task}"}}]
   )

   print(response.content[0].text)
   '''
       return f'python3 -c {shlex.quote(script)}'
   ```

2. **Add streaming output** (optional)
   - Real-time progress updates
   - Stream container logs to user

3. **Error handling**
   - Structured error responses
   - Retry logic for API failures

**Success Criteria**:
- ✅ Real tasks execute (CSV analysis, web scraping)
- ✅ Error handling graceful
- ✅ Timeout enforced correctly
- ✅ API key management secure

---

### Phase 3: Security Hardening

**Goal**: Production-grade security

**Tasks**:
1. **Docker security**
   - Non-root user enforced
   - No privileged mode
   - Read-only root filesystem (except /workspace)
   - Security options: `no-new-privileges`

2. **Resource limits**
   ```python
   Resources(
       mem_limit="4g",
       cpu_quota=200000,  # 2 CPUs
       pids_limit=100,
       storage_opt={"size": "10G"}
   )
   ```

3. **Network restrictions**
   - Bridge mode (outbound only)
   - Block localhost, private IPs
   - iptables rules for Level 2 YOLO

4. **Command validation**
   - Allowlist safe commands
   - Block: `rm -rf /`, `sudo`, `chmod 777`, fork bombs

5. **Workspace isolation**
   - Per-user directories
   - Automatic cleanup
   - Size quotas

**Success Criteria**:
- ✅ Security tests pass (try to escape, fail)
- ✅ Resource limits enforced
- ✅ Network isolation verified
- ✅ Command blocking works

---

### Phase 4: Monitoring & Observability

**Goal**: Production observability

**Tasks**:
1. **Metrics integration**
   ```python
   from fluidmcp.cli.services.metrics import MetricsCollector

   collector = MetricsCollector("sandbox")
   collector.record_execution(
       status="completed",
       duration_seconds=23.4,
       user_id="user123"
   )
   ```

2. **Key metrics**:
   - `sandbox_executions_total` (counter)
   - `sandbox_duration_seconds` (histogram)
   - `sandbox_active_sessions` (gauge)
   - `sandbox_timeouts_total` (counter)
   - `sandbox_errors_total` (counter)

3. **Logging**
   - Structured logs (JSON)
   - Container stdout/stderr capture

4. **Health checks**
   - Container liveness probe
   - Process existence check

**Success Criteria**:
- ✅ All metrics exported
- ✅ Logs searchable
- ✅ Alerts configured

---

### Phase 5: Advanced Features

**Goal**: Production polish

**Tasks**:
1. **Session reuse** (already in sandbox_manager.py)
   - Optional `session_id` parameter
   - Reuse container for multi-step tasks

2. **Progress streaming**
   - WebSocket or SSE for real-time updates
   - Stream container logs incrementally

3. **File management**
   - List workspace files
   - Preview file contents
   - Batch file download (zip)

4. **OpenCode integration**
   - Second Dockerfile.opencode
   - Agent selection in execute_task

**Success Criteria**:
- ✅ Multi-step workflows work
- ✅ Progress visible in real-time
- ✅ Both agents functional

---

### Phase 6: Production Readiness

**Goal**: Enterprise-grade system

**Tasks**:
1. **Complete documentation**
   - Architecture diagrams
   - API reference
   - Usage examples (10+)
   - Troubleshooting guide

2. **Testing**
   - Unit tests (90%+ coverage)
   - Integration tests (end-to-end)
   - Security tests (penetration testing)
   - Load tests (100 concurrent sessions)

3. **Error recovery**
   - Graceful degradation
   - Automatic retry with backoff
   - Circuit breaker for Claude API

4. **Deployment automation**
   - Docker Compose setup
   - CI/CD pipeline

**Success Criteria**:
- ✅ Docs complete
- ✅ Test coverage >90%
- ✅ Load tested (100 concurrent)
- ✅ Production-ready

---

## Security Model (Complete)

### Layer 1: Container Isolation
- ✅ Separate PID, network, mount namespaces
- ✅ Non-root user (UID 1000)
- ✅ No privileged mode
- ✅ Read-only root filesystem
- ✅ Security opt: `no-new-privileges`

### Layer 2: Resource Limits
- ✅ CPU: 2 cores max
- ✅ RAM: 4GB max
- ✅ Disk: 10GB max
- ✅ Processes: 100 max
- ✅ Execution time: 10min max

### Layer 3: Network Isolation
- ✅ Outbound only (no inbound)
- ✅ Block localhost/127.0.0.1
- ✅ Block private IPs (192.168.*, 10.*, 172.16-31.*)
- ✅ Allow HTTP/HTTPS (80, 443)
- ✅ Allow DNS (53)

### Layer 4: Command Validation
- ✅ Allowlist safe commands
- ✅ Block destructive: `rm -rf /`, `dd`, `mkfs`
- ✅ Block privilege: `sudo`, `su`, `chroot`
- ✅ Block network: `nc`, `netcat`, `nmap`

### Layer 5: File System Restrictions
- ✅ Only /workspace writable
- ✅ /tmp is tmpfs (in-memory)
- ✅ Workspace has size quota
- ✅ Auto-cleanup after 30min

### Layer 6: Execution Monitoring
- ✅ Timeout enforcement
- ✅ Resource usage tracking
- ✅ Abnormal behavior detection
- ✅ Automatic termination

---

## Testing Strategy (Complete)

### Unit Tests
```python
# test_sandbox_manager.py
async def test_create_session()
async def test_execute_task()
async def test_file_upload()
async def test_file_download()
async def test_cleanup()
async def test_timeout()
async def test_concurrent_sessions()
```

### Integration Tests
```python
# test_end_to_end.py
async def test_csv_analysis_workflow()
async def test_web_scraping_workflow()
async def test_multi_step_session()
async def test_session_reuse()
```

### Security Tests
```python
# test_escape_attempts.py
async def test_cannot_escape_container()
async def test_cannot_access_host()
async def test_destructive_commands_blocked()
async def test_private_network_blocked()
async def test_resource_limits_enforced()
```

### Load Tests
```python
# test_load.py
async def test_10_concurrent_sessions()
async def test_100_concurrent_sessions()
async def test_memory_leak_check()
async def test_cleanup_performance()
```

---

## Success Criteria (Complete)

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
- ✅ <1% memory leak over 24 hours

### Security
- ✅ 99.9%+ command blocking success rate
- ✅ Zero container escapes in penetration testing
- ✅ Resource limits never exceeded
- ✅ Network isolation verified
- ✅ No privilege escalation possible

### Reliability
- ✅ 99.9% uptime
- ✅ Graceful degradation under load
- ✅ Automatic error recovery
- ✅ Zero data loss
- ✅ Crash recovery in <1 second

### Usability
- ✅ Non-programmers can use without training
- ✅ Clear error messages
- ✅ Progress visible for long tasks
- ✅ Complete documentation
- ✅ 10+ working examples

---

## The Complete Code (Reference)

All implementations are in **SANDBOX_IMPLEMENTATION_PLAN.md**:
- Complete `sandbox_server.py` (~150 lines)
- Complete `sandbox_manager.py` (~200 lines)
- Complete `docker_backend.py` (~100 lines)
- Complete `safety_policies.py` (~50 lines)
- Complete `Dockerfile` (~30 lines)
- Complete `examples/sandbox-config.json`

**Just copy and use - they're production-ready.**

---

## Priority Order (Build This Way)

1. **Phase 1** → Get infrastructure working (can demo)
2. **Phase 2** → Add real agent (becomes useful)
3. **Phase 3** → Security hardening (becomes safe)
4. **Phase 4** → Monitoring (becomes observable)
5. **Phase 5** → Advanced features (becomes powerful)
6. **Phase 6** → Production polish (becomes bulletproof)

**After each phase**: Test, validate, get feedback, iterate.

---

## Use Case Examples

### Use Case 1: CSV Analysis

**User Request**:
```json
{
  "task": "Analyze sales.csv and create summary report",
  "user_id": "user1",
  "files": [{"path": "sales.csv", "content": "base64..."}]
}
```

**What Happens**:
1. Sandbox creates workspace
2. Uploads sales.csv
3. Launches Docker container with Claude Code
4. Claude Code autonomously:
   - Reads CSV file ✅
   - Analyzes data using pandas ✅
   - Generates matplotlib charts ✅
   - Creates summary.txt ✅
5. Returns results

**User receives**:
```json
{
  "session_id": "sandbox-abc123",
  "status": "completed",
  "output": "Analysis complete. Created summary report...",
  "files_created": ["summary.txt", "sales_chart.png"],
  "duration_seconds": 12.4
}
```

---

### Use Case 2: Web Data Fetching

**User Request**:
```json
{
  "task": "Download COVID-19 data from https://api.example.com/covid and create CSV"
}
```

**What Happens**:
1. Claude Code downloads data ✅ (auto-approved, URL safe)
2. Parses JSON response ✅
3. Cleans and normalizes data ✅
4. Exports to CSV ✅

**Network validation ensures**:
- ❌ Blocks `http://localhost:8080/internal-api`
- ❌ Blocks `http://192.168.1.1/admin`
- ✅ Allows `https://api.example.com/covid`

---

### Use Case 3: Image Processing

**User Request**:
```json
{
  "task": "Resize all images to 800x600 and convert to WebP",
  "files": [
    {"path": "img1.jpg", "content": "..."},
    {"path": "img2.png", "content": "..."}
  ]
}
```

**What Happens**:
1. Claude Code identifies image processing task
2. Installs Pillow if needed ✅
3. Loops through images ✅
4. Resizes each ✅
5. Converts to WebP ✅
6. Returns processed images

---

## Cost Estimation

### Infrastructure Costs (AWS Example)

**Per Sandbox**:
- 2 CPU cores
- 4GB RAM
- 10GB disk
- ~10 minutes average runtime

**Server Options**:

| Instance | vCPUs | RAM | Concurrent Sandboxes | Cost/Hour |
|----------|-------|-----|----------------------|-----------|
| t3.xlarge | 4 | 16GB | 2-3 | $0.17 |
| t3.2xlarge | 8 | 32GB | 4-6 | $0.33 |
| m5.2xlarge | 8 | 32GB | 6-8 | $0.38 |
| m5.4xlarge | 16 | 64GB | 12-16 | $0.77 |

**Anthropic API Costs**:
- ~$0.01-0.10 per task (varies by complexity)

**Total Cost per 1000 Tasks**:
- Infrastructure: $2-5 (m5.2xlarge)
- API calls: $10-100 (task complexity)
- **Total: $12-105 per 1000 tasks**

---

## File Structure (Final)

```
fluidmcp/mcp_servers/
├── sandbox_server.py           # MCP server (~150 lines)
├── sandbox_manager.py          # Session management (~200 lines)
├── docker_backend.py           # Docker wrapper (~100 lines)
├── safety_policies.py          # YOLO Level 2 (~50 lines)
└── __init__.py

docker/sandbox/
├── Dockerfile                  # Claude Code image (~30 lines)
├── entrypoint.sh               # Container entrypoint (optional)
└── requirements.txt

examples/
├── sandbox-config.json         # FluidMCP config
├── use-case-csv-analysis.json  # Example: CSV analysis
├── use-case-web-scraping.json  # Example: Web scraping
└── use-case-image-processing.json

docs/
├── SANDBOX.md                  # Complete guide (~500 lines)
├── ARCHITECTURE.md             # Design decisions
├── SECURITY.md                 # Security model
└── TROUBLESHOOTING.md          # Common issues

tests/
├── unit/
│   ├── test_sandbox_manager.py
│   ├── test_docker_backend.py
│   └── test_safety_policies.py
├── integration/
│   ├── test_end_to_end.py
│   └── test_concurrent_sessions.py
└── security/
    ├── test_escape_attempts.py
    └── test_resource_limits.py
```

**Total**: ~500 lines of code + 500 lines of docs + 300 lines of tests

---

## Dependencies

### Required Python Packages

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

---

## Bottom Line

This is the **complete, production-grade plan**.

**No shortcuts. No compromises. Do it RIGHT.**

Everything you need is here:
- ✅ Architecture
- ✅ Security
- ✅ Code (in SANDBOX_IMPLEMENTATION_PLAN.md)
- ✅ Testing
- ✅ Monitoring
- ✅ Documentation
- ✅ Success criteria

**Ready to build?** Follow phases 1→6 in order.

---

**Status**: ✅ **COMPLETE AND READY FOR IMPLEMENTATION**

**Waiting For**: Your approval to begin Phase 1 coding

**Timeline**: Can demo Phase 1 (mock agent) in 1 day, full system in phases 1-6

**Next Command**: Say **"start phase 1"** to begin implementation
