# GitHub Clone: Adding MCP Servers from GitHub Repositories

FluidMCP supports cloning GitHub repositories and registering them as MCP servers via the REST API and the web UI. This document covers the architecture, API, security model, and known limitations.

## Overview

The GitHub clone feature allows users to:

1. Provide a GitHub repository URL (or `owner/repo` shorthand)
2. FluidMCP clones the repo, extracts `metadata.json`, and reads the MCP server configuration
3. The server config is persisted to MongoDB and becomes available for start/stop like any other server

This works for both single-server repos and monorepos containing multiple MCP servers.
1
## API

### `POST /api/servers/from-github`

Clones a GitHub repository, extracts MCP server configuration from `metadata.json`, and registers the server(s) in MongoDB.

**Headers:**

| Header | Required | Description |
|--------|----------|-------------|
| `X-GitHub-Token` | Yes | GitHub personal access token. Sent in header only — never in the request body, never logged, never persisted. |

**Request body:**

```json
{
  "github_repo": "awslabs/mcp",
  "branch": "main",
  "server_id": "aws-docs",
  "subdirectory": "src/aws-documentation-mcp-server",
  "env": { "API_KEY": "value" },
  "enabled": true,
  "restart_policy": "never",
  "max_restarts": 3,
  "test_before_save": false
}
```

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `github_repo` | Yes | — | `owner/repo` or full GitHub URL |
| `server_id` | Yes | — | Base server identifier (lowercase, hyphens, numbers) |
| `branch` | No | `"main"` | Branch to clone |
| `subdirectory` | No | — | Subdirectory containing `metadata.json` (for monorepos) |
| `server_name` | No | — | Select a specific server from a multi-server repo |
| `env` | No | `{}` | Extra env vars merged on top of repo defaults |
| `enabled` | No | `true` | Whether the server is enabled after creation |
| `restart_policy` | No | `"never"` | `never`, `on-failure`, or `always` |
| `max_restarts` | No | `3` | Max restart attempts (0–10) |
| `test_before_save` | No | `true` | Validate via test-start before persisting |

**Success response (200):**

```json
{
  "message": "Successfully added 1 server(s) from GitHub repository",
  "servers": [
    { "id": "aws-docs", "name": "awslabs.aws-documentation-mcp-server", "status": "added" }
  ],
  "repository": "awslabs/mcp",
  "branch": "main",
  "clone_path": "/app/.fmcp-packages/awslabs/mcp/main"
}
```

**Error responses:**

| Status | Cause |
|--------|-------|
| 400 | Missing required fields, invalid repo, blocked command, validation failure |
| 409 | Server ID already exists (pre-flight check or post-clone duplicate) |

## Architecture

### Clone & Registration Flow

```
User submits form
        │
        ▼
Pre-flight: check if server_id exists in MongoDB ──► 409 (instant, no clone)
        │
        ▼ (ID is free)
Clone/update repo to .fmcp-packages/{owner}/{repo}/{branch}/
        │
        ▼
Resolve subdirectory (if provided)
        │
        ▼
Extract metadata.json (or generate from README)
        │
        ▼
For each server in metadata:
  ├─ Validate command against allowlist
  ├─ Build flat config via ServerBuilder
  ├─ (Optional) Test-start through ServerManager lifecycle
  └─ Persist to MongoDB + register in manager.configs
        │
        ▼
Return created server list
```

### Key Files

| File | Purpose |
|------|---------|
| `fluidmcp/cli/api/management.py` | `POST /api/servers/from-github` endpoint |
| `fluidmcp/cli/services/github_utils.py` | `clone_or_update_repo()`, `GitHubService.build_server_configs()` |
| `fluidmcp/cli/services/server_builder.py` | `ServerBuilder` — ID generation, slug normalisation, flat config assembly |
| `fluidmcp/cli/services/validators.py` | `validate_command_allowlist()` |
| `fluidmcp/cli/models/api.py` | Pydantic models for request/response |
| `fluidmcp/frontend/src/components/CloneFromGithubForm.tsx` | UI form component |
| `fluidmcp/frontend/src/services/api.ts` | `cloneFromGithub()` client method, `ApiHttpError` class |

### Server ID Generation

For single-server repos, the final ID equals `server_id` as entered by the user.

For multi-server repos, the ID is `{server_id}-{slugified_server_name}`:
- `server_id = "tools"`, server name `"filesystem"` → `"tools-filesystem"`
- `server_id = "tools"`, server name `"API Server"` → `"tools-api-server"`

### Config Format

Cloned servers use the same **flat format** as all other servers. This means they get the same process lifecycle (start/stop/restart), health monitoring, and log collection as manually-added servers.

```json
{
  "id": "aws-docs",
  "name": "awslabs.aws-documentation-mcp-server",
  "command": "npx",
  "args": ["-y", "@awslabs/aws-documentation-mcp-server"],
  "env": {},
  "working_dir": "/app/.fmcp-packages/awslabs/mcp/main",
  "install_path": "/app/.fmcp-packages/awslabs/mcp/main/src/aws-documentation-mcp-server",
  "source": "github",
  "github_repo": "awslabs/mcp",
  "github_branch": "main",
  "restart_policy": "never",
  "enabled": true
}
```

### Working Directory

| Server type | `working_dir` | Why |
|-------------|---------------|-----|
| GitHub-cloned | Repo clone root (`.fmcp-packages/{owner}/{repo}/{branch}/`) | Monorepo commands like `uv --directory src/subdir` resolve relative to the repo root |
| Manually-added (`npx`, `docker`, `uvx`) | `"."` (process cwd) | These tools resolve packages from global registries, not local disk |
| Package-installed (registry) | Package install path | Source code lives in the extracted package directory |

## Security

### Command Allowlist

Only these commands are permitted in `metadata.json`. Any other command (e.g. `rm`, `bash`, `curl`) is rejected:

```
npx, node, python, python3, uv, uvx, docker, deno, bun
```

The allowlist is extensible via the `FMCP_COMMAND_ALLOWLIST` environment variable (comma-separated).

### GitHub Token Handling

- Token is sent in `X-GitHub-Token` header — never in the request body
- Token is never logged, never persisted to MongoDB
- Frontend clears the token from React state immediately after a successful clone

### Duplicate Prevention

1. **Pre-flight check** — Before cloning (instant), the endpoint checks if `server_id` exists in MongoDB or in-memory. Returns 409 immediately if taken, avoiding a 60-second clone wait.
2. **Post-clone check** — After building configs, each generated `sid` is checked again (guards against multi-server ID collisions).
3. **MongoDB unique index** — Final safety net via `DuplicateKeyError` catch.

Soft-deleted servers (records with `deleted_at`) are excluded from duplicate checks, so deleting a server and re-cloning with the same ID works as expected.

## Frontend

The `CloneFromGithubForm` component provides:

- **Form fields**: Repo URL, Server ID (auto-suggested from repo name), Branch, GitHub Token, Subdirectory, Environment Variables
- **Progress indicator**: Multi-step animation (Connecting → Cloning → Extracting → Registering)
- **Success view**: Lists created servers with Start and View Details buttons
- **Conflict handling**: On 409, auto-bumps the Server ID (`aws-docs` → `aws-docs-2` → `aws-docs-3`) and shows a clear retry message

The frontend API client (`ApiHttpError`) preserves HTTP status codes so the form can distinguish 409 conflicts from other errors and handle them appropriately.

## Known Limitation: Railway Container Restarts

### Problem

Railway containers are ephemeral. On restart or redeploy, the filesystem is wiped. Cloned repos in `.fmcp-packages/` are lost, but MongoDB still references their paths as `working_dir`. The server fails to start because the directory no longer exists.

This only affects `source: "github"` servers. Servers using `npx`/`docker`/`uvx` are unaffected — those tools resolve packages from global registries.

### Solution: Railway Persistent Volume

Mount a persistent volume at `/app/.fmcp-packages` so cloned repos survive container restarts.

**Railway Dashboard:** Service → Settings → Volumes → Add Volume → Mount path: `/app/.fmcp-packages`

**Or in `railway.json`:**

```json
{
  "deploy": {
    "volumes": [
      {
        "mountPath": "/app/.fmcp-packages"
      }
    ]
  }
}
```

### Future: Hybrid Re-clone Fallback

When user authentication with secure credential storage is added, a startup re-clone fallback can be implemented:

1. On `fmcp serve` boot, scan MongoDB for `source: "github"` configs
2. Check if `working_dir` exists on disk
3. If missing: re-clone public repos automatically; for private repos, surface a "needs re-clone" status in the UI prompting the user to re-provide their token

This is deferred until the auth system supports secure token vaults.

## Tests

```bash
# Unit tests — ServerBuilder, clone_or_update_repo, GitHubService, allowlist (62 tests)
pytest tests/test_github_service.py -v

# Integration tests — endpoint validation, persistence, duplicates (13 tests)
pytest tests/test_github_integration_api.py -v

# Both
pytest tests/test_github_service.py tests/test_github_integration_api.py -v
```
