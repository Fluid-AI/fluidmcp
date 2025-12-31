# FluidMCP Quick Start - Airbnb Package

Run the Airbnb package with FluidMCP in under 5 minutes!

---

## 📋 Prerequisites

- Python 3.11+
- Node.js and npm
- Git

---

## 🚀 Installation

```bash
git clone https://github.com/Fluid-AI/fluidmcp.git
cd fluidmcp
pip install -r requirements.txt
pip install -e .
fluidmcp --version
```

---

## 🏠 Run Airbnb

### Option 1: Quick Test (No Auth)

```bash
fluidmcp install Airbnb/airbnb@0.1.0
fluidmcp run Airbnb/airbnb@0.1.0 --start-server
```

Access: http://localhost:8099/docs

---

### Option 2: With OAuth (Recommended)

#### 1. Setup Auth0

- Create account: https://auth0.com/signup
- Create Application: Dashboard → Applications → Create Application
- Type: "Regular Web Applications"

#### 2. Configure URLs

Get your URLs:
```bash
python print-auth0-urls.py
```

**GitHub Codespaces:**
```
Allowed Callback URLs:
https://*.app.github.dev/auth/callback,http://localhost:8099/auth/callback

Allowed Logout URLs:
https://*.app.github.dev/,http://localhost:8099/

Allowed Web Origins:
https://*.app.github.dev,http://localhost:8099
```

**Local:**
```
Allowed Callback URLs:
http://localhost:8099/auth/callback

Allowed Logout URLs:
http://localhost:8099/

Allowed Web Origins:
http://localhost:8099
```

#### 3. Set Credentials

```bash
export AUTH0_DOMAIN="your-tenant.us.auth0.com"
export AUTH0_CLIENT_ID="your_client_id"
export AUTH0_CLIENT_SECRET="your_client_secret"
export FMCP_JWT_SECRET=$(openssl rand -base64 32)
```

#### 4. Run Airbnb with OAuth

```bash
fluidmcp install Airbnb/airbnb@0.1.0
fluidmcp run Airbnb/airbnb@0.1.0 --start-server --auth0
```

#### 5. Access

Open the URL shown in terminal → Sign in → Access /docs

---

## 🌐 GitHub Codespaces

### Make Port Public

1. Press `Cmd/Ctrl + Shift + P`
2. Type "Ports: Focus on Ports View"
3. Right-click port 8099 → Change Port Visibility → **Public**

### Run

```bash
fluidmcp run Airbnb/airbnb@0.1.0 --start-server --auth0
```

---

## 🧪 Test

### Without Auth
```bash
fluidmcp run Airbnb/airbnb@0.1.0 --start-server
curl -X POST http://localhost:8099/airbnb/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

### With OAuth
```bash
fluidmcp run Airbnb/airbnb@0.1.0 --start-server --auth0
# Login via browser, then test with JWT token
```

---

## 🔒 Protected Endpoints

All endpoints require authentication with `--auth0`:

- `/` - Login page
- `/docs` - Swagger UI
- `/airbnb/mcp` - JSON-RPC proxy
- `/airbnb/mcp/tools/list` - List tools
- `/airbnb/mcp/tools/call` - Call tools

---

## 🐛 Troubleshooting

### Port in use
```bash
fluidmcp run Airbnb/airbnb@0.1.0 --start-server --force-reload
```

### Missing credentials
```bash
echo $AUTH0_DOMAIN $AUTH0_CLIENT_ID $AUTH0_CLIENT_SECRET $FMCP_JWT_SECRET
```

### Callback mismatch
```bash
python print-auth0-urls.py
```

---

## 📚 Documentation

- [Full Docs](docs/INDEX.md)
- [OAuth Setup](docs/OAUTH_SETUP_QUICK_START.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

---
