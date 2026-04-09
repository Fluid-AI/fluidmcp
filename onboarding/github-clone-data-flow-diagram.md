# GitHub Clone → Data Flow Diagram

> Shows how data moves through the system from CLI input to running HTTP server, tracing transformations at each processing layer.

## Overview

This diagram traces the data pipeline for cloning a GitHub repository and launching an MCP server, showing how raw CLI arguments transform through validation, cloning, metadata extraction, server launch, and ultimately become HTTP endpoints.

## Data Flow

```
┌─── INPUT ───────────────────────────────────────────────────────────────────┐
│                                                                              │
│  [ CLI Command ]                                                             │
│  fluidmcp github owner/repo --github-token gh_token123 --start-server       │
│  cli.py · github_command()                                                   │
│                                                                              │
│                     ↓                                                        │
│                                                                              │
│  [ Parsed Args ]                                                             │
│  {                                                                           │
│    repo: "owner/repo",                                                       │
│    github_token: "gh_token123",                                              │
│    branch: None  // defaults to "main"                                       │
│    start_server: True                                                        │
│  }                                                                           │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                     ↓
┌─── VALIDATION ──────────────────────────────────────────────────────────────┐
│                                                                              │
│  ┌──────────────────────────────────────────┐                               │
│  │  normalize_github_repo()                 │                               │
│  │  github_utils.py:22-54                   │                               │
│  │  Input: "owner/repo"                     │                               │
│  │  Removes: https://, .git suffix          │                               │
│  │  Validates: "/" count == 1               │                               │
│  └──────────────────────────────────────────┘                               │
│                     ↓                                                        │
│  [ Normalized Repo ]                                                         │
│  (owner="owner", repo="repo")  // tuple                                      │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                     ↓
┌─── PROCESSING ──────────────────────────────────────────────────────────────┐
│                                                                              │
│  ┌──────────────────────────────────────────┐                               │
│  │  clone_github_repo()                     │                               │
│  │  github_utils.py:57-179                  │                               │
│  │  Input: ("owner", "repo", "gh_token123", "main")                         │
│  └──────────────────────────────────────────┘                               │
│                     ↓                                                        │
│                                                                              │
│  [ Clone URL ]                                                               │
│  f"https://{token}@github.com/{owner}/{repo}.git"                           │
│  → "https://gh_token123@github.com/owner/repo.git"                          │
│                                                                              │
│                     ↓                                                        │
│                                                                              │
│  [ Git Command ]                                                             │
│  ["git", "clone", "--depth", "1", "--branch", "main", clone_url, dest_dir]  │
│  subprocess.run() → github_utils.py:102-117                                  │
│                                                                              │
│                     ↓                                                        │
│                                                                              │
│  [ Cloned Files ]  ──────────────────► Filesystem                            │
│  .fmcp-packages/owner/repo/main/                                             │
│    ├── README.md                                                             │
│    ├── src/                                                                  │
│    ├── package.json                                                          │
│    └── ... (repository contents)                                             │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                     ↓
┌─── METADATA EXTRACTION ─────────────────────────────────────────────────────┐
│                                                                              │
│  ┌──────────────────────────────────────────┐                               │
│  │  extract_or_create_metadata()            │                               │
│  │  github_utils.py:323-383                 │                               │
│  └──────────────────────────────────────────┘                               │
│                     ↓                                                        │
│                                                                              │
│  < metadata.json exists? >                                                   │
│         │                                                                    │
│     [NO]                                                                     │
│         ↓                                                                    │
│  ┌──────────────────────────────────────────┐                               │
│  │  find_readme_file()                      │                               │
│  │  github_utils.py:181-209                 │                               │
│  │  Searches for: README.md, readme.md, ... │                               │
│  └──────────────────────────────────────────┘                               │
│                     ↓                                                        │
│  [ README Content ]                                                          │
│  "# MCP Server\n```json\n{\"mcpServers\": {...}}\n```"                       │
│                                                                              │
│                     ↓                                                        │
│  ┌──────────────────────────────────────────┐                               │
│  │  extract_json_from_readme()              │                               │
│  │  github_utils.py:211-267                 │                               │
│  │  Regex: r'```(?:json)?\s*\n([\s\S]*?)\n```'                              │
│  └──────────────────────────────────────────┘                               │
│                     ↓                                                        │
│  [ JSON String ]                                                             │
│  "{\"mcpServers\": {\"server-name\": {\"command\": \"npx\", ...}}}"          │
│                                                                              │
│                     ↓                                                        │
│  json.loads() → github_utils.py:239                                          │
│                     ↓                                                        │
│  [ Metadata Dict ]                                                           │
│  {                                                                           │
│    "mcpServers": {                                                           │
│      "server-name": {                                                        │
│        "command": "npx",                                                     │
│        "args": ["-y", "@modelcontextprotocol/server-example"],              │
│        "env": {"API_KEY": "placeholder"}                                     │
│      }                                                                       │
│    }                                                                         │
│  }                                                                           │
│                     ↓                                                        │
│  ┌──────────────────────────────────────────┐                               │
│  │  validate_mcp_metadata()                 │                               │
│  │  github_utils.py:269-321                 │                               │
│  │  Checks: mcpServers key, command, args   │                               │
│  └──────────────────────────────────────────┘                               │
│                     ↓                                                        │
│  [ Validated Metadata ] ──────────────► Write to Filesystem                 │
│  .fmcp-packages/owner/repo/main/metadata.json                                │
│  json.dump() → github_utils.py:366-369                                       │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                     ↓
┌─── SERVER LAUNCH ───────────────────────────────────────────────────────────┐
│                                                                              │
│  ┌──────────────────────────────────────────┐                               │
│  │  launch_mcp_using_fastapi_proxy()        │                               │
│  │  package_launcher.py:106-232             │                               │
│  └──────────────────────────────────────────┘                               │
│                     ↓                                                        │
│  [ Read Metadata ]  ◄──────────────────── Filesystem                        │
│  metadata = json.load(metadata.json)                                         │
│  package_launcher.py:124-126                                                 │
│                     ↓                                                        │
│  [ Extract Server Config ]                                                   │
│  command = servers["command"]  // "npx"                                      │
│  args = servers["args"]        // ["-y", "@modelcontextprotocol/..."]       │
│  env = servers.get("env", {}) // {"API_KEY": "..."}                         │
│  package_launcher.py:152-168                                                 │
│                     ↓                                                        │
│  [ Resolve Command Path ]                                                    │
│  npx_path = shutil.which("npx")  // "/usr/bin/npx"                          │
│  package_launcher.py:156-162                                                 │
│                     ↓                                                        │
│  [ Subprocess Command ]                                                      │
│  stdio_command = ["/usr/bin/npx", "-y", "@modelcontextprotocol/..."]        │
│  package_launcher.py:167                                                     │
│                     ↓                                                        │
│  ┌──────────────────────────────────────────┐                               │
│  │  subprocess.Popen()                      │                               │
│  │  package_launcher.py:201-210             │                               │
│  │  stdin=PIPE, stdout=PIPE, stderr=PIPE    │                               │
│  │  env=merged_env, cwd=working_dir         │                               │
│  └──────────────────────────────────────────┘                               │
│                     ↓                                                        │
│  [ Running Process ]                                                         │
│  subprocess.Popen object with PID                                            │
│  process.stdin  ──► Pipe to MCP subprocess                                   │
│  process.stdout ◄── Pipe from MCP subprocess                                 │
│                     ↓                                                        │
│  ┌──────────────────────────────────────────┐                               │
│  │  initialize_mcp_server()                 │                               │
│  │  package_launcher.py:261-362             │                               │
│  │  Send: {"jsonrpc": "2.0", "method": "initialize", ...}                   │
│  │  Receive: {"id": 0, "result": {...}}     │                               │
│  └──────────────────────────────────────────┘                               │
│                     ↓                                                        │
│  [ Initialized MCP Server ]                                                  │
│  Process ready to handle JSON-RPC requests                                   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                     ↓
┌─── ROUTER CREATION ─────────────────────────────────────────────────────────┐
│                                                                              │
│  ┌──────────────────────────────────────────┐                               │
│  │  create_mcp_router()                     │                               │
│  │  package_launcher.py:365-604             │                               │
│  └──────────────────────────────────────────┘                               │
│                     ↓                                                        │
│  [ FastAPI Router ]                                                          │
│  APIRouter() with endpoints:                                                 │
│    • POST   /{package_name}/mcp           → JSON-RPC proxy                   │
│    • POST   /{package_name}/sse           → Server-sent events               │
│    • GET    /{package_name}/mcp/tools/list → Tool discovery                  │
│    • POST   /{package_name}/mcp/tools/call → Tool execution                  │
│  package_launcher.py:372-604                                                 │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                     ↓
┌─── OUTPUT ──────────────────────────────────────────────────────────────────┐
│                                                                              │
│  ┌──────────────────────────────────────────┐                               │
│  │  FastAPI Application                     │                               │
│  │  cli.py:532-537                          │                               │
│  │  app = FastAPI(title, description, ...)  │                               │
│  │  app.include_router(router)              │                               │
│  └──────────────────────────────────────────┘                               │
│                     ↓                                                        │
│  ┌──────────────────────────────────────────┐                               │
│  │  uvicorn.run()                           │                               │
│  │  cli.py:544                              │                               │
│  │  (app, host="0.0.0.0", port=8090)        │                               │
│  └──────────────────────────────────────────┘                               │
│                     ↓                                                        │
│  [ Running HTTP Server ]                                                     │
│  http://0.0.0.0:8090                                                         │
│                                                                              │
│  Available endpoints:                                                        │
│    GET  /docs                    → Swagger UI                                │
│    POST /{server}/mcp            → JSON-RPC requests to MCP server           │
│    POST /{server}/sse            → SSE streaming from MCP server             │
│    GET  /{server}/mcp/tools/list → List available tools                      │
│    POST /{server}/mcp/tools/call → Execute a tool                            │
│                                                                              │
│  User can now make HTTP requests ───────────► HTTP 200 responses             │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Data Transformations

| Input | Transformation | Output | Location |
|-------|---------------|--------|----------|
| CLI string "owner/repo" | normalize_github_repo() | Tuple (owner, repo) | github_utils.py:22-54 |
| Tuple + token | Build clone URL | HTTPS URL with token | github_utils.py:99 |
| Clone URL + dest | Git subprocess | Cloned files on disk | github_utils.py:102-117 |
| README markdown | Regex + JSON parse | Metadata dict | github_utils.py:211-267 |
| Metadata dict | JSON validation | Validated metadata | github_utils.py:269-321 |
| Validated metadata | json.dump() | metadata.json file | github_utils.py:366-369 |
| metadata.json | Read + parse | Server config dict | package_launcher.py:124-126 |
| Server config | Resolve paths | Subprocess command list | package_launcher.py:152-168 |
| Command list + env | subprocess.Popen() | Running process | package_launcher.py:201-210 |
| Running process | JSON-RPC handshake | Initialized MCP server | package_launcher.py:261-362 |
| Process + config | create_mcp_router() | FastAPI APIRouter | package_launcher.py:365-604 |
| APIRouter | app.include_router() | Mounted HTTP routes | cli.py:539 |
| FastAPI app | uvicorn.run() | HTTP server on port 8090 | cli.py:544 |

## Data Flow Summary

| Step | Component | File | Function | Data In | Data Out |
|------|-----------|------|----------|---------|----------|
| 1 | CLI Parser | cli.py | github_command() | CLI args string | Parsed namespace |
| 2 | URL Normalizer | github_utils.py | normalize_github_repo() | "owner/repo" string | (owner, repo) tuple |
| 3 | Git Cloner | github_utils.py | clone_github_repo() | Tuple + token + branch | Cloned repo path |
| 4 | README Finder | github_utils.py | find_readme_file() | Directory path | README path |
| 5 | JSON Extractor | github_utils.py | extract_json_from_readme() | README text | Metadata dict |
| 6 | Metadata Validator | github_utils.py | validate_mcp_metadata() | Dict | Validated dict |
| 7 | Metadata Writer | github_utils.py | json.dump() | Dict | metadata.json file |
| 8 | Config Reader | package_launcher.py | json.load() | metadata.json | Config dict |
| 9 | Server Launcher | package_launcher.py | launch_mcp_using_fastapi_proxy() | Config + path | (name, router, process) |
| 10 | Process Spawner | package_launcher.py | subprocess.Popen() | Command + env | Popen object |
| 11 | MCP Initializer | package_launcher.py | initialize_mcp_server() | Process | Initialized state |
| 12 | Router Creator | package_launcher.py | create_mcp_router() | Name + process | APIRouter |
| 13 | App Builder | cli.py | FastAPI() | Title + config | FastAPI app |
| 14 | Router Mounter | cli.py | include_router() | Router | Mounted routes |
| 15 | Server Starter | cli.py | uvicorn.run() | App + port | HTTP server |
