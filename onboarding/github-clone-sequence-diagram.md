# GitHub Clone → Sequence Diagram

> Step-by-step interactions between actors showing who calls who, in what order, with what data during GitHub repository cloning and MCP server launch.

## Participants

| Actor | File | Key Function |
|-------|------|-------------|
| User | – | CLI caller |
| CLI | cli.py | github_command() |
| GitHubUtils | github_utils.py | clone_github_repo(), extract_or_create_metadata() |
| Git Process | External | git clone subprocess |
| Filesystem | OS | File I/O operations |
| PackageLauncher | package_launcher.py | launch_mcp_using_fastapi_proxy(), create_mcp_router() |
| MCP Process | Subprocess | MCP server subprocess |
| Uvicorn | External | HTTP server |

## Sequence

```
     User                 CLI                 GitHubUtils          Git Process        Filesystem
                       cli.py                github_utils.py       (subprocess)        (disk)
                       github_command()
        │                  │                      │                    │                 │
   1.   │──fluidmcp github owner/repo ───────────►│                    │                 │
        │  --github-token TOKEN --start-server    │                    │                 │
        │                  │                      │                    │                 │
   2.   │                  │──clone_github_repo()─►│                    │                 │
        │                  │  (repo, token, branch)│                    │                 │
        │                  │                      │                    │                 │
   3.   │                  │                      │──normalize_github_repo()──►          │
        │                  │                      │  (owner/repo)      │                 │
        │                  │                      │                    │                 │
   4.   │                  │                      │◄─── (owner, repo) ─│                 │
        │                  │                      │                    │                 │
   5.   │                  │                      │──Check: .fmcp-packages/owner/repo/branch/─►│
        │                  │                      │  Path.exists()     │                 │
        │                  │                      │                    │                 │
   6.   │                  │                      │◄─── False ─────────│                 │
        │                  │                      │  (not exists)      │                 │
        │                  │                      │                    │                 │
   7.   │                  │                      │──subprocess.run()──►│                 │
        │                  │                      │  ['git', 'clone',  │                 │
        │                  │                      │   '--depth', '1',  │                 │
        │                  │                      │   '--branch', branch,│                │
        │                  │                      │   clone_url, dest] │                 │
        │                  │                      │                    │                 │
   8.   │                  │                      │                    │──Clone repo to disk─►│
        │                  │                      │                    │  .fmcp-packages/   │
        │                  │                      │                    │  owner/repo/branch/│
        │                  │                      │                    │                 │
   9.   │                  │                      │◄─── returncode 0 ──│                 │
        │                  │                      │  (success)         │                 │
        │                  │                      │                    │                 │
  10.   │                  │◄─── dest_dir ────────│                    │                 │
        │                  │  Path object         │                    │                 │
        │                  │                      │                    │                 │
  11.   │                  │──extract_or_create_metadata()──►          │                 │
        │                  │  (dest_dir)          │                    │                 │
        │                  │                      │                    │                 │
  12.   │                  │                      │──Check: dest_dir/metadata.json ──────►│
        │                  │                      │  Path.exists()     │                 │
        │                  │                      │                    │                 │
  13.   │                  │                      │◄─── False ─────────│                 │
        │                  │                      │                    │                 │
  14.   │                  │                      │──find_readme_file()──────────────────►│
        │                  │                      │  Search for README │                 │
        │                  │                      │                    │                 │
  15.   │                  │                      │◄─── README.md path │                 │
        │                  │                      │                    │                 │
  16.   │                  │                      │──Read README.md ───────────────────────►│
        │                  │                      │                    │                 │
  17.   │                  │                      │◄─── file contents ──│                 │
        │                  │                      │                    │                 │
  18.   │                  │                      │──extract_json_from_readme()──►       │
        │                  │                      │  Parse JSON blocks │                 │
        │                  │                      │                    │                 │
  19.   │                  │                      │◄─── metadata dict ─│                 │
        │                  │                      │  {mcpServers: ...} │                 │
        │                  │                      │                    │                 │
  20.   │                  │                      │──Write metadata.json ─────────────────►│
        │                  │                      │  json.dump()       │                 │
        │                  │                      │                    │                 │
  21.   │                  │◄─── metadata_path ───│                    │                 │
        │                  │  Path object         │                    │                 │
        │                  │                      │                    │                 │


     User                 CLI              PackageLauncher         MCP Process        Uvicorn
                       cli.py             package_launcher.py      (subprocess)      (server)
                       github_command()
        │                  │                      │                    │                 │
  22.   │                  │──launch_mcp_using_fastapi_proxy()─────────►│                 │
        │                  │  (dest_dir, lock)    │                    │                 │
        │                  │                      │                    │                 │
  23.   │                  │                      │──Read metadata.json ─────►           │
        │                  │                      │  (from dest_dir)   │                 │
        │                  │                      │                    │                 │
  24.   │                  │                      │──subprocess.Popen()─►│                │
        │                  │                      │  [command, args],  │                 │
        │                  │                      │  stdin=PIPE,       │                 │
        │                  │                      │  stdout=PIPE       │                 │
        │                  │                      │                    │                 │
  25.   │                  │                      │                    │──MCP process    │
        │                  │                      │                    │  starts         │
        │                  │                      │                    │  (running)      │
        │                  │                      │                    │                 │
  26.   │                  │                      │──initialize_mcp_server()─────►       │
        │                  │                      │  JSON-RPC init     │                 │
        │                  │                      │  {"jsonrpc": "2.0",│                 │
        │                  │                      │   "method": "initialize",│            │
        │                  │                      │   ...}             │                 │
        │                  │                      │                    │                 │
  27.   │                  │                      │  process.stdin.write()───────────►    │
        │                  │                      │  Send init request │                 │
        │                  │                      │                    │                 │
  28.   │                  │                      │◄─── response ───────│                 │
        │                  │                      │  process.stdout.readline()           │
        │                  │                      │  {"result": {...}} │                 │
        │                  │                      │                    │                 │
  29.   │                  │                      │──Send initialized notification───────►│
        │                  │                      │  {"method": "notifications/          │
        │                  │                      │   initialized"}    │                 │
        │                  │                      │                    │                 │
  30.   │                  │                      │──create_mcp_router()────►            │
        │                  │                      │  (package_name, process, lock)       │
        │                  │                      │  Creates APIRouter │                 │
        │                  │                      │  with endpoints:   │                 │
        │                  │                      │  - POST /{server}/mcp│                │
        │                  │                      │  - POST /{server}/sse│                │
        │                  │                      │  - GET /{server}/mcp/tools/list      │
        │                  │                      │                    │                 │
  31.   │                  │◄─── (name, router, process) ──────────────│                 │
        │                  │  Tuple return        │                    │                 │
        │                  │                      │                    │                 │
  32.   │                  │──Create FastAPI app──►│                    │                 │
        │                  │  FastAPI()           │                    │                 │
        │                  │                      │                    │                 │
  33.   │                  │──app.include_router(router)───►           │                 │
        │                  │  Mount routes        │                    │                 │
        │                  │                      │                    │                 │
  34.   │                  │──uvicorn.run()────────────────────────────►│                 │
        │                  │  (app, host="0.0.0.0", port=8090)         │                 │
        │                  │                      │                    │                 │
  35.   │                  │                      │                    │──HTTP server    │
        │                  │                      │                    │  listening      │
        │                  │                      │                    │  0.0.0.0:8090   │
        │                  │                      │                    │                 │
  36.   │◄───Server ready: http://localhost:8090/docs────────────────────────────────────│
        │                  │                      │                    │                 │
```

## Notes

- **Steps 1-21**: Repository cloning and metadata extraction phase
- **Steps 22-31**: MCP server launch and initialization phase
- **Steps 32-36**: FastAPI application setup and server startup
- **Parallel execution**: The MCP subprocess (step 24) runs concurrently with the CLI process after being spawned
- **Synchronous communication**: Steps 26-29 show JSON-RPC request/response over stdin/stdout pipes
- **Port binding**: Step 34 binds to port 8090 (configurable via MCP_CLIENT_SERVER_PORT env var)

## Interaction Summary

| Step | From | To | Call | Returns |
|------|------|----|------|---------|
| 1 | User | CLI | fluidmcp github command | – |
| 2 | CLI | GitHubUtils | clone_github_repo() | Path |
| 3-4 | GitHubUtils | GitHubUtils | normalize_github_repo() | (owner, repo) |
| 5-6 | GitHubUtils | Filesystem | Check if cloned | False |
| 7-9 | GitHubUtils | Git Process | subprocess.run() | returncode 0 |
| 8 | Git Process | Filesystem | Clone files | – |
| 10 | GitHubUtils | CLI | dest_dir | Path |
| 11 | CLI | GitHubUtils | extract_or_create_metadata() | Path |
| 12-13 | GitHubUtils | Filesystem | Check metadata.json | False |
| 14-15 | GitHubUtils | Filesystem | find_readme_file() | Path |
| 16-17 | GitHubUtils | Filesystem | Read README.md | str |
| 18-19 | GitHubUtils | GitHubUtils | extract_json_from_readme() | dict |
| 20 | GitHubUtils | Filesystem | Write metadata.json | – |
| 21 | GitHubUtils | CLI | metadata_path | Path |
| 22 | CLI | PackageLauncher | launch_mcp_using_fastapi_proxy() | tuple |
| 23 | PackageLauncher | Filesystem | Read metadata.json | dict |
| 24 | PackageLauncher | MCP Process | subprocess.Popen() | Popen |
| 26-28 | PackageLauncher | MCP Process | JSON-RPC initialize | response |
| 29 | PackageLauncher | MCP Process | notifications/initialized | – |
| 30 | PackageLauncher | PackageLauncher | create_mcp_router() | APIRouter |
| 31 | PackageLauncher | CLI | tuple | (name, router, process) |
| 32 | CLI | CLI | FastAPI() | FastAPI app |
| 33 | CLI | FastAPI | include_router() | – |
| 34 | CLI | Uvicorn | uvicorn.run() | – |
| 36 | Uvicorn | User | Server URL | – |
