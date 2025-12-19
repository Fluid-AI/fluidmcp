# FluidMCP – Airbnb Search UI

This project adds a user-friendly React-based frontend on top of the
FluidMCP Airbnb MCP tool.

The goal is to replace developer-only interactions (Swagger / JSON)
with a simple customer-facing interface for searching Airbnb listings.


## Architecture

The frontend is added as a separate UI layer and does not modify
any existing FluidMCP or MCP server logic.

- Backend: FluidMCP + FastAPI (unchanged)
- Frontend: React + TypeScript (new)
- Communication: HTTP calls to existing MCP endpoints

Swagger UI remains available for developers.


## Folder Structure

fluidmcp/
├── frontend/              # React + TypeScript UI
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Home.tsx
│   │   │   └── Airbnb.tsx
│   │   ├── components/
│   │   │   └── ListingCard.tsx
│   │   ├── services/
│   │   │   └── api.ts
│   │   └── main.tsx
│   └── package.json
├── fluidai_mcp/           # Existing backend (unchanged)
└── .fmcp-packages/


## Features Implemented

- Home page listing available MCP tools (currently Airbnb – hardcoded)
- Airbnb search form (Location, Guests, Check-in / Check-out dates)
- Server-side MCP tool invocation
- Results displayed as cards
- Cursor-based pagination (Load More)
- Duplicate listing handling during pagination
- Price sorting (Low → High, High → Low)
- Client-side rating filter (e.g. 4★+, 5★)
- Direct link to Airbnb full search results
- Clean separation between backend (MCP) and frontend (UI)


## User Flow

1. User opens the home page and selects the Airbnb tool
2. User fills the search form and submits
3. React UI converts input into MCP-compatible payload
4. Backend calls Airbnb MCP tool
5. Results are parsed and displayed as cards
6. User can:
   - Load more results (cursor-based pagination)
   - Sort results by price
   - Filter results by rating
   - Open the full Airbnb search in a new tab


## Running Locally

### Backend

fmcp run Airbnb/airbnb@0.1.0 --start-server
http://localhost:8090

### Frontend
cd frontend
npm install
npm run dev
http://localhost:5173


### Environment Variables

Create a `.env` file in `frontend/`:
VITE_API_BASE_URL=http://localhost:8090

If running inside GitHub Codespaces, use the public backend URL instead:
VITE_API_BASE_URL=https://<your-codespace-name>-8090.app.github.dev
Note - Replace <your-codespace-name> with the actual Codespaces URL shown in the browser when the backend is running.

## Notes & Limitations

- The home page currently lists tools statically
- Layout uses a simple vertical list (grid layout intentionally avoided)
- Sorting and filtering are performed client-side
- Filters apply only to currently loaded results (not across all pages)

## Future Improvements

- Dynamic MCP tool discovery for the home page
- Price range filtering
- Shared UI components for multiple MCP tools
- Enhanced error handling
