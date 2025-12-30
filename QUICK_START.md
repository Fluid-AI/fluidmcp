# Quick Start - Fix Callback URL Issue

## The Problem
Auth0 is redirecting to `https://localhost:8099` instead of your Codespaces URL.

## The Solution

### Step 1: Update Auth0 Dashboard

Go to https://manage.auth0.com and paste these EXACT URLs:

**Allowed Callback URLs:**
```
https://studious-adventure-5gjvrq9gv4jrhpxqr-8099.app.github.dev/auth/callback
```

**Allowed Logout URLs:**
```
https://studious-adventure-5gjvrq9gv4jrhpxqr-8099.app.github.dev/
```

**Allowed Web Origins:**
```
https://studious-adventure-5gjvrq9gv4jrhpxqr-8099.app.github.dev
```

**IMPORTANT:**
- Click **"Save Changes"** at the bottom
- **Wait 60 seconds** for Auth0 to update

### Step 2: Set Environment Variables

Run these commands in your terminal (all in one go):

```bash
export AUTH0_DOMAIN=dev-4anz4n3tvh3iyixx.us.auth0.com
export AUTH0_CLIENT_ID=k80RDWadsrIXntnv7kbai1i3aL6ZgHRe
export AUTH0_CLIENT_SECRET=YOUR_CLIENT_SECRET_HERE
export AUTH0_CALLBACK_URL=https://studious-adventure-5gjvrq9gv4jrhpxqr-8099.app.github.dev/auth/callback
export FMCP_JWT_SECRET=$(openssl rand -base64 32)
```

Replace `YOUR_CLIENT_SECRET_HERE` with your actual Auth0 Client Secret.

### Step 3: Start Server

```bash
fluidmcp run all --start-server --auth0
```

### Step 4: Test

1. Open: `https://studious-adventure-5gjvrq9gv4jrhpxqr-8099.app.github.dev/`
2. Click **"Continue with Google"** (or any provider)
3. Login with your account
4. You should be redirected back successfully!

## Still Getting Errors?

### Verify Environment Variables:
```bash
echo "Callback URL: $AUTH0_CALLBACK_URL"
```

It should show:
```
Callback URL: https://studious-adventure-5gjvrq9gv4jrhpxqr-8099.app.github.dev/auth/callback
```

### Check Auth0 Configuration:
Make sure you **saved the changes** in Auth0 Dashboard and **waited 60 seconds**.

### Clear Browser Cache:
Try opening in an **incognito/private window**.
