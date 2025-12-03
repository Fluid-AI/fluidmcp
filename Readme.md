# FluidMCP — Gateway OAuth (PKCE) Authentication

**FluidMCP** now supports a completely stateless, authentication flow hosted directly by the API Gateway. This architecture removes the need for CLI-based pre-authentication and allows clients (users, scripts, or LLMs) to authenticate with specific MCP packages dynamically.

-----

## 🏗 Architecture Overview

Instead of authenticating via the CLI before running a server, the Gateway (running on port `8099`) automatically generates authentication endpoints for any package that requires them.

### The Flow

1.  **Start Server**: You run `fluidmcp run <package> --start-server`.
2.  **Endpoint Creation**: The Gateway detects the `auth` configuration in the package's `metadata.json` and creates `/auth/login` and `/auth/callback` endpoints.
3.  **Login**: The client visits `http://localhost:8099/<package>/auth/login`.
4.  **OAuth Flow**: The user authenticates with the provider (Google, Jira) via the browser.
5.  **Token Delivery**: The Gateway exchanges the code for an access token and returns it to the client as JSON.
6.  **Authenticated Requests**: The client includes the token in the `Authorization` header for subsequent requests.

-----

## ⚙️ Configuration

To enable On-Demand OAuth for a package, you must configure the `metadata.json` file and set the necessary environment variables.

### 1\. `metadata.json` Setup

Add an `auth` block to your package configuration.

```json
{
  "mcpServers": {
    "gmail-mock": {
      "command": "node",
      "args": ["dist/index.js"],
      "auth": {
        "type": "oauth2",
        "flow": "pkce",
        "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        "client_id_env": "GOOGLE_CLIENT_ID",
        "client_secret_env": "GOOGLE_CLIENT_SECRET",
        "env_var_name": "GMAIL_ACCESS_TOKEN"
      }
    }
  }
}
```

### 2\. Environment Variables

You must set the client ID (and secret, if required) in your shell before running FluidMCP. These must match the keys defined in `client_id_env` above.

```bash
export GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"
export GOOGLE_CLIENT_SECRET="your-client-secret" # If required
```

-----

## 🚀 Usage Guide

### 1\. Start the Server

Run the package normally. No pre-authentication command (`fluidmcp auth`) is required.

```bash
fluidmcp run test/gmail-mock@1.0.0 --start-server
```

*Output:*

```text
Reading metadata.json...
Added gmail-mock endpoints with OAuth support
  Login: http://localhost:8099/gmail-mock/auth/login
Starting FastAPI server on port 8099
```

### 2\. Authenticate

Open the login URL in your browser or trigger it programmatically:
**URL:** `http://localhost:8099/<package-name>/auth/login`

After logging in with the provider, you will receive a JSON response containing your token:

```json
{
  "success": true,
  "package": "gmail-mock",
  "token_data": {
    "access_token": "ya29.a0AfH6SMB...",
    "refresh_token": "1//0gW...",
    "expires_in": 3600,
    "token_type": "Bearer",
    "scope": "https://www.googleapis.com/auth/gmail.readonly"
  },
  "message": "Authentication successful! Use the access_token in Authorization header."
}
```

### 3\. Make Authenticated Requests

Use the `access_token` from the previous step in the `Authorization` header.

**cURL Example:**

```bash
curl -X POST http://localhost:8099/gmail-mock/mcp \
  -H "Authorization: Bearer ya29.a0AfH6SMB..." \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list"
  }'
```

**Python Example:**

```python
import requests

token = "ya29.a0AfH6SMB..." # Token received from auth flow

response = requests.post(
    "http://localhost:8099/gmail-mock/mcp",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list"
    }
)
print(response.json())
```

-----

## 📡 API Reference

When a package is configured with OAuth, the following endpoints are dynamically mounted at `http://localhost:8099`:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| **GET** | `/{package}/auth/login` | Initiates the PKCE flow. Redirects to the OAuth provider. |
| **GET** | `/{package}/auth/callback` | Handles the OAuth callback. Exchanges code for token. Returns JSON. |
| **POST** | `/{package}/mcp` | The standard JSON-RPC proxy. Accepts `Authorization: Bearer <token>`. |
| **POST** | `/{package}/sse` | Server-Sent Events stream. Accepts `Authorization: Bearer <token>`. |

-----

## 🔒 Security Features

1.  **Stateless Architecture**: Tokens are returned to the client and never stored persistently on the FluidMCP server.
2.  **PKCE (RFC 7636)**: Uses Proof Key for Code Exchange to secure the authorization code flow, preventing interception attacks.
3.  **State Parameter**: A unique, random `state` string is generated for every login attempt to prevent CSRF attacks.
4.  **Memory-Only Verification**: The PKCE verifier is stored in memory (`pending_auth_states`) only for the duration of the redirect flow and is cleared immediately upon callback.

-----

## ❓ Troubleshooting

**"client\_id not found"**

  * Ensure you have exported the environment variable referenced in `client_id_env` in your `metadata.json`.
  * Example: `export GOOGLE_CLIENT_ID="xxx"`

**"Invalid or expired state parameter"**

  * The login flow allows only one callback per attempt. If you refresh the callback page or wait too long (process restart), the state is lost.
  * **Fix:** Go back to `/{package}/auth/login` to start a new flow.

**Authentication is not persisting**

  * This is by design. The server does not store tokens. The client (you or your application) must hold the token and send it with every request.

**"Package does not require OAuth authentication"**

  * Check your `metadata.json`. It must contain a valid `auth` object inside the server configuration.



  ## 📸 Demos & Screenshots

### FluidMCP Usage Demos

<div align="center">
  <h4>Demo 1: Gateway Authentication Flow</h4>
  <video width="100%" autoplay loop muted playsinline>
    <source src="./Images/20251201-0840-16.8228187.mp4" type="video/mp4">
    Your browser does not support the video tag.
  </video>
  
  <br/><br/>

  <h4>Demo 2: MCP Server Management</h4>
  <video width="100%" autoplay loop muted playsinline>
    <source src="./Images/20251128-1604-47.7338821.mp4" type="video/mp4">
    Your browser does not support the video tag.
  </video>
</div>

---

### 🖼️ Interface Screenshots

<div align="center">
  <img src="./Images/image (1).png" alt="FluidMCP Interface Main" width="800" />
  <br/><br/>
  <img src="./Images/image (1) (1).png" alt="FluidMCP Interface Details" width="800" />
</div>