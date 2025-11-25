# FluidMCP CLI Code Flow

This document describes the execution flow for each CLI command in FluidMCP.

---

## Entry Point

All commands start in `fluidai_mcp/cli.py:main()` (line 856):

```
main()
├── ArgumentParser setup (lines 861-888)
├── Secure mode token handling (lines 894-905)
└── Command dispatch (lines 908-928)
    ├── "install" → install_command()
    ├── "run" → run_server() / run_all() / run_all_master() / run_from_source()
    ├── "edit-env" → edit_env()
    └── "list" → list_installed_packages()
```

---

## Command: `fluidmcp install <package>`

**Entry:** `install_command()` (line 601)

```
install_command(args)
│
├── parse_package_string(args.package)          [package_installer.py:20]
│   └── Returns {author, package_name, version}
│
├── install_package(package_str, skip_env)      [package_installer.py:63]
│   ├── make_registry_request()                 [package_installer.py:164]
│   │   └── Build headers/payload for API call
│   │
│   ├── POST to MCP_FETCH_URL (registry API)
│   │   └── Returns pre_signed_url for S3
│   │
│   ├── GET from S3 pre_signed_url
│   │   └── Download package content
│   │
│   ├── Detect file type (tar.gz or JSON)
│   │   ├── tar.gz → Extract to dest_dir
│   │   └── JSON → Save as metadata.json
│   │
│   └── write_keys_during_install()             [env_manager.py]
│       └── Prompt user for env variables (unless skip_env=True)
│
├── resolve_package_dest_dir()                  [cli.py:41]
│   └── Find installed package path
│
└── [if --master] update_env_from_common_env()  [cli.py:531]
    └── Read .env from install dir, update metadata.json
```

**Package destination:** `.fmcp-packages/{author}/{package_name}/{version}/`

---

## Command: `fluidmcp run <package> --start-server`

**Entry:** `run_server()` (line 282)

```
run_server(args, secure_mode, token)
│
├── resolve_package_dest_dir(args.package)      [cli.py:41]
│   └── Find package install path
│
├── package_exists(dest_dir)                    [package_installer.py:129]
│
├── [if secure_mode] Set FMCP_BEARER_TOKEN env var
│
├── launch_mcp_using_fastapi_proxy(dest_dir)    [package_launcher.py:35]
│   │
│   ├── Read metadata.json from dest_dir
│   │   └── Extract command, args, env from mcpServers
│   │
│   ├── Resolve command path (npm/npx)
│   │
│   ├── subprocess.Popen(stdio_command)
│   │   └── Start MCP server as child process with STDIO
│   │
│   ├── initialize_mcp_server(process)          [package_launcher.py:116]
│   │   ├── Send JSON-RPC "initialize" request
│   │   ├── Wait for response
│   │   └── Send "notifications/initialized"
│   │
│   └── create_mcp_router(pkg, process)         [package_launcher.py:157]
│       └── Create FastAPI router with endpoints:
│           ├── POST /{pkg}/mcp        (JSON-RPC proxy)
│           ├── POST /{pkg}/sse        (SSE streaming)
│           ├── GET  /{pkg}/mcp/tools/list
│           └── POST /{pkg}/mcp/tools/call
│
├── [if --start-server]
│   ├── Check port availability (is_port_in_use)
│   ├── [if busy] Kill existing or prompt user
│   │
│   ├── Create FastAPI app
│   ├── app.include_router(router)
│   └── uvicorn.run(app, port=8090)
```

---

## Command: `fluidmcp run all --start-server`

**Entry:** `run_all()` (line 207)

```
run_all(secure_mode, token)
│
├── Check INSTALLATION_DIR exists
│
├── Load existing metadata_all.json (if exists)
│   └── Collect already-assigned ports
│
├── collect_installed_servers_metadata()        [cli.py:151]
│   │
│   └── For each installed package:
│       ├── get_latest_version_dir()
│       ├── Read metadata.json
│       ├── find_free_port(taken_ports)
│       ├── Assign port to server config
│       └── Add to merged metadata
│
├── Write merged metadata to metadata_all.json
│
├── Create FastAPI app (Multi-Server Gateway)
│
├── For each server in merged metadata:
│   ├── launch_mcp_using_fastapi_proxy(dest_dir)
│   └── app.include_router(router)
│
├── kill_process_on_port(8099)
└── uvicorn.run(app, port=8099)
```

---

## Command: `fluidmcp run <file.json> --file --start-server`

**Entry:** `run_from_source("file", ...)` (line 619)

```
run_from_source("file", source_path, secure_mode, token)
│
├── extract_config_from_file(source_path)       [cli.py:736]
│   │
│   ├── preprocess_metadata_file(file_path)     [cli.py:800]
│   │   │
│   │   └── For each server in mcpServers:
│   │       ├── [if dict] Skip (already expanded)
│   │       └── [if string] Replace with actual metadata
│   │           ├── replace_package_metadata_from_package_name()
│   │           │   └── GET from registry to fetch full metadata
│   │           ├── Delete string entry
│   │           ├── Add expanded metadata with package_name key
│   │           └── Assign free port
│   │
│   ├── Load JSON from file
│   ├── validate_metadata_config()
│   └── Return config dict
│
├── For each package in config:
│   ├── parse_package_string()
│   ├── install_package_from_file()             [package_installer.py:138]
│   │   └── install_package(skip_env=True)
│   │
│   └── update_env_from_config()                [env_manager.py]
│       └── Copy env values from config to metadata.json
│
├── Create FastAPI app
│
├── For each server with install_path:
│   ├── launch_mcp_using_fastapi_proxy()
│   └── app.include_router(router)
│
├── kill_process_on_port(8099)
└── uvicorn.run(app, port=8099)
```

---

## Command: `fluidmcp run <s3-url> --s3 --start-server`

**Entry:** `run_from_source("s3", ...)` (line 619)

```
run_from_source("s3", presigned_url, secure_mode, token)
│
├── extract_config_from_s3(presigned_url)       [cli.py:756]
│   │
│   ├── Create temp file path in INSTALLATION_DIR
│   ├── requests.get(presigned_url)
│   ├── Save response to s3_metadata_all.json
│   ├── preprocess_metadata_file()              [same as --file]
│   ├── Load and validate JSON
│   └── Return config dict
│
└── [Rest is identical to --file flow]
```

---

## Command: `fluidmcp run all --master`

**Entry:** `run_all_master()` (line 361)

```
run_all_master(args, secure_mode, token)
│
├── Create S3 client (boto3)
│
├── Check if s3_metadata_all.json exists in S3
│   ├── [if exists] s3_download_file() to local
│   └── [if not] collect_installed_servers_metadata()
│       ├── write_json_file() locally
│       └── s3_upload_file() to S3
│
├── Load s3_metadata_all.json
│
├── Kill processes on assigned ports
│
├── For each fmcp_package:
│   ├── parse_package_string()
│   ├── install_package(skip_env=True)
│   └── update_env_from_common_env()
│       └── Read from shared .env file
│
├── Create FastAPI app (Master Mode)
│
├── For each server with install_path:
│   ├── launch_mcp_using_fastapi_proxy()
│   └── app.include_router(router)
│
├── kill_process_on_port(8099)
└── uvicorn.run(app, port=8099)
```

---

## Command: `fluidmcp list`

**Entry:** `list_installed_packages()` (line 88)

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

**Entry:** `edit_env()` (line 131)

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

## Key File Locations

| Purpose | Location |
|---------|----------|
| Installed packages | `.fmcp-packages/{author}/{package}/{version}/` |
| Package metadata | `.fmcp-packages/{author}/{package}/{version}/metadata.json` |
| Merged metadata (run all) | `.fmcp-packages/metadata_all.json` |
| S3 metadata (master mode) | `.fmcp-packages/s3_metadata_all.json` |
| Shared env file (master) | `.fmcp-packages/.env` |
