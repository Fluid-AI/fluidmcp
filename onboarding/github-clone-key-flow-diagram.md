# GitHub Clone → Key Flow

> Quick overview of how FluidMCP clones and runs MCP servers from GitHub repositories.

**Key steps:** Receive GitHub command → Normalize repo URL → Clone repository → Extract metadata → Launch MCP server → Create FastAPI router → Start uvicorn

## Flow Diagram

```
  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
  │  1. Receive     │───► │  2. Normalize   │───► │  3. Clone       │───► │  4. Extract     │
  │  GitHub Command │     │  Repo URL       │     │  Repository     │     │  Metadata       │
  │  cli.py         │     │  github_utils   │     │  github_utils   │     │  github_utils   │
  │  github_        │     │  .py            │     │  .py            │     │  .py            │
  │  command()      │     │  normalize_     │     │  clone_github_  │     │  extract_or_    │
  └─────────────────┘     │  github_repo()  │     │  repo()         │     │  create_        │
                          └─────────────────┘     └─────────────────┘     │  metadata()     │
                                                                           └─────────────────┘
                                                                                    │
                                                                                    ▼
  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
  │  7. Start       │◄─── │  6. Create      │◄─── │  5. Launch      │◄────│                 │
  │  Uvicorn        │     │  FastAPI Router │     │  MCP Server     │     │                 │
  │  cli.py         │     │  package_       │     │  package_       │     │                 │
  │  github_        │     │  launcher.py    │     │  launcher.py    │     │                 │
  │  command()      │     │  create_mcp_    │     │  launch_mcp_    │     │                 │
  │  uvicorn.run()  │     │  router()       │     │  using_fastapi_ │     │                 │
  └─────────────────┘     └─────────────────┘     │  proxy()        │     │                 │
                                                   └─────────────────┘     │                 │
                                                                           └─────────────────┘
```

## Notes

- **Step 1-2**: CLI parses `fluidmcp github owner/repo --github-token TOKEN --start-server` and normalizes the GitHub URL
- **Step 3**: Uses `git clone --depth 1` to shallow clone the repository into `.fmcp-packages/owner/repo/branch/`
- **Step 4**: Checks for metadata.json, falls back to extracting JSON from README if needed
- **Step 5**: Spawns MCP subprocess with stdin/stdout pipes, initializes via JSON-RPC handshake
- **Step 6**: Creates FastAPI router with POST /{server}/mcp endpoint for JSON-RPC proxying
- **Step 7**: Binds to port 8090, provides Swagger UI at /docs

## Step Summary

| Step | Name | File | Function | Role |
|------|------|------|----------|------|
| 1 | Receive GitHub Command | cli.py | github_command() | Parse CLI args & validate |
| 2 | Normalize Repo URL | github_utils.py | normalize_github_repo() | Convert URL to (owner, repo) |
| 3 | Clone Repository | github_utils.py | clone_github_repo() | Git shallow clone to local |
| 4 | Extract Metadata | github_utils.py | extract_or_create_metadata() | Get/create metadata.json |
| 5 | Launch MCP Server | package_launcher.py | launch_mcp_using_fastapi_proxy() | Spawn subprocess & initialize |
| 6 | Create FastAPI Router | package_launcher.py | create_mcp_router() | Build HTTP endpoints |
| 7 | Start Uvicorn | cli.py | github_command() → uvicorn.run() | Start HTTP server |
