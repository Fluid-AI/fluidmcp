# Token Lifecycle — Data Flow Diagram

> Complete trace of how tokens are born (Auth0 code exchange), stored (httpOnly cookie), transmitted (header or cookie), and validated (RS256 JWT or bearer comparison) for every authenticated request in FluidMCP.

## Overview

FluidMCP supports two authentication paths: an OAuth 2.0 Authorization Code flow backed by Auth0 (producing RS256-signed JWTs), and a static bearer token flow for CLI/programmatic access (`fmcp serve --secure`). Both paths converge in `dependencies.py · get_current_user()`, which produces a uniform `user` dict that protected handlers consume.

---

## OAuth Token Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  ─── PHASE 1: INPUT ────────────────────────────────────────────────────   │
│                                                                             │
│  Browser                          FluidMCP                                 │
│  ────────                         ─────────                                │
│                                                                             │
│  User clicks "Login"                                                        │
│       │                                                                     │
│       ▼                                                                     │
│  GET /auth/login                                                            │
│       │                                                                     │
│       │   routes.py · login()                                               │
│       │   ├─ create_state()  →  secrets.token_urlsafe(32)                  │
│       │   │                     stored in _state_store{state: timestamp}   │
│       │   └─ oauth_client.get_authorization_url(state, redirect_uri)       │
│       │                                                                     │
│       ◄── 302 Redirect to Auth0 ─────────────────────────────────────────  │
│            https://{domain}/authorize?                                      │
│              response_type=code                                             │
│              &client_id={FMCP_AUTH0_CLIENT_ID}                             │
│              &redirect_uri={FMCP_BASE_URL}/auth/callback                   │
│              &scope=openid profile email                                    │
│              &state={csrf_token}                                            │
│              &audience={FMCP_AUTH0_AUDIENCE}                               │
│                                                                             │
│  [User authenticates at Auth0]                                              │
│       │                                                                     │
│       ▼                                                                     │
│  Auth0 redirects browser back:                                              │
│                                                                             │
│  GET /auth/callback                                                         │
│    ?code=AUTHORIZATION_CODE                                                 │
│    &state=CSRF_TOKEN                                                        │
│                                                                             │
│  Data entering system:                                                      │
│    [authorization_code: str]   ← one-time use, short TTL                   │
│    [state: str]                ← must match value in _state_store           │
│                                                                             │
│  Entry point: routes.py · callback()                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         │  CSRF check: validate_state(state)
         │  ├─ state found in _state_store → delete it (one-time use) → OK
         │  └─ state missing / expired → raise HTTP 400 "Invalid state"
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  ─── PHASE 2: TOKEN EXCHANGE ───────────────────────────────────────────   │
│                                                                             │
│  FluidMCP                         Auth0                                    │
│  ─────────                        ─────                                    │
│                                                                             │
│  routes.py · callback()                                                     │
│       │                                                                     │
│       │  oauth_client.exchange_code_for_tokens(code, redirect_uri)         │
│       │  POST https://{domain}/oauth/token                                 │
│       │  Body: {                                                            │
│       │    grant_type:    "authorization_code"                             │
│       │    client_id:     FMCP_AUTH0_CLIENT_ID                             │
│       │    client_secret: FMCP_AUTH0_CLIENT_SECRET   ← server-side only   │
│       │    code:          AUTHORIZATION_CODE                                │
│       │    redirect_uri:  FMCP_BASE_URL/auth/callback                      │
│       │    audience:      FMCP_AUTH0_AUDIENCE                              │
│       │  }                                                                  │
│       │                                                                     │
│       ◄── Response: {                                                       │
│              access_token:  JWT string  ← RS256-signed, used for API auth  │
│              id_token:      JWT string  ← identity claims (not used here)  │
│              refresh_token: str                                             │
│              expires_in:    int (seconds)                                   │
│              token_type:    "Bearer"                                        │
│           }                                                                 │
│                                                                             │
│       │  oauth_client.get_user_info(access_token)                          │
│       │  GET https://{domain}/userinfo                                      │
│       │  Header: Authorization: Bearer {access_token}                      │
│       │                                                                     │
│       ◄── Response: {                                                       │
│              sub:     str   ← Auth0 user ID (e.g. "google-oauth2|123456")  │
│              email:   str                                                   │
│              name:    str                                                   │
│              picture: str                                                   │
│           }                                                                 │
│                                                                             │
│  access_token = tokens["access_token"]   ← ID token discarded here        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         │  [access_token: JWT string]
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  ─── PHASE 3: STORAGE ──────────────────────────────────────────────────   │
│                                                                             │
│  FluidMCP                         Browser                                  │
│  ─────────                        ───────                                  │
│                                                                             │
│  routes.py · callback()                                                     │
│  response.set_cookie(                                                       │
│    key      = "fmcp_auth_token"                                            │
│    value    = access_token          ← JWT stored verbatim                  │
│    httponly = True                  ← JavaScript CANNOT read this cookie   │
│    secure   = not is_local_development()                                    │
│               True in production (HTTPS only)                               │
│               False on localhost / 127.0.0.1 (HTTP allowed)                │
│    samesite = "lax"                 ← blocks cross-site POST; allows GET   │
│                                       redirects (required for OAuth)       │
│    max_age  = 86400                 ← 24 hours in seconds                  │
│    path     = "/"                   ← available to all routes              │
│  )                                                                          │
│                                                                             │
│  ─── What does NOT happen ──────────────────────────────────────────────   │
│  - Token is NOT written to localStorage or sessionStorage                   │
│  - Token is NOT exposed in the HTML success page                            │
│  - ID token is NOT stored (discarded after user display name extracted)     │
│                                                                             │
│  Browser auto-stores cookie. No JavaScript involved.                        │
│                                                                             │
│       ◄── HTTP 200 success page + Set-Cookie header                         │
│                                                                             │
│  After 1 second JavaScript redirects browser → /ui                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         │  [fmcp_auth_token cookie stored in browser]
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  ─── PHASE 4: REQUEST ──────────────────────────────────────────────────   │
│                                                                             │
│  Browser / API Client             FluidMCP                                 │
│  ────────────────────             ─────────                                │
│                                                                             │
│  Browser (cookie path):                                                     │
│    fetch("/api/servers", { credentials: "include" })                        │
│    → browser attaches cookie automatically                                  │
│    → Header: Cookie: fmcp_auth_token=eyJhbGc...                            │
│                                                                             │
│  API client (header path):                                                  │
│    curl -H "Authorization: Bearer eyJhbGc..."                              │
│                                                                             │
│  ─────────────────────────────────────────────────────────────────────     │
│                                                                             │
│  dependencies.py · get_current_user(request, credentials)                  │
│                                                                             │
│  Step 1 — Mode detection:                                                   │
│    auth0_mode  = (FMCP_AUTH0_MODE  == "true")                              │
│    secure_mode = (FMCP_SECURE_MODE == "true")                              │
│    if neither: return anonymous user immediately (no token needed)          │
│                                                                             │
│  Step 2 — Token extraction (priority order):                                │
│    1. credentials.credentials                                               │
│       if Authorization header present → extract Bearer token               │
│                                                                             │
│    2. request.cookies.get("fmcp_auth_token")                               │
│       fallback: read httpOnly cookie                                        │
│                                                                             │
│    3. neither present → raise HTTP 401                                      │
│       "Authentication required. Please provide a valid token."              │
│                                                                             │
│  Data at this point: [raw_token: str]                                       │
│  (opaque string — handler does not know if it is JWT or bearer)             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         │  [raw_token: str]
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  ─── PHASE 5: VALIDATION ───────────────────────────────────────────────   │
│                                                                             │
│  dependencies.py · get_current_user()                                       │
│  ─── if auth0_mode ─────────────────────────────────────────────────────   │
│                                                                             │
│  jwt_validator.py · validate_oauth_jwt(token)                              │
│                                                                             │
│  Step 1: Decode unverified header                                           │
│    unverified_header = jwt.get_unverified_header(token)                     │
│    kid = unverified_header["kid"]    ← Key ID identifying signing key       │
│    if no kid → raise ValueError                                             │
│                                                                             │
│  Step 2: Resolve public key                                                 │
│    JWKSCache.get_signing_key(kid)                                           │
│    ├─ cache hit (< 1 hour old) → return cached key immediately             │
│    ├─ cache miss or expired → fetch https://{domain}/.well-known/jwks.json │
│    │   with 10s timeout; update _expires_at = now + 3600s                  │
│    ├─ key with matching kid found → jwk.construct(key_data) → public key   │
│    └─ kid not in JWKS → raise ValueError("Key ID {kid} not found")        │
│         └─ auto-retry once: invalidate cache, re-fetch, retry validation   │
│            (handles Auth0 key rotation transparently)                       │
│                                                                             │
│  Step 3: Decode and verify JWT                                              │
│    jwt.decode(                                                              │
│      token,                                                                 │
│      signing_key,                                                           │
│      algorithms = ["RS256"],             ← rejects HS256, none, etc.       │
│      audience   = FMCP_AUTH0_AUDIENCE,   ← prevents token reuse across    │
│      issuer     = "https://{domain}/"    │   services and issuers          │
│    )                                     ←                                 │
│    Verifies: cryptographic signature, expiration (exp), issuer, audience   │
│                                                                             │
│  Step 4: Extract claims from verified payload                               │
│    user_id = payload["sub"]                                                 │
│    email   = payload.get("email") or payload.get("name")                   │
│    name    = payload.get("name")  or payload.get("email") or "Unknown"     │
│                                                                             │
│  Error mapping:                                                             │
│    ExpiredSignatureError  → ValueError("Token has expired")                │
│    JWTClaimsError         → ValueError("Token claims validation failed")   │
│    JWTError               → ValueError("Token validation failed")          │
│    Any other              → ValueError("Unexpected error...")               │
│    All → raise HTTP 401 in get_current_user()                              │
│                                                                             │
│  JWKS cache is thread-safe: guarded by threading.Lock()                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         │  validated payload
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  ─── PHASE 6: OUTPUT ───────────────────────────────────────────────────   │
│                                                                             │
│  dependencies.py returns user dict to handler:                              │
│    {                                                                        │
│      "user_id":     payload["sub"],       ← e.g. "google-oauth2|123456"   │
│      "email":       payload["email"],                                       │
│      "name":        payload["name"],                                        │
│      "auth_method": "oauth"                                                 │
│    }                                                                        │
│                                                                             │
│  Handler usage examples (management.py):                                    │
│    user_id = user["user_id"]                                                │
│                                                                             │
│    add_server_from_github:                                                  │
│      GitHubService.build_server_configs(..., created_by=user_id)           │
│      → user_id written to MongoDB server config document as "created_by"   │
│                                                                             │
│    delete_server / start_server / stop_server / restart_server:            │
│      user_id = user["user_id"]  ← extracted for audit logging              │
│                                                                             │
│  Response: JSONResponse with operation result returned to client            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Bearer Token Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  ─── INPUT ─────────────────────────────────────────────────────────────   │
│                                                                             │
│  Server startup:                                                            │
│    fmcp serve --secure --token SECRET                                       │
│    └─ sets env var FMCP_BEARER_TOKEN=SECRET                                │
│       (or pre-set in environment / Railway config)                          │
│                                                                             │
│  Alternatively: Railway sets FMCP_BEARER_TOKEN before container start.     │
│  Without it, FMCP_SECURE_MODE=true will return HTTP 500 on every request.  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  ─── REQUEST ───────────────────────────────────────────────────────────   │
│                                                                             │
│  API client sends:                                                          │
│    Authorization: Bearer SECRET                                             │
│                                                                             │
│  dependencies.py · get_current_user()                                       │
│    secure_mode = (FMCP_SECURE_MODE == "true") → True                       │
│    token = credentials.credentials   ← from Authorization header           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         │  [raw_token: str]
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  ─── VALIDATION ────────────────────────────────────────────────────────   │
│                                                                             │
│  dependencies.py · get_current_user()  (secure_mode branch)                │
│                                                                             │
│  bearer_token = os.getenv("FMCP_BEARER_TOKEN")                             │
│  if not bearer_token → raise HTTP 500 (misconfiguration)                   │
│                                                                             │
│  if token == bearer_token:                                                  │
│    └─ direct string equality check                                          │
│       Note: not secrets.compare_digest(); timing-safe comparison           │
│       not currently applied in this branch                                  │
│                                                                             │
│  if mismatch → raise HTTP 401 "Invalid or expired token"                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  ─── OUTPUT ────────────────────────────────────────────────────────────   │
│                                                                             │
│  dependencies.py returns:                                                   │
│    {                                                                        │
│      "user_id":     f"bearer_{token[:8]}",  ← first 8 chars of token      │
│      "email":       None,                                                   │
│      "name":        f"Bearer User {token[:8]}",                            │
│      "auth_method": "bearer"                                                │
│    }                                                                        │
│                                                                             │
│  Handler receives same user dict shape as OAuth path.                       │
│  Audit fields (created_by) use the bearer_{token[:8]} user_id.             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Security Properties

| Property | Mechanism | File | Function / Location |
|---|---|---|---|
| XSS protection | `httponly=True` on cookie; token never in JS-accessible storage | `fluidmcp/cli/auth/routes.py` | `callback()` · `set_cookie()` |
| CSRF protection (state) | `secrets.token_urlsafe(32)` state bound to session; validated once then deleted | `fluidmcp/cli/auth/routes.py` | `create_state()` / `validate_state()` |
| CSRF protection (cookie) | `samesite="lax"` blocks cross-origin POST requests while allowing OAuth redirect | `fluidmcp/cli/auth/routes.py` | `callback()` · `set_cookie()` |
| HTTPS enforcement | `secure=True` in production (cookie not sent over HTTP) | `fluidmcp/cli/auth/routes.py` | `is_local_development()` check |
| Algorithm pinning | `algorithms=["RS256"]` — rejects `HS256`, `none`, and algorithm-confusion attacks | `fluidmcp/cli/auth/jwt_validator.py` | `validate_oauth_jwt()` |
| Audience validation | `audience=FMCP_AUTH0_AUDIENCE` — token must target this specific API | `fluidmcp/cli/auth/jwt_validator.py` | `validate_oauth_jwt()` |
| Issuer validation | `issuer=f"https://{domain}/"` — token must originate from configured Auth0 tenant | `fluidmcp/cli/auth/jwt_validator.py` | `validate_oauth_jwt()` |
| Key rotation handling | On `kid` cache miss: invalidate cache, re-fetch JWKS, retry once | `fluidmcp/cli/auth/jwt_validator.py` | `validate_oauth_jwt()` / `JWKSCache.get_signing_key()` |
| JWKS cache thread safety | `threading.Lock()` around cache reads and writes | `fluidmcp/cli/auth/jwt_validator.py` | `JWKSCache._lock` |
| Token extraction priority | `Authorization` header beats cookie — API clients always win over browser session | `fluidmcp/cli/auth/dependencies.py` | `get_current_user()` |
| Bearer token comparison | `token == bearer_token` direct equality; note: `secrets.compare_digest()` not currently used in bearer path | `fluidmcp/cli/auth/dependencies.py` | `get_current_user()` secure_mode branch |
| ID token discarded | Only `access_token` stored; `id_token` and `refresh_token` dropped after exchange | `fluidmcp/cli/auth/routes.py` | `callback()` |
| Audit trail | `created_by=user["user_id"]` written to MongoDB on server creation | `fluidmcp/cli/api/management.py` | `add_server_from_github()` |

---

## Data Flow Summary

| Step | Phase | Component | File | Function | Data In | Data Out |
|---|---|---|---|---|---|---|
| 1 | INPUT | FastAPI route | `fluidmcp/cli/auth/routes.py` | `login()` | `connection: str \| None` | 302 redirect to Auth0 with `state`, `client_id`, `scope`, `audience` |
| 2 | INPUT | State store | `fluidmcp/cli/auth/routes.py` | `create_state()` | — | `state: str` (random 32-byte URL-safe token, stored in `_state_store`) |
| 3 | INPUT | FastAPI route | `fluidmcp/cli/auth/routes.py` | `callback()` | `code: str`, `state: str` | proceeds if CSRF check passes |
| 4 | INPUT | State validator | `fluidmcp/cli/auth/routes.py` | `validate_state(state)` | `state: str` | `True` (deletes from store) or raises HTTP 400 |
| 5 | TOKEN EXCHANGE | Auth0 client | `fluidmcp/cli/auth/oauth_client.py` | `exchange_code_for_tokens(code, redirect_uri)` | `code: str`, `redirect_uri: str` | `{access_token, id_token, refresh_token, expires_in, token_type}` |
| 6 | TOKEN EXCHANGE | Auth0 client | `fluidmcp/cli/auth/oauth_client.py` | `get_user_info(access_token)` | `access_token: str` | `{sub, email, name, picture}` |
| 7 | STORAGE | FastAPI response | `fluidmcp/cli/auth/routes.py` | `callback()` · `set_cookie()` | `access_token: str` | `Set-Cookie: fmcp_auth_token=<jwt>; HttpOnly; SameSite=Lax; Max-Age=86400` |
| 8 | REQUEST | FastAPI dependency | `fluidmcp/cli/auth/dependencies.py` | `get_current_user()` | HTTP request (header or cookie) | `raw_token: str` |
| 9 | VALIDATION | JWT validator | `fluidmcp/cli/auth/jwt_validator.py` | `validate_oauth_jwt(token)` · header decode | `token: str` | `kid: str` from unverified JWT header |
| 10 | VALIDATION | JWKS cache | `fluidmcp/cli/auth/jwt_validator.py` | `JWKSCache.get_signing_key(kid)` | `kid: str` | `signing_key` (RSA public key object) |
| 11 | VALIDATION | JWT validator | `fluidmcp/cli/auth/jwt_validator.py` | `validate_oauth_jwt()` · `jwt.decode()` | `token`, `signing_key`, `audience`, `issuer` | verified `payload: dict` or raises `ValueError` |
| 12 | VALIDATION | JWT validator | `fluidmcp/cli/auth/jwt_validator.py` | `validate_oauth_jwt()` · claims extract | `payload: dict` | `{user_id: sub, email, name, auth_method: "oauth"}` |
| 13 | OUTPUT | FastAPI handler | `fluidmcp/cli/api/management.py` | any protected endpoint | `user: dict` | `user["user_id"]` used as `created_by` in MongoDB writes, audit logging |
| 14 | OUTPUT | FastAPI response | `fluidmcp/cli/api/management.py` | any protected endpoint | operation result | `JSONResponse` to client |
| B1 | INPUT (bearer) | CLI / env | `fmcp serve --secure` | — | `--token SECRET` flag | `FMCP_BEARER_TOKEN` env var set |
| B2 | REQUEST (bearer) | FastAPI dependency | `fluidmcp/cli/auth/dependencies.py` | `get_current_user()` | `Authorization: Bearer SECRET` header | `raw_token: str` |
| B3 | VALIDATION (bearer) | FastAPI dependency | `fluidmcp/cli/auth/dependencies.py` | `get_current_user()` secure_mode branch | `raw_token` vs `FMCP_BEARER_TOKEN` | match → proceed; mismatch → HTTP 401 |
| B4 | OUTPUT (bearer) | FastAPI dependency | `fluidmcp/cli/auth/dependencies.py` | `get_current_user()` | match confirmed | `{user_id: "bearer_{token[:8]}", email: None, name: "Bearer User {token[:8]}", auth_method: "bearer"}` |
