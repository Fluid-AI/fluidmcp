# FluidMCP CLI Code Flow

This document describes the execution flow for each CLI command in FluidMCP.

---

## Architecture Overview

The run command uses a clean separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                     Config Resolvers                         │
│                (services/config_resolver.py)                 │
├─────────────────────────────────────────────────────────────┤
│  resolve_from_package(pkg)     → ServerConfig               │
│  resolve_from_installed()      → ServerConfig               │
│  resolve_from_file(path)       → ServerConfig               │
│  resolve_from_s3_url(url)      → ServerConfig               │
│  resolve_from_s3_master()      → ServerConfig               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Unified Runner                             │
│                 (services/run_servers.py)                    │
├─────────────────────────────────────────────────────────────┤
│  run_servers(config: ServerConfig, ...)                     │
│    - Install packages if needed                              │
│    - Launch MCP servers via STDIO                            │
│    - Create FastAPI app with routers                         │
│    - Start uvicorn server                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Entry Point

All commands start in `fluidai_mcp/cli.py:main()` (line 223):

```
main()
├── ArgumentParser setup (lines 228-254)
├── Secure mode token handling (lines 261-272)
└── Command dispatch (lines 274-284)
    ├── "install" → install_command()
    ├── "run"     → run_command()
    ├── "edit-env" → edit_env()
    └── "list"    → list_installed_packages()
```

---

## Command: `fluidmcp install <package>`

**Entry:** `install_command()` (line 205)

```
install_command(args)
│
├── parse_package_string(args.package)          [package_installer.py:20]
│   └── Returns {author, package_name, version}
│
├── install_package(package_str, skip_env)      [package_installer.py:63]
│   ├── POST to registry API → get pre_signed_url
│   ├── GET from S3 → download package
│   ├── Extract tar.gz or save JSON
│   └── write_keys_during_install() - prompt for env vars
│
├── resolve_package_dest_dir()                  [cli.py:22]
│
└── [if --master] update_env_from_common_env()  [cli.py:131]
    └── Read .env from install dir, update metadata.json
```

---

## Command: `fluidmcp run ...`

**Entry:** `run_command()` (line 287)

All run variations flow through the same unified path:

```
run_command(args, secure_mode, token)
│
├── resolve_config(args)                        [config_resolver.py:47]
│   │
│   └── Routes to appropriate resolver based on args:
│       ├── --s3           → resolve_from_s3_url()
│       ├── --file         → resolve_from_file()
│       ├── "all" --master → resolve_from_s3_master()
│       ├── "all"          → resolve_from_installed()
│       └── <package>      → resolve_from_package()
│
└── run_servers(config, ...)                    [run_servers.py:32]
    │
    ├── [if config.needs_install]
    │   └── _install_packages_from_config()
    │       ├── install_package() for each
    │       └── update_env_from_config()
    │
    ├── Create FastAPI app
    │
    ├── For each server in config.servers:
    │   └── launch_mcp_using_fastapi_proxy()    [package_launcher.py:35]
    │       ├── Read metadata.json
    │       ├── subprocess.Popen(command) via STDIO
    │       ├── initialize_mcp_server() - handshake
    │       └── create_mcp_router() - FastAPI endpoints
    │
    └── _start_server(app, port)
        └── uvicorn.run()
```

---

## Config Resolvers

Each resolver returns a `ServerConfig` dataclass:

```python
@dataclass
class ServerConfig:
    servers: Dict[str, dict]      # mcpServers config
    needs_install: bool           # Install packages first?
    sync_to_s3: bool              # Sync metadata to S3?
    source_type: str              # For logging
    metadata_path: Optional[Path] # Config file path
```

### Resolver Summary

| Resolver | Source | needs_install | sync_to_s3 |
|----------|--------|---------------|------------|
| `resolve_from_package()` | Single installed package | No | No |
| `resolve_from_installed()` | All installed packages | No | No |
| `resolve_from_file()` | Local JSON file | Yes | No |
| `resolve_from_s3_url()` | S3 presigned URL | Yes | No |
| `resolve_from_s3_master()` | S3 master mode | Yes | Yes |

---

## Command: `fluidmcp list`

**Entry:** `list_installed_packages()` (line 69)

```
list_installed_packages()
│
├── Check INSTALLATION_DIR exists
│
└── For each author/package/version directory:
    └── Print "{author}/{package}@{version}"
```

---

## Command: `fluidmcp edit-env <package>`

**Entry:** `edit_env()` (line 112)

```
edit_env(args)
│
├── resolve_package_dest_dir(args.package)
├── package_exists(dest_dir)
└── edit_env_variables(dest_dir)                [env_manager.py]
    └── Interactive prompt to edit env vars in metadata.json
```

---

## MCP Server Communication Flow

Once an MCP server is launched, communication happens via STDIO:

```
HTTP Request → FastAPI Endpoint
                    │
                    ▼
            JSON-RPC Request
                    │
                    ▼
         process.stdin.write(msg)
                    │
                    ▼
            MCP Server (STDIO)
                    │
                    ▼
         process.stdout.readline()
                    │
                    ▼
            JSON-RPC Response
                    │
                    ▼
         JSONResponse to client
```

**Available endpoints per package:**
- `POST /{package}/mcp` - Raw JSON-RPC proxy
- `POST /{package}/sse` - Server-Sent Events streaming
- `GET /{package}/mcp/tools/list` - List available tools
- `POST /{package}/mcp/tools/call` - Call a specific tool

---

## Key Files

| File | Purpose |
|------|---------|
| `cli.py` | Entry point, argument parsing, command dispatch |
| `services/config_resolver.py` | Config resolution from various sources |
| `services/run_servers.py` | Unified server launching |
| `services/package_installer.py` | Package download and installation |
| `services/package_launcher.py` | MCP server process and FastAPI router creation |
| `services/env_manager.py` | Environment variable management |

---

## Key Directories

| Location | Purpose |
|----------|---------|
| `.fmcp-packages/` | Installed packages root |
| `.fmcp-packages/{author}/{package}/{version}/` | Single package |
| `.fmcp-packages/{...}/metadata.json` | Package config |
| `.fmcp-packages/metadata_all.json` | Merged config (run all) |
| `.fmcp-packages/s3_metadata_all.json` | S3 master config |
| `.fmcp-packages/.env` | Shared env file (master mode) |
