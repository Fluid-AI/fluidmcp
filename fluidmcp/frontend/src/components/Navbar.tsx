import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import apiClient from "@/services/api";

interface NavbarProps {
  showAddButton?: boolean;
  onOpenAddDialog?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ showAddButton, onOpenAddDialog }) => {
  const location = useLocation();
  const isActive = (path: string) => location.pathname === path || location.pathname.startsWith(path);
  const [apiToken, setApiToken] = React.useState("");
  const [appliedToken, setAppliedToken] = React.useState<string | null>(null);
  const [showSettings, setShowSettings] = React.useState(false);

  React.useEffect(() => {
    const savedToken = localStorage.getItem("api_token");

    if (savedToken) {
      setApiToken(savedToken);
      setAppliedToken(savedToken);
      apiClient.setToken(savedToken);
    }
  }, []);

  return (
    <>
      <header className="fixed top-0 left-0 right-0 z-50 border-b border-border/40 bg-background/95 backdrop-blur-md supports-[backdrop-filter]:bg-background/60 transition-all duration-200">
      <div className="container mx-auto flex h-16 max-w-screen-xl items-center justify-between px-6">
        {/* LEFT */}
        <div className="flex items-center space-x-8">
          <Link to="/" className="flex items-center space-x-2 group transition-all duration-200 hover:scale-105">
            <span className="text-lg font-bold bg-gradient-to-r from-foreground to-foreground/80 bg-clip-text whitespace-nowrap">Fluid MCP</span>
          </Link>
          <nav className="hidden md:flex items-center space-x-1 text-sm">
            <Link
              to="/servers"
              className={`inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none ${
                isActive('/servers') && !location.pathname.includes('/manage') ? 'text-foreground' : 'text-foreground/60'
              }`}
            >
              Servers
            </Link>
            <Link
              to="/llm/models"
              className={`inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none ${
                isActive('/llm/models') ? 'text-foreground' : 'text-foreground/60'
              }`}
            >
              LLM Models
            </Link>
            <Link
              to="/status"
              className={`inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none ${
                isActive('/status') ? 'text-foreground' : 'text-foreground/60'
              }`}
            >
              Status
            </Link>
            <Link
              to="/servers/manage"
              className={`inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none ${
                location.pathname.includes('/manage') ? 'text-foreground' : 'text-foreground/60'
              }`}
            >
              Manage
            </Link>
            <Link
              to="/inspector"
              className={`inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none ${
                isActive('/inspector') ? 'text-foreground' : 'text-foreground/60'
              }`}
            >
              Inspector
            </Link>
            <Link
              to="/documentation"
              className={`inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none ${
                isActive('/documentation') ? 'text-foreground' : 'text-foreground/60'
              }`}
            >
              Documentation
            </Link>
          </nav>
        </div>
        {/* RIGHT */}
        <div className="flex items-center space-x-3" >
          {showAddButton && onOpenAddDialog && (
            <button
              onClick={onOpenAddDialog}
              style={{ background: '#000', color: '#fff', border: 'none', padding: '0.5rem 1rem', borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '500', display: 'inline-flex', alignItems: 'center', transition: 'all 0.2s', margin: 0 }}
              onMouseEnter={(e) => e.currentTarget.style.background = '#18181b'}
              onMouseLeave={(e) => e.currentTarget.style.background = '#000'}
            >
              <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Add Server
            </button>
          )}
          <a
            href="https://www.fluid.ai/"
            target="_blank"
            rel="noopener noreferrer"
            style={{ background: '#000', color: '#fff', border: 'none', padding: '0.5rem 1rem', borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '500', display: 'inline-flex', alignItems: 'center', transition: 'all 0.2s', margin: 0, textDecoration: 'none' }}
            onMouseEnter={(e) => e.currentTarget.style.background = '#18181b'}
            onMouseLeave={(e) => e.currentTarget.style.background = '#000'}
          >
            <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
            </svg>
            Fluid MCP for your Enterprise
          </a>
          <a
            href="https://www.fluid.ai/contact-us"
            target="_blank"
            rel="noopener noreferrer"
            style={{ background: '#000', color: '#fff', border: 'none', padding: '0.5rem 1rem', borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '500', display: 'inline-flex', alignItems: 'center', transition: 'all 0.2s', margin: 0, textDecoration: 'none' }}
            onMouseEnter={(e) => e.currentTarget.style.background = '#18181b'}
            onMouseLeave={(e) => e.currentTarget.style.background = '#000'}
          >
            <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
            </svg>
            Report Issue
          </a>

          {/* Hamburger */}
          <button
            onClick={() => setShowSettings(true)}
            style={{
              padding: "0.4rem",
              border: "1px solid #444",
              borderRadius: "6px",
              cursor: "pointer"
            }}
          >
            ☰
          </button>
        </div>
      </div>
        
    </header>
    {/* SETTINGS DRAWER */}    
        {showSettings && (
          <>
            {/* Overlay */}
            <div
              onClick={() => setShowSettings(false)}
              style={{
                position: "fixed",
                top: 0,
                left: 0,
                width: "100%",
                height: "100%",
                background: "rgba(0, 0, 0, 0.6)",
                zIndex: 999
              }}
            />

            {/* Drawer */}
            <div
              onClick={(e) => e.stopPropagation()}  
              style={{
                position: "fixed",
                top: 0,
                right: 0,
                height: "100%",
                width: "320px",
                background: "#18181b",
                borderLeft: "1px solid rgba(63,63,70,0.6)",
                zIndex: 1000,
                padding: "20px",
                isolation: "isolate",
                boxShadow: "-4px 0 20px rgba(0,0,0,0.5)"
              }}
            >
              <h3 style={{ marginBottom: "16px" }}>Settings</h3>

              {/* Token Section */}
              <div style={{ marginBottom: "20px" }}>
                <label style={{ fontSize: "12px", color: "#aaa" }}>
                  API Bearer Token
                </label>

                <input
                  type="password"
                  value={apiToken}
                  onChange={(e) => setApiToken(e.target.value)}
                  style={{
                    width: "100%",
                    marginTop: "6px",
                    padding: "0.5rem",
                    borderRadius: "6px",
                    border: "1px solid #333",
                    background: "#000",
                    color: "#fff"
                  }}
                />
                {/* ACTIVE INDICATOR */}
                {appliedToken && (
                  <div style={{ fontSize: "11px", color: "#22c55e", marginTop: "4px" }}>
                    ● Active
                  </div>
                )}
                {/* BUTTONS */}
                <div style={{ display: "flex", gap: "8px", marginTop: "10px" }}>
                  <button
                    onClick={() => {
                      apiClient.setToken(apiToken || null);
                      setAppliedToken(apiToken || null);
                      if (apiToken) localStorage.setItem("api_token", apiToken);
                    }}
                    style={{
                      padding: "6px 10px",
                      background: "#16a34a",
                      color: "#fff",
                      border: "none",
                      borderRadius: "4px",
                      cursor: "pointer"
                    }}
                  >
                    Set
                  </button>

                  <button
                    onClick={() => {
                      setApiToken("");
                      setAppliedToken(null);
                      apiClient.setToken(null);
                      localStorage.removeItem("api_token");
                    }}
                    style={{
                      padding: "6px 10px",
                      background: "#3f3f46",
                      color: "#fff",
                      border: "none",
                      borderRadius: "4px",
                      cursor: "pointer"
                    }}
                  >
                    Clear
                  </button>
                </div>
              </div>

              {/* Close */}
              <button 
                onClick={() => setShowSettings(false)}
                style={{ marginTop: "20px" }}
              >
                Close
              </button>
            </div>
          </>
      )}
    </>
  );
};
