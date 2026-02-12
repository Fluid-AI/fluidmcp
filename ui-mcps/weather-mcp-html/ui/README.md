# UI Template Files

**Important**: These files are **NOT loaded at runtime**. They serve as templates/reference only.

## Current Implementation

The Weather MCP server uses an **embedded HTML approach** where all HTML, CSS, and JavaScript are generated inline within [server.py](../server.py) at runtime.

See `generate_weather_html()` function in [server.py:17-214](../server.py#L17-L214) for the actual implementation.

## Files in This Directory

### weather.html
- **Purpose**: Reference template showing the HTML structure
- **Status**: Not loaded by server
- **Note**: The actual HTML is generated programmatically in server.py

### weather.css
- **Purpose**: Reference stylesheet showing the design system
- **Status**: Not loaded by server
- **Note**: CSS is embedded inline in the generated HTML (server.py lines 49-177)

### weather.js
- **Purpose**: Reference JavaScript showing intended interactivity
- **Status**: Not loaded by server
- **Note**: Contains postMessage patterns that were planned for Phase 2

## Why Embedded HTML?

The embedded approach (all code in one HTML string) is designed for **ChatGPT MCP compatibility**:

1. **Self-contained**: No external file dependencies
2. **Guaranteed rendering**: Works in any MCP client
3. **Simple deployment**: Single server.py file contains everything
4. **Compatible**: Follows the pattern used by successful MCP servers

## Phase 2 Plans

These template files can be used as reference when implementing:
- Interactive unit toggle (°C ↔ °F)
- Refresh functionality
- Extended weather forecast display
- Real-time weather updates

## For Developers

If you want to modify the UI:
1. Edit the HTML generation in `server.py` (function `generate_weather_html()`)
2. Update the embedded CSS in the `<style>` block (lines 49-177)
3. Modify inline JavaScript if needed (currently minimal)
4. These template files can be updated to match for reference purposes
