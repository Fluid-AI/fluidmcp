# Airbnb Search UI (React)

This folder contains the **React + TypeScript frontend** for the FluidMCP Airbnb search tool.

The UI consumes MCP endpoints exposed by the FluidMCP gateway and does not modify any backend logic.

For full system setup and architecture, see:
👉 `react-airbnb.md` at the repository root.


## Tech Stack

   - React
   - TypeScript
   - Vite


## Folder Structure

frontend/
├── src/
│ ├── pages/
│ │ ├── Home.tsx
│ │ └── Airbnb.tsx
│ ├── components/
│ │ └── ListingCard.tsx
│ ├── services/
│ │ └── api.ts
│ └── main.tsx
└── package.json


## Running the Frontend Only

cd frontend
npm install
npm run dev

The UI will be available at:
http://localhost:5173 or https://<your-codespace-name>-5173.app.github.dev

Environment Variables
Create a .env file inside frontend/:
VITE_API_BASE_URL=http://localhost:8090

If running inside GitHub Codespaces, use the public backend URL instead:
VITE_API_BASE_URL=https://<your-codespace-name>-8090.app.github.dev
Note - Replace <your-codespace-name> with the actual Codespaces URL shown in the browser when the backend is running.

Notes
Assumes the FluidMCP gateway is already running
API base URL is configurable via environment variables
