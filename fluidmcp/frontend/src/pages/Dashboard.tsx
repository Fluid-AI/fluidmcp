import ServerCard from "../components/ServerCard";
import { mockServers } from "../data/servers.mock";

export default function Dashboard() {

  const activeServers = mockServers.filter(
    (server) => server.status === "running" || server.status === "starting"
  );


  return (
    <div className="dashboard">
      {/* Header */}
      <header className="dashboard-header">
        <h1>FluidMCP Dashboard</h1>
        <p className="subtitle">
          Manage and run your configured MCP servers
        </p>
      </header>

      {/* Main content */}
      <section className="dashboard-section">
        <h2>Currently configured servers</h2>

        {/* Server list will go here */}
        <div className="server-list">
          {mockServers.map((server) => (
            <ServerCard key={server.id} server={server} />
          ))}
        </div>
      </section>
      <section className="dashboard-section">
        <h2>Currently active servers</h2>

        <div className="active-server-container">
          {activeServers.length === 0 ? (
            <p className="empty-state">
              No servers are currently running
            </p>
          ) : (
            <div className="active-server-list">
              {activeServers.map((server) => (
                <div key={server.id} className="active-server-row">
                  <div>
                    <strong>{server.name}</strong>
                    <span className={`status ${server.status}`}>
                      {server.status}
                    </span>
                  </div>

                  <button disabled className="details-btn">
                    See details
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