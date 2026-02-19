# FluidMCP Frontend

A **React + TypeScript frontend** providing user-friendly interfaces for MCP (Model Context Protocol) servers managed by FluidMCP.

This UI layer sits on top of FluidMCP's FastAPI gateway, consuming MCP endpoints without modifying any backend logic. The goal is to transform developer-oriented MCP tools (Swagger/JSON) into intuitive web interfaces.

> **Note:** The project has been restructured as a monorepo. The frontend is now located at `fluidmcp/frontend/` (previously `frontend/`), and the CLI is at `fluidmcp/cli/` (previously `fluidmcp/backend/`). If you have an existing setup, update your paths and CI/CD pipelines accordingly. The root `package.json` scripts now use `--prefix fluidmcp/frontend`.

## Overview

**Architecture:**
- **CLI**: FluidMCP + FastAPI gateway
- **MCP Servers**: Any MCP-compatible server (filesystem, Airbnb, memory, etc.)
- **Frontend**: React + TypeScript (Vite)
- **Communication**: HTTP calls to MCP endpoints
- **Deployment**: Single-port deployment (frontend + backend on same port)

**Production Mode (Single-Port Deployment):**
- Frontend UI: `http://localhost:8099/ui`
- Backend API: `http://localhost:8099/docs` (Swagger UI)
- Both served from the same port for simplified deployment

**Development Mode (Separate Servers):**
- Frontend UI: `http://localhost:5173` (Vite dev server with hot reload)
- Backend API: `http://localhost:8099/docs` (Swagger UI)

## Current Implementation

### Generic MCP Server Management Interface

A comprehensive web UI for managing and interacting with any MCP-compatible server:

**Core Features:**
- **Server Dashboard** - View all registered MCP servers with status indicators
- **Dynamic Tool Discovery** - Automatically detect and list available tools from each server
- **JSON Schema Forms** - Auto-generate input forms based on tool schemas
- **Tool Runner** - Execute any MCP tool with real-time result display
- **Environment Management** - Configure server-level and instance-level environment variables
- **Result Viewers** - Multiple formats (JSON, Table, Text, MCP Content)
- **Error Handling** - Comprehensive error boundaries and user-friendly error messages
- **Tool History** - Track recent tool executions for quick re-runs

### Server Management Page

A dedicated interface for CRUD operations on MCP server configurations:

**Access:** Navigate to "Manage" in the navigation bar or visit `/servers/manage`

**Features:**
- **Add Servers** - Create new server configurations with validation
  - Server ID (immutable, lowercase alphanumeric + hyphens)
  - Display name and description
  - Command and arguments
  - Environment variables (KEY=value format)
  - Enabled/disabled toggle
- **Edit Servers** - Modify existing configurations (blocked while server is running)
- **Delete Servers** - Two-step delete flow:
  - **Disable**: Sets `enabled=false`, hides from Dashboard (reversible)
  - **Delete**: Soft delete with recovery option for administrators
- **Search & Filter** - Find servers by name/ID, filter by status (all/running/stopped/failed)
- **Pagination** - Browse configurations 10 per page
- **Show Deleted** - Toggle to view soft-deleted servers (admin recovery)

**Lifecycle States:**
- **Enabled** - Visible on Dashboard, can be started/stopped
- **Disabled** - Hidden from Dashboard, shown in Manage page, cannot be started
- **Deleted** - Soft-deleted, hidden from both Dashboard and Manage (admin recovery only)

**Validation & Safety:**
- Cannot edit servers while they're running
- Cannot start disabled servers
- Server ID is immutable after creation
- Deleting a running server automatically stops it first

**User Flow:**
1. User opens the dashboard at `/ui`
2. Browses available MCP servers (filesystem, memory, Airbnb, etc.)
3. Selects a server to view details and available tools
4. Chooses a tool to execute
5. Fills out auto-generated form based on tool's JSON schema
6. Submits request - backend invokes the MCP tool
7. Results are displayed with appropriate viewer (table/json/text)
8. Can configure environment variables, manage server instances, or run another tool

## Tech Stack

- **React** - UI library
- **TypeScript** - Type safety
- **Vite** - Build tool and dev server

## Folder Structure

```
frontend/
├── src/
│   ├── pages/
│   │   ├── Dashboard.tsx         # Main server list view
│   │   ├── ServerDetails.tsx     # Server detail page with tools list
│   │   ├── ManageServers.tsx     # Server configuration management (CRUD)
│   │   └── ToolRunner.tsx        # Tool execution interface
│   ├── components/
│   │   ├── form/                 # JSON Schema form components
│   │   │   ├── JsonSchemaForm.tsx      # Dynamic form generator
│   │   │   ├── SchemaFieldRenderer.tsx # Field type router
│   │   │   ├── StringInput.tsx         # Text/email/date inputs
│   │   │   └── FormValidation.ts       # Validation utilities
│   │   ├── result/               # Tool result display components
│   │   │   ├── ToolResult.tsx          # Main result container
│   │   │   ├── JsonResultView.tsx      # JSON pretty-print view
│   │   │   ├── McpContentView.tsx      # MCP content renderer
│   │   ├── Navbar.tsx            # Reusable navigation bar
│   │   ├── ServerCard.tsx        # Server list item component
│   │   ├── ServerForm.tsx        # Server configuration form (create/edit)
│   │   ├── ServerEnvForm.tsx     # Environment variable editor
│   │   ├── DeleteConfirmationModal.tsx # Two-step delete flow
│   │   ├── ErrorBoundary.tsx     # Error boundary wrapper
│   │   ├── ErrorMessage.tsx      # Error display component
│   │   └── LoadingSpinner.tsx    # Loading indicator
│   ├── hooks/
│   │   ├── useServers.ts         # Server list data hook
│   │   ├── useServerDetails.ts   # Server detail data hook
│   │   ├── useServerManagement.ts # Server CRUD operations hook
│   │   ├── useServerEnv.ts       # Environment management hook
│   │   └── useToolRunner.ts      # Tool execution hook
│   ├── services/
│   │   ├── api.ts                # API client for backend
│   │   ├── toast.ts              # Toast notification service
│   │   └── toolHistory.ts        # Tool execution history
│   ├── types/
│   │   └── server.ts             # TypeScript type definitions
│   ├── _archive/                 # Legacy/archived code
│   │   ├── pages/                # Archived Airbnb and Home pages
│   │   └── data/                 # Archived mock data (no longer used)
│   ├── App.tsx                   # Root component with routing
│   ├── main.tsx                  # Application entry point
│   └── index.css                 # Global styles
├── dist/                         # Production build output (after npm run build)
├── .env                          # Environment configuration (dev mode)
├── package.json
├── vite.config.ts               # Vite build configuration
└── tsconfig.json                # TypeScript configuration
```

## Running the Frontend

### Prerequisites
- Node.js + npm
- Python virtual environment activated (if FluidMCP installed in venv)
- FluidMCP CLI installed (`pip install -e .` from repository root)

### Option 1: Production Mode (Single-Port Deployment) ⭐ Recommended

Build the frontend and serve it from the backend on a single port:

```bash
# 1. Build the frontend
cd fluidmcp/frontend
npm install
npm run build

# 2. Start the backend (serves both API and UI)
cd ../..
fmcp serve --allow-insecure

# Access:
# - Frontend UI: http://localhost:8099/ui
# - Backend API: http://localhost:8099/docs
```

This is the **recommended** approach for:
- Production deployments
- Testing the production build
- Simplified port management
- No CORS configuration needed

### Option 2: Development Mode (Separate Servers)

Run frontend and backend separately for hot reload during development:

```bash
# Terminal 1: Start backend
fmcp serve --allow-insecure --allow-all-origins

# Terminal 2: Start frontend dev server
cd fluidmcp/frontend
npm install
npm run dev

# Access:
# - Frontend UI: http://localhost:5173 (with hot reload)
# - Backend API: http://localhost:8099/docs
```

This is the **recommended** approach for:
- Active frontend development
- Hot module replacement (HMR)
- Faster feedback loop
- Debugging React components

**Codespaces URLs:**
- Frontend: `https://<codespace-name>-5173.app.github.dev`
- Backend: `https://<codespace-name>-8099.app.github.dev`

### Building for Production

To create an optimized production build:

```bash
cd fluidmcp/frontend
npm run build
```

This creates a `dist/` directory with optimized static files. The FluidMCP backend automatically serves this directory at `/ui` when you run:

```bash
fmcp serve
```

**Build Output:**
- `dist/index.html` - Main HTML file
- `dist/assets/` - Bundled JavaScript and CSS files

**Note:** The backend checks for the `dist/` directory on startup. If not found, it logs a warning but continues to run (backend API still works).

## Environment Configuration

Environment configuration depends on your deployment mode:

### Production Mode (Single-Port)
**No `.env` file needed!** The built frontend is served from the backend, so API calls use relative paths.

### Development Mode (Separate Servers)
Create a `.env` file inside `fluidmcp/frontend/`:

```bash
# Local development (backend on port 8099)
VITE_API_BASE_URL=http://localhost:8099

# GitHub Codespaces
# VITE_API_BASE_URL=https://<your-codespace-name>-8099.app.github.dev
```

**Note**: Replace `<your-codespace-name>` with the actual Codespaces URL shown in your browser when the backend is running.

**Port Update:** The default backend port changed from `8090` to `8099`. Update any existing `.env` files accordingly.

## Development Notes

### Current Limitations
- Server discovery requires backend API call (no WebSocket live updates)
- Form validation is basic (only required fields and type checking)
- No batch tool execution (run multiple tools simultaneously)
- Tool history stored in memory only (not persisted)
- Limited result formatting options for complex data structures
- No tool output streaming for long-running operations

### Recently Implemented ✅
- ✅ **Dynamic MCP tool discovery** - Auto-detect available tools from any server
- ✅ **Generic UI components** - JSON Schema-based forms work with any MCP tool
- ✅ **Multi-tool support** - Dashboard for all registered MCP servers
- ✅ **Error handling** - Error boundaries and user-friendly error messages
- ✅ **Multiple result viewers** - JSON, Table, Text, and MCP Content formats
- ✅ **Environment management** - Server-level and instance-level configuration
- ✅ **Single-port deployment** - Frontend served from backend at `/ui`
- ✅ **Server Management Page** - Full CRUD operations for server configurations
  - Create/edit/delete servers with validation
  - Two-step delete flow (disable vs soft delete)
  - Search, filter, and pagination
  - Show deleted servers toggle for admin recovery
  - Runtime safety (cannot edit running servers)

### Planned Improvements
- **Real-time updates** - WebSocket support for server status and logs
- **Advanced form validation** - Schema-based validation with custom rules
- **Tool workflows** - Chain multiple tools together
- **Result export** - Download results in CSV, JSON, or other formats
- **Search and filters** - Search servers/tools, filter by status/type
- **User preferences** - Save favorite tools, default form values
- **Streaming support** - Real-time output for long-running tools
- **Collaborative features** - Share tool configurations and results

### Architecture Benefits

**Single-Port Deployment:**
- ✅ Simplified deployment (one port to expose)
- ✅ No CORS configuration needed
- ✅ Easier container orchestration
- ✅ Reduced attack surface
- ✅ Better for production environments

**Development Flexibility:**
- ✅ Hot module replacement (HMR) when running separately
- ✅ Independent frontend/backend development
- ✅ Fast feedback loop for UI changes
- ✅ Same production architecture can be tested locally

## MCP Server Setup

The frontend works with any MCP-compatible server. Here are some examples:

### Using Built-in Servers (No Installation)

Run servers directly from configuration:

```bash
# Using a local config file
fmcp run examples/sample-config.json --file --start-server
```

The `examples/sample-config.json` includes filesystem and memory servers.

### Installing from FluidMCP Registry

Install popular MCP packages:

```bash
# Airbnb search tool
fmcp install Airbnb/airbnb@0.1.0

# Run after installation
fmcp run Airbnb/airbnb@0.1.0 --start-server
```

### Running from GitHub

Clone and run servers directly from GitHub:

```bash
fmcp github owner/repo --github-token TOKEN --start-server
```

### Using the Standalone Server

For persistent server management with the UI:

```bash
fmcp serve --allow-insecure
# Access UI at: http://localhost:8099/ui
# Use the UI to start/stop servers, configure environments, and run tools
```

For more server configuration options, refer to the FluidMCP documentation at the repository root.

## API Integration

The frontend communicates with FluidMCP via standard HTTP requests:

```typescript
// Example: Invoking an MCP tool
// Production: POST http://localhost:8099/airbnb/mcp
// Development: POST http://localhost:8099/airbnb/mcp (or configured via VITE_API_BASE_URL)
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

**Deployment Modes:**
- **Production**: Frontend at `/ui` makes API calls to the same origin
- **Development**: Frontend at `:5173` makes cross-origin API calls to `:8099` (requires CORS)

See `src/services/api.ts` for implementation details.

## Contributing

This frontend is evolving towards a generic MCP interface. When adding new tool integrations:

1. Keep backend logic unchanged
2. Create reusable components where possible
3. Follow existing patterns in `src/pages/`
4. Update this README with new features

For full FluidMCP documentation, see the root `README.md` and `CLAUDE.md`.
