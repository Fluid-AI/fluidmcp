# Auth0 Configuration File Guide

## Overview

FluidMCP now supports loading Auth0 credentials from a configuration file! No more setting environment variables every time you start the server.

## Quick Start

### Option 1: Interactive Setup (Easiest) 🎯

Run the interactive setup script:

```bash
python setup-auth0-config.py
```

The script will:
- ✅ Prompt you for your Auth0 credentials
- ✅ Auto-detect Codespaces URL (if applicable)
- ✅ Generate a secure JWT secret
- ✅ Save everything to `auth0-config.json`
- ✅ Set file permissions to 600 (owner only)
- ✅ Add the file to `.gitignore`
- ✅ Show you what to configure in Auth0 Dashboard

### Option 2: Manual Setup

1. **Copy the template:**
   ```bash
   cp auth0-config.example.json auth0-config.json
   ```

2. **Edit the file:**
   ```bash
   nano auth0-config.json
   ```

3. **Fill in your credentials:**
   ```json
   {
     "domain": "dev-4anz4n3tvh3iyixx.us.auth0.com",
     "client_id": "k80RDWadsrIXntnv7kbai1i3aL6ZgHRe",
     "client_secret": "YOUR_CLIENT_SECRET",
     "callback_url": "https://your-url.app.github.dev/auth/callback",
     "jwt_secret": "generate-with-openssl-rand-base64-32",
     "jwt_expiration_minutes": 30
   }
   ```

4. **Start the server:**
   ```bash
   fluidmcp run all --start-server --auth0
   ```

## Configuration File Format

### Required Fields

```json
{
  "domain": "your-tenant.us.auth0.com",
  "client_id": "YOUR_CLIENT_ID",
  "client_secret": "YOUR_CLIENT_SECRET",
  "callback_url": "http://localhost:8099/auth/callback",
  "jwt_secret": "YOUR_JWT_SECRET"
}
```

### Optional Fields

```json
{
  "audience": "https://your-api-identifier",
  "jwt_algorithm": "HS256",
  "jwt_expiration_minutes": 30
}
```

### Field Descriptions

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `domain` | ✅ Yes | Auth0 tenant domain | `dev-xxxxx.us.auth0.com` |
| `client_id` | ✅ Yes | Auth0 application client ID | `abc123...` |
| `client_secret` | ✅ Yes | Auth0 application client secret | `secret123...` |
| `callback_url` | ✅ Yes | OAuth callback URL | `http://localhost:8099/auth/callback` |
| `jwt_secret` | ✅ Yes | Secret for signing JWT tokens | Generate with `openssl rand -base64 32` |
| `audience` | ❌ No | Auth0 API identifier (optional) | `https://your-api` |
| `jwt_algorithm` | ❌ No | JWT signing algorithm (default: HS256) | `HS256` |
| `jwt_expiration_minutes` | ❌ No | JWT token lifetime in minutes (default: 30) | `30` |

## Configuration Priority

FluidMCP loads configuration in this order (highest to lowest priority):

1. **Environment Variables** (highest priority)
   - `AUTH0_DOMAIN`
   - `AUTH0_CLIENT_ID`
   - `AUTH0_CLIENT_SECRET`
   - `AUTH0_CALLBACK_URL`
   - `FMCP_JWT_SECRET`

2. **Configuration File** (medium priority)
   - `./auth0-config.json`

3. **Default Values** (lowest priority)
   - callback_url: `http://localhost:8099/auth/callback`
   - jwt_algorithm: `HS256`
   - jwt_expiration_minutes: `30`

### Example: Override Callback URL

If you have `auth0-config.json` but want to temporarily use a different callback URL:

```bash
export AUTH0_CALLBACK_URL=https://different-url.com/auth/callback
fluidmcp run all --start-server --auth0
```

The environment variable will take precedence over the file config.

## Usage

### Start Server with Config File

Just start the server with the `--auth0` flag:

```bash
fluidmcp run all --start-server --auth0
```

FluidMCP will automatically:
1. Look for `auth0-config.json` in current directory
2. Load credentials from the file
3. Apply any environment variable overrides
4. Start with Auth0 authentication enabled

### No Environment Variables Needed!

Before (with environment variables):
```bash
export AUTH0_DOMAIN=dev-4anz4n3tvh3iyixx.us.auth0.com
export AUTH0_CLIENT_ID=k80RDWadsrIXntnv7kbai1i3aL6ZgHRe
export AUTH0_CLIENT_SECRET=TGIB02bymxvstSX-XWjTMp2WJd-uw1WFEWjyJDPFCMfsiwzITDYP11OLTdgzwaF-
export AUTH0_CALLBACK_URL=https://...
export FMCP_JWT_SECRET=$(openssl rand -base64 32)

fluidmcp run all --start-server --auth0
```

After (with config file):
```bash
fluidmcp run all --start-server --auth0
```

That's it! 🎉

## Security Best Practices

### 1. File Permissions

The setup script automatically sets file permissions to 600 (owner read/write only):

```bash
chmod 600 auth0-config.json
```

Verify permissions:
```bash
ls -la auth0-config.json
# Should show: -rw------- (owner read/write only)
```

### 2. Git Ignore

The config file is automatically added to `.gitignore` to prevent accidentally committing secrets:

```gitignore
# Auth0 configuration (contains secrets)
auth0-config.json
auth0-config-*.json
```

### 3. Never Commit Secrets

**❌ NEVER do this:**
```bash
git add auth0-config.json
git commit -m "Add Auth0 config"
```

**✅ Always check before committing:**
```bash
git status
# auth0-config.json should NOT appear in the list
```

### 4. Backup Safely

If you need to backup your config:
- Store in a password manager (1Password, LastPass, etc.)
- Use encrypted storage (encrypted USB drive, encrypted cloud storage)
- Never email or share via unencrypted channels

### 5. Rotate Secrets Regularly

Periodically rotate your Auth0 Client Secret:
1. Generate new secret in Auth0 Dashboard
2. Update `auth0-config.json`
3. Restart FluidMCP
4. Delete old secret from Auth0

## Troubleshooting

### Error: "Config file not found"

**Problem:** FluidMCP can't find `auth0-config.json`

**Solution:**
1. Make sure you're in the right directory:
   ```bash
   pwd  # Should be /workspaces/fluidmcp or your project root
   ```

2. Check if file exists:
   ```bash
   ls -la auth0-config.json
   ```

3. Run the setup script to create it:
   ```bash
   python setup-auth0-config.py
   ```

### Error: "Invalid JSON in config file"

**Problem:** The JSON format is incorrect

**Solution:**
1. Validate your JSON:
   ```bash
   python -m json.tool auth0-config.json
   ```

2. Common JSON mistakes:
   - Missing commas between fields
   - Extra comma after last field
   - Missing quotes around strings
   - Unclosed brackets or braces

3. Copy from template:
   ```bash
   cp auth0-config.example.json auth0-config.json
   # Then edit with correct values
   ```

### Error: "Missing required fields"

**Problem:** One or more required fields are missing or empty

**Solution:**
```bash
# Check what's loaded
python3 << 'EOF'
from fluidai_mcp.auth.config import Auth0Config
config = Auth0Config.from_env_or_file()
print(f"Domain: {config.domain}")
print(f"Client ID: {config.client_id}")
print(f"Client Secret: {config.client_secret[:10] if config.client_secret else 'MISSING'}...")
print(f"Callback URL: {config.callback_url}")
print(f"JWT Secret: {config.jwt_secret[:10] if config.jwt_secret else 'MISSING'}...")
EOF
```

Make sure all required fields have values.

### Error: "401 Unauthorized" when logging in

**Problem:** Client secret is incorrect

**Solution:**
1. Get correct secret from Auth0 Dashboard
2. Update `auth0-config.json`:
   ```json
   {
     "client_secret": "CORRECT_SECRET_HERE"
   }
   ```
3. Restart server

### Error: "Callback URL mismatch"

**Problem:** Callback URL in config doesn't match Auth0 Dashboard

**Solution:**
1. Check config file:
   ```bash
   grep callback_url auth0-config.json
   ```

2. Update Auth0 Dashboard:
   - Go to https://manage.auth0.com
   - Applications → Your App → Settings
   - Update "Allowed Callback URLs" to match your config
   - Click "Save Changes"

## Multiple Environments

You can create different config files for different environments:

### Development (localhost)
```json
// auth0-config-dev.json
{
  "domain": "dev-xxxxx.us.auth0.com",
  "client_id": "...",
  "client_secret": "...",
  "callback_url": "http://localhost:8099/auth/callback",
  "jwt_secret": "..."
}
```

### Codespaces
```json
// auth0-config-codespaces.json
{
  "domain": "dev-xxxxx.us.auth0.com",
  "client_id": "...",
  "client_secret": "...",
  "callback_url": "https://your-codespace.app.github.dev/auth/callback",
  "jwt_secret": "..."
}
```

### Production
```json
// auth0-config-prod.json
{
  "domain": "prod-xxxxx.us.auth0.com",
  "client_id": "...",
  "client_secret": "...",
  "callback_url": "https://yourdomain.com/auth/callback",
  "jwt_secret": "..."
}
```

### Usage
```bash
# Copy the config for your environment
cp auth0-config-dev.json auth0-config.json

# Or use environment-specific config directly
# (future enhancement - not yet implemented)
fluidmcp run all --start-server --auth0 --auth0-config auth0-config-prod.json
```

## Advanced: Programmatic Access

You can load the config in your own Python scripts:

```python
from fluidai_mcp.auth.config import Auth0Config

# Load from default location
config = Auth0Config.from_env_or_file()

# Load from specific file
config = Auth0Config.from_file('path/to/auth0-config.json')

# Load with env override
config = Auth0Config.from_env_or_file('custom-config.json')

# Validate
try:
    config.validate_required()
    print("Config is valid!")
except ValueError as e:
    print(f"Config error: {e}")
```

## Migration from Environment Variables

If you've been using environment variables, here's how to migrate:

1. **Check current env vars:**
   ```bash
   echo "Domain: $AUTH0_DOMAIN"
   echo "Client ID: $AUTH0_CLIENT_ID"
   echo "Callback: $AUTH0_CALLBACK_URL"
   ```

2. **Create config file:**
   ```bash
   python setup-auth0-config.py
   # Enter the values from your environment variables
   ```

3. **Test:**
   ```bash
   # Unset env vars to test config file
   unset AUTH0_DOMAIN AUTH0_CLIENT_ID AUTH0_CLIENT_SECRET AUTH0_CALLBACK_URL FMCP_JWT_SECRET

   # Start server - should work with config file
   fluidmcp run all --start-server --auth0
   ```

4. **Clean up:**
   Remove env var exports from your shell profile (`.bashrc`, `.zshrc`, etc.)

## Files Reference

- [auth0-config.json](auth0-config.json) - Your actual config (gitignored, created by you)
- [auth0-config.example.json](auth0-config.example.json) - Template file with placeholders
- [setup-auth0-config.py](setup-auth0-config.py) - Interactive setup script
- [fluidai_mcp/auth/config.py](fluidai_mcp/auth/config.py) - Config loading implementation

## Benefits

✅ **Convenience** - One-time setup, no need to export vars every time
✅ **Persistence** - Config survives terminal sessions
✅ **Flexibility** - Can have multiple configs for different environments
✅ **Backward Compatible** - Environment variables still work
✅ **Security** - File can be gitignored and have restricted permissions
✅ **User-Friendly** - Interactive setup script makes it easy

## Summary

1. Run `python setup-auth0-config.py` to create config file
2. Update Auth0 Dashboard with callback URLs
3. Start server with `fluidmcp run all --start-server --auth0`
4. Done! No more environment variables needed 🎉
