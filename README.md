# MCP
A protocol(interface) that defines how a model interacts with its external context/environment without being tightly coupled

Model = Your logic.
Context = The thing which provides you data (API, DB).
Protocol = A Rule that connects the two.

Goal = to make code easy to test by keeping Logic and data seperate.



# FluidMCP CLI

A powerful command-line interface for managing and running MCP (Model Context Protocol) servers. FluidMCP CLI allows you to install, configure, and run MCP packages from the FluidMCP registry with ease.

---

## Features

- 🚀 **Install MCP packages** from the FluidMCP registry
- 🔧 **Interactive environment variable configuration**
- 🌐 **Run individual or multiple MCP servers**
- 🔒 **Secure mode** with bearer token authentication
- ☁️ **S3-based configuration management**
- 📁 **Local and remote configuration file support**
- 🎯 **Automatic port management and conflict resolution**

---

## Installation

```bash
pip install fluidmcp
```

---

## Quick Start

**Install a package:**
```bash
fluidmcp install author/package@version
```

**List installed packages:**
```bash
fluidmcp list
```

**Run a package:**
```bash
fluidmcp run package --port 8111 --start-server
```

---

## Commands

### `install`

Install MCP packages from the FluidMCP registry.

```bash
fluidmcp install <author/package@version> [--master]
```

**Examples:**
```bash
# Install a specific version
fluidmcp install Perplexity/perplexity-ask@1.0.0

# Install latest version
fluidmcp install Perplexity/perplexity-ask

# Install with master env file (skips API key prompts)
fluidmcp install Perplexity/perplexity-ask --master
```

**Options:**
- `--master`: Use master environment file for API keys (skips interactive prompts)

**Package Format:**
- `author/package@version` - Install specific version
- `author/package` - Install latest version

---

### `run`

Run MCP servers from installed packages or configuration files.

```bash
fluidmcp run <package|all|file> [options]
```

**Examples:**
```bash
# Run a specific package with FastAPI client server
fluidmcp run Airbnb/airbnb@0.1.0 --port 8200 --start-server

#Run all installed packages
#For runn all, FluidMCP automatically assigns unique ports to each server
fluidmcp run all

# Run with master S3 configuration
fluidmcp run all --master

# Run from local configuration file
fluidmcp run <path-to-your-directory>config.json --file

# Run from S3 presigned URL
fluidmcp run https://s3.amazonaws.com/bucket/config.json --s3

# Run with secure mode and custom token
fluidmcp run Fluid_AI/jupyter@1.0.0 --secure your-bearer-token --port 8200 --start-server
```

**Options:**
- `--port <number>`: Specify port for SuperGateway (default: 8111)
- `--start-server`: Start FastAPI client server
- `--force-reload`: Force reload by killing existing processes without prompt
- `--master`: Use master metadata file from S3
- `--secure`: Enable secure mode with bearer token authentication
- `--token <token>`: Bearer token for secure mode (auto-generated if not provided)
- `--file`: Treat package argument as path to local JSON configuration file
- `--s3`: Treat package argument as S3 presigned URL to configuration file

---

### `list`

Display all installed MCP packages.

```bash
fluidmcp list
```

**Output format:**
```
Installation directory: /path/to/.fmcp-packages
author1/package1@1.0.0
author2/package2@2.1.0
```

---

### `edit-env`

Interactively edit environment variables for installed packages.

```bash
fluidmcp edit-env <authorname/package@version>
```

**Example:**
```bash
# Edit environment variables for a specific package
fluidmcp edit-env Fluid_AI/jupyter@1.0.0
```

**Features:**
- Interactive environment variable editor
- Secure masking of API keys and sensitive data
- Support for both structured and simple environment formats
- Real-time validation and updates

---

## Configuration

### Environment Variables

FluidMCP CLI uses several environment variables for configuration:

```bash

# S3 Configuration (for --master mode you must set the S3 environment variables. Without these, --master mode operations will fail.)

export S3_BUCKET_NAME="your-bucket"
export S3_ACCESS_KEY="your-access-key"
export S3_SECRET_KEY="your-secret-key"
export S3_REGION="us-east-1"

# Registry configuration
export MCP_FETCH_URL="https://registry.fluidmcp.com/fetch-mcp-package"
export MCP_TOKEN="your-registry-token"
```

---

## Package Structure

Installed packages follow this directory structure:

```
.fmcp-packages/
├── author1/
│   └── package1/
│       └── 1.0.0/
│           ├── metadata.json
│           └── [package files]
└── author2/
    └── package2/
        └── 2.1.0/
            ├── metadata.json
            └── [package files]
```

---

## Metadata Format

Each package contains a `metadata.json` file:

```json
{
  "mcpServers": {
    "package-name": {
      "command": "npx",
      "args": ["-y", "@package/server"],
      "env": {
        "API_KEY": "value"
      }
    }
  }
}
```

---

## S3 Files

For S3 operations, you can use following `Json` format:

```json
{
  "mcpServers": {
    "server1": {
      "command": "npx",
      "args": ["-y", "example-package@1.0.0"],
      "env": {
        "API_KEY": "your-api-key"
      },
      "port": "8100",
      "install_path": "/path/to/.fmcp-packages/Author/package/1.0.0",
      "fmcp_package": "Author/package@1.0.0"
    },
    "server2": {
      "command": "uvx",
      "args": ["another-server"],
      "env": {
        "TOKEN": "value"
      },
      "port": "8101",
      "install_path": "/path/to/.fmcp-packages/Author/another-package/2.0.0",
      "fmcp_package": "Author/another-package@2.0.0"
    }
  }
}
```
---

## Trying out an MCP server

### Create MCP Server:
```bash
pip install fluidmcp
fmcp install "Google Maps MCP Server/google-maps@0.6.2"
```
**Output:**
```
:wrench: Installing Google Maps MCP Server/google-maps@0.6.2
:cloud: Installing package from Fluid MCP registry...
:cloud: Downloading packages
:package: Saving metadata.json...
:information_source: Reading metadata.json for API key configuration
:key: Saving API key(s) to metadata.json
:information_source: API key(s) saved to metadata.json.
:white_check_mark: Installation completed successfully.
```

```bash
fmcp list
```
**Output:**
```
Installation directory: /content/.fmcp-packages
Google Maps MCP Server/google-maps@0.6.2
```

```bash
fmcp run all
```
**Output:**
```
✅ Wrote merged metadata to /content/.fmcp-packages/metadata_all.json
:blue_book: Reading metadata.json from /content/.fmcp-packages/Google Maps MCP Server/google-maps/0.6.2/metadata.json
google-maps {'command': 'npx', 'args': ['-y', '@modelcontextprotocol/server-google-maps'], 'env': {'GOOGLE_MAPS_API_KEY': '<YOUR_API_KEY>'}}
✅ Added google-maps endpoints
2025-06-06 09:19:04.284 | INFO     | fluidai_mcp.cli:run_all:279 - Starting FastAPI client server on port 8099
INFO:     Started server process [6848]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8099 (Press CTRL+C to quit)
```

### Quick-trying out MCP server:

# IMP NOTE: You have to add GOOGLE_MAPS_API_KEY in .fmcp-packages/{Package}/metadata.json

```python
import requests
import json

mcp_url = "http://localhost:8099/google-maps/mcp"
mcp_payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "maps_search_places",
      "arguments": {
        "query": "coffee shops in San Francisco"
      }
    }
}
mcp_response = requests.post(mcp_url, json=mcp_payload)
print("Status code:", mcp_response.status_code)
# Print the response in pretty JSON format
try:
    parsed_response = json.loads(mcp_response.text)
    for item in parsed_response["result"]["content"]:
            if item["type"] == "text":
                nested_json = json.loads(item["text"])
                print(json.dumps(nested_json, indent=2))
    # print(json.dumps(mcp_response.json(), indent=2))
except Exception as e:
    print("Error decoding JSON:", e)
```
**Output:**
```json
Status code: 200
{
  "places": [
    {
      "name": "The Coffee Movement",
      "formatted_address": "1030 Washington St, San Francisco, CA 94108, United States",
      "location": {
        "lat": 37.7947575,
        "lng": -122.4102936
      },
      "place_id": "ChIJoTMb3PKAhYARsXkQt469sBw",
      "rating": 4.8,
      "types": [
        "cafe",
        "food",
        "point_of_interest",
        "store",
        "establishment"
      ]
    },
    {
      "name": "Sextant Coffee Roasters",
      "formatted_address": "1415 Folsom St, San Francisco, CA 94103, United States",
      "location": {
        "lat": 37.7724716,
        "lng": -122.4040877
      },
      "place_id": "ChIJW9Zu0uGAhYARQ5p0JqvV0Ew",
      "rating": 4.6,
      "types": [
        "cafe",
        "restaurant",
        "food",
        "point_of_interest",
        "store",
        "establishment"
      ]
    }
  ]
}
```
You can further checkout 'examples/chat_google_maps.ipynb'



---

## Advanced Usage

### Using Server-Sent Events (SSE) for Streaming Responses

For MCP tools that support incremental or chunked data delivery, FluidMCP provides a Server-Sent Events (SSE) endpoint. This is particularly useful for long-running operations or when you want to process data as it arrives, rather than waiting for the entire response. To use this, you would typically make a POST request to the `/{package_name}/sse` endpoint with your standard JSON-RPC payload. The server will then hold the connection open and stream back events, where each event's data field will contain a part of the JSON response. Clients should be configured to listen for these events and process them accordingly. This allows for a more responsive user experience, especially when dealing with large language models or other tools that generate output progressively.

### Master Mode

Master mode allows centralized management of MCP servers using S3 storage:

```bash
# Install package for master mode (skips env prompts)
fluidmcp install package --master

# Run all servers using S3 configuration
fluidmcp run all --master
```

**In master mode:**
- Environment variables are managed via a central `.env` file
- Server metadata is stored in S3 (`s3_metadata_all.json`)
- Automatic synchronization across multiple environments

---

### Secure Mode

Enable secure mode for production deployments:

```bash
# Run with auto-generated token
fluidmcp run package --secure

# Run with custom token
fluidmcp run package --secure --token your-custom-token
```

**Secure mode features:**
- Bearer token authentication
- Encrypted communication between servers
- Environment variable injection for security tokens

---

### Port Management

FluidMCP automatically manages ports to avoid conflicts:

- Scans for available ports in range 8100-9000
- Kills existing processes when using `--force-reload`
- Assigns unique ports to each server in multi-server setups

---

### API Registry

FluidMCP CLI connects to the FluidMCP registry to download packages. The registry provides:

- Package versioning and metadata
- Secure package distribution via S3 pre-signed URLs
- Authentication and authorization
- Package discovery and search

---