# FMCP Serve → Key Flow

> Quick overview of how the `fmcp serve` command starts the standalone API server for dynamic MCP management.

**Key steps:** Parse CLI args → Connect to MongoDB → Initialize managers → Create FastAPI app → Add routes → Serve frontend → Start uvicorn → Ready for API calls

## Flow Diagram

```
  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
  │  1. Parse       │───► │  2. Connect to  │───► │  3. Initialize  │───► │  4. Create      │
  │  CLI Args       │     │  MongoDB        │     │  Managers       │     │  FastAPI App    │
  │  cli.py         │     │  database.py    │     │  server.py      │     │  server.py      │
  │  main()         │     │  DatabaseManager│     │  main()         │     │  create_app()   │
  │  serve parser   │     │  .connect()     │     │  ServerManager()│     │                 │
  └─────────────────┘     │  .init_db()     │     └─────────────────┘     └─────────────────┘
                          └─────────────────┘                                       │
                                                                                     ▼
  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
  │  8. Ready for   │◄─── │  7. Start       │◄─── │  6. Serve       │◄─── │  5. Add Routes  │
  │  API Calls      │     │  Uvicorn        │     │  Frontend       │     │  & Middleware   │
  │  http://0.0.0.0:│     │  server.py      │     │  frontend_      │     │  server.py      │
  │  8099           │     │  main()         │     │  utils.py       │     │  create_app()   │
  │  • POST /api/   │     │  uvicorn.run()  │     │  setup_frontend │     │  • CORS         │
  │    servers      │     │                 │     │  _routes()      │     │  • Auth         │
  │  • POST /{srv}/ │     │                 │     │                 │     │  • Mgmt API     │
  │    mcp          │     │                 │     │                 │     │  • Dynamic      │
  │  • GET /docs    │     │                 │     │                 │     │    Router       │
  └─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Notes

- **Step 1-2**: CLI parses `fmcp serve --secure --mongodb-uri ...` and establishes MongoDB connection with retry logic (3 attempts with exponential backoff)
- **Step 3**: Creates ServerManager (for MCP lifecycle) and starts idle cleanup background task
- **Step 4**: FastAPI app created with CORS, request size limiting, and bearer token authentication
- **Step 5**: Includes Management API (`/api/*`), Dynamic MCP Router (`/{server}/*`), health (`/health`), and metrics (`/metrics`)
- **Step 6**: Serves built React app from static files at root path (`/`)
- **Step 7**: Binds to `0.0.0.0:8099` (port configurable via `--port` or `$PORT` env var)
- **Step 8**: Server running with **no MCP servers loaded** — all servers added dynamically via API

## Step Summary

| Step | Name | File | Function | Role |
|------|------|------|----------|------|
| 1 | Parse CLI Args | cli.py | main() → serve parser | Validate flags, generate/load bearer token |
| 2 | Connect to MongoDB | repositories/database.py | DatabaseManager.connect(), init_db() | Establish persistence with retry |
| 3 | Initialize Managers | server.py | main() | Create ServerManager, start background tasks |
| 4 | Create FastAPI App | server.py | create_app() | Build app with middleware stack |
| 5 | Add Routes | server.py | create_app() | Include API routers and endpoints |
| 6 | Serve Frontend | services/frontend_utils.py | setup_frontend_routes() | Mount React static files |
| 7 | Start Uvicorn | server.py | main() → uvicorn.run() | Bind HTTP server to port |
| 8 | Ready for API Calls | – | – | Server listening, no MCP servers loaded |

## Configuration Priority

| Setting | Priority Order |
|---------|---------------|
| Bearer Token | CLI `--token` > Env `FMCP_BEARER_TOKEN` > Auto-generate |
| MongoDB URI | CLI `--mongodb-uri` > Env `MONGODB_URI` > `mongodb://localhost:27017` |
| Port | CLI `--port` > Env `PORT` > Default `8099` |
| CORS Origins | CLI `--allowed-origins` > Env `FMCP_ALLOWED_ORIGINS` > Localhost only |

## Startup Modes

| Mode | Command | Persistence | Use Case |
|------|---------|------------|----------|
| Secure + MongoDB | `fmcp serve --secure` | MongoDB | Production (Railway) |
| Secure + In-Memory | `fmcp serve --secure --in-memory` | None | Testing with auth |
| Insecure + In-Memory | `fmcp serve --in-memory` | None | Local development |
| Require Persistence | `fmcp serve --require-persistence` | MongoDB (fail if unavailable) | Production with strict requirements |

## Post-Startup

After server starts, manage MCP servers via REST API:

```bash
# Add server configuration
curl -X POST http://localhost:8099/api/servers \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "filesystem",
    "config": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
      "env": {}
    }
  }'

# Start the server
curl -X POST http://localhost:8099/api/servers/filesystem/start \
  -H "Authorization: Bearer YOUR_TOKEN"

# List all servers
curl http://localhost:8099/api/servers \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Key Differences from `fmcp run`

| Aspect | `fmcp run` | `fmcp serve` |
|--------|-----------|-------------|
| Server Loading | Pre-loaded from config | None at startup (added via API) |
| Configuration | Static (config file) | Dynamic (REST API) |
| Persistence | Not required | Recommended (MongoDB) |
| Use Case | Quick testing | Production deployment |
| Management | CLI only | REST API + Frontend UI |
