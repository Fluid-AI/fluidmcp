# Weather MCP Server

Weather information MCP server with embedded HTML visualization for ChatGPT and other MCP clients.

## Overview

Provides current weather information for Indian cities with a beautiful dark-themed dashboard UI. Returns complete self-contained HTML pages that can be rendered directly by MCP clients like ChatGPT Desktop.

## Features

- ✅ **Embedded HTML UI**: Complete self-contained HTML with inline CSS/JS
- ✅ **15 Indian Cities**: Pre-configured mock data for major cities
- ✅ **Unit Conversion**: Supports both Celsius and Fahrenheit
- ✅ **City Search**: Fuzzy search to find cities
- ✅ **Dark Theme**: Modern, responsive design optimized for readability
- ✅ **ChatGPT Compatible**: Works with ChatGPT Desktop MCP integration

## Quick Start

### Installation

```bash
cd ui-mcps/weather-mcp-html
pip install -e .
```

### Run with FluidMCP

```bash
# From the repository root
fluidmcp run ui-mcps/weather-mcp-html/weather-config.json --file --start-server

# Server starts on http://localhost:8099
# Swagger UI: http://localhost:8099/docs
```

### Use with Frontend HTML Renderer (Recommended for Testing)

1. Start the weather MCP server:
```bash
MCP_CLIENT_SERVER_ALL_PORT=8100 fmcp run ui-mcps/weather-mcp-html/weather-config.json --file --start-server
```

2. Open the frontend in your browser:
```bash
# Open frontend-weather.html in your browser
open ui-mcps/weather-mcp-html/frontend-weather.html
# Or on Linux
xdg-open ui-mcps/weather-mcp-html/frontend-weather.html
```

3. Click any city button to see the weather dashboard rendered in an iframe!

**Features of the Frontend:**
- ✅ 15-city quick access buttons
- ✅ Temperature unit toggle (°C / °F)
- ✅ City search functionality
- ✅ HTML and JSON view tabs
- ✅ Auto-renders HTML responses in iframe
- ✅ Beautiful gradient UI

### Use with ChatGPT Desktop

1. Add to your ChatGPT MCP configuration:
```json
{
  "mcpServers": {
    "weather": {
      "command": "python",
      "args": ["/path/to/fluidmcp/ui-mcps/weather-mcp-html/server.py"]
    }
  }
}
```

2. In ChatGPT, request: "Show me the weather in Bangalore"

3. The assistant will call the `get_weather` tool and render the HTML UI

## Available Tools

### 1. get_weather(city, units="metric")
Returns complete HTML page with weather visualization.

**Example:**
```python
get_weather("Bangalore")
get_weather("Mumbai", "imperial")
```

### 2. get_weather_json(city, units="metric")
Returns just the data as JSON (no UI).

**Example:**
```python
get_weather_json("Delhi")
```

### 3. search_city(query)
Search for cities matching a query.

**Example:**
```python
search_city("Ban")  # Returns: ["Bangalore"]
search_city("Mum")  # Returns: ["Mumbai"]
```

### 4. get_forecast(city, days=5, units="metric")
Weather forecast (Phase 2 - stub implementation).

## Supported Cities

Currently supports 15 Indian cities with mock data:
- Bangalore, Mumbai, Delhi, Chennai, Kolkata
- Pune, Hyderabad, Ahmedabad, Jaipur, Lucknow
- Surat, Kanpur, Nagpur, Indore, Kochi

## Architecture

### Design Pattern: Embedded HTML

The server generates **complete, self-contained HTML** pages with:
- All CSS embedded in `<style>` tags
- All JavaScript inline (minimal for Phase 1)
- No external dependencies or CDN links
- Weather data directly injected into HTML

See [server.py:17-214](server.py#L17-L214) for the `generate_weather_html()` function.

### Why Embedded?

This approach ensures **maximum compatibility** with MCP clients:
- ✅ Works in ChatGPT Desktop
- ✅ Works in Claude Desktop (if HTML rendering supported)
- ✅ No CORS or external resource issues
- ✅ Reliable rendering across different clients

### Technology Stack

- **Framework**: FastMCP (lightweight MCP server framework)
- **Communication**: stdio (not HTTP - for MCP protocol)
- **Python**: 3.12+
- **Dependencies**: mcp>=1.0.0, requests>=2.31.0

## Testing

### Test with curl (via FluidMCP)

```bash
# Start the server first
fluidmcp run ui-mcps/weather-mcp-html/weather-config.json --file --start-server

# Call the tool
curl -X POST http://localhost:8099/weather/mcp \
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

### Test Directly

```bash
# Run server directly (stdio mode)
python ui-mcps/weather-mcp-html/server.py
```

## File Structure

```
weather-mcp-html/
├── server.py              # Main MCP server with embedded HTML generation
├── pyproject.toml         # Package configuration
├── metadata.json          # MCP server metadata
├── weather-config.json    # FluidMCP configuration
├── tools/
│   ├── __init__.py
│   └── weather.py         # Weather data layer (mock data + future API support)
└── ui/                    # Reference templates (NOT loaded at runtime)
    ├── README.md          # Explains template files
    ├── weather.html       # HTML structure reference
    ├── weather.css        # Styling reference
    └── weather.js         # JavaScript reference (Phase 2)
```

**Important**: The `ui/` directory contains reference templates only. The actual HTML/CSS is generated in `server.py`.

## Configuration Files

### metadata.json
Describes the MCP server capabilities and tools for FluidMCP registry.

### weather-config.json
FluidMCP configuration for running the server locally.

## Development Phases

### Phase 1 (Current) ✅
- Embedded HTML generation
- Mock weather data for 15 cities
- Unit conversion (Celsius ↔ Fahrenheit)
- City search functionality
- Dark theme UI

### Phase 2 (Planned)
- Interactive unit toggle button
- Refresh functionality
- Real-time weather updates
- Extended forecast display
- Bi-directional MCP communication

### Phase 3 (Future)
- Real weather API integration (OpenWeatherMap)
- Error handling with fallback to mock data
- More cities and regions
- Historical weather data

## Troubleshooting

### HTML not rendering in custom agent?

The custom agent might expect the raw MCP protocol format (`TextContent` objects) instead of FastMCP's string responses. If that's the case, we'll need to switch from FastMCP to the raw MCP SDK (like the games-hub implementation).

**Check**: Does the agent render HTML from the games-hub MCP? If yes, but not this one, the issue is likely the response format.

### Port already in use?

```bash
# Kill existing process on port 8099
lsof -ti:8099 | xargs kill -9

# Or use a different port
MCP_CLIENT_SERVER_ALL_PORT=8098 fluidmcp run ...
```

### Import errors?

```bash
# Make sure dependencies are installed
pip install -r requirements.txt

# Or install in development mode
pip install -e .
```

## Contributing

To modify the UI:
1. Edit `generate_weather_html()` in [server.py](server.py)
2. Update embedded CSS (lines 49-177)
3. Test with FluidMCP
4. Optionally update reference templates in `ui/` folder

## License

MIT License - see repository root for details.

## Contact

Part of the FluidMCP project by Fluid-AI.
- GitHub: https://github.com/Fluid-AI/fluidmcp
- Issues: https://github.com/Fluid-AI/fluidmcp/issues
