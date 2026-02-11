# Automated Netlify Deployment Guide

## Overview

Your MCP server now supports **fully automated deployment** with three options:

1. **Files Only** (No Netlify CLI required) - Generate files locally
2. **Manual Deployment** - Generate files + manual Netlify CLI setup
3. **Automated Deployment** - Fully automated with Netlify API token

## Option 1: Files Only (Default - Works Now!)

The server will **automatically generate website files** even without Netlify CLI.

### How it works:

When you call `create_and_deploy_site`:
- ✅ Generates HTML, CSS, JS files
- ✅ Creates netlify.toml configuration
- ✅ Saves to `~/.netlify-mcp/sites/`
- ✅ Returns helpful instructions
- ❌ Does not deploy to Netlify

### Response format:

```
Website Successfully Generated!

Site Type: Todo App
Site Name: todo-20240210...
Location: /home/codespace/.netlify-mcp/sites/todo-...

Features included:
- Add and delete tasks
- Mark tasks complete
...

Files generated successfully!

Note: Netlify deployment requires CLI setup. To deploy:
1. Install: npm install -g netlify-cli
2. Login: netlify login
3. Deploy: netlify deploy --prod --dir [path]

Or preview locally:
cd [path] && python3 -m http.server 8000
```

### When to use:

- Testing the server
- Developing locally
- You don't have Netlify account yet
- You want manual control over deployment

## Option 2: Manual Deployment

The server will **auto-install Netlify CLI** but you need to authenticate manually.

### Setup steps:

```bash
# Server will auto-install CLI, but you need to login once
netlify login
```

This opens a browser for authentication.

### How it works:

- ✅ Server auto-installs `netlify-cli` if missing
- ⚠️ You must run `netlify login` once manually
- ✅ Then deployments work automatically
- ✅ Returns live Netlify URL

### Response format:

```
Website Successfully Generated and Deployed!

Live URL: https://todo-20240210.netlify.app

Site Type: Todo App
Site Name: todo-20240210

Features included:
- Add and delete tasks
...

Your site is ready to use right now!
```

## Option 3: Automated Deployment (Recommended for Production)

**Fully automated deployment** using Netlify API token - no manual login required!

### Setup steps:

1. **Get Netlify Personal Access Token:**
   - Go to: https://app.netlify.com/user/applications
   - Click "New access token"
   - Give it a name (e.g., "MCP Server")
   - Copy the token

2. **Add token to config:**

Edit `examples/netlify-deploy-config.json`:

```json
{
  "mcpServers": {
    "netlify-deploy": {
      "command": "python3",
      "args": [
        "/workspaces/fluidmcp/examples/netlify-deploy-mcp/server.py"
      ],
      "env": {
        "NETLIFY_AUTH_TOKEN": "your_token_here"
      }
    }
  }
}
```

3. **Restart the server:**

```bash
fluidmcp run examples/netlify-deploy-config.json --file --start-server
```

### How it works:

- ✅ Server auto-installs `netlify-cli` if missing
- ✅ Uses API token for authentication (no manual login!)
- ✅ Deploys automatically to Netlify
- ✅ Returns live URL immediately
- ✅ Works in CI/CD, containers, headless environments

### Response format:

Same as Option 2 - returns live Netlify URL.

## Current Status

**Right now your server is working in Option 1 mode** (Files Only).

To upgrade:

- **For Option 2:** Just run `netlify login` once in your Codespace
- **For Option 3:** Add `NETLIFY_AUTH_TOKEN` to config and restart

## Testing

Test that files are being generated:

```bash
curl -X POST http://localhost:8099/netlify-deploy/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "create_and_deploy_site",
      "arguments": {
        "prompt": "create a todo app"
      }
    }
  }'
```

Expected: Should return success with local file path.

## Your MCP Agent

Your agent will now receive helpful responses regardless of deployment status:

### If Netlify CLI not available:

```
Website Successfully Generated!
...
Note: Netlify deployment requires CLI setup...
```

Your system prompt handles this case correctly.

### If Netlify CLI available and authenticated:

```
Website Successfully Generated and Deployed!
Live URL: https://...netlify.app
...
```

Your agent receives the live URL as expected!

## Environment Variables

Supported environment variables:

- `NETLIFY_AUTH_TOKEN` - Personal access token for automated deployment
- `NETLIFY_SITE_ID` - (Optional) Specific site ID to deploy to

Add these to the `env` section of your config.

## Security Notes

- **Never commit your Netlify token to git!**
- Use environment variables or secrets management
- The token has full access to your Netlify account
- Rotate tokens periodically

## Troubleshooting

### "Not authenticated with Netlify"

**Cause:** No auth token and `netlify login` not run.

**Fix Option 1:** Run `netlify login` once
**Fix Option 2:** Add `NETLIFY_AUTH_TOKEN` to config

### "Netlify CLI is not available"

**Cause:** Auto-installation failed (no npm or permissions issue)

**Fix:** Install manually:
```bash
npm install -g netlify-cli
```

### "npm: command not found"

**Cause:** Node.js/npm not installed in Codespace

**Fix:** Install Node.js:
```bash
# For Codespaces
sudo apt-get update && sudo apt-get install -y nodejs npm
```

### Files generated but deployment skipped

**This is normal!** The server generates files first, then tries deployment.
If deployment fails, you still get the files and can deploy manually.

## Summary

| Option | CLI Install | Auth | Deployment | Best For |
|--------|-------------|------|------------|----------|
| Files Only | ❌ No | ❌ No | ❌ Manual | Testing, development |
| Manual | ✅ Auto | 🔐 Manual | ✅ Auto | Personal use |
| Automated | ✅ Auto | 🔐 Token | ✅ Auto | Production, CI/CD |

**Your current status: Option 1 (Files Only)**

To enable full deployment, choose Option 2 or 3 above!

---

**Last Updated:** 2024-02-10
**Server Status:** ✅ Operational with graceful deployment fallback
