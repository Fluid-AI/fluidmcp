# GitHub MCP Server Support - Specification

## Overview

Adds native support for launching MCP servers directly from GitHub repositories. Users can now configure and run GitHub-based MCP servers alongside registry packages, with automatic metadata extraction from README files when metadata.json is missing.

## Key Changes

### New Functions

#### `find_readme_file(directory: Path) -> Path`

- Searches for README with common naming patterns
- Returns first match or raises FileNotFoundError

#### `extract_json_from_readme(readme_content: str) -> dict`

- Extracts JSON from markdown code blocks or raw JSON
- Prioritizes blocks containing mcpServers key
- Handles nested braces with regex

#### `validate_mcp_metadata(metadata: dict) -> bool`

- Validates JSON structure: must have mcpServers, command, args
- Raises ValueError with specific errors if invalid

### Modified Functions

#### `run_github_server(args, secure_mode, token)`

- Added metadata.json check after cloning
- If missing: README → Extract → Validate → Create metadata.json
- Prompts for env vars using write_keys_during_install

#### `run_from_source(source, source_path, secure_mode, token)`

- Old: Extract fmcp_packages list → loop strings → search config again
- New: Loop config directly → detect type (github_repo vs fmcp_package) → install
- Keeps server_name context throughout (no searching needed)
- Renames package in metadata to match config server name (critical for router URLs)
- Supports both GitHub and registry packages in same config

#### `launch_mcp_using_fastapi_proxy(dest_dir)`

- Added GitHub repo detection: `is_github_repo = (dest_dir / ".git").exists()`
- Sets working directory based on package type:
  - GitHub + npx -y → parent directory (avoids package.json conflicts)
  - GitHub + source code → repo directory (needs source files)
  - Registry → package directory (standard)

## Supported Configuration Formats

### Standalone CLI

```bash
fluidmcp github owner/repo --github-token TOKEN --start-server
fluidmcp github owner/repo --github-token TOKEN --branch develop --start-server
```

### Structured GitHub Config (Recommended)

```json
{
  "mcpServers": {
    "my-server": {
      "github_repo": "owner/repo",
      "github_token": "GITHUB_TOKEN",
      "branch": "main",
      "env": {"API_KEY": "value"},
      "port": "8100"
    }
  }
}
```

### Mixed Registry + GitHub

```json
{
  "mcpServers": {
    "tavily": {
      "fmcp_package": "Tavily/tavily-mcp@0.1.4",
      "env": {"TAVILY_API_KEY": "key"},
      "port": "8100"
    },
    "airbnb": {
      "github_repo": "openbnb-org/mcp-server-airbnb",
      "github_token": "TOKEN",
      "env": {},
      "port": "8200"
    }
  }
}
```

Detection: `github_repo` field → GitHub package, `fmcp_package` field → Registry package

## Directory Structure

- **Registry**: `INSTALLATION_DIR/Author/package-name/version/`
- **GitHub**: `INSTALLATION_DIR/owner/repo-name/branch/` (contains `.git/` directory)

## Key Design Decisions

### 1. Package Renaming

Config uses custom names ("my-server"), metadata has package names ("original-name"). Code renames metadata to match config for correct router URLs (`/my-server/mcp`).

### 2. Working Directory Detection

Checks for `.git` directory instead of path patterns. More reliable, portable across systems.

### 3. README Fallback

`metadata.json` exists → use it. Missing → extract from README → create metadata.json. No README → error.

## Workflow Example

```bash
fluidmcp github openbnb-org/mcp-server-airbnb --github-token TOKEN --start-server
```

1. Clone to `INSTALLATION_DIR/openbnb-org/mcp-server-airbnb/main/`
2. Check `metadata.json` (exists) or extract from README (if missing)
3. Check env vars
4. Launch MCP subprocess with correct working directory
5. Start FastAPI on port 8090