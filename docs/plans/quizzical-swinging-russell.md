# Sandboxed AI Code Agent MCP Server (OpenCode/Claude Code in Yolo Mode)

## Overview
Create an MCP server that runs AI coding agents (OpenCode, Claude Code) in sandboxed environments, enabling non-technical users to leverage AI coding capabilities for everyday tasks through FluidMCP's unified gateway.

## User Requirements Summary
- **Primary Goal**: Enable non-programming users to use AI coding agents (OpenCode, Claude Code)
- **Deployment**: Sandboxed execution environment for safety
- **Mode**: "Yolo mode" - auto-approval of actions without manual confirmation
- **Use Cases**: File operations, data processing, web scraping, automation tasks
- **Inspiration**: AgentBox-style architecture (repository to research)
- **Integration**: Should work seamlessly with FluidMCP's existing MCP server infrastructure

## Problem Statement

**Current Limitation**: AI coding agents like Claude Code and OpenCode require:
1. Manual approval for each action (safe but slow)
2. Technical knowledge to set up and configure
3. Direct access to user's file system (security risk)
4. Understanding of programming concepts

**Desired State**: Non-technical users should be able to:
1. Ask AI to "analyze this CSV file" without knowing how
2. Request "download data from this website" without coding
3. Perform file operations through natural language
4. Have actions execute automatically (yolo mode) within safe boundaries

## Architecture Options

### Option 1: Docker Container Sandbox (Recommended)

**Architecture**:
```
FluidMCP Gateway
       |
       |-- MCP Server: code-agent-sandbox
                |
                |-- stdin/stdout JSON-RPC
                |-- Docker Container (isolated environment)
                     |
                     |-- Claude Code CLI / OpenCode
                     |-- Working Directory: /workspace (mounted volume)
                     |-- Resource Limits: CPU, Memory, Network
                     |-- Auto-approve mode enabled
```

**Pros**:
- ✅ Strong isolation (filesystem, network, processes)
- ✅ Resource limits (CPU, memory, disk)
- ✅ Works on any platform with Docker
- ✅ Easy cleanup (remove container)
- ✅ Well-tested technology

**Cons**:
- ❌ Requires Docker installation
- ❌ Overhead of container management
- ❌ Slower startup (container launch)

### Option 2: Python subprocess with cgroups (Linux only)

**Architecture**:
```
FluidMCP Gateway
       |
       |-- MCP Server: code-agent-sandbox
                |
                |-- subprocess.Popen with cgroups
                |-- Restricted working directory
                |-- Resource limits via cgroups
                |-- No container overhead
```

**Pros**:
- ✅ Lower overhead
- ✅ Faster startup
- ✅ No Docker dependency

**Cons**:
- ❌ Linux only (cgroups)
- ❌ Weaker isolation
- ❌ More complex implementation

### Option 3: Hybrid - Docker for sandbox, subprocess for orchestration

**Architecture**:
```
FluidMCP Gateway
       |
       |-- MCP Server: code-agent-orchestrator
                |
                |-- Manages Docker containers
                |-- Maps MCP tools → Agent commands
                |-- Handles file uploads/downloads
                |-- Session management
```

**Pros**:
- ✅ Best of both worlds
- ✅ Strong isolation + flexible orchestration
- ✅ Can run multiple agents simultaneously

**Cons**:
- ❌ Most complex implementation
- ❌ Higher resource usage

## Recommended Approach: Option 1 (Docker Container Sandbox)

### Why Docker?
1. **Security**: Strong isolation from host system
2. **Portability**: Works on Linux, macOS, Windows
3. **Resource Control**: Built-in CPU/memory limits
4. **Cleanup**: Easy to remove containers
5. **Proven**: Industry-standard for sandboxing

### Implementation Strategy

**Phase 1**: Research AgentBox architecture
- Understand how AgentBox implements sandboxing
- Identify key security patterns
- Learn best practices for yolo mode

**Phase 2**: Create Docker-based MCP server
- Design MCP tools for code execution
- Implement Docker container management
- Add yolo mode configuration

**Phase 3**: Integrate with FluidMCP
- Use existing config_resolver.py patterns
- Follow package_launcher.py subprocess model
- Leverage metrics.py for monitoring

## Key Questions for User

Before proceeding with detailed planning, I need clarification on:

### 1. AgentBox Repository
- What is the correct GitHub URL for AgentBox?
- Is it public or private?
- Can you describe its key features if not accessible?

### 2. Scope of "Yolo Mode"
Which level of automation do you want?
- **Level 1**: Auto-approve file operations only (read, write, delete)
- **Level 2**: Auto-approve + network operations (API calls, downloads)
- **Level 3**: Auto-approve + system operations (install packages, run commands)
- **Level 4**: Fully autonomous (all operations without user confirmation)

### 3. Safety Boundaries
What restrictions should apply in sandbox?
- File system: Only specific directories? Size limits?
- Network: Allow all domains? Whitelist only?
- Resources: CPU/memory limits?
- Time: Maximum execution time per task?

### 4. User Authentication
How should users be identified?
- Per-user sandboxes?
- Shared sandbox for all users?
- API token-based access?

### 5. Agent Choice
Which agents should be supported initially?
- Claude Code only?
- OpenCode only?
- Both?
- Others (Cursor, Windsurf, etc.)?

## Preliminary Technical Design (Subject to answers above)

### MCP Tools to Expose

```json
{
  "tools": [
    {
      "name": "execute_code_task",
      "description": "Execute a coding task using AI agent in sandboxed environment",
      "inputSchema": {
        "type": "object",
        "properties": {
          "task_description": {
            "type": "string",
            "description": "Natural language description of what to do"
          },
          "agent": {
            "type": "string",
            "enum": ["claude-code", "opencode"],
            "default": "claude-code"
          },
          "working_directory": {
            "type": "string",
            "description": "Path to working directory (relative to sandbox)"
          },
          "timeout": {
            "type": "integer",
            "description": "Maximum execution time in seconds",
            "default": 300
          },
          "files": {
            "type": "array",
            "description": "Files to upload to sandbox before execution",
            "items": {
              "type": "object",
              "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
              }
            }
          }
        },
        "required": ["task_description"]
      }
    },
    {
      "name": "get_sandbox_status",
      "description": "Get status of running sandbox",
      "inputSchema": {
        "type": "object",
        "properties": {
          "session_id": {"type": "string"}
        },
        "required": ["session_id"]
      }
    },
    {
      "name": "download_sandbox_files",
      "description": "Download files from sandbox after task completion",
      "inputSchema": {
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
    }
  ]
}
```

### Configuration Structure

```json
{
  "mcpServers": {
    "code-agent-sandbox": {
      "command": "python",
      "args": ["sandbox_server.py"],
      "env": {
        "SANDBOX_TYPE": "docker",
        "DOCKER_IMAGE": "anthropic/claude-code:latest",
        "YOLO_MODE": "true",
        "SANDBOX_CPU_LIMIT": "2",
        "SANDBOX_MEMORY_LIMIT": "4g",
        "SANDBOX_NETWORK": "restricted",
        "SANDBOX_TIMEOUT": "300",
        "ALLOWED_FILE_SIZE": "100M",
        "ANTHROPIC_API_KEY": "<your-key>"
      }
    }
  }
}
```

### Docker Container Design

**Base Image**: Ubuntu 22.04 with Python 3.11
**Pre-installed**:
- Claude Code CLI
- OpenCode (if applicable)
- Common tools: git, curl, wget, jq
- Python packages: requests, pandas, beautifulsoup4

**Security**:
- Non-root user
- Read-only root filesystem (except /workspace)
- No privileged mode
- Network isolation (optional)
- Resource limits (CPU, memory)

**Dockerfile**:
```dockerfile
FROM ubuntu:22.04

# Install Claude Code
RUN curl -fsSL https://claude.com/install.sh | sh

# Create non-root user
RUN useradd -m -s /bin/bash sandbox

# Create workspace
RUN mkdir /workspace && chown sandbox:sandbox /workspace

# Switch to non-root
USER sandbox
WORKDIR /workspace

ENTRYPOINT ["claude-code", "--yolo"]
```

## Files to Create

1. **`/workspaces/fluidmcp/sandbox_server.py`** (~500-700 lines)
   - MCP server using stdin/stdout JSON-RPC
   - Docker container management
   - File upload/download handling
   - Session management
   - Yolo mode orchestration

2. **`/workspaces/fluidmcp/docker/Dockerfile.claude-code`**
   - Claude Code sandbox image

3. **`/workspaces/fluidmcp/docker/Dockerfile.opencode`**
   - OpenCode sandbox image

4. **`/workspaces/fluidmcp/examples/sandbox-config.json`**
   - Example configuration

5. **`/workspaces/fluidmcp/README-SANDBOX.md`**
   - Complete documentation
   - Security model explanation
   - Use cases and examples

## Files to Reference

- `/workspaces/fluidmcp/fluidmcp/cli/services/package_launcher.py` - Subprocess pattern
- `/workspaces/fluidmcp/fluidmcp/cli/services/server_manager.py` - Process lifecycle
- `/workspaces/fluidmcp/fluidmcp/cli/services/tool_executor.py` - Tool execution pattern
- `/workspaces/fluidmcp/fluidmcp/cli/services/config_resolver.py` - Config handling

## Security Considerations

### Defense Layers

1. **Container Isolation**
   - Filesystem isolation (only /workspace accessible)
   - Network isolation (optional)
   - Process isolation

2. **Resource Limits**
   - CPU: 2 cores max
   - Memory: 4GB max
   - Disk: 100MB per file
   - Time: 5 minutes per task

3. **Network Restrictions**
   - Whitelist approved domains
   - Block localhost access
   - Rate limiting

4. **File System Restrictions**
   - No access to host filesystem
   - Only /workspace is writable
   - File size limits
   - Dangerous file type blocking

5. **Execution Monitoring**
   - Log all commands executed
   - Track resource usage
   - Alert on suspicious activity

## Next Steps

**I need answers to the 5 key questions above before I can finalize the implementation plan.**

Specifically:
1. AgentBox repository URL or description
2. Desired yolo mode level (1-4)
3. Safety boundaries
4. Authentication model
5. Agent preference (Claude Code, OpenCode, or both)

Once you provide this information, I will:
1. Research AgentBox (if URL provided)
2. Create detailed implementation plan
3. Design complete MCP tool schemas
4. Write Docker configurations
5. Provide step-by-step implementation guide
