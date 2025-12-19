import { Link } from "react-router-dom";

/* Home page of the FluidMCP frontend.

 Purpose:
 - Acts as an entry point for end users
 - Displays available MCP tools in a simple, user-friendly way
 - Currently tools are hardcoded (can be made dynamic later)
*/

function Home(){
    return (
        // Centered container for the homepage content
        <div style={{textAlign: "center", marginTop: "4rem"}}>
            <h1>FluidMCP</h1>
            <p style={{ opacity: 0.8 }}>Select a tool to continue</p>
            <h2 style={{ marginTop: "3rem" }}>Available Tools</h2>

            {/* Tool card (Airbnb Search) Currently hardcoded */}
            <div style={{
                margin: "1.5rem auto",
                padding: "1.25rem",
                maxWidth: 320,
                borderRadius: 12,
                background: "#0f172a",
                boxShadow: "0 8px 24px rgba(0,0,0,0.3)",
                border: "1px solid #334155",
                }}>
                 {/* Tool name, sescription and link */}
                <h3>Airbnb Search</h3>
                <p style={{ fontSize: "0.9rem", opacity: 0.85 }}> Search Airbnb listings with filters</p>
                <Link to="/airbnb" style={{ display: "inline-block", marginTop: "0.75rem", fontWeight: 600,}}>Open</Link>
            </div>
        </div>
    );
}

export default Home;