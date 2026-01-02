# Auth0 Wildcard Configuration for Dynamic URLs

## 🎯 Problem

Codespace URLs change every time you restart, requiring manual Auth0 updates. This is not scalable.

## ✅ Solution

Use **Auth0 wildcard URLs** to support all your Codespace instances automatically.

---

## 📋 One-Time Setup (Works Forever)

### Step 1: Configure Auth0 with Wildcards

Go to your Auth0 application settings and use these **wildcard patterns**:

#### Allowed Callback URLs:
```
https://*.app.github.dev/auth/callback,
http://localhost:*/auth/callback
```

#### Allowed Logout URLs:
```
https://*.app.github.dev/,
http://localhost:*/
```

#### Allowed Web Origins:
```
https://*.app.github.dev,
http://localhost:*
```

**What this does:**
- `*.app.github.dev` matches ANY Codespace URL
- `localhost:*` works for local development
- You'll NEVER need to update Auth0 again for Codespaces! 🎉

---

## 🚀 That's It!

Now you can:

```bash
# Just run the server - it will work in ANY Codespace!
fluidmcp run examples/sample-config.json --file --start-server --auth0
```

**No matter what your Codespace URL is, Auth0 will accept it!**

---

## 🔒 Security Notes

### Is Wildcard Secure?

**Yes, for Codespaces:**
- GitHub Codespaces URLs are unique per instance
- They're not guessable (long random strings)
- They require GitHub authentication to access
- The wildcard only matches `*.app.github.dev` domain

### For Production

For production, you should use **specific URLs**:

```bash
# Set a specific production URL
export FMCP_BASE_URL="https://api.yourdomain.com"

# Then in Auth0, use:
# Allowed Callback URLs: https://api.yourdomain.com/auth/callback
```

---

## 🎓 How It Works

```
User tries to login
    ↓
FluidMCP detects Codespace URL:
  https://effective-journey-xxxx-8099.app.github.dev
    ↓
Redirects to Auth0 with that URL as callback
    ↓
Auth0 checks: Does it match *.app.github.dev? ✅ YES
    ↓
Auth0 allows the callback
    ↓
User is authenticated! 🎉
```

---

## 📊 Comparison

### Before (Manual)
```
1. Run server
2. Get URL: effective-journey-xxxx-8099.app.github.dev
3. Go to Auth0 Dashboard
4. Update callback URLs
5. Save
6. Restart server
7. Test
⏱️  Time: 5-10 minutes per Codespace
```

### After (Wildcard)
```
1. Configure Auth0 once with wildcards
2. Run server (any Codespace, any time)
3. It just works! ✅
⏱️  Time: 0 minutes (one-time setup)
```

---

## 🛠️ Alternative: Custom Domain (Best for Production)

For a permanent solution that doesn't require wildcards:

### Option 1: Use GitHub Codespaces Port Forwarding with Custom Domain

```bash
# Set up a custom domain that forwards to your Codespace
# (This is advanced - see GitHub docs)
export FMCP_BASE_URL="https://api.yourdomain.com"
```

### Option 2: Use ngrok or Similar Tunneling

```bash
# Install ngrok
# Sign up at https://ngrok.com

# Create tunnel
ngrok http 8099

# Get stable URL: https://your-subdomain.ngrok.io
export FMCP_BASE_URL="https://your-subdomain.ngrok.io"
```

Then in Auth0, use your stable URL:
```
Allowed Callback URLs: https://your-subdomain.ngrok.io/auth/callback
```

---

## 📝 Summary

**For Development (Codespaces):**
- ✅ Use wildcards: `https://*.app.github.dev/auth/callback`
- ✅ Works forever, no updates needed
- ✅ Secure (GitHub authentication required)

**For Production:**
- ✅ Use specific domain: `https://api.yourdomain.com/auth/callback`
- ✅ More secure
- ✅ No wildcards needed

**For Testing/Demos:**
- ✅ Use ngrok or similar for stable URL
- ✅ Share one URL with everyone
- ✅ No Auth0 updates when restarting

---

## ✨ Quick Setup Commands

```bash
# 1. Configure Auth0 (one time)
# Go to: https://manage.auth0.com
# Add wildcard URLs (see above)

# 2. Run server (any time, any Codespace)
export AUTH0_DOMAIN="your-tenant.us.auth0.com"
export AUTH0_CLIENT_ID="your_client_id"
export AUTH0_CLIENT_SECRET="your_client_secret"
export FMCP_JWT_SECRET=$(openssl rand -base64 32)

fluidmcp run examples/sample-config.json --file --start-server --auth0

# 3. Access and test - it just works! ✅
```

---

**That's it! Set up the wildcards once, and never worry about Codespace URLs again!** 🎉
