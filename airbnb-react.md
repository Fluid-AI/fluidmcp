# FluidMCP – Airbnb Search Tool (React UI)

This document describes the **Airbnb search tool built on top of FluidMCP**, consisting of:
- An MCP-based backend (Airbnb MCP server via FluidMCP)
- A React + TypeScript frontend UI
- A unified developer workflow to start both together

The goal is to provide a **user-friendly interface** over developer-oriented MCP tools (Swagger / JSON).


## Architecture Overview

This tool is implemented as a **clean UI layer** on top of FluidMCP.

- **Backend**: FluidMCP + FastAPI gateway (unchanged)
- **MCP Tool**: Airbnb MCP server (`@openbnb/mcp-server-airbnb`)
- **Frontend**: React + TypeScript (Vite)
- **Communication**: HTTP calls to MCP endpoints

No MCP server or gateway logic is modified.

Swagger UI remains available for developers at:
http://localhost:8090/docs


## Repository Layout (Relevant Parts)


fluidmcp/
├── frontend/ # React + TypeScript UI
├── fluidai_mcp/ # FluidMCP core (unchanged)
├── .fmcp-packages/ # Installed MCP packages
├── react-airbnb.md # This document
└── README.md # FluidMCP core documentation


## Features

- Home page listing available MCP tools (currently Airbnb)
- Airbnb search form:
    - Location
    - Guests
    - Dates
- MCP tool invocation via FluidMCP gateway
- Search results displayed as cards
- Cursor-based pagination (Load More)
- Duplicate listing handling
- Price sorting:
    - Low → High
    - High → Low
- Direct link to Airbnb full search results


## User Flow

1. User opens the UI home page
2. Selects the Airbnb tool
3. Fills out search criteria
4. React UI converts input into MCP-compatible payload
5. Backend invokes Airbnb MCP tool
6. Results are displayed
7. User can:
    - Load more results
    - Sort by price
    - Open Airbnb search externally


## Running Locally (Recommended)

### Prerequisites
- Node.js + npm
- Python
- FluidMCP installed and available (fmcp in PATH)
- Python virtual environment activated (if package installed in venv)
- Airbnb MCP package installed (Airbnb/airbnb@0.1.0)
        fmcp install Airbnb/airbnb@0.1.0
- Frontend necessities installed

### Start Backend + Frontend Together

From the **repository root**:

.venv\Scripts\activate (if required)
npm install
npm run airbnb-dev


This starts:
    MCP Gateway → http://localhost:8090 
    React UI → http://localhost:5173

Environment Variables
    Create a .env file inside frontend/:
    VITE_API_BASE_URL=http://localhost:8090

    If running inside GitHub Codespaces, use the public backend URL instead:
        VITE_API_BASE_URL=https://<your-codespace-name>-8090.app.github.dev
    Note - Replace <your-codespace-name> with the actual Codespaces URL shown in the browser when the backend is running.

Notes & Limitations
- Tool discovery is currently static
- Sorting is client-side
- Grid layout and advanced filters are intentionally out of scope

Future Improvements
- Dynamic MCP tool discovery
- Shared UI for multiple MCP tools
- Rating and price range filters
- Better error and loading states