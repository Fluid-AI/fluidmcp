# FluidMCP Frontend

A **React + TypeScript frontend** providing user-friendly interfaces for MCP (Model Context Protocol) servers managed by FluidMCP.

This UI layer sits on top of FluidMCP's FastAPI gateway, consuming MCP endpoints without modifying any backend logic. The goal is to transform developer-oriented MCP tools (Swagger/JSON) into intuitive web interfaces.

## Overview

**Architecture:**
- **Backend**: FluidMCP + FastAPI gateway
- **MCP Servers**: Any MCP-compatible server (filesystem, Airbnb, memory, etc.)
- **Frontend**: React + TypeScript (Vite)
- **Communication**: HTTP calls to MCP endpoints

The Swagger UI remains available for developers at: `http://localhost:8090/docs`

## Current Implementation

### Airbnb Search Tool
The first implementation showcases an Airbnb search interface:

**Features:**
- Location-based property search
- Guest count and date selection
- Real-time MCP tool invocation via FluidMCP gateway
- Search results displayed as cards
- Cursor-based pagination (Load More)
- Duplicate listing filtering
- Price sorting (Low → High, High → Low)
- Direct link to Airbnb full search results

**User Flow:**
1. User opens the UI home page
2. Selects the Airbnb tool
3. Fills out search criteria (location, guests, dates)
4. React UI converts input into MCP-compatible payload
5. Backend invokes Airbnb MCP tool
6. Results are displayed with interactive controls
7. User can load more results, sort, or open Airbnb externally

## Tech Stack

- **React** - UI library
- **TypeScript** - Type safety
- **Vite** - Build tool and dev server

## Folder Structure

```
frontend/
├── src/
│   ├── pages/
│   │   └── Dashboard.tsx     # (New) Generic MCP dashboard
│   ├── components/
│   ├── services/
│   │   └── api.ts            # API client for MCP endpoints
│   ├── _archive/             # Archived components
│   └── main.tsx              # Application entry point
├── .env                      # Environment configuration
└── package.json
```

## Running the Frontend

### Prerequisites
- Node.js + npm
- FluidMCP backend running (see root README.md)
- Python virtual environment activated (if FluidMCP installed in venv)

### Option 1: Frontend + Backend Together (Recommended)

From the **repository root**:

```bash
# Activate virtual environment (if required)
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate     # Windows

# Install dependencies and start both services
npm install
npm run dev
```

This starts:
- **MCP Gateway**: `http://localhost:8090`
- **React UI**: `http://localhost:5173`

### Option 2: Frontend Only

If the FluidMCP backend is already running:

```bash
cd fluidmcp/frontend
npm install
npm run dev
```

The UI will be available at:
- Local: `http://localhost:5173`
- Codespaces: `https://<your-codespace-name>-5173.app.github.dev`

## Environment Configuration

Create a `.env` file inside `fluidmcp/frontend/`:

```bash
# Local development
VITE_API_BASE_URL=http://localhost:8090

# GitHub Codespaces
# VITE_API_BASE_URL=https://<your-codespace-name>-8090.app.github.dev
```

**Note**: Replace `<your-codespace-name>` with the actual Codespaces URL shown in your browser when the backend is running.

## Development Notes

### Current Limitations
- Tool discovery is currently static
- Sorting is client-side only
- Grid layout and advanced filters intentionally out of scope (MVP)
- Single tool implementation (Airbnb)

### Planned Improvements
- **Dynamic MCP tool discovery** - Auto-detect available tools
- **Generic UI components** - Shared interfaces for multiple MCP tools
- **Enhanced filtering** - Rating, price range, and custom filters
- **Better UX** - Improved error handling and loading states
- **Multi-tool support** - Dashboard for all available MCP servers

## MCP Server Setup

To use the Airbnb search tool, install the Airbnb MCP package:

```bash
fmcp install Airbnb/airbnb@0.1.0
```

For other MCP servers, refer to the FluidMCP documentation at the repository root.

## API Integration

The frontend communicates with FluidMCP via standard HTTP requests:

```typescript
// Example: Invoking an MCP tool
POST http://localhost:8090/airbnb/mcp
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "airbnb_search",
    "arguments": { /* search parameters */ }
  }
}
```

See `src/services/api.ts` for implementation details.

## Contributing

This frontend is evolving towards a generic MCP interface. When adding new tool integrations:

1. Keep backend logic unchanged
2. Create reusable components where possible
3. Follow existing patterns in `src/pages/`
4. Update this README with new features

For full FluidMCP documentation, see the root `README.md` and `CLAUDE.md`.
