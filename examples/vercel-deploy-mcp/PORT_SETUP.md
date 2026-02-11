# Port Setup Guide for GitHub Codespaces

## 🎯 The Problem

You're getting a **404 error** because GitHub Codespaces ports are **private by default**.

Your error message:
```
Request to `https://solid-palm-tree-4jqrv9rv4p4jfjwv7-8099.app.github.dev/netlify-deploy/mcp`
failed with status code `404`
```

## ✅ The Solution (2 Minutes)

### Visual Guide

```
┌─────────────────────────────────────────────────────────────────┐
│ VS Code Window                                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [Your Code Here]                                                │
│                                                                  │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│ Bottom Panel (Look here! ↓)                                      │
├─────┬─────────┬───────┬─────────┬──────────────────────────────┤
│ ... │ TERMINAL │ DEBUG │ **PORTS** │ ...                        │ ← Click PORTS tab
└─────┴─────────┴───────┴─────────┴──────────────────────────────┘
```

### Step-by-Step Instructions

#### Step 1: Open PORTS Tab
- Look at the **bottom panel** of VS Code
- You'll see tabs: `TERMINAL`, `PROBLEMS`, `OUTPUT`, **`PORTS`**
- Click on **`PORTS`**

#### Step 2: Find Port 8099
In the PORTS list, you should see:
```
Port    Address                 Visibility   Label
8099    127.0.0.1:8099         Private      [Process Name]
8001    127.0.0.1:8001         Private      [Process Name]
```

#### Step 3: Make Port 8099 Public
1. **RIGHT-CLICK** on the row with port `8099`
2. Hover over **"Port Visibility"**
3. Click **"Public"**
4. The "Visibility" column will change to **"Public"**

#### Step 4: Make Port 8001 Public (for test page)
1. **RIGHT-CLICK** on the row with port `8001`
2. Hover over **"Port Visibility"**
3. Click **"Public"**
4. The "Visibility" column will change to **"Public"**

#### Step 5: Get Your URLs
After making ports public, you should see:
```
Port    Address                 Visibility   Label
8099    127.0.0.1:8099         Public       [Process Name]
8001    127.0.0.1:8001         Public       [Process Name]
```

**Hover** over the port number to see the forwarded URL, or right-click and select "Copy Local Address".

---

## 🌐 Your Exact URLs

Based on your Codespace name: `solid-palm-tree-4jqrv9rv4p4jfjwv7`

### For MCP Client
```
https://solid-palm-tree-4jqrv9rv4p4jfjwv7-8099.app.github.dev/netlify-deploy/mcp
```

### For Testing (Test Page)
```
https://solid-palm-tree-4jqrv9rv4p4jfjwv7-8001.app.github.dev/test.html
```

### For Documentation
```
https://solid-palm-tree-4jqrv9rv4p4jfjwv7-8099.app.github.dev/docs
```

---

## 🧪 Verify It's Working

### Method 1: Use the Test Page (Easiest)

1. Open: `https://solid-palm-tree-4jqrv9rv4p4jfjwv7-8001.app.github.dev/test.html`
2. The server URL should already be filled in
3. Click **"Test Connection"** button
4. ✅ Success! You should see 3 tools listed

### Method 2: Use curl

```bash
curl -X POST \
  https://solid-palm-tree-4jqrv9rv4p4jfjwv7-8099.app.github.dev/netlify-deploy/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

**Expected output:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "generate_and_deploy_website",
        "description": "Generate a static website..."
      },
      ...
    ]
  }
}
```

### Method 3: Open API Docs

Open: `https://solid-palm-tree-4jqrv9rv4p4jfjwv7-8099.app.github.dev/docs`

You should see the Swagger UI with all endpoints.

---

## 🐛 Still Getting 404?

### Check 1: Are the ports actually public?
```bash
# Run in terminal
gh codespace ports -c $CODESPACE_NAME
```

Look for `Visibility: public` on ports 8099 and 8001.

### Check 2: Is the server still running?
```bash
ps aux | grep fluidmcp | grep 8099
```

If nothing shows up, restart the server:
```bash
fluidmcp run examples/netlify-deploy-config.json --file --start-server
```

### Check 3: Try the local URL first
```bash
curl -X POST http://localhost:8099/netlify-deploy/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

If this works but the public URL doesn't, the issue is definitely port visibility.

### Check 4: Verify the exact URL format
- ✅ Correct: `https://YOUR-CODESPACE-8099.app.github.dev/netlify-deploy/mcp`
- ❌ Wrong: `https://YOUR-CODESPACE-8099.app.github.dev/netlify-deploy`
- ❌ Wrong: `https://YOUR-CODESPACE-8099.app.github.dev/tools/list`

The path **must** end with `/mcp`

---

## 🎯 Next Steps After Port Setup

1. ✅ **Test the connection** (use test page)
2. 🔌 **Use in your MCP client** (paste the URL)
3. 🎨 **Generate your first website**
4. 🎉 **Profit!**

---

## 💡 Pro Tips

- **Bookmark your Codespace URLs** - they'll stay the same for this Codespace
- **Ports remember their visibility** - once public, they'll stay public in this Codespace
- **Test locally first** - always verify with `curl http://localhost:8099/...` before testing the public URL
- **Check server logs** - If something doesn't work, check: `tail -f /tmp/claude-1000/-workspaces-fluidmcp/tasks/*.output`

---

## 📚 Documentation

- **Quick Start**: [QUICKSTART.md](QUICKSTART.md)
- **Full Guide**: [README.md](README.md)
- **Testing**: [TESTING.md](TESTING.md)
- **Test Connection**: [test_connection.html](test_connection.html)

---

**Need more help?** The server is working perfectly locally. The only issue is port visibility. Once you make the ports public, everything will work!
