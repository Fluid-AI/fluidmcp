import type { Server } from "../data/servers.mock"

export default function ServerCard( {server}: { server: Server}){
    return(
        <div className="server-card">
            <div className="server-card-header">
                <h3>{server.name}</h3>
                <span className={`status ${server.status}`}>
                    {server.status}
                </span>
            </div>
            <p className="server-description">{server.description}</p>

            <button disabled className="server-action">
                {server.status === "running" ? "Running" : "Start"}
            </button>
        </div>
    )
}