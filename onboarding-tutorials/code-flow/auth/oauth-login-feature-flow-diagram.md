# OAuth Login — Feature Flow Diagram

> End-to-end OAuth2 Authorization Code flow from user clicking "Login" through Auth0 authentication, CSRF validation, token exchange, httpOnly cookie issuance, and final redirect to the dashboard.

## Overview

When a user visits a protected route, `AuthContext.tsx` checks `isAuthenticated` and, if unauthenticated, redirects the browser to `GET /auth/login`. The backend generates a CSRF state token, redirects to Auth0, and after the user authenticates, Auth0 calls back to `GET /auth/callback`. The backend validates the CSRF state, exchanges the authorization code for tokens, fetches the user's profile, and sets a secure httpOnly cookie before redirecting the browser to `/ui`. The frontend then calls `GET /auth/me` to confirm authentication and render the dashboard.

## Feature Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  BROWSER / FRONTEND                                                          │
└─────────────────────────────────────────────────────────────────────────────┘

  [1] TRIGGER: Protected Route Visit
      File : fluidmcp/frontend/src/contexts/AuthContext.tsx
      Fn   : requireAuth(returnUrl?)
      ─────────────────────────────────────────────────────
      ↳ Calls checkAuth() → authService.getConfig()
        → GET /auth/config (returns {enabled, domain, clientId})
      ↳ Calls authService.getCurrentUser() → GET /auth/me
      ↳ isAuthenticated = !!user

      < isAuthenticated? >
      ├── YES ──────────────────────────────────────────────► Dashboard renders
      │                                                        (skip to step 10)
      └── NO
           ↳ sessionStorage.setItem('auth_return_url', fullReturnUrl)
             (prepends /ui/ prefix if missing)
           ↳ authService.login()
             File: fluidmcp/frontend/src/services/auth.ts · login()
             → window.location.href = '/auth/login'

             │
             ▼

  [2] LOGIN ENDPOINT
      File : fluidmcp/cli/auth/routes.py
      Fn   : login(request, connection?)
      GET  : /auth/login
      ─────────────────────────────────────────────────────
      ↳ Guards: if not oauth_client → HTTP 500

      ↳ create_state()
          • state = secrets.token_urlsafe(32)          ← cryptographically random
          • _state_store[state] = datetime.utcnow()    ← stored in-memory dict
          • Prunes entries older than 10 minutes

      ↳ redirect_uri = config.callback_url             ← supports Codespaces/custom domains
      ↳ oauth_client.get_authorization_url(state, redirect_uri, connection?)
          File: fluidmcp/cli/auth/oauth_client.py
          Fn  : get_authorization_url()
          Builds: https://{domain}/authorize?
                    response_type=code
                    &client_id={client_id}
                    &redirect_uri={callback_url}
                    &scope=openid%20profile%20email
                    &state={state}
                    [&audience={audience}]          ← if configured
                    [&connection={connection}]      ← if provider specified

      → Returns RedirectResponse(url=auth_url)

             │
             ▼

  [3] REDIRECT TO AUTH0
      Browser follows redirect to:
      https://{auth0_domain}/authorize?response_type=code&client_id=...&state=...
      ─────────────────────────────────────────────────────
      (Browser leaves the application — Auth0 takes over)

             │
             ▼

  [4] USER AUTHENTICATES AT AUTH0
      Auth0 Universal Login page
      ─────────────────────────────────────────────────────
      User chooses one of:
        • Email + password
        • Social provider (Google, GitHub, etc.)
        • Enterprise SSO (connection= param routes directly)

      Auth0 validates credentials, issues short-lived authorization code.

             │
             ▼

  [5] AUTH0 CALLBACK
      Auth0 redirects browser to:
      GET /auth/callback?code=AUTH_CODE&state=CSRF_TOKEN
      ─────────────────────────────────────────────────────
      (Alternatively: ?error=ERROR_DESCRIPTION if auth failed)

             │
             ▼

┌─────────────────────────────────────────────────────────────────────────────┐
│  BACKEND — fluidmcp/cli/auth/routes.py · callback()                         │
└─────────────────────────────────────────────────────────────────────────────┘

  [5a] ERROR BRANCH
       if request contains ?error=...
       ─────────────────────────────────────────────────────
       ↳ logger.error(f"OAuth callback error: {error}")
       → Returns HTMLResponse with error message + "Try again" link
       (flow ends here for this branch)

  [5b] MISSING PARAMS CHECK
       if not code or not state
       ─────────────────────────────────────────────────────
       → raise HTTPException(status_code=400, detail="Missing code or state parameter")

             │
             ▼

  [6] CSRF STATE VALIDATION
      File : fluidmcp/cli/auth/routes.py
      Fn   : validate_state(state)  ← called inside callback()
      ─────────────────────────────────────────────────────
      ↳ Looks up state in _state_store dict

      < state in _state_store? >
      ├── NO  → logger.warning(f"Invalid state parameter from {ip_address}")
      │         raise HTTPException(400, "Invalid state parameter. Possible CSRF attack.")
      │         ──────────────────────────────────────────────────────────────────────────
      │         ERROR PATH: 400 response, flow ends
      │
      └── YES
           ↳ del _state_store[state]    ← one-time use: removed immediately after validation
           ↳ returns True

             │
             ▼

  [7] TOKEN EXCHANGE
      File : fluidmcp/cli/auth/oauth_client.py
      Fn   : exchange_code_for_tokens(code, redirect_uri)
      ─────────────────────────────────────────────────────
      POST https://{domain}/oauth/token
      Body (JSON):
        grant_type    = "authorization_code"
        client_id     = config.client_id
        client_secret = config.client_secret       ← server-side only, never exposed to browser
        code          = AUTH_CODE
        redirect_uri  = config.callback_url
        [audience]    = config.audience             ← if configured; critical for JWT validation

      ↳ response.raise_for_status()                ← propagates HTTP errors to caller

      Returns Dict:
        {
          access_token,   ← used for API authentication
          id_token,       ← client identity (not used for cookie)
          refresh_token,  ← may be absent depending on Auth0 settings
          expires_in
        }

      < exchange successful? >
      ├── NO  → logger.error(f"OAuth token exchange failed: {e}")
      │         Returns HTMLResponse with error details + "Try again" link
      │         ──────────────────────────────────────────────────────────
      │         ERROR PATH: 200 HTML error page, flow ends
      │
      └── YES
             │
             ▼

  [8] FETCH USER INFO
      File : fluidmcp/cli/auth/oauth_client.py
      Fn   : get_user_info(access_token)
      ─────────────────────────────────────────────────────
      GET https://{domain}/userinfo
      Headers:
        Authorization: Bearer {access_token}

      ↳ response.raise_for_status()

      Returns Dict (OIDC standard claims):
        {
          sub,       ← Auth0 unique user ID
          email,
          name,
          picture,
          ...        ← additional claims per Auth0 app configuration
        }

      ↳ Non-fatal if partial: exception propagates but welcome message falls back
        to user_info.get('name', user_info.get('email', 'User'))

             │
             ▼

  [9] SET COOKIE + RESPOND
      File : fluidmcp/cli/auth/routes.py
      Fn   : callback()  (continued)
      ─────────────────────────────────────────────────────
      ↳ access_token = tokens.get('access_token')
      ↳ if not access_token → raise ValueError("No access_token returned from Auth0")

      ↳ is_local_development()
          Checks FMCP_BASE_URL env var:
          True  → "localhost" or "127.0.0.1" in URL, or URL is empty
          False → production/remote URL

      response.set_cookie(
        key      = "fmcp_auth_token"
        value    = access_token
        httponly = True                          ← JavaScript cannot read (XSS protection)
        secure   = not is_local_development()   ← HTTPS only in production; HTTP ok for localhost
        samesite = "lax"                         ← CSRF protection; allows OAuth redirects
        max_age  = 86400                         ← 24-hour expiry
        path     = "/"                           ← sent with all requests to this origin
      )

      ↳ logger.info(f"OAuth login successful for user: {email|sub}")

      Response: HTML page ("Login Successful!" + spinner) with inline script:
        setTimeout(() => window.location.href = '/ui', 1000)

             │
             ▼

┌─────────────────────────────────────────────────────────────────────────────┐
│  BROWSER / FRONTEND — post-cookie                                            │
└─────────────────────────────────────────────────────────────────────────────┘

  [10] REDIRECT TO DASHBOARD + AUTH CONFIRMATION
       File : fluidmcp/frontend/src/contexts/AuthContext.tsx
       Fn   : checkAuth()
       ─────────────────────────────────────────────────────
       ↳ Browser follows script redirect → /ui
       ↳ Protected route component calls requireAuth()
       ↳ requireAuth() calls checkAuth()
       ↳ authService.getCurrentUser()
           → GET /auth/me  (cookie fmcp_auth_token sent automatically by browser)
           File: fluidmcp/cli/auth/routes.py · get_user_info()
           Uses: dependencies.get_current_user (reads + validates cookie)
           Returns: { user_id, email, name, picture, ... }
       ↳ setUser(currentUser)
       ↳ isAuthenticated = true

       → Dashboard renders with authenticated user context

       ↳ If sessionStorage['auth_return_url'] is set:
         router navigates to that URL, then clears sessionStorage entry
```

## Logout Flow

```
  [L1] USER CLICKS LOGOUT
       File : fluidmcp/frontend/src/services/auth.ts
       Fn   : authService.logout()
       ─────────────────────────────────────────────────────
       ↳ await apiClient.logout()
           → POST /auth/logout
       ↳ window.location.href = '/'

             │
             ▼

  [L2] LOGOUT ENDPOINT
       File : fluidmcp/cli/auth/routes.py
       Fn   : logout(request)
       POST : /auth/logout
       ─────────────────────────────────────────────────────
       ↳ base_url = str(request.base_url).rstrip('/')
       ↳ logout_url = oauth_client.logout_url(base_url)
           File: fluidmcp/cli/auth/oauth_client.py
           Fn  : logout_url(return_to)
           Builds: https://{domain}/v2/logout?
                     client_id={client_id}
                     &returnTo={base_url}

       ↳ response.delete_cookie(key="fmcp_auth_token", path="/")
           ← Clears httpOnly cookie; browser will no longer send it

       Returns JSONResponse:
         {
           "logout_url": "https://{domain}/v2/logout?...",
           "message": "Cookie cleared, redirect to logout_url"
         }

             │
             ▼

  [L3] AUTH0 GLOBAL LOGOUT
       ─────────────────────────────────────────────────────
       ↳ authService.logout() redirects → window.location.href = '/'
         (frontend redirects to home; caller may also use logout_url
          to hit Auth0 directly for SSO session clearing)

       Auth0 /v2/logout:
         • Invalidates Auth0 session
         • Clears Auth0 SSO cookies (all apps in tenant logged out)
         • Redirects browser to returnTo URL (base_url of the app)
```

## Key Decision Points

| Decision | Location | Yes Path | No Path |
|---|---|---|---|
| `isAuthenticated` on protected route | `AuthContext.tsx · requireAuth()` | Dashboard renders immediately | Store `auth_return_url`, call `authService.login()`, redirect to `/auth/login` |
| `oauth_client` initialized | `routes.py · login()` | Build authorization URL | HTTP 500 "OAuth not configured" |
| Auth0 returns `?error=` param | `routes.py · callback()` | Return HTML error page | Continue to CSRF validation |
| `code` and `state` present | `routes.py · callback()` | Continue to CSRF check | HTTP 400 "Missing code or state parameter" |
| `state in _state_store` | `routes.py · validate_state()` | Delete from store, return `True` | HTTP 400 "Invalid state parameter. Possible CSRF attack." |
| Token exchange succeeds | `routes.py · callback()` | Fetch user info, set cookie | Return HTML error page with exception details |
| `is_local_development()` | `routes.py · is_local_development()` | `secure=False` (HTTP ok) | `secure=True` (HTTPS only) |
| `getCurrentUser()` returns user | `AuthContext.tsx · checkAuth()` | `isAuthenticated=true`, render dashboard | Return `false`; `requireAuth()` loops back to login |

## Side Effects

| Step | Side Effect | Where |
|---|---|---|
| 1 | `auth_return_url` written to `sessionStorage` | Browser `sessionStorage` |
| 2 | State token inserted into `_state_store` dict with `datetime.utcnow()` timestamp | Server in-memory dict |
| 2 | Expired states (>10 min) pruned from `_state_store` | Server in-memory dict |
| 6 | Validated state deleted from `_state_store` (one-time use) | Server in-memory dict |
| 7 | Auth0 marks authorization code as consumed (codes are single-use) | Auth0 service |
| 9 | `fmcp_auth_token` httpOnly cookie written to browser | Browser cookie jar |
| 9 | Login success logged: `f"OAuth login successful for user: {email|sub}"` | Server log via `loguru` |
| L2 | `fmcp_auth_token` cookie deleted from browser | Browser cookie jar |
| L3 | Auth0 SSO session cleared globally across all tenant apps | Auth0 service |

## Error Paths

| Trigger | Response | Code | Notes |
|---|---|---|---|
| `oauth_client` not initialized at login | `HTTPException` | 500 | Set `FMCP_AUTH0_*` env vars |
| Auth0 returns `?error=` on callback | HTML error page with "Try again" link | 200 HTML | Auth0-side error (wrong password, blocked user, etc.) |
| `code` or `state` missing from callback | `HTTPException` | 400 | Malformed or tampered callback URL |
| `state` not found in `_state_store` | `HTTPException` | 400 | CSRF attack, expired state (>10 min), or replay attack |
| Auth0 token endpoint returns non-2xx | HTML error page via `Exception` catch block | 200 HTML | `raise_for_status()` in `exchange_code_for_tokens()` |
| Auth0 `/userinfo` returns non-2xx | HTML error page via `Exception` catch block | 200 HTML | `raise_for_status()` in `get_user_info()` |
| `access_token` absent from token response | HTML error page via `Exception` catch block | 200 HTML | `ValueError("No access_token returned from Auth0")` |
| `GET /auth/me` returns 401 | `authService.getCurrentUser()` returns `null` | — | `checkAuth()` returns `false`; `requireAuth()` redirects to login again |
| `oauth_client` not initialized at logout | `HTTPException` | 500 | Same guard as login endpoint |

## Step Reference

| Step | Name | File | Function | Notes |
|---|---|---|---|---|
| 1 | Protected Route Guard | `fluidmcp/frontend/src/contexts/AuthContext.tsx` | `requireAuth(returnUrl?)` | Calls `checkAuth()` first; stores return URL in `sessionStorage` before redirect |
| 1a | Auth Service Login Redirect | `fluidmcp/frontend/src/services/auth.ts` | `authService.login()` | Sets `window.location.href = '/auth/login'`; no async call |
| 1b | Auth Config Fetch | `fluidmcp/frontend/src/contexts/AuthContext.tsx` | `checkAuth()` | Calls `authService.getConfig()` → `GET /auth/config`; skips auth check if `enabled=false` |
| 2 | Login Endpoint | `fluidmcp/cli/auth/routes.py` | `login(request, connection?)` | `GET /auth/login`; accepts optional `connection` query param for direct provider routing |
| 2a | CSRF State Creation | `fluidmcp/cli/auth/routes.py` | `create_state()` | Uses `secrets.token_urlsafe(32)`; stores timestamp for 10-min expiry window |
| 2b | Authorization URL Builder | `fluidmcp/cli/auth/oauth_client.py` | `get_authorization_url(state, redirect_uri, connection?)` | Appends `audience` and `connection` only when configured/provided |
| 3 | Auth0 Authorize Redirect | Browser navigation | — | `https://{domain}/authorize?...` — browser leaves the app |
| 4 | Auth0 Authentication | Auth0 Universal Login | — | Email/password, social, or enterprise SSO; out of app control |
| 5 | Auth0 Callback Arrival | `fluidmcp/cli/auth/routes.py` | `callback(request, code, state, error)` | `GET /auth/callback`; error branch returns HTML, not exception |
| 6 | CSRF State Validation | `fluidmcp/cli/auth/routes.py` | `validate_state(state)` | Deletes state on first valid use; prevents replay; 400 on mismatch |
| 7 | Authorization Code Exchange | `fluidmcp/cli/auth/oauth_client.py` | `exchange_code_for_tokens(code, redirect_uri)` | `POST /oauth/token`; `client_secret` used server-side only; includes `audience` for JWT validation |
| 8 | User Profile Fetch | `fluidmcp/cli/auth/oauth_client.py` | `get_user_info(access_token)` | `GET /userinfo` with Bearer token; returns OIDC standard claims |
| 9 | Cookie Issuance | `fluidmcp/cli/auth/routes.py` | `callback()` (continued) | `fmcp_auth_token`; `httponly=True`, `secure` depends on `is_local_development()`, `samesite="lax"`, `max_age=86400` |
| 9a | Local Dev Detection | `fluidmcp/cli/auth/routes.py` | `is_local_development()` | Reads `FMCP_BASE_URL`; `secure=False` for localhost so HTTP works |
| 10 | Auth Confirmation + Dashboard | `fluidmcp/frontend/src/contexts/AuthContext.tsx` | `checkAuth()` | `GET /auth/me` with cookie; sets `user` state; `isAuthenticated = !!user` |
| L1 | Logout Trigger | `fluidmcp/frontend/src/services/auth.ts` | `authService.logout()` | `POST /auth/logout` then `window.location.href = '/'` |
| L2 | Logout Endpoint | `fluidmcp/cli/auth/routes.py` | `logout(request)` | Deletes cookie; returns `logout_url` for Auth0 global session clearing |
| L2a | Auth0 Logout URL Builder | `fluidmcp/cli/auth/oauth_client.py` | `logout_url(return_to)` | `https://{domain}/v2/logout?client_id=...&returnTo=...` |
