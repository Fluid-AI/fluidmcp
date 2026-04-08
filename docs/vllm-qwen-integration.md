# FluidMCP + Qwen vLLM Integration Guide

## Overview

This document explains how to integrate a vLLM-served language model (Qwen 2.5 7B Instruct) with FluidMCP, so that users can query the model directly through the FluidMCP Swagger UI. It also covers all the issues encountered during the integration and how they were resolved.

---

## Architecture

```
User (Browser)
    ↓
FluidMCP Server (port 8099) → /qwen/v1/chat/completions
    ↓
Qwen vLLM Container (port 8000)
    ↓
NVIDIA GPU (NVIDIA GB10, 128GB VRAM)
```

All users share one FluidMCP server. The Swagger UI is available at:
```
http://<box-ip>:8099/docs
```

---

## Prerequisites

- Docker and Docker Compose installed on the host
- NVIDIA GPU with vLLM image: `nvcr.io/nvidia/vllm:25.09-py3`
- FluidMCP repo cloned: `https://github.com/Fluid-AI/fluidmcp`
- Python 3.12+

---

## Step 1 — Run the Qwen Model via vLLM

Add the following service to your `docker-compose.yml`:

```yaml
qwen-7b:
  image: nvcr.io/nvidia/vllm:25.09-py3
  container_name: qwen-7b
  restart: unless-stopped
  ports:
    - "8001:8000"
  volumes:
    - huggingface-cache:/root/.cache/huggingface
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            capabilities: [gpu]
            count: 1
  entrypoint: ["python3", "-m", "vllm.entrypoints.openai.api_server"]
  command:
    - "--model"
    - "Qwen/Qwen2.5-7B-Instruct"
    - "--host"
    - "0.0.0.0"
    - "--port"
    - "8000"
    - "--gpu-memory-utilization"
    - "0.3"
  networks:
    - codespace-net
```

> **Note:** Set `--gpu-memory-utilization` based on available VRAM. If other models are running on the same GPU, reduce this value accordingly.

Start the container:

```bash
docker compose up -d qwen-7b
docker logs -f qwen-7b
```

Wait until you see:
```
INFO: Application startup complete.
```

Verify the model is running:
```bash
curl http://localhost:8001/v1/models
```

---

## Step 2 — Patch FluidMCP Source Code

FluidMCP has two bugs that prevent it from working with non-registry MCP packages (like `filesystem` and `memory`). These must be patched before running.

### Bug 1 — `replace_package_metadata_from_package_name` returns `None`

When a package is not found in FluidMCP's cloud registry, it returns an empty dict `{}` which causes a crash downstream.

**Fix:** Add a null check after the registry call in `cli.py`:

```python
# In preprocess_metadata_file() function
replaced_metadata = replace_package_metadata_from_package_name(raw_metadata['mcpServers'][package])
if not replaced_metadata:   # ADD THIS
    continue                # ADD THIS
fmcp_package = raw_metadata['mcpServers'][package]
```

### Bug 2 — `parse_package_string(None)` crashes

When `fmcp_package` is `None` (standard MCP packages don't have this field), passing it to `parse_package_string` causes a crash.

**Fix:** Add a `None` check in the package install loop in `run_from_source()`:

```python
for package in fmcp_packages:
    if not package:   # ADD THIS
        continue      # ADD THIS
    pkg = parse_package_string(package)
```

The patched file is available at `fluidmcp/cli_patched.py` in this repo.

---

## Step 3 — Prepare MCP Server Packages

FluidMCP's cloud registry does not support standard MCP packages (`filesystem`, `memory`). These need to be pre-installed and their paths specified manually in the config.

Pre-install the packages inside a container where FluidMCP is already set up:

```bash
# Inside a container with FluidMCP installed
fluidmcp run --file config.json --start-server
# This will auto-install filesystem and memory into .fmcp-packages/.temp_servers/
```

Then copy the packages out to the host:
```bash
docker cp <container_name>:/home/coder/workspace/fluidmcp/.fmcp-packages ./fmcp-packages
```

---

## Step 4 — Create config.json

The config file must include `install_path` and `port` for each MCP server (required to bypass the registry):

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem"],
      "env": {},
      "port": 8091,
      "install_path": "/app/.fmcp-packages/.temp_servers/filesystem"
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"],
      "env": {},
      "port": 8092,
      "install_path": "/app/.fmcp-packages/.temp_servers/memory"
    }
  }
}
```

---

## Step 5 — Create start.py

This is the main integration file. It starts a single FastAPI server that includes both the Qwen vLLM endpoints and the MCP server endpoints.

```python
import json, os
from pathlib import Path
from fluidai_mcp.cli import extract_config_from_file
from fluidai_mcp.services.package_launcher import launch_mcp_using_fastapi_proxy
from fastapi import FastAPI, Request, APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import requests as req_lib
import uvicorn

config = extract_config_from_file('/app/config.json')

app = FastAPI(
    title="FluidMCP + Qwen vLLM",
    description="FluidMCP with Qwen vLLM integrated"
)

# Pydantic Models for Swagger UI
class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str = "Qwen/Qwen2.5-7B-Instruct"
    messages: List[Message]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 512

# Qwen vLLM Router
qwen_url = os.environ.get("VLLM_BASE_URL", "http://qwen-7b:8000/v1")
qwen_router = APIRouter(prefix="/qwen", tags=["Qwen vLLM"])

@qwen_router.post("/v1/chat/completions")
async def qwen_chat(chat_request: ChatRequest):
    """Send a message to Qwen vLLM model"""
    response = req_lib.post(
        f"{qwen_url}/chat/completions",
        json=chat_request.model_dump()
    )
    return JSONResponse(content=response.json())

@qwen_router.get("/v1/models")
async def qwen_models():
    """List available Qwen models"""
    response = req_lib.get(f"{qwen_url}/models")
    return JSONResponse(content=response.json())

app.include_router(qwen_router)

# MCP Servers (filesystem + memory)
for server_name, server_config in config["mcpServers"].items():
    install_path = Path(server_config["install_path"])
    print(f"Launching {server_name}...")
    pkg_name, router = launch_mcp_using_fastapi_proxy(install_path)
    app.include_router(router)
    print(f"✅ {server_name} ready")

print("🚀 Starting FluidMCP server...")
uvicorn.run(app, host="0.0.0.0", port=8099)
```

---

## Step 6 — Create Dockerfile

```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    curl git nodejs npm \
    && rm -rf /var/lib/apt/lists/*

RUN pip install fluidmcp fastapi uvicorn requests pydantic

# Apply the patched cli.py
COPY cli_patched.py /usr/local/lib/python3.12/dist-packages/fluidai_mcp/cli.py

WORKDIR /app
COPY config.json .
COPY fmcp-packages /app/.fmcp-packages
COPY start.py .

EXPOSE 8099

CMD ["python3", "start.py"]
```

---

## Step 7 — Add to docker-compose.yml

```yaml
fluidmcp:
  build:
    context: ./fluidmcp
    dockerfile: Dockerfile.fluidmcp
  container_name: fluidmcp
  restart: unless-stopped
  environment:
    - VLLM_BASE_URL=http://qwen-7b:8000/v1
  ports:
    - "8099:8099"
  networks:
    - codespace-net
```

> **Important:** `VLLM_BASE_URL=http://qwen-7b:8000/v1` uses Docker DNS to resolve the container name. This ensures the URL stays valid even if the container restarts and gets a new IP address.

Start the FluidMCP container:
```bash
docker compose build fluidmcp
docker compose up -d fluidmcp
docker logs fluidmcp
```

---

## Step 8 — Access and Test

Open the Swagger UI in your browser:
```
http://<box-ip>:8099/docs
```

You will see three sections:
- **Qwen vLLM** — `POST /qwen/v1/chat/completions`, `GET /qwen/v1/models`
- **filesystem** — MCP filesystem tools
- **memory** — MCP memory tools

To test Qwen from the Swagger UI:
1. Click `POST /qwen/v1/chat/completions`
2. Click **"Try it out"**
3. Paste this in the request body:

```json
{
  "model": "Qwen/Qwen2.5-7B-Instruct",
  "messages": [
    {
      "role": "user",
      "content": "Hello! What can you do?"
    }
  ],
  "temperature": 0.7,
  "max_tokens": 512
}
```

4. Click **"Execute"**

Or via curl from any VS Code container:
```bash
curl http://localhost:8099/qwen/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-7B-Instruct",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

---

## Issues Encountered and Fixes

### Issue 1 — vLLM container failed to start (GPU memory error)

**Error:**
```
ValueError: Free memory on device (38.23/119.64 GiB) is less than desired GPU memory utilization (0.9, 107.67 GiB)
```

**Cause:** Another model (Nanonets OCR) was already using ~68GB of VRAM. The default `gpu-memory-utilization` of 0.9 required more memory than was available.

**Fix:** Set `--gpu-memory-utilization 0.3` to limit Qwen to 30% of total VRAM (~38GB).

---

### Issue 2 — FluidMCP crashed with `expected string or bytes-like object, got 'NoneType'`

**Cause:** FluidMCP's `preprocess_metadata_file()` tries to fetch metadata from its cloud registry for any MCP server that is defined as a string. Standard packages like `filesystem` and `memory` are not in FluidMCP's registry, so `replace_package_metadata_from_package_name()` returns `{}`, and downstream code crashes trying to call `.keys()` on it.

**Fix:** Added null check after registry call. See `fluidmcp/cli_patched.py`.

---

### Issue 3 — MCP packages not found in FluidMCP registry

**Error:**
```
Error fetching package from MCP registry: {'detail': 'Package not found in the incoming request.'}
```

**Cause:** FluidMCP's registry only contains their own registered packages. Standard MCP packages (`@modelcontextprotocol/server-filesystem`, etc.) are not supported via `fluidmcp install`.

**Fix:** Pre-installed the packages by running FluidMCP once in a VS Code container (which auto-installs them into `.fmcp-packages/.temp_servers/`), then copied and baked them into the Docker image.

---

### Issue 4 — Container-to-container DNS resolution failed

**Error:**
```
curl: (6) Could not resolve host: qwen-7b
```

**Cause:** The FluidMCP container was not on the same Docker network as the Qwen container, or the container was started with `docker run` instead of `docker compose`, which prevented Docker DNS from working.

**Fix:** Ensured both containers are on the same network (`codespace-net`) in `docker-compose.yml`. Used `VLLM_BASE_URL=http://qwen-7b:8000/v1` with Docker DNS instead of a hardcoded IP.

---

### Issue 5 — Qwen container had no IP address

**Cause:** The `qwen-7b` container was originally started with `docker run` outside of compose, so it was not properly attached to the compose network.

**Fix:** Removed the standalone container and re-created it via `docker compose up -d qwen-7b` to ensure proper network attachment.

---

### Issue 6 — Swagger UI showed "No parameters" for Qwen endpoint

**Cause:** The original Qwen endpoint used `async def qwen_chat(request: Request)` which does not expose a schema to the Swagger UI.

**Fix:** Replaced with a Pydantic model (`ChatRequest`) so FastAPI can generate the schema and show input fields in the Swagger UI.

---

## File Structure

```
fluidmcp/
├── Dockerfile.fluidmcp        # Docker image for FluidMCP + Qwen
├── start.py                   # Main integration server
├── config.json                # MCP server config with install paths
├── cli_patched.py             # Patched FluidMCP source with bug fixes
├── fmcp-packages/             # Pre-installed MCP server packages
│   └── .temp_servers/
│       ├── filesystem/
│       └── memory/
└── examples/
    └── qwen-vllm-config.json  # Example config for vLLM integration
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VLLM_BASE_URL` | `http://qwen-7b:8000/v1` | Base URL of the vLLM server |

---

## Adding a New LLM Model

To integrate a different model, simply:

1. Run the new model via vLLM in a new container
2. Update `VLLM_BASE_URL` in `docker-compose.yml` to point to the new container
3. Restart the FluidMCP container:

```bash
docker compose up -d fluidmcp
```

No code changes needed in `start.py`.
