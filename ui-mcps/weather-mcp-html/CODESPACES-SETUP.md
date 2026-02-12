# Weather MCP - Codespaces Setup

## Your Codespace URLs

Your weather MCP server is running on port 8100. Here are your **specific Codespaces URLs**:

### 🌐 Main URLs

**MCP Endpoint:**
```
https://crispy-yodel-5gj9969v77w4h4jr9-8100.app.github.dev/weather/mcp
```

**Swagger API Docs:**
```
https://crispy-yodel-5gj9969v77w4h4jr9-8100.app.github.dev/docs
```

**FluidMCP Built-in UI:**
```
https://crispy-yodel-5gj9969v77w4h4jr9-8100.app.github.dev/ui
```

---

## 🚀 Quick Start Steps

### 1. Open the Frontend

Open `frontend-weather.html` in your browser (it's already in your workspace).

### 2. Update the Endpoint

When the page loads:

1. Look for the **"Server Configuration"** box at the top
2. You'll see a text input with the current endpoint
3. **Replace it with:**
   ```
   https://crispy-yodel-5gj9969v77w4h4jr9-8100.app.github.dev/weather/mcp
   ```
4. Click **"Update"** button

### 3. Test It

Click any city button (e.g., "Bangalore") and you should see the weather dashboard!

---

## 🧪 Test with curl

```bash
curl -X POST https://crispy-yodel-5gj9969v77w4h4jr9-8100.app.github.dev/weather/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "get_weather",
      "arguments": {"city": "Bangalore"}
    }
  }'
```

---

## 🔧 Troubleshooting

### Port Forwarding

Codespaces automatically forwards ports. You can check your forwarded ports:

1. In VS Code, go to the **"PORTS"** tab (bottom panel)
2. You should see port **8100** listed
3. Make sure visibility is set to **"Public"**

### Server Not Running?

Restart the server:

```bash
# Stop any existing servers
lsof -ti:8100 | xargs kill -9 2>/dev/null || true

# Start the server
MCP_CLIENT_SERVER_ALL_PORT=8100 fmcp run ui-mcps/weather-mcp-html/weather-config.json --file --start-server
```

---

## 📱 For Your Custom Agent

Your custom agent should call:

**Endpoint:**
```
https://crispy-yodel-5gj9969v77w4h4jr9-8100.app.github.dev/weather/mcp
```

**Request Format:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "get_weather",
    "arguments": {
      "city": "Bangalore",
      "units": "metric"
    }
  }
}
```

**Response will contain HTML in:**
```
response.result.content[0].text
```

Then render it in an iframe:

```javascript
const iframe = document.createElement('iframe');
iframe.style.width = '100%';
iframe.style.height = '700px';
document.body.appendChild(iframe);

iframe.contentWindow.document.open();
iframe.contentWindow.document.write(htmlContent);
iframe.contentWindow.document.close();
```

---

## ✅ Success Checklist

- [ ] Server running on port 8100
- [ ] Port 8100 is public in Codespaces
- [ ] Frontend HTML opened in browser
- [ ] Endpoint updated to Codespaces URL
- [ ] Clicked city button and saw weather dashboard

---

**Note:** If you restart your Codespace, the URLs will stay the same for this specific codespace.
