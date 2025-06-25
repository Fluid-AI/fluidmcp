<h1  style="font-size: 4.2em;">🌀 FluidMCP CLI</h1>
<p ><strong>Run your MCP server with just one file</strong></p>

---
<p >
  <video autoplay loop muted playsinline width="800">
    <source src="https://github.com/user-attachments/assets/ace6a67b-a2f7-45b8-a040-2db1aed8bcd2" type="video/mp4">
    Your browser does not support the video tag.
  </video>
</p>





---
## 🚀 Features


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


## ⚡ Quick Start


### 1. Install a Package


```bash
fluidmcp install author/package@version
```


### 2. List Installed Packages


```bash
fluidmcp list
```


### 3. Run a Package


```bash
fluidmcp run ./config.json --file
```


---



### 🔐 Secure Run (Token Auth)

`fluidmcp file_directory/config.json --file --secure --token your_token --start-server`



<p >
  <video autoplay loop muted playsinline width="800">
    <source src="https://github.com/user-attachments/assets/fb81db4e-e189-4cbe-9b34-befe7190840f" type="video/mp4">
    Your browser does not support the video tag.
  </video>
</p>

---

### after authorisation

<p >
  <video autoplay loop muted playsinline width="800">
    <source src="https://github.com/user-attachments/assets/1bbfd0e1-060e-4106-a1ce-77f46c7ac37d" type="video/mp4">
    Your browser does not support the video tag.
  </video>
</p>




---




### ☁️ Run from S3 URL

`fluidmcp run "https://bucket.s3.amazonaws.com/config.json" --s3`




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

---
### 📄 Run as an individual package


```bash
fluidmcp run author/package@version --start-server  
```


### 4. Run All Installed Packages


```bash
fluidmcp run all
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

<p >
  <video autoplay loop muted playsinline width="800">
    <source src="https://github.com/user-attachments/assets/38f14459-7c62-4e88-8ffc-7bcd47191bba" type="video/mp4">
    Your browser does not support the video tag.
  </video>
</p>


---

### Running an individual package

<p >
  <video autoplay loop muted playsinline width="800">
    <source src="https://github.com/user-attachments/assets/ccad65fe-f733-47cf-98b6-bcbb5c281022" type="video/mp4">
    Your browser does not support the video tag.
  </video>
</p>


---

### Edit environment of a package

<p >
  <video autoplay loop muted playsinline width="800">
    <source src="https://github.com/user-attachments/assets/a36a832d-0ac7-44ab-8831-ecbf7e3032c7" type="video/mp4">
    Your browser does not support the video tag.
  </video>
</p>


---


## 🤝 Contribute


FluidMCP is open for collaboration. Feel free to open issues or submit PRs.


---


## 📌 License


[MIT License](LICENSE)


---







