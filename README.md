<h1  style="font-size: 4.2em;">🌀 FluidMCP CLI</h1>
<p ><strong>Orchestrate multiple MCP servers with a single configuration file</strong></p>

---

## ⚡ Quick Start - Run Multiple MCP Servers

The main power of FluidMCP is running multiple MCP servers from a single configuration file over a unified FastAPI endpoint.

### 1. Create a Configuration File

Create a `config.json` file with your MCP servers:

```json
{
  "mcpServers": {
    "google-maps": {
      "command": "npx",
      "args": ["-y", "@google-maps/mcp-server"],
      "env": {
        "GOOGLE_MAPS_API_KEY": "your-api-key"
      }
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/files"],
      "env": {}
    }
  }
}
```

### 2. Launch All Servers

```bash
fluidmcp run config.json --file --start-server
```

This will:
- Install and configure all MCP servers listed in your config
- Launch them through a unified FastAPI gateway
- Make them available at `http://localhost:8099`
- Provide automatic API documentation at `http://localhost:8099/docs`


![fluidmcp_file_](https://github.com/user-attachments/assets/56bac081-0027-48c5-9462-f06e83cabcf7)




---
## 🚀 Features


- **📁 Multi-Server Orchestration**
  - Define multiple MCP servers in a single JSON configuration file
  - Launch all servers with one command: `fluidmcp run --file <config.json>`
  - Unified FastAPI gateway serving all your MCP tools


- **📦 Package Management**
  - Install MCP packages with `fluidmcp install author/package@version`
  - Automatic dependency resolution and environment setup
  - Support for npm, Python, and custom MCP servers


- **🚀 FastAPI Gateway**
  - Unified HTTP endpoints for all MCP tools
  - Server-Sent Events (SSE) streaming support
  - Swagger documentation at `/docs`


- **🔐 Security & Authentication**
  - Bearer token authentication
  - Secure mode with encrypted communications
  - Environment variable encryption for API keys


---


## 📥 Installation


```bash
pip install fluidmcp
```


---


## 🔧 Alternative Usage Patterns


### Install Individual Packages


```bash
fluidmcp install author/package@version
```


### List Installed Packages


```bash
fluidmcp list
```


### Run Individual Package


```bash
fluidmcp run author/package@version --start-server
```

### 3b. Clone & Run Directly from GitHub

```bash
fluidmcp github owner/repo --github-token <token> --branch main --start-server
```


---


## 🔐 Advanced Usage


### Secure Mode with Authentication

Run with bearer token authentication:

```bash
fluidmcp run config.json --file --secure --token your_token --start-server
```


![fluidmcp_secure_1](https://github.com/user-attachments/assets/6d5d38c5-c912-476a-af85-f7da44b15358)


---

### after authorisation

![fluidmcp_secure_2](https://github.com/user-attachments/assets/5bc9e34c-99fc-46c3-ba75-025de9077811)



---




### ☁️ Run from S3 URL

Run configuration directly from S3:

```bash
fluidmcp run "https://bucket.s3.amazonaws.com/config.json" --s3
```


**Common Options:**


- `--start-server` – Starts FastAPI server
- `--master` – Use S3-driven config
- `--file` – Run from local config.json
- `--s3` – Run from S3 URL
- `--secure` – Enable secure token mode
- `--token <token>` – Custom bearer token

### Run All Installed Packages

```bash
fluidmcp run all --start-server
```


---


## 📂 Run Modes


### 🧠 Master Mode (S3 Centralized)


```bash
fluidmcp install author/package@version --master
fluidmcp run all --master
```


---


## 🧩 Environment Variables


```bash
# S3 Credentials (used in --master mode)
export S3_BUCKET_NAME="..."
export S3_ACCESS_KEY="..."
export S3_SECRET_KEY="..."
export S3_REGION="..."


# Registry access
export MCP_FETCH_URL="https://registry.fluidmcp.com/fetch-mcp-package"
export MCP_TOKEN="..."
```


### Edit Environment


```bash
fluidmcp edit-env <author/package@version>
```


---


## 📁 Directory Layout


```
.fmcp-packages/
└── Author/
    └── Package/
        └── Version/
            ├── metadata.json
            └── [tool files]
```


---


## 📑 metadata.json Example


```json
{
  "mcpServers": {
    "maps": {
      "command": "npx",
      "args": ["-y", "@package/server"],
      "env": {
        "API_KEY": "xxx"
      }
    }
  }
}
```


---


## 🧪 Try an MCP Server


```bash
fluidmcp install Google_Maps/google-maps@0.6.2
fluidmcp run all
```


Then call it using:


```python
import requests, json


url = "http://localhost:8099/google-maps/mcp"
payload = {
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
response = requests.post(url, json=payload)
print(json.dumps(response.json(), indent=2))
```


---


## 📡 Streaming with SSE


```bash
curl -N -X POST http://localhost:8099/package/sse \
  -H "Content-Type: application/json" \
  -d @payload.json
```


- `sse/start`
- `sse/stream`
- `sse/message`
- `sse/tools_call`


Useful for LLMs, web scraping, or AI workflows that stream data.


---


## 📸 Demo 

### Installing an individual package


![fluidmcp_install](https://github.com/user-attachments/assets/39b6fc64-6b46-4045-84df-63af298fe6bf)

---

### Running an individual package

![fluidmcp_run_individual (2)](https://github.com/user-attachments/assets/4073c072-3210-4e88-a84a-162e13af168b)


---

### Edit environment of a package

![fluidmcp_edit-env (2)](https://github.com/user-attachments/assets/b8cf8a0c-3434-4730-8d0e-1e74b6357edd)

---


## 🤝 Contribute


FluidMCP is open for collaboration. Feel free to open issues or submit PRs.


---


## 📌 License


[MIT License](LICENSE)


---







