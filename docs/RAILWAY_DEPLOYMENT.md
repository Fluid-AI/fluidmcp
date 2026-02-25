# Railway Deployment Guide for FluidMCP

This guide covers deploying FluidMCP to Railway using `fmcp serve` mode with MongoDB persistence.

## Prerequisites

- Railway account ([railway.app](https://railway.app))
- GitHub repository with FluidMCP code
- Basic understanding of Docker and environment variables

## Architecture Overview

FluidMCP on Railway uses:
- **`fmcp serve`** - Standalone API server (NOT `fmcp run`)
- **MongoDB** - Persistent storage for server configurations
- **Bearer Token Auth** - Secure API access
- **Dynamic Server Management** - Add/remove MCP servers via REST API

## Quick Start Deployment

### Step 1: Add MongoDB Service

1. Go to Railway dashboard
2. Click **New** → **Database** → **Add MongoDB**
3. Wait for MongoDB to provision
4. Note: `MONGODB_URI` is automatically added to your environment variables

### Step 2: Generate Bearer Token

⚠️ **CRITICAL**: Railway containers have no persistent storage. You MUST set a static bearer token.

```bash
# Generate secure token (64-character hex)
openssl rand -hex 32

# Example output:
# a7f3e9c2d1b8f4e6a3c9d7b2f5e8a1c4d6b9e2f7a4c8d3b6e9f2a5c7d1b4e8f3
```

**Save this token securely** (password manager recommended)

### Step 3: Configure Environment Variables

In Railway project settings → Variables → Raw Editor:

```bash
# MANDATORY: Bearer authentication token
FMCP_BEARER_TOKEN=<your-generated-token-from-step-2>

# Auto-provided by Railway MongoDB service
MONGODB_URI=mongodb://mongo.railway.internal:27017

# Auto-provided by Railway (service port)
PORT=<railway-assigns-automatically>

# Optional: CORS origins (comma-separated)
FMCP_ALLOWED_ORIGINS=https://your-frontend.com,https://app.example.com

# Optional: Database name (default: fluidmcp)
FMCP_DATABASE=fluidmcp
```

### Step 4: Connect GitHub Repository

1. Click **New** → **GitHub Repo**
2. Select your FluidMCP repository
3. **Important**: Select branch `fluidmcp_V1`
4. Railway auto-detects `Dockerfile`

### Step 5: Deploy

Railway automatically:
- Builds Docker image from `Dockerfile`
- Injects environment variables
- Starts container with `fmcp serve`
- Monitors health via `/health` endpoint

### Step 6: Verify Deployment

```bash
# Get your Railway URL from dashboard
RAILWAY_URL="https://your-app.railway.app"

# Check health
curl $RAILWAY_URL/health

# Expected response:
# {
#   "status": "healthy",
#   "database": "connected",
#   "persistence_enabled": true
# }
```

## Using the Management API

### List All Servers

```bash
curl -X GET https://your-app.railway.app/api/servers \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Add MCP Server

```bash
curl -X POST https://your-app.railway.app/api/servers \
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
```

### Start Server

```bash
curl -X POST https://your-app.railway.app/api/servers/filesystem/start \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Stop Server

```bash
curl -X POST https://your-app.railway.app/api/servers/filesystem/stop \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Get Server Status

```bash
curl -X GET https://your-app.railway.app/api/servers/filesystem/status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### View Server Logs

```bash
curl -X GET https://your-app.railway.app/api/servers/filesystem/logs \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Delete Server

```bash
curl -X DELETE https://your-app.railway.app/api/servers/filesystem \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Environment Variables Reference

### Required Variables

| Variable | Source | Purpose |
|----------|--------|---------|
| `FMCP_BEARER_TOKEN` | **YOU MUST SET** | Authentication token (prevents regeneration on restart) |
| `MONGODB_URI` | Railway MongoDB service | MongoDB connection string |
| `PORT` | Railway platform | Service port (dynamically assigned) |

### Optional Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `FMCP_DATABASE` | `fluidmcp` | MongoDB database name |
| `FMCP_ALLOWED_ORIGINS` | localhost only | CORS origins (comma-separated URLs) |
| `FMCP_MONGODB_SERVER_TIMEOUT` | `30000` | MongoDB server selection timeout (ms) |
| `FMCP_MONGODB_CONNECT_TIMEOUT` | `10000` | MongoDB connection timeout (ms) |
| `FMCP_MONGODB_SOCKET_TIMEOUT` | `45000` | MongoDB socket timeout (ms) |

## Health Monitoring

Railway automatically monitors the `/health` endpoint:

```bash
curl https://your-app.railway.app/health
```

**Response when healthy**:
```json
{
  "status": "healthy",
  "database": "connected",
  "database_error": null,
  "persistence_enabled": true
}
```

**Response when MongoDB unavailable**:
- Container exits immediately (`--require-persistence` flag)
- Railway restarts container (crash loop until MongoDB fixed)
- **This is intentional fail-fast behavior** (no silent degradation)

## MongoDB Connection Behavior

### Automatic Retry Logic

On startup, FluidMCP attempts to connect to MongoDB with:
- **3 retry attempts**
- **Exponential backoff**: 2s → 4s → 8s
- **Healthcheck start period**: 40s (accounts for retry delays)

### Fail-Fast Strategy

The `--require-persistence` flag ensures:
- ✅ **No silent fallback** to in-memory mode
- ✅ **Data consistency** (no unexpected behavior)
- ✅ **Clear failure signals** (crash loop indicates misconfiguration)

**If MongoDB is misconfigured**:
1. Container starts and tries to connect
2. Retry 1 fails (wait 2s) → Retry 2 fails (wait 4s) → Retry 3 fails (wait 8s)
3. Container exits with error
4. Railway restarts container
5. Repeat until MongoDB is fixed

## CORS Configuration

### Default (Localhost Only)

```python
[
    "http://localhost:*",
    "http://127.0.0.1:*",
    "http://localhost:3000",
    "http://localhost:8080",
]
```

### Production (Custom Origins)

```bash
# Set in Railway environment variables
FMCP_ALLOWED_ORIGINS=https://your-frontend.com,https://admin.example.com
```

### Development (Allow All) - NOT RECOMMENDED

```bash
# DO NOT USE IN PRODUCTION
FMCP_ALLOWED_ORIGINS=*
```

## Troubleshooting

### Issue: Container Keeps Restarting

**Symptoms**: Railway shows constant restarts, health check fails

**Causes**:
- MongoDB connection string incorrect
- MongoDB service not provisioned
- MongoDB credentials expired

**Fix**:
1. Check Railway logs: `railway logs`
2. Verify `MONGODB_URI` in environment variables
3. Ensure MongoDB service is running
4. Check MongoDB service logs

### Issue: 401 Unauthorized

**Symptoms**: All API requests return 401

**Causes**:
- Bearer token not set in Railway
- Token mismatch between client and server
- Token contains whitespace or special characters

**Fix**:
1. Verify `FMCP_BEARER_TOKEN` is set in Railway dashboard
2. Ensure client uses exact same token
3. Check for extra spaces or line breaks in token

### Issue: Health Check Fails

**Symptoms**: Railway shows service as unhealthy

**Causes**:
- Port mismatch (server not listening on `$PORT`)
- Server startup taking longer than healthcheck start-period (40s)
- MongoDB connection issues

**Fix**:
1. Check Railway logs for startup errors
2. Verify `PORT` environment variable is set
3. Increase healthcheck start-period if needed (edit Dockerfile)
4. Ensure MongoDB connection succeeds within 40s

### Issue: MCP Servers Not Starting

**Symptoms**: Server added but won't start

**Causes**:
- npx package download timeout (first-time download)
- Invalid package name
- Missing environment variables for MCP server

**Fix**:
1. Check server logs: `curl .../api/servers/{id}/logs`
2. Wait 30-60s for npx to fetch packages on first use
3. Verify package name is correct
4. Ensure all required env vars are set in config

### Issue: CORS Errors in Frontend

**Symptoms**: Browser console shows CORS errors

**Causes**:
- Frontend origin not in allowed origins list
- Preflight OPTIONS requests blocked

**Fix**:
1. Add frontend URL to `FMCP_ALLOWED_ORIGINS`
2. Format: `https://app.example.com` (no trailing slash)
3. Multiple origins: comma-separated, no spaces
4. Redeploy after changing environment variables

## Best Practices

### Security

1. **Use strong bearer tokens**: 64-character hex minimum
2. **Rotate tokens periodically**: Every 90 days recommended
3. **Store tokens securely**: Password manager or secret vault
4. **Never commit tokens**: Keep out of version control
5. **Restrict CORS origins**: Only allow trusted domains

### Monitoring

1. **Set up alerts**: Railway → Settings → Notifications
2. **Monitor health endpoint**: External uptime monitoring
3. **Check logs regularly**: `railway logs --follow`
4. **Track MongoDB usage**: Railway dashboard metrics
5. **Monitor container restarts**: Investigate crash loops immediately

### Maintenance

1. **Update dependencies**: Keep FluidMCP and npm packages current
2. **Review MongoDB size**: Clean old logs if database grows large
3. **Test in staging**: Use separate Railway project for testing
4. **Document tokens**: Keep secure record of which token is in use
5. **Backup configurations**: Export server configs periodically

## API Documentation

Once deployed, access interactive API documentation:

```
https://your-app.railway.app/docs
```

Swagger UI provides:
- Complete API endpoint reference
- Interactive request testing
- Request/response schemas
- Authentication setup

## Advanced Configuration

### Custom MongoDB Timeouts

For slow network connections or large databases:

```bash
FMCP_MONGODB_SERVER_TIMEOUT=60000      # 60 seconds
FMCP_MONGODB_CONNECT_TIMEOUT=20000     # 20 seconds
FMCP_MONGODB_SOCKET_TIMEOUT=90000      # 90 seconds
```

### Custom Database Name

```bash
FMCP_DATABASE=fluidmcp_production
```

### Multiple Environments

Create separate Railway projects:
- `fluidmcp-production` - Production deployment
- `fluidmcp-staging` - Testing environment
- `fluidmcp-development` - Development environment

Each with separate:
- MongoDB instances
- Bearer tokens
- CORS origins

## Migration from `fmcp run` Mode

If you previously deployed using `fmcp run` with static configs:

### Old Approach (Static Config)

```dockerfile
CMD fmcp run config.json --file --start-server
```

**Limitations**:
- Server configs baked into Docker image
- Requires rebuild to change servers
- No dynamic management
- No persistence across restarts

### New Approach (`fmcp serve`)

```dockerfile
CMD fmcp serve --host 0.0.0.0 --port ${PORT} --secure
```

**Benefits**:
- Server configs in MongoDB (persistent)
- Add/remove servers via API (no rebuild)
- Bearer token authentication
- Automatic health checks

### Migration Steps

1. Export existing server configurations
2. Deploy new `fmcp serve` mode to Railway
3. Use Management API to add servers
4. Test thoroughly before decommissioning old deployment
5. Update frontend to use bearer token authentication

## Support

For issues or questions:
- GitHub Issues: [fluidmcp/issues](https://github.com/anthropics/fluidmcp/issues)
- Documentation: [CLAUDE.md](../CLAUDE.md)
- Railway Support: [railway.app/help](https://railway.app/help)

---

**Remember**: This deployment uses `fmcp serve` (API server mode), NOT `fmcp run` (static config mode). All server management happens via REST API with MongoDB persistence.
