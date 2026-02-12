# Agent Integration Guide

## Problem
Your custom LLM agent receives HTML as plain text but cannot render it in an iframe.

## Solution
We've added a new tool `get_weather_ui` that returns a **structured JSON response** with:
- A **data URL** (base64-encoded HTML) that can be used directly as iframe `src`
- The raw HTML (in case agent prefers document.write method)
- Rendering instructions

## Quick Start

### Call the New Tool
```javascript
POST https://crispy-yodel-5gj9969v77w4h4jr9-8100.app.github.dev/weather/mcp

{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "get_weather_ui",
    "arguments": {
      "city": "Bangalore",
      "units": "metric"
    }
  }
}
```

### Response Format
```json
{
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"type\":\"html_ui\",\"city\":\"Bangalore\",\"rendering\":{\"method\":\"iframe\",\"data_url\":\"data:text/html;base64,PCFETy...\",\"instructions\":\"...\"},\"html\":\"<!DOCTYPE html>...\"}"
      }
    ]
  }
}
```

## Implementation in Your Agent

### Method 1: Data URL (Recommended ⭐)

This is the **easiest** method. Just use the data URL as iframe `src`:

```javascript
// In your agent's MCP response handler
async function handleWeatherUI(city) {
  // Call the MCP tool
  const response = await fetch(MCP_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: Date.now(),
      method: "tools/call",
      params: {
        name: "get_weather_ui",
        arguments: { city: city, units: "metric" }
      }
    })
  });

  const data = await response.json();

  // Parse the text content as JSON
  const uiData = JSON.parse(data.result.content[0].text);

  // Check if it's a UI response
  if (uiData.type === 'html_ui') {
    // Create iframe with data URL as src
    const iframe = document.createElement('iframe');
    iframe.src = uiData.rendering.data_url;
    iframe.style.width = '100%';
    iframe.style.height = '700px';
    iframe.style.border = 'none';
    iframe.style.borderRadius = '10px';

    // Append to your response container
    document.getElementById('your-response-container').appendChild(iframe);
  }
}
```

### Method 2: contentWindow.document.write()

If data URLs don't work in your environment:

```javascript
// Parse the response
const uiData = JSON.parse(data.result.content[0].text);

if (uiData.type === 'html_ui') {
  // Create iframe
  const iframe = document.createElement('iframe');
  iframe.style.width = '100%';
  iframe.style.height = '700px';
  iframe.style.border = 'none';

  // Append first
  document.getElementById('your-response-container').appendChild(iframe);

  // Write HTML
  iframe.contentWindow.document.open();
  iframe.contentWindow.document.write(uiData.html);
  iframe.contentWindow.document.close();
}
```

### Method 3: Auto-detect Response Type

Make your agent smart about handling different response types:

```javascript
function handleMCPResponse(response) {
  const content = response.result.content[0].text;

  try {
    // Try to parse as JSON
    const data = JSON.parse(content);

    // Check response type
    if (data.type === 'html_ui') {
      // It's a UI response - render in iframe
      renderInIframe(data);
    } else {
      // It's a JSON data response - display as formatted JSON
      displayJSON(data);
    }
  } catch (e) {
    // Not JSON - display as plain text
    displayText(content);
  }
}

function renderInIframe(uiData) {
  const iframe = document.createElement('iframe');
  iframe.src = uiData.rendering.data_url; // Use Method 1
  iframe.style.width = '100%';
  iframe.style.height = '700px';
  iframe.style.border = 'none';
  document.getElementById('response-container').appendChild(iframe);
}
```

## Testing

### Test the Server
```bash
# Restart the server with new tool
MCP_CLIENT_SERVER_ALL_PORT=8100 fmcp run ui-mcps/weather-mcp-html/weather-config.json --file --start-server
```

### Test the Tool
```bash
curl -X POST https://crispy-yodel-5gj9969v77w4h4jr9-8100.app.github.dev/weather/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "get_weather_ui",
      "arguments": {"city": "Bangalore"}
    }
  }'
```

### Interactive Example
Open `agent-integration-example.html` in your browser to see working examples of both methods.

## Available Tools

| Tool | Returns | Use Case |
|------|---------|----------|
| `get_weather` | Raw HTML | For agents with custom rendering logic |
| `get_weather_ui` | JSON with data URL | **For agents that need help rendering (RECOMMENDED)** |
| `get_weather_json` | JSON data only | For agents that build their own UI |

## Comparison

### Before (get_weather)
```
Response: "<!DOCTYPE html><html>..."
Agent: Displays as text ❌
```

### After (get_weather_ui)
```
Response: {"type":"html_ui","rendering":{"data_url":"data:text/html;base64,..."}}
Agent: iframe.src = data_url ✅
```

## Summary

**What We Changed:**
1. Added `get_weather_ui` tool that returns structured JSON
2. JSON includes a data URL (base64-encoded HTML)
3. Agent can use data URL directly as iframe `src` - no complex rendering logic needed

**What Your Agent Needs:**
- Parse the JSON response
- Extract `data.rendering.data_url`
- Create an iframe and set `iframe.src = data_url`
- Done! 🎉

## Example Integration

```javascript
// Complete example for your agent
class WeatherMCPHandler {
  constructor(endpoint) {
    this.endpoint = endpoint;
  }

  async showWeather(city) {
    try {
      // Call MCP tool
      const response = await fetch(this.endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          jsonrpc: "2.0",
          id: Date.now(),
          method: "tools/call",
          params: {
            name: "get_weather_ui",
            arguments: { city, units: "metric" }
          }
        })
      });

      const result = await response.json();
      const uiData = JSON.parse(result.result.content[0].text);

      // Render in iframe
      if (uiData.type === 'html_ui') {
        this.renderUI(uiData);
      }
    } catch (error) {
      console.error('Weather error:', error);
    }
  }

  renderUI(uiData) {
    // Clear previous content
    const container = document.getElementById('weather-container');
    container.innerHTML = '';

    // Create and append iframe
    const iframe = document.createElement('iframe');
    iframe.src = uiData.rendering.data_url;
    iframe.style.width = '100%';
    iframe.style.height = '700px';
    iframe.style.border = 'none';
    container.appendChild(iframe);

    console.log(`✅ Weather UI loaded for ${uiData.city}`);
  }
}

// Usage
const handler = new WeatherMCPHandler('https://crispy-yodel-5gj9969v77w4h4jr9-8100.app.github.dev/weather/mcp');
handler.showWeather('Bangalore');
```

## Need Help?

1. Check `agent-integration-example.html` for working demos
2. Test with `frontend-weather.html` to see expected output
3. Check browser console for errors
4. Verify MCP endpoint is accessible

---

✅ **Key Takeaway**: Use `get_weather_ui` tool and set `iframe.src = data.rendering.data_url` - that's it!
