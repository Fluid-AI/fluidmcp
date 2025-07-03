# 🌀 FluidMCP CLI

**Define your tools in a JSON file, run with one command, and instantly get unified HTTP endpoints for all your MCP tools.**

---

## 📝 What is FluidMCP?

FluidMCP is a universal Model Context Protocol (MCP) runner and gateway. You define your tools and workflows in a JSON config, then run them with a single command. FluidMCP automatically exposes all your MCP tools as HTTP endpoints via a FastAPI server—no extra code required.

---

## ⚙️ How It Works

1. **Define** your MCP tools and settings in a JSON file (e.g., `config.json`).
2. **Run** with `fluidmcp run ./config.json --file` (or from S3, or as a package).
3. **Access** all your tools as REST endpoints instantly (with docs, streaming, and security built-in).

---

## 🚀 Key Features

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

## ⚡ Quick Start

### 1. Install FluidMCP

```bash
pip install fluidmcp
```

### 2. Define Your MCP Config

Create a `config.json` describing your tools and servers (see below for example).

### 3. Run Your Tools

```bash
fluidmcp run ./config.json --file
```

All tools defined in your config are now available as HTTP endpoints!

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

## 🔍 Example: metadata.json

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

## ☁️ Advanced Usage

- Run from S3: `fluidmcp run "https://bucket.s3.amazonaws.com/config.json" --s3`
- Secure mode: `fluidmcp run ./config.json --file --secure --token your_token --start-server`
- Edit environment: `fluidmcp edit-env <author/package@version>`
- Master mode (S3 centralized): `fluidmcp install author/package@version --master`

---

## 📂 Directory Layout


```
.fmcp-packages/
└── Author/
    └── Package/
        └── Version/
            ├── metadata.json
            └── [tool files]
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


## 🤝 Contribute


FluidMCP is open for collaboration. Feel free to open issues or submit PRs.


---


## 📌 License


[MIT License](LICENSE)


---







