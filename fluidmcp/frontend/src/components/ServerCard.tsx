import type { Server } from "../data/servers.mock"

export default function ServerCard({ server }: { server: Server }) {
    return(
        <div className="server-card">
            <div className="server-card-header">
                <h3>{server.name}</h3>
                <span className={`status ${server.status}`}>
                    {server.status}
                </span>
            </div>
            <p className="server-description">{server.description}</p>

            {/* TODO: Make button functional once API integration is complete */}
            <button disabled className="server-action">
                {server.status === "running" ? "Running" : "Start"}
            </button>
        </div>
    )
}