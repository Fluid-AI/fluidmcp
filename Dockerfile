FROM python:3.10-slim

ARG NODE_VERSION=20
ARG NPM_VERSION=11.4.0

WORKDIR /app

# Install system dependencies (git for GitHub repos, curl for Node.js)
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20 and npm 11 (intentional pairing from current Dockerfile)
# Node 20 is LTS, npm 11 provides improved performance and security fixes
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g npm@${NPM_VERSION} \
    && npm cache clean --force

# NOTE: Removed ajv, supergateway, yargs global installs
# These are only needed for legacy run-mode (supergateway is FastAPI proxy wrapper)
# fmcp serve uses native FastAPI - no external proxy needed
# npx will fetch packages on-demand when MCP servers are started

# Install Python dependencies (includes motor/pymongo for MongoDB)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Install FluidMCP in production mode (NOT editable)
# Production containers don't need -e (editable mode is for development)
RUN pip install --no-cache-dir .

# Build frontend (React + Vite)
# Frontend is served by FastAPI backend at /ui path
WORKDIR /app/fluidmcp/frontend
RUN npm install && npm run build

# Copy built dist INTO package directory BEFORE pip install
# This ensures the frontend dist is included in the installed Python package
RUN mkdir -p /app/fluidmcp/cli/frontend && \
    cp -r /app/fluidmcp/frontend/dist /app/fluidmcp/cli/frontend/

# Return to app root
WORKDIR /app

# Create token directory with secure permissions
# NOTE: For Railway production, set FMCP_BEARER_TOKEN env var instead
# Relying on auto-generated token causes regeneration on every container restart
RUN mkdir -p /app/.fmcp/tokens && chmod 700 /app/.fmcp

# Environment defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/app \
    FMCP_HOME=/app/.fmcp \
    PORT=8099

# Health check for Railway monitoring
# Start period: 40s (allows MongoDB connection retry: 2s + 4s + 8s + startup time)
# CRITICAL: Use ${PORT} env var, not hardcoded 8099 (Railway assigns PORT dynamically)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Expose port (informational only - Railway binds to $PORT env var)
# Docker EXPOSE does not resolve env vars at build time
EXPOSE 8099

# Production command with secure mode
# ⚠️  CRITICAL: Set FMCP_BEARER_TOKEN in Railway dashboard to prevent token regeneration
# ⚠️  CRITICAL: Set MONGODB_URI in Railway (provided by MongoDB service)
# --require-persistence: Fail fast if MongoDB unavailable (no silent in-memory fallback)
CMD fmcp serve \
    --host 0.0.0.0 \
    --port ${PORT} \
    --secure \
    --mongodb-uri ${MONGODB_URI} \
    --database ${FMCP_DATABASE:-fluidmcp} \
    --require-persistence
