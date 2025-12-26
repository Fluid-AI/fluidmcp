// Base URL of the FluidMCP backend
// This is injected via Vite environment variables
// const BASE_URL = "http://localhost:8090"
const BASE_URL = import.meta.env.VITE_API_BASE_URL;

/*
 Calls the Airbnb MCP tool via the FluidMCP backend.
  This function:
 1. Sends a POST request to the FastAPI gateway
 2. Invokes the `airbnb_search` MCP tool
 3. Passes user-selected search parameters (location, dates, guests, cursor)
 4. Returns the raw MCP JSON response
*/
export async function callAirbnbSearch(payload : any){
    const response = await fetch(
        `${BASE_URL}/airbnb/mcp/tools/call`,
        {
            method : "POST",
            headers : {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
        }
    )
    // If backend responds with non-2xx status, throw an friendly error
    if(!response.ok){
        throw new Error("Failed to fetch Airbnb results");
    }
    // Return raw MCP response (parsed later in the UI)
    return response.json();
}