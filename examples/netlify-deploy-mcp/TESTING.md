# Testing Guide

This guide explains how to test the Netlify Deploy MCP server.

## Prerequisites

1. Python 3.8+ with `mcp` package installed
2. FluidMCP installed
3. (Optional) Netlify CLI for deployment testing

## Local Testing (Without Deployment)

### 1. Test File Generation

Run the test suite to verify all website generators work:

```bash
cd /workspaces/fluidmcp
python3 examples/netlify-deploy-mcp/test_generator.py
```

Expected output:
```
============================================================
Netlify Deploy MCP Server - Test Suite
============================================================

Sites directory: /home/user/.netlify-mcp/sites
Testing Todo App generation...
✓ Todo app generated at: /home/user/.netlify-mcp/sites/test-todo_TIMESTAMP
✓ All required files exist
  - index.html: 1022 bytes
  - style.css: 2784 bytes
  - script.js: 3862 bytes

Testing Portfolio generation...
✓ Portfolio generated at: /home/user/.netlify-mcp/sites/test-portfolio_TIMESTAMP
✓ All required files exist

Testing Landing Page generation...
✓ Landing page generated at: /home/user/.netlify-mcp/sites/test-landing_TIMESTAMP
✓ All required files exist

============================================================
Test Summary
============================================================
Passed: 3/3
✓ All tests passed!
```

### 2. Inspect Generated Files

Generated files are stored in `~/.netlify-mcp/sites/`. You can open them in a browser:

```bash
# Open todo app
open ~/.netlify-mcp/sites/test-todo_*/index.html

# Or use Python's http.server
cd ~/.netlify-mcp/sites/test-todo_*/
python3 -m http.server 8000
# Then visit http://localhost:8000
```

## Testing with FluidMCP

### 1. Start the MCP Server

```bash
cd /workspaces/fluidmcp
fluidmcp run examples/netlify-deploy-config.json --file --start-server
```

The server will start on `http://localhost:8099`

### 2. Test Tool Discovery

```bash
curl -X POST http://localhost:8099/netlify-deploy/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list"
  }'
```

Expected response:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "generate_and_deploy_website",
        "description": "Generate a static website from a prompt and automatically deploy it to Netlify...",
        "inputSchema": {...}
      },
      {
        "name": "generate_website_files",
        "description": "Generate website files without deploying...",
        "inputSchema": {...}
      },
      {
        "name": "deploy_to_netlify",
        "description": "Deploy an existing project directory to Netlify...",
        "inputSchema": {...}
      }
    ]
  }
}
```

### 3. Test File Generation (No Deployment)

```bash
curl -X POST http://localhost:8099/netlify-deploy/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "generate_website_files",
      "arguments": {
        "site_type": "todo",
        "site_name": "my-test-todo",
        "custom_content": {
          "title": "My Todo List"
        }
      }
    }
  }'
```

Expected response:
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\n  \"status\": \"success\",\n  \"message\": \"Successfully generated todo website files\",\n  \"site_name\": \"my-test-todo\",\n  \"project_path\": \"/home/user/.netlify-mcp/sites/my-test-todo_TIMESTAMP\",\n  \"site_type\": \"todo\",\n  \"files\": [\"index.html\", \"style.css\", \"script.js\", \"netlify.toml\"]\n}"
      }
    ]
  }
}
```

### 4. Test Portfolio Generation

```bash
curl -X POST http://localhost:8099/netlify-deploy/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "generate_website_files",
      "arguments": {
        "site_type": "portfolio",
        "site_name": "jane-portfolio",
        "custom_content": {
          "title": "Jane Developer",
          "description": "Senior Software Engineer"
        }
      }
    }
  }'
```

### 5. Test Landing Page Generation

```bash
curl -X POST http://localhost:8099/netlify-deploy/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
      "name": "generate_website_files",
      "arguments": {
        "site_type": "landing",
        "site_name": "awesome-product",
        "custom_content": {
          "title": "SuperApp",
          "description": "The Ultimate Productivity Tool"
        }
      }
    }
  }'
```

## Testing with Netlify Deployment

**Note:** This requires Netlify CLI installation and authentication.

### 1. Install Netlify CLI

```bash
npm install -g netlify-cli
netlify login
```

### 2. Test Full Workflow

```bash
curl -X POST http://localhost:8099/netlify-deploy/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 5,
    "method": "tools/call",
    "params": {
      "name": "generate_and_deploy_website",
      "arguments": {
        "site_type": "todo",
        "site_name": "my-awesome-todo"
      }
    }
  }'
```

If successful, you'll receive a response with the live URL:
```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\n  \"status\": \"success\",\n  \"message\": \"Successfully generated and deployed todo website\",\n  \"site_name\": \"my-awesome-todo\",\n  \"project_path\": \"/home/user/.netlify-mcp/sites/my-awesome-todo_TIMESTAMP\",\n  \"live_url\": \"https://my-awesome-todo.netlify.app\",\n  \"site_type\": \"todo\"\n}"
      }
    ]
  }
}
```

## Error Testing

### 1. Test Invalid Site Type

```bash
curl -X POST http://localhost:8099/netlify-deploy/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 6,
    "method": "tools/call",
    "params": {
      "name": "generate_website_files",
      "arguments": {
        "site_type": "invalid",
        "site_name": "test"
      }
    }
  }'
```

Expected error response:
```json
{
  "jsonrpc": "2.0",
  "id": 6,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\n  \"status\": \"error\",\n  \"message\": \"Unknown site type: invalid\",\n  \"tool\": \"generate_website_files\"\n}"
      }
    ]
  }
}
```

### 2. Test Missing Netlify CLI (Deployment)

If Netlify CLI is not installed, deployment will fail with:
```json
{
  "status": "error",
  "message": "Netlify CLI is not installed. Install with: npm install -g netlify-cli"
}
```

## Viewing Generated Sites

All generated sites are stored in `~/.netlify-mcp/sites/` with timestamped directories.

To view a site locally:

```bash
# Find the latest site
cd ~/.netlify-mcp/sites/
ls -lt | head -5

# Serve the site
cd <site-directory>
python3 -m http.server 8000
```

Then open http://localhost:8000 in your browser.

## Cleanup

To remove test sites:

```bash
rm -rf ~/.netlify-mcp/sites/test-*
```

## Troubleshooting

### Server won't start
- Check if port 8099 is already in use
- Ensure `mcp` package is installed: `pip install mcp`
- Check Python version: `python3 --version` (should be 3.8+)

### File generation fails
- Check write permissions for `~/.netlify-mcp/sites/`
- Check disk space
- Review server logs for detailed error messages

### Deployment fails
- Ensure Netlify CLI is installed: `netlify --version`
- Check authentication: `netlify status`
- Review Netlify CLI logs
- Try manual deployment to test Netlify connection:
  ```bash
  cd ~/.netlify-mcp/sites/<site-directory>
  netlify deploy --prod
  ```

## Performance Notes

- File generation is fast (< 100ms per site)
- Deployment time depends on Netlify and can take 30-60 seconds
- The server uses a 5-minute timeout for deployments
- Generated sites are small (< 10KB total) for fast uploads
