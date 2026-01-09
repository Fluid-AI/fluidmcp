import { useParams, useNavigate } from "react-router-dom";
import { mockServerDetails } from "../data/serverDetails.mock";

export default function ServerDetails(){
    const { serverId } = useParams();
    const navigate = useNavigate();

    // For now we only support mock "time" server
    const server = serverId === "time" ? mockServerDetails : null;

    if(!server){
        return (
            <div className="dashboard">
                <header className="dashboard-header">
                    <button className="details-btn" onClick={()=> navigate("/dashboard")}>
                        ← Back to Dashboard
                    </button>
                    <h1>Server Not Found</h1>
                    <p className="subtitle">The requested server could not be found.</p>
                </header>
            </div>
        )
    }

    return(
        <div className="dashboard">
            {/* Header with Back Button */}
            <header className="dashboard-header">
                <button className="details-btn" onClick={()=> navigate("/dashboard")}>
                    ← Back to Dashboard
                </button>
                <h1>{server.name}</h1>
                <span className={`status ${server.status}`}>
                    {server.status}
                </span>
                <p className="subtitle">{server.description}</p>
            </header>

            {/* Tools */}
            <section className="dashboard-section">
                <h2>Available tools</h2>
                <div className="active-server-container">
                    {server.tools.length === 0 ? (
                        <p className="empty-state">No tools available for this server</p>
                    ) : (
                        <div className="active-server-list">
                            {server.tools.map((tool)=>(
                                <div key={tool.name} className="active-server-row">
                                    <div>
                                        <strong>{tool.name}</strong>
                                        <p className="subtitle">{tool.description}</p>
                                    </div>

                                    <button
                                        className="details-btn"
                                        onClick={()=> alert(`Navigate to tool runner for ${tool.name}`)}
                                    >
                                        Run tool
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </section>
        </div>
    );
}