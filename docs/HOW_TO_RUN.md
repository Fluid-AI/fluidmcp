# How to Run FluidMCP

This guide covers all methods to run FluidMCP, from basic usage to OAuth-secured production deployments.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Basic Usage (No Authentication)](#basic-usage-no-authentication)
3. [With OAuth Authentication](#with-oauth-authentication)
4. [Running in Different Environments](#running-in-different-environments)
5. [Docker Deployment](#docker-deployment)
6. [Production Deployment](#production-deployment)
7. [Common Issues](#common-issues)

---

## Prerequisites

### Required

```bash
# Python 3.11 or higher
python --version

# Install FluidMCP
pip install -r requirements.txt
pip install -e .

# Verify installation
fluidmcp --version
```

### Optional (for OAuth)

- **Auth0 Account**: Free tier at https://auth0.com
- **GitHub/Google Account**: For OAuth login

---

## Basic Usage (No Authentication)

### 1. Run with Example Configuration

The simplest way to get started:

```bash
# Create test directory (for filesystem MCP server)
mkdir -p /tmp/test-directory

# Run with example config
fluidmcp run examples/sample-config.json --file --start-server
```

**Output:**
```
Launching server 'filesystem' from: /workspaces/fluidmcp/.fmcp-packages/.temp_servers/filesystem
Added filesystem endpoints
Launching server 'memory' from: /workspaces/fluidmcp/.fmcp-packages/.temp_servers/memory
Added memory endpoints
Successfully launched 2 MCP server(s)

======================================================================
🚀 FluidMCP Server Starting
======================================================================
   Base URL: http://localhost:8099
   Swagger UI: http://localhost:8099/docs
======================================================================

Server running on http://localhost:8099
```

**Access the server:**
- Base URL: http://localhost:8099
- Swagger UI: http://localhost:8099/docs
- API Endpoint: http://localhost:8099/filesystem/mcp

### 2. Run All Installed Packages

```bash
# Run all MCP servers from registry
fluidmcp run all --start-server
```

### 3. Run from Configuration File

```bash
# Run from custom config
fluidmcp run /path/to/config.json --file --start-server

# With force reload (kills existing process on port)
fluidmcp run config.json --file --start-server --force-reload
```

### 4. Run from S3 Configuration

```bash
# Set S3 credentials
export S3_BUCKET_NAME="your-bucket"
export S3_ACCESS_KEY="your-access-key"
export S3_SECRET_KEY="your-secret-key"
export S3_REGION="us-east-1"

# Run from S3
fluidmcp run s3://bucket/config.json --s3 --start-server
```

### 5. Run from GitHub Repository

```bash
# Set GitHub token
export FMCP_GITHUB_TOKEN="your_github_token"

# Clone and run MCP server from GitHub
fluidmcp github owner/repo --start-server

# With specific branch
fluidmcp github owner/repo --branch develop --start-server
```

### 6. Run Registry Package with OAuth Authentication

To require authentication for registry packages (like Airbnb, Google Maps):

```bash
# Install package
fluidmcp install Airbnb/airbnb@0.1.0

# Run with OAuth authentication
fluidmcp run Airbnb/airbnb@0.1.0 --start-server --auth0
```

**Setup required:**
1. Configure Auth0 (see [OAUTH_SETUP_QUICK_START.md](OAUTH_SETUP_QUICK_START.md))
2. Set environment variables (AUTH0_DOMAIN, AUTH0_CLIENT_ID, AUTH0_CLIENT_SECRET, FMCP_JWT_SECRET)
3. Add `--auth0` flag when running

**Result:**
- Users must log in before accessing `/docs`
- All API endpoints require JWT token
- Swagger UI shows "Authorize" button
- Full OAuth security for registry packages

**Example:**
```bash
# Set up Auth0 credentials
export AUTH0_DOMAIN="your-tenant.us.auth0.com"
export AUTH0_CLIENT_ID="your_client_id"
export AUTH0_CLIENT_SECRET="your_client_secret"
export FMCP_JWT_SECRET=$(openssl rand -base64 32)

# Run Airbnb with OAuth
fluidmcp run Airbnb/airbnb@0.1.0 --start-server --auth0

# Access and authenticate
# Open: https://your-url/ (auto-detected)
# Log in with GitHub/Google
# Access /docs with authentication
```

---

## With OAuth Authentication

### Quick Start (5 minutes)

#### Step 1: Get Your URLs

```bash
python print-auth0-urls.py
```

**Output:**
```
======================================================================
🔐 Auth0 OAuth Configuration
======================================================================
📍 Environment: CODESPACES
🌐 Detected Remote Environment

🔗 URLs for your application:
   Base URL:     https://workspace-8099.app.github.dev
   Login URL:    https://workspace-8099.app.github.dev/
   Swagger UI:   https://workspace-8099.app.github.dev/docs
   Callback URL: https://workspace-8099.app.github.dev/auth/callback

⚙️  Auth0 Dashboard Configuration:
   Add these URLs to your Auth0 application settings:

   Allowed Callback URLs:
   https://workspace-8099.app.github.dev/auth/callback

   Allowed Logout URLs:
   https://workspace-8099.app.github.dev/

   Allowed Web Origins:
   https://workspace-8099.app.github.dev
======================================================================
```

#### Step 2: Set Up Auth0 (First Time Only)

1. **Create Auth0 account** (free): https://auth0.com/signup

2. **Create Application**:
   ```
   Dashboard → Applications → Create Application
   Name: "FluidMCP"
   Type: Regular Web Applications
   ```

3. **Configure URLs**:
   - Copy the URLs from Step 1
   - Paste into Auth0 application settings:
     - Allowed Callback URLs
     - Allowed Logout URLs
     - Allowed Web Origins
   - Save Changes

4. **Enable Social Login** (optional):
   ```
   Dashboard → Authentication → Social
   Enable: GitHub, Google, etc.
   Link to your application
   ```

5. **Copy Credentials**:
   - Domain (e.g., `your-tenant.us.auth0.com`)
   - Client ID
   - Client Secret

#### Step 3: Set Environment Variables

```bash
# Required: Auth0 credentials
export AUTH0_DOMAIN="your-tenant.us.auth0.com"
export AUTH0_CLIENT_ID="your_client_id_here"
export AUTH0_CLIENT_SECRET="your_client_secret_here"

# Required: JWT secret (generate secure random secret)
export FMCP_JWT_SECRET=$(openssl rand -base64 32)

# Optional: Override auto-detected URLs
# export AUTH0_CALLBACK_URL="https://custom.domain.com/auth/callback"
# export FMCP_BASE_URL="https://api.yourdomain.com"
```

**Save to .env file** (recommended):
```bash
cat > .env <<EOF
AUTH0_DOMAIN=your-tenant.us.auth0.com
AUTH0_CLIENT_ID=your_client_id_here
AUTH0_CLIENT_SECRET=your_client_secret_here
FMCP_JWT_SECRET=$(openssl rand -base64 32)
EOF

# Load environment
source .env
```

#### Step 4: Run with OAuth

```bash
# Run with OAuth enabled
fluidmcp run examples/sample-config.json --file --start-server --auth0
```

**Output:**
```
🔐 Auth0 OAuth authentication enabled
   Supported providers: GitHub, Google, Zoho, Atlassian, Confluence

======================================================================
🔐 Auth0 OAuth Configuration
======================================================================
[URLs displayed here]
======================================================================

Launching servers...
Successfully launched 2 MCP server(s)

======================================================================
🚀 FluidMCP Server Starting
======================================================================
🔐 Auth0 OAuth: ENABLED
   Login at: https://workspace-8099.app.github.dev/
   Swagger UI: https://workspace-8099.app.github.dev/docs
======================================================================

Server running on https://workspace-8099.app.github.dev
```

#### Step 5: Access and Test

1. **Open Login URL** in browser:
   ```
   https://workspace-8099.app.github.dev/
   ```

2. **Sign in**:
   - Click "Sign in with Auth0"
   - Choose provider (GitHub, Google, etc.)
   - Authorize application

3. **Access Swagger UI**:
   ```
   https://workspace-8099.app.github.dev/docs
   ```

4. **Test API** (with authentication):
   ```bash
   # Get your JWT token from browser (after login)
   curl -X POST https://workspace-8099.app.github.dev/filesystem/mcp \
     -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
   ```

---

## Running in Different Environments

### Local Development

```bash
# Basic (no auth)
fluidmcp run examples/sample-config.json --file --start-server

# With OAuth
fluidmcp run examples/sample-config.json --file --start-server --auth0

# Access at: http://localhost:8099
```

### GitHub Codespaces

```bash
# URLs are auto-detected!
fluidmcp run examples/sample-config.json --file --start-server --auth0

# ✅ Automatically uses: https://codespace-8099.app.github.dev
```

**Important**: Make sure port 8099 is set to **Public**:
```
1. Cmd/Ctrl + Shift + P
2. Type "Ports: Focus on Ports View"
3. Right-click port 8099
4. Change Port Visibility → Public
```

### Gitpod

```bash
# URLs are auto-detected!
fluidmcp run examples/sample-config.json --file --start-server --auth0

# ✅ Automatically uses: https://8099-workspace-url
```

### Custom Domain (Production)

```bash
# Set custom base URL
export FMCP_BASE_URL="https://api.yourdomain.com"

# Run with OAuth
fluidmcp run all --start-server --auth0

# ✅ Uses your custom domain
```

---

## Docker Deployment

### Option 1: Docker Run

```bash
# Build image
docker build -t fluidmcp .

# Run without OAuth
docker run -p 8099:8099 fluidmcp

# Run with OAuth
docker run -p 8099:8099 \
  -e AUTH0_DOMAIN="your-tenant.us.auth0.com" \
  -e AUTH0_CLIENT_ID="your_client_id" \
  -e AUTH0_CLIENT_SECRET="your_client_secret" \
  -e FMCP_JWT_SECRET="your_jwt_secret" \
  -e FMCP_BASE_URL="https://api.yourdomain.com" \
  fluidmcp
```

### Option 2: Docker Compose

**Create docker-compose.yml:**
```yaml
version: '3.8'

services:
  fluidmcp:
    build: .
    ports:
      - "8099:8099"
    environment:
      - FMCP_BASE_URL=https://api.yourdomain.com
      - AUTH0_DOMAIN=${AUTH0_DOMAIN}
      - AUTH0_CLIENT_ID=${AUTH0_CLIENT_ID}
      - AUTH0_CLIENT_SECRET=${AUTH0_CLIENT_SECRET}
      - FMCP_JWT_SECRET=${FMCP_JWT_SECRET}
    env_file:
      - .env
    restart: unless-stopped
```

**Run:**
```bash
# Start
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Option 3: Create Custom Dockerfile

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy application
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install -e .

# Expose port
EXPOSE 8099

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8099/docs || exit 1

# Run server
CMD ["fluidmcp", "run", "all", "--start-server", "--auth0"]
```

**Build and run:**
```bash
docker build -t fluidmcp:latest .
docker run -p 8099:8099 --env-file .env fluidmcp:latest
```

---

## Production Deployment

### Option 1: Systemd Service (Linux)

**Create service file** `/etc/systemd/system/fluidmcp.service`:
```ini
[Unit]
Description=FluidMCP Server
After=network.target

[Service]
Type=simple
User=fluidmcp
WorkingDirectory=/opt/fluidmcp
EnvironmentFile=/opt/fluidmcp/.env
ExecStart=/opt/fluidmcp/venv/bin/fluidmcp run all --start-server --auth0
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable fluidmcp
sudo systemctl start fluidmcp
sudo systemctl status fluidmcp
```

### Option 2: Nginx Reverse Proxy

**Install Nginx:**
```bash
sudo apt update
sudo apt install nginx certbot python3-certbot-nginx
```

**Configure Nginx** `/etc/nginx/sites-available/fluidmcp`:
```nginx
server {
    listen 80;
    server_name api.yourdomain.com;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    # SSL certificates (from Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    # Proxy to FluidMCP
    location / {
        proxy_pass http://localhost:8099;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

**Enable and test:**
```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/fluidmcp /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Get SSL certificate
sudo certbot --nginx -d api.yourdomain.com

# Reload Nginx
sudo systemctl reload nginx
```

### Option 3: Kubernetes

**Create deployment** `kubernetes/deployment.yaml`:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: fluidmcp-secrets
type: Opaque
stringData:
  AUTH0_DOMAIN: "your-tenant.us.auth0.com"
  AUTH0_CLIENT_ID: "your_client_id"
  AUTH0_CLIENT_SECRET: "your_client_secret"
  FMCP_JWT_SECRET: "your_jwt_secret"

---

apiVersion: apps/v1
kind: Deployment
metadata:
  name: fluidmcp
  labels:
    app: fluidmcp
spec:
  replicas: 3
  selector:
    matchLabels:
      app: fluidmcp
  template:
    metadata:
      labels:
        app: fluidmcp
    spec:
      containers:
      - name: fluidmcp
        image: fluidmcp:latest
        ports:
        - containerPort: 8099
        env:
        - name: FMCP_BASE_URL
          value: "https://api.yourdomain.com"
        envFrom:
        - secretRef:
            name: fluidmcp-secrets
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /docs
            port: 8099
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /docs
            port: 8099
          initialDelaySeconds: 5
          periodSeconds: 10

---

apiVersion: v1
kind: Service
metadata:
  name: fluidmcp-service
spec:
  selector:
    app: fluidmcp
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8099
  type: LoadBalancer
```

**Deploy:**
```bash
# Create secret
kubectl apply -f kubernetes/deployment.yaml

# Check status
kubectl get pods
kubectl get services

# View logs
kubectl logs -f deployment/fluidmcp
```

---

## Common Issues

### Issue 1: Port Already in Use

**Problem:**
```
Error: Port 8099 is already in use
```

**Solutions:**
```bash
# Option 1: Use force reload
fluidmcp run all --start-server --force-reload

# Option 2: Kill process manually
lsof -ti:8099 | xargs kill -9

# Option 3: Use different port
export MCP_CLIENT_SERVER_ALL_PORT=8100
fluidmcp run all --start-server
```

### Issue 2: Auth0 Configuration Missing

**Problem:**
```
⚠️  Auth0 configuration incomplete!
Missing required environment variables:
  - AUTH0_DOMAIN
  - AUTH0_CLIENT_ID
```

**Solution:**
```bash
# Set required environment variables
export AUTH0_DOMAIN="your-tenant.us.auth0.com"
export AUTH0_CLIENT_ID="your_client_id"
export AUTH0_CLIENT_SECRET="your_client_secret"
export FMCP_JWT_SECRET=$(openssl rand -base64 32)

# Run again
fluidmcp run all --start-server --auth0
```

### Issue 3: Port Not Accessible (Codespaces)

**Problem:**
External users can't access the server

**Solution:**
```
1. Open Ports panel (Cmd/Ctrl + Shift + P)
2. Search "Ports: Focus on Ports View"
3. Right-click port 8099
4. Change Port Visibility → Public
```

### Issue 4: Callback URL Mismatch

**Problem:**
```
Auth0 error: callback URL mismatch
```

**Solution:**
```bash
# Get correct URL
python print-auth0-urls.py

# Copy exact URL to Auth0 application settings
# Restart server
fluidmcp run all --start-server --auth0
```

### Issue 5: MCP Server Initialization Failed

**Problem:**
```
Warning: Failed to initialize MCP server for filesystem
```

**Solution:**
```bash
# Check if npm/npx is installed
which npx

# Install Node.js if missing
# Ubuntu/Debian:
sudo apt install nodejs npm

# macOS:
brew install node

# Test MCP server manually
npx -y @modelcontextprotocol/server-filesystem /tmp/test-directory
```

---

## Environment Variables Reference

### Core Settings

```bash
# Port configuration
MCP_CLIENT_SERVER_PORT=8090          # Single package server port
MCP_CLIENT_SERVER_ALL_PORT=8099      # All packages server port
```

### OAuth Settings

```bash
# Required
AUTH0_DOMAIN="your-tenant.us.auth0.com"
AUTH0_CLIENT_ID="your_client_id"
AUTH0_CLIENT_SECRET="your_client_secret"
FMCP_JWT_SECRET="your_jwt_secret"

# Optional
AUTH0_CALLBACK_URL="https://custom.com/auth/callback"
AUTH0_AUDIENCE="https://your-api"
FMCP_BASE_URL="https://api.custom.com"
FMCP_ALLOWED_ORIGINS="https://app1.com,https://app2.com"
```

### Registry Settings

```bash
MCP_FETCH_URL="https://registry.fluidmcp.com/fetch-mcp-package"
MCP_TOKEN="your_registry_token"
```

### GitHub Settings

```bash
FMCP_GITHUB_TOKEN="your_github_token"
GITHUB_TOKEN="alternative_token"
```

### S3 Settings

```bash
S3_BUCKET_NAME="your-bucket"
S3_ACCESS_KEY="your-access-key"
S3_SECRET_KEY="your-secret-key"
S3_REGION="us-east-1"
```

---

## Quick Command Reference

```bash
# Basic commands
fluidmcp --help                                     # Show help
fluidmcp --version                                  # Show version
fluidmcp list                                       # List installed packages

# Run commands
fluidmcp run all --start-server                     # Run all (no auth)
fluidmcp run all --start-server --auth0             # Run all (with OAuth)
fluidmcp run config.json --file --start-server      # Run from file
fluidmcp run config.json --file --start-server --auth0  # Run from file (with OAuth)

# Install commands
fluidmcp install author/package@version             # Install package
fluidmcp install author/package@version --master    # Install in master mode

# GitHub commands
fluidmcp github owner/repo --start-server           # Run from GitHub
fluidmcp github owner/repo --branch dev --start-server  # Run specific branch

# Utility commands
python print-auth0-urls.py                          # Get OAuth URLs
python test-dynamic-oauth.py                        # Run tests
```

---

## Additional Resources

- **Full OAuth Guide**: [OAUTH_AUTHENTICATION_GUIDE.md](OAUTH_AUTHENTICATION_GUIDE.md)
- **Quick Setup**: [OAUTH_SETUP_QUICK_START.md](OAUTH_SETUP_QUICK_START.md)
- **Sharing Guide**: [SETUP_INSTRUCTIONS_FOR_SHARING.md](SETUP_INSTRUCTIONS_FOR_SHARING.md)
- **Project Docs**: [CLAUDE.md](CLAUDE.md)

---

## Need Help?

- **Check Examples**: See `examples/` directory
- **Run Tests**: `python test-dynamic-oauth.py`
- **View Logs**: Check terminal output for errors
- **Documentation**: Read the guides linked above

---

**Last Updated**: December 31, 2025
**Version**: 2.0.0
