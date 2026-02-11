# Netlify Deploy MCP Server - Quick Start Guide

## 🎯 Quick Summary

The Netlify Deploy MCP server is **running and working** on your Codespace!

- ✅ Server Status: **ACTIVE**
- 🌐 Local URL: `http://localhost:8099`
- 📚 API Docs: `http://localhost:8099/docs`
- 🧪 Test Page: `http://localhost:8001/test.html`

## 🔧 Fix the 404 Error (GitHub Codespaces)

The error you're seeing happens because port 8099 needs to be **PUBLIC** in GitHub Codespaces.

### Step-by-Step Fix:

1. **Open the PORTS tab** in VS Code (bottom panel, next to Terminal)
2. **Find port 8099** in the list
3. **Right-click** on port 8099
4. **Select**: `Port Visibility` → `Public`
5. **Copy the forwarded URL** that looks like:
   ```
   https://solid-palm-tree-4jqrv9rv4p4jfjwv7-8099.app.github.dev
   ```

6. **Use this URL format** in your MCP client:
   ```
   https://YOUR-CODESPACE-8099.app.github.dev/netlify-deploy/mcp
   ```

## 🧪 Easy Testing Method

Instead of configuring your MCP client immediately, test the connection first:

### Option 1: Use the Test Page (Easiest!)

1. **Make port 8001 public** (same way as port 8099)
2. Open the forwarded URL for port 8001: `https://YOUR-CODESPACE-8001.app.github.dev/test.html`
3. Update the server URL field if needed
4. Click **"Test Connection"** button
5. If it works, you'll see the available tools!

### Option 2: Use curl

```bash
# Test from your Codespace terminal
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
        ...
      },
      {
        "name": "generate_website_files",
        ...
      },
      {
        "name": "deploy_to_netlify",
        ...
      }
    ]
  }
}
```

## 🎨 Available Tools

### 1. `generate_website_files`
Generate website files without deploying (perfect for testing).

**Parameters:**
- `site_type`: `"todo"`, `"portfolio"`, or `"landing"`
- `site_name`: Name for the site
- `custom_content` (optional): `{ "title": "...", "description": "..." }`

**Example:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "generate_website_files",
    "arguments": {
      "site_type": "todo",
      "site_name": "my-tasks",
      "custom_content": {
        "title": "My Todo List"
      }
    }
  }
}
```

### 2. `generate_and_deploy_website`
Full workflow: Generate + Deploy to Netlify (requires Netlify CLI).

**Parameters:**
- Same as `generate_website_files`

**Returns:**
- Live Netlify URL

### 3. `deploy_to_netlify`
Deploy an existing project directory.

**Parameters:**
- `project_path`: Path to the project directory
- `site_name` (optional): Name for the Netlify site

## 📋 Website Templates

### ✅ Todo App (`site_type: "todo"`)
- Add, delete, mark complete tasks
- localStorage persistence
- Filter views (all/active/completed)
- Clear completed button
- Modern responsive design

### 💼 Portfolio (`site_type: "portfolio"`)
- Navigation with smooth scroll
- Hero section with name and tagline
- About & skills sections
- Projects grid (3 sample projects)
- Contact section with links
- Mobile-responsive layout

### 🚀 Landing Page (`site_type: "landing"`)
- Hero with CTA button
- 6 feature cards
- Benefits section (3 items)
- Email capture form
- Full footer with links
- Marketing-focused design

## 🔌 Using with MCP Clients

### Claude Desktop (Local)

If running Claude Desktop locally, use:
```json
{
  "mcpServers": {
    "netlify-deploy": {
      "url": "http://localhost:8099/netlify-deploy/mcp"
    }
  }
}
```

### Claude.ai (Web Deploy MCP Agent)

1. **Make port 8099 public** first (see above)
2. Use your Codespace URL:
   ```
   https://YOUR-CODESPACE-8099.app.github.dev/netlify-deploy/mcp
   ```
3. Test connection first using the test page
4. Once confirmed working, paste the URL in the MCP agent dialog

## 🐛 Troubleshooting

### "404 Not Found" Error
- ✅ Port 8099 is not public → Make it public in PORTS tab
- ✅ Wrong URL → Use `/netlify-deploy/mcp` not `/netlify-deploy/tools/list`
- ✅ Server not running → Check with `ps aux | grep fluidmcp`

### "Connection Refused" Error
- Server might not be running
- Restart with: `fluidmcp run examples/netlify-deploy-config.json --file --start-server`

### "CORS" Error (from browser)
- This is expected when testing from different origins
- Use curl or the test page from the same Codespace instead

### Tool Calls Fail
- Check server logs: `tail -f /tmp/claude-1000/-workspaces-fluidmcp/tasks/[TASK_ID].output`
- Verify JSON-RPC format is correct
- Ensure `tools/call` method is used (not just `generate_website_files`)

## 📚 More Information

- **Full Documentation**: [README.md](README.md)
- **Testing Guide**: [TESTING.md](TESTING.md)
- **Server Code**: [server.py](server.py)
- **API Documentation**: http://localhost:8099/docs

## 🚀 Example Workflow

1. **Test the connection** using test page or curl
2. **Generate a todo app** to verify it works
3. **Preview the generated site** in the output directory
4. **Optional**: Deploy to Netlify (requires `npm install -g netlify-cli` and `netlify login`)

## ✨ Pro Tips

- Generated sites are stored in `~/.netlify-mcp/sites/` with timestamps
- You can preview any site with: `python3 -m http.server 8002` (from the site directory)
- All templates use vanilla HTML/CSS/JS (no frameworks)
- Todo app uses localStorage for data persistence
- Custom content merges with default templates

---

**Need help?** Check the logs or open an issue in the repository!
