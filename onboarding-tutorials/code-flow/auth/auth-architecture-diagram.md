# FluidMCP Authentication — Architecture Diagram

> FluidMCP supports two mutually exclusive authentication modes — static bearer tokens and Auth0 OAuth2/OIDC — unified behind a single FastAPI dependency (`get_current_user`) that also accepts browser cookies set by the OAuth callback.

## System Architecture

The auth system is structured as four left-to-right layers: the Entry / API layer (frontend React components + FastAPI app + OAuth routes + protected management routes), the Auth Logic layer (unified dependency resolver, bearer-token validator, JWKS-backed JWT validator, and the Auth0 HTTP client), the Config / Utils layer (pydantic config model and environment-aware URL helpers), and the External layer (the four Auth0 cloud endpoints the system talks to).

```
╔══════════════════════════════╗  ╔══════════════════════════════╗  ╔══════════════════════════════╗  ╔══════════════════════════════╗
║      ENTRY / API LAYER       ║  ║      AUTH LOGIC LAYER        ║  ║    CONFIG / UTILS LAYER      ║  ║      EXTERNAL LAYER          ║
╠══════════════════════════════╣  ╠══════════════════════════════╣  ╠══════════════════════════════╣  ╠══════════════════════════════╣
║                              ║  ║                              ║  ║                              ║  ║                              ║
║  ┌──────────────────────┐    ║  ║  ┌──────────────────────┐   ║  ║  ┌──────────────────────┐   ║  ║  ┌──────────────────────┐   ║
║  │   AuthProvider       │    ║  ║  │  get_current_user()  │   ║  ║  │    Auth0Config        │   ║  ║  │  Auth0 /authorize    │   ║
║  │   useAuth()          │    ║  ║  │  get_optional_user() │   ║  ║  │    from_env()         │   ║  ║  │  (Authorization      │   ║
║  │ AuthContext.tsx       │    ║  ║  │  dependencies.py     │   ║  ║  │    from_file()        │   ║  ║  │   endpoint)          │   ║
║  └──────────┬───────────┘    ║  ║  │  (unified resolver)  │   ║  ║  │    from_env_or_file() │   ║  ║  └──────────────────────┘   ║
║             │                ║  ║  └──────────┬───────────┘   ║  ║  │    auth/config.py     │   ║  ║                              ║
║  ┌──────────▼───────────┐    ║  ║             │               ║  ║  └──────────┬────────────┘   ║  ║  ┌──────────────────────┐   ║
║  │   authService        │    ║  ║     ┌───────┴───────┐       ║  ║             │                ║  ║  │  Auth0 /oauth/token  │   ║
║  │   .login()           │    ║  ║     │               │       ║  ║  ┌──────────▼────────────┐   ║  ║  │  (Token exchange     │   ║
║  │   .getCurrentUser()  │    ║  ║     ▼               ▼       ║  ║  │    url_utils.py        │   ║  ║  │   endpoint)          │   ║
║  │   .logout()          ├────╫──╫──► Bearer        OAuth      ║  ║  │    get_base_url()      │   ║  ║  └──────────────────────┘   ║
║  │   services/auth.ts   │    ║  ║     │     path    │  path   ║  ║  │    get_callback_url()  │   ║  ║                              ║
║  └──────────────────────┘    ║  ║     │               │       ║  ║  │    get_cors_origins()  │   ║  ║  ┌──────────────────────┐   ║
║                              ║  ║     ▼               ▼       ║  ║  └────────────────────────┘   ║  ║  │  Auth0 /userinfo     │   ║
║  ┌──────────────────────┐    ║  ║  ┌──────────┐ ┌──────────┐ ║  ║                              ║  ║  │  (User profile       │   ║
║  │   FastAPI App        │    ║  ║  │ verify_  │ │ validate_│ ║  ║                              ║  ║  │   endpoint)          │   ║
║  │   create_app()       │    ║  ║  │ token()  │ │ oauth_   │ ║  ║                              ║  ║  └──────────────────────┘   ║
║  │   server.py          │    ║  ║  │ _validate│ │ jwt()    │ ║  ║                              ║  ║                              ║
║  └──────────┬───────────┘    ║  ║  │ _bearer_ │ │  +       │ ║  ║                              ║  ║  ┌──────────────────────┐   ║
║             │                ║  ║  │ token()  │ │ JWKSCache│ ║  ║                              ║  ║  │  Auth0 JWKS          │   ║
║  ┌──────────▼───────────┐    ║  ║  │ auth.py  │ │ jwt_     │ ║  ║                              ║  ║  │  /.well-known/       │   ║
║  │  CORS Middleware      │    ║  ║  └──────────┘ │ validator│ ║  ║                              ║  ║  │  jwks.json           │   ║
║  │  (CORSMiddleware)     │    ║  ║               │ .py      │ ║  ║                              ║  ║  │  (Key material for   │   ║
║  │  Security Headers     │    ║  ║               └────┬─────┘ ║  ║                              ║  ║  │   RS256 validation)  │   ║
║  │  (add_security_       │    ║  ║                    │       ║  ║                              ║  ║  └──────────────────────┘   ║
║  │   headers middleware) │    ║  ║  ┌─────────────────▼────┐  ║  ║                              ║  ║                              ║
║  │  server.py            │    ║  ║  │  Auth0Client          │  ║  ║                              ║  ║                              ║
║  └──────────┬───────────┘    ║  ║  │  get_authorization_   │  ║  ║                              ║  ║                              ║
║             │                ║  ║  │    url()              │  ║  ║                              ║  ║                              ║
║  ┌──────────▼───────────┐    ║  ║  │  exchange_code_for_   │  ║  ║                              ║  ║                              ║
║  │  OAuth Routes         │    ║  ║  │    tokens()           │  ║  ║                              ║  ║                              ║
║  │  GET  /auth/login     │    ║  ║  │  get_user_info()      │  ║  ║                              ║  ║                              ║
║  │  GET  /auth/callback  │    ║  ║  │  logout_url()         │  ║  ║                              ║  ║                              ║
║  │  POST /auth/logout    │    ║  ║  │  oauth_client.py      │  ║  ║                              ║  ║                              ║
║  │  GET  /auth/me        │    ║  ║  └──────────────────────┘   ║  ║                              ║  ║                              ║
║  │  GET  /auth/config    │    ║  ║                              ║  ║                              ║  ║                              ║
║  │  auth/routes.py       │    ║  ║                              ║  ║                              ║  ║                              ║
║  └──────────┬───────────┘    ║  ║                              ║  ║                              ║  ║                              ║
║             │                ║  ║                              ║  ║                              ║  ║                              ║
║  ┌──────────▼───────────┐    ║  ║                              ║  ║                              ║  ║                              ║
║  │  Management API       │    ║  ║                              ║  ║                              ║  ║                              ║
║  │  Depends(             │    ║  ║                              ║  ║                              ║  ║                              ║
║  │   get_current_user)   │    ║  ║                              ║  ║                              ║  ║                              ║
║  │  on /api/* routes     │    ║  ║                              ║  ║                              ║  ║                              ║
║  │  api/management.py    │    ║  ║                              ║  ║                              ║  ║                              ║
║  └──────────────────────┘    ║  ║                              ║  ║                              ║  ║                              ║
╚══════════════════════════════╝  ╚══════════════════════════════╝  ╚══════════════════════════════╝  ╚══════════════════════════════╝
```

---

## Key Request Flows

### Flow 1 — Browser Login (OAuth)
```
AuthProvider / useAuth()        GET /auth/login              Auth0 /authorize
  authService.login()    ──────►  routes.py           ──────►  (external)
  (window.location.href =          create_state()
   '/auth/login')                  get_authorization_url()
                                   ─► Auth0Client
                                       .get_authorization_url()
                                       uses Auth0Config.callback_url
                                       (from url_utils.get_callback_url())
```

### Flow 2 — OAuth Callback & Cookie Set
```
Auth0 redirects to              oauth_client                 Auth0 /oauth/token
  GET /auth/callback     ──────► .exchange_code_for_tokens() ──────► (external)
  routes.py                      .get_user_info()            ──────► Auth0 /userinfo
    validate_state()              └─► access_token
    │                                  set as httpOnly
    │                                  cookie: fmcp_auth_token
    └─► redirect to /ui
```

### Flow 3 — Protected API Request (two-path token resolution)
```
Browser / API client            get_current_user()
  Authorization: Bearer  ──────►  dependencies.py
  OR cookie: fmcp_auth_token       reads FMCP_AUTH0_MODE
                                   reads FMCP_SECURE_MODE
                                        │
                          ┌────────────►┤◄────────────────┐
                          │             │                  │
                    Bearer path    OAuth path         Anonymous
                          │             │
                    verify_token()  validate_oauth_jwt()
                    _validate_      jwt_validator.py
                    bearer_token()       │
                    auth.py         JWKSCache
                    secrets.        .get_signing_key(kid)
                    compare_digest       │
                                   cache miss?
                                        │
                                   ─────►  Auth0 JWKS
                                           /.well-known/jwks.json
                                           (external)
```

### Flow 4 — Config feeds into runtime
```
Auth0Config.from_env()           Auth0Client.__init__(config)
  auth/config.py          ──────►  oauth_client.py
  reads FMCP_AUTH0_DOMAIN           uses config.domain
       FMCP_AUTH0_CLIENT_ID               config.client_id
       FMCP_AUTH0_CLIENT_SECRET           config.client_secret
       FMCP_AUTH0_AUDIENCE                config.audience
                                          config.callback_url

url_utils.get_cors_origins()     create_app() CORS middleware
  auth/url_utils.py       ──────►  server.py
  (auto-detects Codespaces,         app.add_middleware(CORSMiddleware,
   Gitpod, FMCP_BASE_URL)            allow_origins=auto_origins)

url_utils.get_callback_url()     routes.py /auth/login, /auth/callback
  auth/url_utils.py       ──────►  config.callback_url
```

---

## Layer Breakdown

### Entry / API Layer

**Frontend — AuthProvider**
- File: `fluidmcp/frontend/src/contexts/AuthContext.tsx`
- Exports: `AuthProvider` (React context provider), `useAuth()` hook
- Responsibilities: wraps the React tree; exposes `checkAuth()`, `requireAuth()`, `logout()`, and `isAuthenticated`; on-demand auth checking (not mounted eagerly); stores `User` and `AuthConfig` state; calls `authService.login()` to redirect when unauthenticated

**Frontend — authService**
- File: `fluidmcp/frontend/src/services/auth.ts`
- Export: `authService` object literal
- Responsibilities: thin wrapper around `apiClient`; `getConfig()` fetches `GET /auth/config`, `getCurrentUser()` fetches `GET /auth/me`, `login()` redirects to `/auth/login`, `logout()` calls `POST /auth/logout` then redirects to `/`

**FastAPI App — create_app()**
- File: `fluidmcp/cli/server.py`
- Function: `create_app(db_manager, server_manager, secure_mode, token, allowed_origins, port)`
- Responsibilities: constructs the FastAPI app; registers `CORSMiddleware` (auto-expands origins in auth0 mode via `get_cors_origins()`); registers `add_security_headers` middleware (CSP, X-Frame-Options, X-XSS-Protection, etc.); conditionally mounts `auth_router` at `/auth` when `auth0_mode=True`; includes `mgmt_router` at `/api`

**CORS Middleware**
- File: `fluidmcp/cli/server.py` (inside `create_app()`)
- Class: `CORSMiddleware` (FastAPI/Starlette built-in)
- Origins resolved from `get_cors_origins()` in auth0 mode; `allow_credentials=True` is required for httpOnly cookie flow

**Security Headers Middleware**
- File: `fluidmcp/cli/server.py` (inside `create_app()`, function `add_security_headers`)
- Injects: `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`

**OAuth Routes**
- File: `fluidmcp/cli/auth/routes.py`
- Router: `auth_router` (prefix `/auth`)
- Endpoints:
  - `GET /auth/login` — `login()` — generates CSRF state, calls `Auth0Client.get_authorization_url()`, returns 302 redirect to Auth0
  - `GET /auth/callback` — `callback()` — validates CSRF state, calls `exchange_code_for_tokens()` then `get_user_info()`, sets `fmcp_auth_token` httpOnly cookie
  - `POST /auth/logout` — `logout()` — clears cookie, returns `logout_url` pointing to Auth0 logout
  - `GET /auth/me` — `get_user_info()` — depends on `get_current_user()`; returns user dict
  - `GET /auth/config` — `get_auth_config()` — returns public OAuth config (domain, clientId, audience) for frontend

**Management API**
- File: `fluidmcp/cli/api/management.py`
- Router: `mgmt_router` (prefix `/api`)
- Auth guard: `Depends(get_current_user)` applied to individual route handlers that require identity; `Depends(get_token)` used for simpler bearer-only endpoints

---

### Auth Logic Layer

**Unified Dependency — get_current_user()**
- File: `fluidmcp/cli/auth/dependencies.py`
- Functions: `get_current_user()`, `get_optional_user()`
- Responsibilities: reads `FMCP_AUTH0_MODE` and `FMCP_SECURE_MODE` env vars; accepts token from `Authorization: Bearer` header (highest priority) or `fmcp_auth_token` cookie (browser OAuth); if `auth0_mode` → calls `validate_oauth_jwt()`; if `secure_mode` → direct string compare against `FMCP_BEARER_TOKEN`; if neither mode → returns anonymous user context; `get_optional_user()` returns `None` instead of raising 401

**Bearer Token Validator — verify_token() / _validate_bearer_token()**
- File: `fluidmcp/cli/auth.py`
- Functions: `verify_token()` (FastAPI dependency), `_validate_bearer_token()` (internal)
- Responsibilities: reads `FMCP_SECURE_MODE` / `FMCP_BEARER_TOKEN`; no-ops when secure mode is off; uses `secrets.compare_digest()` for constant-time comparison to prevent timing attacks; raises 401 with `WWW-Authenticate: Bearer` on failure; used directly on `/metrics` endpoint

**JWT Validator — JWKSCache + validate_oauth_jwt()**
- File: `fluidmcp/cli/auth/jwt_validator.py`
- Classes / functions: `JWKSCache`, `_get_jwks_cache()`, `validate_oauth_jwt()`
- Responsibilities: `JWKSCache` fetches and caches JWKS keys from `https://{domain}/.well-known/jwks.json` with 1-hour TTL and thread-safe `threading.Lock`; `validate_oauth_jwt()` extracts `kid` from JWT header, calls `cache.get_signing_key(kid)`, decodes JWT with `python-jose` using RS256, validates `iss` and `aud` claims; auto-refreshes cache on key-not-found errors (handles Auth0 key rotation with one retry)

**Auth0 HTTP Client — Auth0Client**
- File: `fluidmcp/cli/auth/oauth_client.py`
- Class: `Auth0Client`
- Methods:
  - `get_authorization_url(state, redirect_uri, connection)` — builds `https://{domain}/authorize?...` URL
  - `exchange_code_for_tokens(code, redirect_uri)` — POST to `https://{domain}/oauth/token`; returns `access_token`, `id_token`, etc.
  - `get_user_info(access_token)` — GET `https://{domain}/userinfo` with Bearer header; returns user profile dict
  - `logout_url(return_to)` — builds `https://{domain}/v2/logout?...` URL

---

### Config / Utils Layer

**Auth0Config — from_env_or_file()**
- File: `fluidmcp/cli/auth/config.py`
- Class: `Auth0Config` (Pydantic `BaseModel`)
- Fields: `domain`, `client_id`, `client_secret`, `callback_url`, `audience`, `jwt_secret`, `jwt_algorithm`, `jwt_expiration_minutes`, `port`
- Factory methods:
  - `from_env(port)` — reads `FMCP_AUTH0_DOMAIN`, `FMCP_AUTH0_CLIENT_ID`, `FMCP_AUTH0_CLIENT_SECRET`, `FMCP_AUTH0_AUDIENCE`, `FMCP_AUTH0_CALLBACK_URL`, `FMCP_JWT_SECRET`; falls back to `get_callback_url(port)` if callback not set
  - `from_file(file_path)` — loads from JSON file
  - `from_env_or_file(file_path, port)` — merges file config then env overrides; highest-priority path used in production

**URL Utilities**
- File: `fluidmcp/cli/auth/url_utils.py`
- Functions:
  - `get_base_url(port)` — detects environment: `FMCP_BASE_URL` → GitHub Codespaces (`CODESPACES` env) → Gitpod → localhost fallback
  - `get_callback_url(port)` — returns `{base_url}/auth/callback`; used in `Auth0Config` and in routes.py login/callback handlers
  - `get_cors_origins(port)` — builds CORS allowlist from `FMCP_ALLOWED_ORIGINS` env var + detected base URL + localhost fallback + Codespaces wildcard

---

### External Dependencies

**Auth0 /authorize**
- URL: `https://{domain}/authorize`
- Called by: `Auth0Client.get_authorization_url()` (URL construction only; browser follows the redirect)
- Purpose: Renders Auth0's hosted login page; returns `code` + `state` to callback URL after successful login

**Auth0 /oauth/token**
- URL: `https://{domain}/oauth/token`
- Called by: `Auth0Client.exchange_code_for_tokens()` (server-side POST)
- Purpose: Exchanges authorization `code` for `access_token` and `id_token`

**Auth0 /userinfo**
- URL: `https://{domain}/userinfo`
- Called by: `Auth0Client.get_user_info()` (server-side GET with Bearer token)
- Purpose: Returns user profile (email, name, picture, sub) for the authenticated user

**Auth0 JWKS**
- URL: `https://{domain}/.well-known/jwks.json`
- Called by: `JWKSCache._refresh_keys()` (lazy-loaded on first JWT validation, then cached for 1 hour)
- Purpose: Provides RSA public keys (by `kid`) used to verify RS256 signatures on access tokens

---

## Dependency Map

| Component | Imports / Calls | Purpose |
|-----------|----------------|---------|
| `server.py` `create_app()` | `auth_router`, `init_auth_routes`, `Auth0Config` (from `fluidmcp.cli.auth`); `get_cors_origins()` from `url_utils`; `verify_token` from `fluidmcp.cli.auth` | Wires together all auth components at app startup |
| `auth/routes.py` | `Auth0Config`, `Auth0Client`, `get_current_user` | Implements the OAuth redirect/callback/logout endpoints |
| `auth/routes.py` `login()` | `Auth0Client.get_authorization_url()`, `config.callback_url` | Builds redirect URL to Auth0 |
| `auth/routes.py` `callback()` | `Auth0Client.exchange_code_for_tokens()`, `Auth0Client.get_user_info()` | Completes OAuth code exchange; sets httpOnly cookie |
| `auth/dependencies.py` `get_current_user()` | `validate_oauth_jwt()` from `jwt_validator`; `FMCP_BEARER_TOKEN` env var | Unified per-request auth resolver |
| `auth/jwt_validator.py` `validate_oauth_jwt()` | `JWKSCache.get_signing_key()`, `jose.jwt.decode()` | Validates Auth0 JWT against JWKS public keys |
| `auth/jwt_validator.py` `JWKSCache` | `requests.get()` → Auth0 JWKS endpoint | Fetches and caches RS256 signing keys |
| `auth/oauth_client.py` `Auth0Client` | `Auth0Config` (injected); `requests.post/get` → Auth0 token/userinfo endpoints | HTTP client for Auth0 OAuth operations |
| `auth/config.py` `Auth0Config` | `get_callback_url()` from `url_utils`; env vars `FMCP_AUTH0_*` | Loads and validates all Auth0 settings |
| `auth/url_utils.py` | `FMCP_BASE_URL`, `CODESPACES`, `GITPOD_WORKSPACE_ID`, `FMCP_ALLOWED_ORIGINS` env vars | Dynamically resolves URLs for any deployment environment |
| `auth.py` `verify_token()` | `_validate_bearer_token()`, `secrets.compare_digest()` | Secures endpoints with static bearer token |
| `frontend/AuthContext.tsx` | `authService` from `services/auth.ts` | React state management for auth; drives login redirects |
| `frontend/services/auth.ts` | `apiClient` (`GET /auth/me`, `GET /auth/config`, `POST /auth/logout`) | HTTP calls to backend auth endpoints |
| `api/management.py` | `get_current_user` from `auth/dependencies`; `get_token` from local helper | Enforces auth on all `/api/*` management routes |

---

## Component Summary

| Component | File | Class / Function | Role |
|-----------|------|-----------------|------|
| AuthProvider | `fluidmcp/frontend/src/contexts/AuthContext.tsx` | `AuthProvider`, `useAuth()` | React context; on-demand auth state management |
| authService | `fluidmcp/frontend/src/services/auth.ts` | `authService` (object literal) | Frontend HTTP client for auth backend endpoints |
| FastAPI App Factory | `fluidmcp/cli/server.py` | `create_app()` | Builds FastAPI app; registers middleware and routers |
| CORS Middleware | `fluidmcp/cli/server.py` | `CORSMiddleware` (in `create_app()`) | Enforces cross-origin policy; auto-expands for OAuth |
| Security Headers Middleware | `fluidmcp/cli/server.py` | `add_security_headers` (in `create_app()`) | Adds CSP, X-Frame-Options, XSS protection headers |
| OAuth Route — login | `fluidmcp/cli/auth/routes.py` | `login()` at `GET /auth/login` | Generates CSRF state; redirects browser to Auth0 |
| OAuth Route — callback | `fluidmcp/cli/auth/routes.py` | `callback()` at `GET /auth/callback` | Exchanges auth code for tokens; sets httpOnly cookie |
| OAuth Route — logout | `fluidmcp/cli/auth/routes.py` | `logout()` at `POST /auth/logout` | Clears cookie; returns Auth0 logout redirect URL |
| OAuth Route — me | `fluidmcp/cli/auth/routes.py` | `get_user_info()` at `GET /auth/me` | Returns current user dict (protected by `get_current_user`) |
| OAuth Route — config | `fluidmcp/cli/auth/routes.py` | `get_auth_config()` at `GET /auth/config` | Returns public OAuth config for frontend |
| Management API | `fluidmcp/cli/api/management.py` | `router` (mgmt_router) | All `/api/*` routes; guarded by `get_current_user` |
| Unified Auth Dependency | `fluidmcp/cli/auth/dependencies.py` | `get_current_user()` | Resolves token from header or cookie; dispatches to OAuth or bearer path |
| Optional Auth Dependency | `fluidmcp/cli/auth/dependencies.py` | `get_optional_user()` | Same as `get_current_user` but returns `None` instead of 401 |
| Bearer Token Validator | `fluidmcp/cli/auth.py` | `verify_token()`, `_validate_bearer_token()` | Constant-time bearer token comparison; used on `/metrics` and secure mode |
| JWKS Cache | `fluidmcp/cli/auth/jwt_validator.py` | `JWKSCache` | Thread-safe 1-hour cache of Auth0 RS256 public keys |
| JWT Validator | `fluidmcp/cli/auth/jwt_validator.py` | `validate_oauth_jwt()` | Decodes and validates Auth0 JWT; retries on key rotation |
| Auth0 HTTP Client | `fluidmcp/cli/auth/oauth_client.py` | `Auth0Client` | Wraps Auth0 `/authorize`, `/oauth/token`, `/userinfo`, `/v2/logout` |
| Auth0 Config | `fluidmcp/cli/auth/config.py` | `Auth0Config`, `from_env_or_file()` | Pydantic model; loads config from env vars, JSON file, or both |
| URL Utilities | `fluidmcp/cli/auth/url_utils.py` | `get_base_url()`, `get_callback_url()`, `get_cors_origins()` | Environment-aware URL resolver (local, Codespaces, Gitpod, custom) |
| Auth0 /authorize | external | — | Hosts login UI; issues authorization code back to callback |
| Auth0 /oauth/token | external | — | Exchanges authorization code for access + ID tokens |
| Auth0 /userinfo | external | — | Returns user profile for a valid access token |
| Auth0 JWKS | external | `/.well-known/jwks.json` | Provides RSA public keys for RS256 JWT signature verification |
