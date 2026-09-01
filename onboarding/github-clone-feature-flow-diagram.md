# GitHub Clone → Feature Flow Diagram

> Complete end-to-end flow showing how FluidMCP clones GitHub repositories and launches MCP servers, including all decision points and error paths.

## Overview

This flow handles the complete lifecycle of running an MCP server from a GitHub repository, from CLI input validation through server startup.

## Feature Flow

```
fluidmcp github owner/repo --github-token TOKEN --start-server
cli.py · github_command()
       │
       ▼
┌────────────────────────────────────┐
│  1. Parse & Validate CLI Args     │
│  cli.py · github_command()         │
└────────────────────────────────────┘
       │
       ▼
< github_token provided? >
  cli.py:494
       │
   [no] ─────────────────────────────────────────► ValueError: "GitHub token is required"
       │
   [yes]
       ▼
┌────────────────────────────────────┐
│  2. Normalize Repository Path     │
│  github_utils.py                   │
│  normalize_github_repo()           │
└────────────────────────────────────┘
  ● Removes URL prefixes
  ● Strips .git suffix
  ● Extracts (owner, repo) tuple
       │
       ▼
< valid 'owner/repo' format? >
  github_utils.py:50
       │
   [no] ─────────────────────────────────────────► ValueError: "Must be 'owner/repo'"
       │
   [yes]
       ▼
┌────────────────────────────────────┐
│  3. Clone GitHub Repository        │
│  github_utils.py                   │
│  clone_github_repo()               │
└────────────────────────────────────┘
  ● Target: .fmcp-packages/owner/repo/branch/
  ● Command: git clone --depth 1 --branch {branch}
       │
       ▼
< repo already cloned? >
  github_utils.py:94
       │
   [yes] ─────────────────────────────────────────► Reuse existing clone (log info)
       │                                              Return dest_dir
       │
   [no]
       ▼
  subprocess.run(['git', 'clone', ...])
  github_utils.py:102-117
       │
       ├─ [auth failed] ────────────────────────────► RuntimeError: "Authentication failed"
       │                                               - Check token validity
       │                                               - Check token permissions
       │
       ├─ [repo not found] ──────────────────────────► RuntimeError: "Repository not found"
       │                                                - Verify owner/repo exists
       │                                                - Check if private + no access
       │
       ├─ [permission denied] ────────────────────────► RuntimeError: "Permission denied"
       │                                                 - Token lacks required scopes
       │
       ├─ [network error] ────────────────────────────► RuntimeError: "Network error"
       │                                                  - Check internet connection
       │
       └─ [success] ──────────────────────────────────► Continue
                                                         Files cloned to disk
       ▼
┌────────────────────────────────────┐
│  4. Extract/Create Metadata        │
│  github_utils.py                   │
│  extract_or_create_metadata()      │
└────────────────────────────────────┘
       │
       ▼
< metadata.json exists? >
  github_utils.py:345
       │
   [yes] ──► Validate existing metadata ──► < valid? > ──[no]──► Log warning, try README
       │                                         │
       │                                      [yes]
       │                                         │
       └─────────────────────────────────────────┘
                                                 │
                                              [no metadata.json]
                                                 │
                                                 ▼
                                    ┌────────────────────────────┐
                                    │  Search for README         │
                                    │  github_utils.py           │
                                    │  find_readme_file()        │
                                    └────────────────────────────┘
                                                 │
                                                 ▼
                                    < README found? >
                                      github_utils.py:194-208
                                                 │
                                             [no] ────────────────► FileNotFoundError:
                                                                     "No README found"
                                                 │
                                             [yes]
                                                 ▼
                                    ┌────────────────────────────┐
                                    │  Extract JSON from README  │
                                    │  github_utils.py           │
                                    │  extract_json_from_readme()│
                                    └────────────────────────────┘
                                      ● Looks for ```json blocks
                                      ● Prioritizes mcpServers key
                                                 │
                                                 ▼
                                    < valid JSON with mcpServers? >
                                      github_utils.py:231-266
                                                 │
                                             [no] ────────────────► ValueError:
                                                                     "No valid JSON in README"
                                                 │
                                             [yes]
                                                 ▼
                                    ┌────────────────────────────┐
                                    │  Write metadata.json       │
                                    │  github_utils.py:366-369   │
                                    └────────────────────────────┘
                                      ● Creates metadata.json in repo root
                                                 │
                                                 └─────────────────────────────────────┐
                                                                                       │
       ┌─────────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────┐
│  5. Launch MCP Server              │
│  package_launcher.py               │
│  launch_mcp_using_fastapi_proxy()  │
└────────────────────────────────────┘
  ● Read metadata.json for command/args
  ● Create subprocess with stdin/stdout pipes
  ● Working dir = metadata location
       │
       ▼
< command found in PATH? >
  package_launcher.py:156-162
       │
   [no] ──────────────────────────────────────────► FileNotFoundError: "Command not found"
       │
   [yes]
       ▼
  subprocess.Popen([command, args], stdin=PIPE, stdout=PIPE)
  package_launcher.py:201-210
       │
       ▼
┌────────────────────────────────────┐
│  6. Initialize MCP Server          │
│  package_launcher.py               │
│  initialize_mcp_server()           │
└────────────────────────────────────┘
  ● Send JSON-RPC initialize request
  ● Wait for response (30s timeout)
       │
       ▼
< initialization success? >
  package_launcher.py:261-362
       │
   [no] ──────────────────────────────────────────► Initialization failed (log warning)
       │                                              Server may not respond properly
       │
   [yes]
       ▼
┌────────────────────────────────────┐
│  7. Create FastAPI Router          │
│  package_launcher.py               │
│  create_mcp_router()               │
└────────────────────────────────────┘
  ● POST /{server}/mcp - JSON-RPC proxy
  ● POST /{server}/sse - Server-sent events
  ● GET /{server}/mcp/tools/list - Tool listing
       │
       ▼
┌────────────────────────────────────┐
│  8. Include Router in FastAPI App  │
│  cli.py · github_command():539     │
│  app.include_router(router)        │
└────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────┐
│  9. Start Uvicorn Server           │
│  cli.py · github_command():544     │
│  uvicorn.run(app, port=8090)       │
└────────────────────────────────────┘
  ● Binds to 0.0.0.0:8090
  ● Swagger UI at /docs
       │
       ▼
  ✓ Server ready: http://localhost:8090/docs
```

## Key Decision Points

| Decision | Location | Yes path | No path |
|----------|----------|----------|---------|
| GitHub token provided? | cli.py:494 | Continue | ValueError: token required |
| Valid 'owner/repo' format? | github_utils.py:50 | Continue | ValueError: invalid format |
| Repository already cloned? | github_utils.py:94 | Reuse existing | Clone from GitHub |
| Git clone successful? | github_utils.py:102-179 | Continue | RuntimeError with details |
| metadata.json exists? | github_utils.py:345 | Validate & use | Try README |
| README found? | github_utils.py:194-208 | Extract JSON | FileNotFoundError |
| Valid JSON in README? | github_utils.py:231-266 | Write metadata.json | ValueError |
| Command in PATH? | package_launcher.py:156-162 | Spawn subprocess | FileNotFoundError |
| MCP initialization success? | package_launcher.py:261-362 | Continue | Log warning, continue |

## Side Effects

| Step | Side Effect | Where |
|------|-------------|-------|
| 3 | Creates directory `.fmcp-packages/owner/repo/branch/` | github_utils.py:90-91 |
| 3 | Clones repository with `git clone --depth 1` | github_utils.py:102-117 |
| 4 | Writes metadata.json (if extracted from README) | github_utils.py:366-369 |
| 5 | Spawns MCP subprocess with stdin/stdout pipes | package_launcher.py:201-210 |
| 6 | Sends JSON-RPC initialize request to subprocess | package_launcher.py:280-294 |
| 9 | Binds HTTP server to port 8090 | cli.py:544 |

## Error Paths

| Trigger | Response | Code |
|---------|----------|------|
| Missing GitHub token | ValueError with message | cli.py (via github_utils:79) |
| Invalid repo format | ValueError: "Must be 'owner/repo'" | github_utils.py:51 |
| Authentication failed | RuntimeError with token help | github_utils.py:128-136 |
| Repository not found | RuntimeError with suggestions | github_utils.py:138-147 |
| Permission denied | RuntimeError with scope help | github_utils.py:149-158 |
| Network error | RuntimeError with network help | github_utils.py:160-169 |
| No README found | FileNotFoundError | github_utils.py:208 |
| Invalid JSON in README | ValueError | github_utils.py:266 |
| Command not found | FileNotFoundError | package_launcher.py:227-229 |
| Init timeout | Logged warning, continues | package_launcher.py:344-357 |

## Step Reference

| Step | Name | File | Function | Notes |
|------|------|------|----------|-------|
| 1 | Parse CLI Args | cli.py | github_command() | Validate token, repo, branch |
| 2 | Normalize Repo Path | github_utils.py | normalize_github_repo() | Convert to (owner, repo) tuple |
| 3 | Clone Repository | github_utils.py | clone_github_repo() | Git shallow clone, checks if already exists |
| 4 | Extract Metadata | github_utils.py | extract_or_create_metadata() | Use existing or extract from README |
| 5 | Launch MCP Server | package_launcher.py | launch_mcp_using_fastapi_proxy() | Spawn subprocess with pipes |
| 6 | Initialize Server | package_launcher.py | initialize_mcp_server() | JSON-RPC handshake, 30s timeout |
| 7 | Create Router | package_launcher.py | create_mcp_router() | Build FastAPI routes |
| 8 | Include Router | cli.py | app.include_router() | Mount routes in app |
| 9 | Start Server | cli.py | uvicorn.run() | Bind to port 8090 |
