# Authentication Modes — Key Flow

> Every `fmcp serve` request travels the same five-step startup path before landing in one of three per-request auth branches selected at runtime by reading two env vars.

**Key steps:** `fmcp serve` → Parse flags → Validate config → Set env vars → Wire dependencies → Request arrives → Auth mode check → User context (or 401)

---

## Startup Flow (Steps 1–5)

```
┌──────────────────────────┐     ┌──────────────────────────┐     ┌──────────────────────────────────────────┐
│  STEP 1                  │     │  STEP 2                  │     │  STEP 3                                  │
│  fmcp serve              │────▶│  Parse auth flags        │────▶│  Validate config                         │
│                          │     │                          │     │                                          │
│  cli.py · main()         │     │  cli.py · main()         │     │  cli.py · main()  (lines 720–737)        │
│  Entry point.            │     │  Reads --secure,         │     │  --secure + --auth0 together → exit(1)   │
│  Parses argv.            │     │  --auth0,                │     │  --auth0 missing env vars    → exit(1)   │
│                          │     │  --token,                │     │  neither + no --allow-insecure → exit(1) │
│                          │     │  --allow-insecure        │     │                                          │
└──────────────────────────┘     └──────────────────────────┘     └──────────────────────────────────────────┘

           │
           ▼
┌──────────────────────────────────────────────────┐     ┌──────────────────────────────────────────────────┐
│  STEP 4                                          │     │  STEP 5                                          │
│  Set env vars + (optionally) generate token      │────▶│  Wire dependency + start uvicorn                 │
│                                                  │     │                                                  │
│  cli.py · main()  (lines 685–737)                │     │  server.py · create_app()  (line 145)            │
│  os.environ["FMCP_SECURE_MODE"]  = "true"        │     │  mgmt_router uses Depends(get_current_user)      │
│  os.environ["FMCP_BEARER_TOKEN"] = <token>       │     │  on every /api/* route                           │
│  os.environ["FMCP_AUTH0_MODE"]   = "true"        │     │  (management.py lines 832, 1196, 1266, …)        │
│  Token auto-generated via secrets.token_urlsafe  │     │  app.include_router(mgmt_router, prefix="/api")  │
│  if --secure given but --token omitted           │     │                                                  │
└──────────────────────────────────────────────────┘     └──────────────────────────────────────────────────┘
```

---

## Auth Mode Decision (per request, Steps 6–7)

```
                          Incoming request to /api/*
                                     │
                                     ▼
              ┌──────────────────────────────────────────┐
              │  STEP 6 — get_current_user()             │
              │  auth/dependencies.py  (line 19)         │
              │                                          │
              │  Read env vars:                          │
              │    auth0_mode  = FMCP_AUTH0_MODE == "true│
              │    secure_mode = FMCP_SECURE_MODE == "true│
              └──────────────────────────────────────────┘
                                     │
           ┌─────────────────────────┼──────────────────────┐
           │                         │                       │
    both False               auth0_mode True          secure_mode True
    (no auth)                (OAuth2/Auth0)           (Bearer Token)
           │                         │                       │
           ▼                         ▼                       ▼
┌──────────────────┐   ┌──────────────────────────┐  ┌──────────────────────────┐
│  MODE 1          │   │  MODE 3                  │  │  MODE 2                  │
│  Anonymous       │   │  OAuth2 / Auth0          │  │  Bearer Token            │
│  (dev only)      │   │                          │  │                          │
│                  │   │  Token source (in order):│  │  Token source:           │
│  Returns:        │   │  1. Authorization header │  │  Authorization header    │
│  {               │   │  2. httpOnly cookie      │  │  "Authorization: Bearer" │
│   user_id:       │   │     fmcp_auth_token      │  │                          │
│    "anonymous",  │   │                          │  │  Validates via:          │
│   auth_method:   │   │  Validates via:          │  │  auth.py ·               │
│    "none"        │   │  jwt_validator.py ·      │  │  _validate_bearer_token()│
│  }               │   │  validate_oauth_jwt()    │  │  (line 18)               │
│                  │   │  RS256 + JWKS cache      │  │  secrets.compare_digest()│
│  NOTE: server    │   │  (1 hr TTL)              │  │  (constant-time compare) │
│  exits at step 3 │   │                          │  │                          │
│  unless          │   │  Returns:                │  │  Returns:                │
│  --allow-insecure│   │  {                       │  │  {                       │
│  is passed       │   │   user_id: <sub>,        │  │   user_id:               │
│                  │   │   email:   <email>,      │  │    "bearer_<token[:8]>", │
└──────────────────┘   │   name:    <name>,       │  │   email: null,           │
                        │   auth_method: "oauth"   │  │   name:  "Bearer User…", │
                        │  }                       │  │   auth_method: "bearer"  │
                        └──────────────────────────┘  │  }                       │
                                                       └──────────────────────────┘
                                   STEP 7 — result
                                        │
                     ┌──────────────────┴──────────────────┐
                     │                                      │
               Validation passes                    Validation fails
                     │                                      │
                     ▼                                      ▼
          User context dict returned              HTTPException 401
          to /api/* route handler                 raised to client
```

**Mode 4 (Bearer + OAuth, defense in depth):** Pass both `--secure` and `--auth0` together.
Note: in `cli.py` (line 721) this combination currently exits with an error — the `run()` entry point in
`server.py` (line 799) has the same guard. The `create_app()` function accepts an `auth0_mode` param
alongside `secure_mode`, and `dependencies.py` falls through from Auth0 to bearer if both env vars are
`true` and OAuth validation fails (lines 84–116).

---

## Mode Comparison

| Mode | CLI Flag | Env Vars Set | Token Type | Client Sends | Use Case |
|------|----------|--------------|------------|--------------|----------|
| **1 — No Auth** | `--allow-insecure` (required) | neither | none | nothing | Local dev only — server refuses to start without explicit opt-in |
| **2 — Bearer Token** | `--secure [--token TOKEN]` | `FMCP_SECURE_MODE=true`, `FMCP_BEARER_TOKEN=<value>` | Static secret | `Authorization: Bearer <token>` | Railway / CI/CD / API-only access |
| **3 — OAuth2 / Auth0** | `--auth0` | `FMCP_AUTH0_MODE=true` + 4 vars below | RS256 JWT | httpOnly cookie `fmcp_auth_token` (browser) or `Authorization: Bearer <jwt>` (API) | Browser UI, SSO, enterprise, multi-user |
| **4 — Bearer + OAuth** | `--secure --auth0` | both sets above | both active | either | Maximum security (defense in depth) |

**Auth0 required env vars (mode 3 / 4):**
- `FMCP_AUTH0_DOMAIN` — e.g. `your-tenant.auth0.com`
- `FMCP_AUTH0_CLIENT_ID`
- `FMCP_AUTH0_CLIENT_SECRET`
- `FMCP_AUTH0_AUDIENCE` — used as JWT `aud` claim during RS256 validation

---

## Notes

- **No-auth is actively rejected in production.** `cli.py` (line 773) calls `sys.exit(1)` if the
  `serve` command is issued without `--secure`, `--auth0`, or `--allow-insecure`. The `--allow-insecure`
  flag emits three warning log lines before continuing.

- **Token auto-generation.** If `--secure` is passed without `--token`, `cli.py` calls
  `secrets.token_urlsafe(32)`, prints the full token to stdout (never to logs), saves it to
  `~/.fmcp/tokens/current_token.txt` with `chmod 0o600`, and sets it in `os.environ`. Retrieve later
  with `fmcp token show`.

- **Bearer comparison is constant-time.** `auth.py · _validate_bearer_token()` uses
  `secrets.compare_digest()` (line 53) to prevent timing oracle attacks.

- **JWKS cache is 1-hour TTL with auto-rotation handling.** `jwt_validator.py · JWKSCache` fetches
  `https://<domain>/.well-known/jwks.json`. On a `kid not found` error it flushes the cache and retries
  once to accommodate Auth0 key rotation.

- **Bearer + OAuth fallthrough.** When both env vars are `true`, `dependencies.py` first tries
  `validate_oauth_jwt()` (line 84); if that raises and `secure_mode` is also active it falls through to
  bearer validation (line 100). This is the runtime behaviour even though the CLI guard currently blocks
  the combination at startup.

---

## Step Summary

| Step | Name | File | Function | Role |
|------|------|------|----------|------|
| 1 | CLI entry | `fluidmcp/cli/cli.py` | `main()` | Parses `argv`; dispatches `serve` sub-command |
| 2 | Flag parsing | `fluidmcp/cli/cli.py` | `main()` (lines 639–665) | Reads `--secure`, `--auth0`, `--token`, `--allow-insecure` from `argparse` |
| 3 | Config validation | `fluidmcp/cli/cli.py` | `main()` (lines 720–778) | Exits on mutual-exclusion violations, missing Auth0 env vars, or missing auth flag |
| 4 | Env var injection | `fluidmcp/cli/cli.py` | `main()` (lines 685–713) | Writes `FMCP_SECURE_MODE`, `FMCP_BEARER_TOKEN`, `FMCP_AUTH0_MODE` into `os.environ` |
| 5 | App wiring | `fluidmcp/cli/server.py` | `create_app()` (line 145) | Mounts `mgmt_router` (all `/api/*` routes carry `Depends(get_current_user)`) |
| 6 | Mode selection | `fluidmcp/cli/auth/dependencies.py` | `get_current_user()` (line 19) | Reads env vars; picks anonymous / bearer / OAuth branch |
| 6a | Bearer validation | `fluidmcp/cli/auth.py` | `_validate_bearer_token()` (line 18) | `secrets.compare_digest()` constant-time comparison against `FMCP_BEARER_TOKEN` |
| 6b | OAuth validation | `fluidmcp/cli/auth/jwt_validator.py` | `validate_oauth_jwt()` (line 98) | RS256 decode via JWKS cache; extracts `sub`, `email`, `name` from payload |
| 7 | User context | `fluidmcp/cli/auth/dependencies.py` | `get_current_user()` return | Returns `{user_id, email, name, auth_method}` to handler, or raises `HTTP 401` |
