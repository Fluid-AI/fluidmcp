// const BASE_URL = "http://localhost:8090"
const BASE_URL = import.meta.env.VITE_API_BASE_URL;


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
    if(!response.ok){
        throw new Error("Failed to fetch Airbnb results");
    }
    return response.json();
}