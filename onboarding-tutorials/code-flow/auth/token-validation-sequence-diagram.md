# Token Validation — Sequence Diagram

> Every authenticated request passes through `get_current_user()` in `dependencies.py`, which branches on environment variables into either an OAuth JWT path (Auth0 RS256 with cached JWKS) or a simple bearer token comparison path.

---

## Participants

| Actor | File | Key Function / Class |
|---|---|---|
| **Client** | — (browser or API caller) | — |
| **FastAPI** | `fluidmcp/cli/server.py` | `create_app()` |
| **get_current_user** | `fluidmcp/cli/auth/dependencies.py` | `get_current_user()` |
| **validate_oauth_jwt** | `fluidmcp/cli/auth/jwt_validator.py` | `validate_oauth_jwt()` |
| **JWKSCache** | `fluidmcp/cli/auth/jwt_validator.py` | `JWKSCache.get_signing_key()` |
| **Auth0 JWKS** | External | `GET https://{domain}/.well-known/jwks.json` |

---

## Path A: OAuth JWT Validation

Triggered when `FMCP_AUTH0_MODE=true`.

```
     Client              FastAPI               get_current_user      validate_oauth_jwt      JWKSCache            Auth0 JWKS
                         server.py             dependencies.py       jwt_validator.py        jwt_validator.py     External
                         create_app()          get_current_user()    validate_oauth_jwt()    JWKSCache
       │                     │                       │                       │                    │                    │
  1.   │─POST /api/servers──►│                       │                       │                    │                    │
       │  Authorization:      │                       │                       │                    │                    │
       │  Bearer <jwt>        │                       │                       │                    │                    │
       │  (or cookie:         │                       │                       │                    │                    │
       │  fmcp_auth_token)    │                       │                       │                    │                    │
       │                     │                       │                       │                    │                    │
  2.   │                     │──Depends(get_current_user)──────────────────►│                    │                    │
       │                     │  (FastAPI resolves dependency                 │                    │                    │
       │                     │   before calling endpoint handler)            │                    │                    │
       │                     │                       │                       │                    │                    │
  3.   │                     │                       │ os.getenv(            │                    │                    │
       │                     │                       │  "FMCP_AUTH0_MODE")   │                    │                    │
       │                     │                       │ → "true"              │                    │                    │
       │                     │                       │ os.getenv(            │                    │                    │
       │                     │                       │  "FMCP_SECURE_MODE")  │                    │                    │
       │                     │                       │ → "false"             │                    │                    │
       │                     │                       │                       │                    │                    │
  4.   │                     │                       │ [Token extraction —   │                    │                    │
       │                     │                       │  priority order:]     │                    │                    │
       │                     │                       │                       │                    │                    │
       │                     │                       │ if credentials:       │                    │                    │
       │                     │                       │   token =             │                    │                    │
       │                     │                       │   credentials         │                    │                    │
       │                     │                       │   .credentials        │                    │                    │
       │                     │                       │   (Authorization      │                    │                    │
       │                     │                       │   header — highest    │                    │                    │
       │                     │                       │   priority)           │                    │                    │
       │                     │                       │                       │                    │                    │
       │                     │                       │ elif "fmcp_auth_token"│                    │                    │
       │                     │                       │    in request.cookies:│                    │                    │
       │                     │                       │   token = request     │                    │                    │
       │                     │                       │   .cookies[           │                    │                    │
       │                     │                       │   "fmcp_auth_token"]  │                    │                    │
       │                     │                       │   (httpOnly cookie —  │                    │                    │
       │                     │                       │   browser OAuth path) │                    │                    │
       │                     │                       │                       │                    │                    │
  5.   │                     │                       │──validate_oauth_jwt(token)────────────────►│                    │
       │                     │                       │                       │                    │                    │
  6.   │                     │                       │                       │ jwt.get_unverified_│                    │
       │                     │                       │                       │ header(token)      │                    │
       │                     │                       │                       │ → extract kid      │                    │
       │                     │                       │                       │   (Key ID)         │                    │
       │                     │                       │                       │                    │                    │
  7.   │                     │                       │                       │──_get_jwks_cache()►│                    │
       │                     │                       │                       │                    │                    │
       │                     │                       │                       │                    │ [Acquire           │
       │                     │                       │                       │                    │  _lock (threading  │
       │                     │                       │                       │                    │  .Lock)]           │
       │                     │                       │                       │                    │                    │
       │                     │                       │                       │                    │ check:             │
       │                     │                       │                       │                    │ _keys is None      │
       │                     │                       │                       │                    │ OR                 │
       │                     │                       │                       │                    │ datetime.utcnow()  │
       │                     │                       │                       │                    │ >= _expires_at     │
       │                     │                       │                       │                    │ (TTL = 3600s)      │
       │                     │                       │                       │                    │                    │
       │                     │    ─────────────────────── CACHE MISS ──────────────────────────  │                    │
       │                     │                       │                       │                    │                    │
  8.   │                     │                       │                       │                    │──GET /.well-known/─►
       │                     │                       │                       │                    │  jwks.json         │
       │                     │                       │                       │                    │  (requests.get,    │
       │                     │                       │                       │                    │   timeout=10s)     │
       │                     │                       │                       │                    │                    │
  9.   │                     │                       │                       │                    │◄─200 OK ───────────
       │                     │                       │                       │                    │  {keys: [...]}     │
       │                     │                       │                       │                    │                    │
 10.   │                     │                       │                       │                    │ _keys = response   │
       │                     │                       │                       │                    │   .json()          │
       │                     │                       │                       │                    │ _expires_at =      │
       │                     │                       │                       │                    │   utcnow() +       │
       │                     │                       │                       │                    │   timedelta(3600s) │
       │                     │                       │                       │                    │ [Release _lock]    │
       │                     │                       │                       │                    │                    │
       │                     │    ─────────────────────── CACHE HIT (subsequent requests) ──────  │                    │
       │                     │                       │                       │                    │                    │
       │                     │                       │                       │                    │ iterate keys[]:    │
       │                     │                       │                       │                    │ find key where     │
       │                     │                       │                       │                    │ key["kid"] == kid  │
       │                     │                       │                       │                    │ → jwk.construct(   │
       │                     │                       │                       │                    │   key_data)        │
       │                     │                       │                       │                    │                    │
       │                     │                       │                       │◄──signing_key──────│                    │
       │                     │                       │                       │                    │                    │
 11.   │                     │                       │                       │ jwt.decode(        │                    │
       │                     │                       │                       │  token,            │                    │
       │                     │                       │                       │  signing_key,      │                    │
       │                     │                       │                       │  algorithms=       │                    │
       │                     │                       │                       │   ["RS256"],       │                    │
       │                     │                       │                       │  audience=         │                    │
       │                     │                       │                       │   FMCP_AUTH0_      │                    │
       │                     │                       │                       │   AUDIENCE,        │                    │
       │                     │                       │                       │  issuer=           │                    │
       │                     │                       │                       │  "https://         │                    │
       │                     │                       │                       │  {domain}/")       │                    │
       │                     │                       │                       │                    │                    │
       │                     │                       │                       │ verify: iss, aud,  │                    │
       │                     │                       │                       │ exp (not expired)  │                    │
       │                     │                       │                       │                    │                    │
 12.   │                     │                       │◄─user dict────────────│                    │                    │
       │                     │                       │  {                    │                    │                    │
       │                     │                       │   user_id: sub,       │                    │                    │
       │                     │                       │   email: email,       │                    │                    │
       │                     │                       │   name: name,         │                    │                    │
       │                     │                       │   auth_method:"oauth" │                    │                    │
       │                     │                       │  }                    │                    │                    │
       │                     │                       │                       │                    │                    │
 13.   │                     │◄─user dict────────────│                       │                    │                    │
       │                     │  (FastAPI injects into│                       │                    │                    │
       │                     │   handler parameter)  │                       │                    │                    │
       │                     │                       │                       │                    │                    │
       │                     │  [handler executes    │                       │                    │                    │
       │                     │   with user["user_id"]│                       │                    │                    │
       │                     │   available]          │                       │                    │                    │
       │                     │                       │                       │                    │                    │
 14.   │◄─200 OK─────────────│                       │                       │                    │                    │
       │                     │                       │                       │                    │                    │
```

---

## Path B: Bearer Token Validation

Triggered when `FMCP_SECURE_MODE=true` and `FMCP_AUTH0_MODE=false` (or unset).

```
     Client              FastAPI               get_current_user
                         server.py             dependencies.py
                         create_app()          get_current_user()
       │                     │                       │
  1.   │─POST /api/servers──►│                       │
       │  Authorization:      │                       │
       │  Bearer <opaque>     │                       │
       │                     │                       │
  2.   │                     │──Depends(get_current_user)──────────────────►│
       │                     │  (FastAPI resolves dependency)               │
       │                     │                       │
  3.   │                     │                       │ os.getenv("FMCP_AUTH0_MODE")
       │                     │                       │ → not "true"  (skip OAuth path)
       │                     │                       │ os.getenv("FMCP_SECURE_MODE")
       │                     │                       │ → "true"
       │                     │                       │
  4.   │                     │                       │ [Token extraction:]
       │                     │                       │ credentials.credentials
       │                     │                       │ (Authorization: Bearer header)
       │                     │                       │ → token = <opaque>
       │                     │                       │
  5.   │                     │                       │ bearer_token =
       │                     │                       │   os.getenv("FMCP_BEARER_TOKEN")
       │                     │                       │
       │                     │                       │ if token == bearer_token:
       │                     │                       │   [NOTE: direct equality check
       │                     │                       │    in dependencies.py; the
       │                     │                       │    separate auth.py module uses
       │                     │                       │    secrets.compare_digest()
       │                     │                       │    for timing-safe comparison]
       │                     │                       │
  6.   │                     │◄─user dict────────────│
       │                     │  {                    │
       │                     │   user_id:            │
       │                     │    "bearer_{token[:8]}",
       │                     │   email: None,        │
       │                     │   name:               │
       │                     │    "Bearer User       │
       │                     │     {token[:8]}",     │
       │                     │   auth_method:"bearer"│
       │                     │  }                    │
       │                     │                       │
  7.   │◄─200 OK─────────────│                       │
       │                     │                       │
```

> Note: `fluidmcp/cli/auth.py` exposes a separate `verify_token()` / `_validate_bearer_token()` dependency pair that is used on endpoints such as `GET /metrics`. That helper uses `secrets.compare_digest()` for constant-time comparison and raises 401 with a `WWW-Authenticate: Bearer` header. `get_current_user()` in `dependencies.py` handles the same bearer path with a direct equality check and is used on data-management endpoints (`/api/servers`, `/api/servers/{id}/start`, etc.).

---

## JWKS Key Rotation Handling

When Auth0 rotates signing keys the `kid` from the JWT header will no longer be present in the cached key set. `validate_oauth_jwt()` handles this transparently with a single retry.

```
     validate_oauth_jwt        JWKSCache            Auth0 JWKS
     jwt_validator.py          jwt_validator.py     External
     validate_oauth_jwt()      JWKSCache
           │                        │                    │
  KR-1.   │──get_signing_key(kid)──►│                    │
           │                        │                    │
           │                        │ iterate cached     │
           │                        │ keys — kid NOT     │
           │                        │ found in any       │
           │                        │ key_data["kid"]    │
           │                        │                    │
  KR-2.   │◄─ValueError: "Key ID    │                    │
           │   {kid} not found       │                    │
           │   in JWKS"              │                    │
           │                        │                    │
           │ [catch ValueError,      │                    │
           │  "Key ID" + "not found" │                    │
           │  in message AND         │                    │
           │  retry_on_key_error]    │                    │
           │                        │                    │
  KR-3.   │ Force-invalidate cache: │                    │
           │──cache._keys = None────►│                    │
           │──cache._expires_at=None►│                    │
           │  (bypasses TTL check)   │                    │
           │                        │                    │
  KR-4.   │ retry: validate_oauth_jwt(token,             │
           │         retry_on_key_error=False)            │
           │                        │                    │
  KR-5.   │──get_signing_key(kid)──►│                    │
           │                        │                    │
           │                        │ _keys is None →    │
           │                        │ _refresh_keys()    │
           │                        │                    │
  KR-6.   │                        │──GET /.well-known/─►
           │                        │  jwks.json         │
           │                        │                    │
  KR-7.   │                        │◄─200 OK ───────────
           │                        │  (new public keys) │
           │                        │                    │
  KR-8.   │                        │ update _keys       │
           │                        │ update _expires_at │
           │                        │                    │
  KR-9.   │                        │ search for kid     │
           │                        │ in refreshed set   │
           │                        │                    │
           │  [kid found] ──────────│                    │
  KR-10.  │◄─signing_key───────────│                    │
           │                        │                    │
           │  [kid still missing]   │                    │
  KR-10b. │◄─ValueError: "Key ID   │                    │
           │   {kid} not found       │                    │
           │   in JWKS"              │                    │
           │  (retry_on_key_error=   │                    │
           │   False → re-raise,     │                    │
           │   → 401 to client)      │                    │
           │                        │                    │
```

---

## Anonymous Mode (No Auth)

When both `FMCP_AUTH0_MODE` and `FMCP_SECURE_MODE` are unset or not `"true"`, `get_current_user()` short-circuits immediately without inspecting the token:

```
get_current_user()

  if not auth0_mode and not secure_mode:
      return {
          "user_id":    "anonymous",
          "email":      None,
          "name":       "Anonymous",
          "auth_method":"none"
      }
```

---

## Error Cases

| Condition | Exception / Source | HTTP Status | Response Body |
|---|---|---|---|
| No token in header and no cookie | `get_current_user()` — `if not token` | 401 | `"Authentication required. Please provide a valid token."` |
| JWT `exp` claim is in the past | `jose.ExpiredSignatureError` → caught in `validate_oauth_jwt()` | 401 (re-raised as HTTPException) | `"Invalid or expired OAuth token: Token has expired"` |
| JWT `iss` or `aud` mismatch | `jose.JWTClaimsError` → `ValueError("Token claims validation failed: ...")` | 401 | `"Invalid or expired OAuth token: Token claims validation failed: ..."` |
| JWT structurally invalid | `jose.JWTError` → `ValueError("Token validation failed: ...")` | 401 | `"Invalid or expired OAuth token: Token validation failed: ..."` |
| Bearer token mismatch | `get_current_user()` — falls through both auth blocks | 401 | `"Invalid or expired token"` |
| `FMCP_BEARER_TOKEN` not set in secure mode | `get_current_user()` | 500 | `"Bearer token authentication is enabled but FMCP_BEARER_TOKEN is not set"` |
| Unknown `kid` after cache refresh | `JWKSCache.get_signing_key()` → `ValueError` | 401 (via re-raise) | `"Invalid or expired OAuth token: Key ID {kid} not found in JWKS"` |
| Auth0 JWKS endpoint unreachable | `requests.RequestException` in `_refresh_keys()` | 401 | `"Invalid or expired OAuth token: Failed to fetch JWKS from ...: ..."` |

---

## Notes

**Token source priority (actual code order in `get_current_user()`):**
1. `Authorization: Bearer` header (`credentials.credentials`) — checked first, highest priority.
2. `request.cookies["fmcp_auth_token"]` — checked only when no `Authorization` header is present. Used by browser-based OAuth flows after the `/auth/callback` endpoint sets an httpOnly cookie.

**JWKS cache TTL:**
- Default is **3600 seconds (1 hour)**, set in `JWKSCache.__init__(ttl_seconds=3600)`.
- Cache is a module-level singleton (`_jwks_cache`) protected by a second `threading.Lock` (`_cache_lock`) for safe initialisation across threads.
- Per-read access inside `get_signing_key()` is protected by a separate per-instance `self._lock`.

**Constant-time comparison:**
- `fluidmcp/cli/auth.py` — `_validate_bearer_token()` uses `secrets.compare_digest(credentials.credentials, bearer_token)`, which takes identical time regardless of where strings first differ, preventing timing oracle attacks.
- `fluidmcp/cli/auth/dependencies.py` — `get_current_user()` uses a direct `token == bearer_token` equality check for the same bearer comparison. For production hardening this should be replaced with `secrets.compare_digest()`.

**Dual auth module design:**
- `fluidmcp/cli/auth.py` — `verify_token()` / `get_token()`: legacy/simple bearer-only Depends used on `/metrics` and legacy routes.
- `fluidmcp/cli/auth/dependencies.py` — `get_current_user()`: unified OAuth + bearer Depends used on all management API routes in `api/management.py`.

**JWT library:** `python-jose` (`from jose import jwt, jwk`). RS256 is the only accepted algorithm, which prevents the "algorithm confusion" attack class.

---

## Interaction Summary

| Step | From | To | Call / Action | Returns |
|---|---|---|---|---|
| 1 | Client | FastAPI | `POST /api/servers` with `Authorization: Bearer <token>` | — |
| 2 | FastAPI | get_current_user | FastAPI resolves `Depends(get_current_user)` | — |
| 3 | get_current_user | — | `os.getenv("FMCP_AUTH0_MODE")`, `os.getenv("FMCP_SECURE_MODE")` | mode booleans |
| 4 | get_current_user | — | Extract token from `credentials.credentials` (header) or `request.cookies["fmcp_auth_token"]` (cookie) | `token` string |
| 5 | get_current_user | validate_oauth_jwt | `await validate_oauth_jwt(token)` | user dict or raises |
| 6 | validate_oauth_jwt | — | `jwt.get_unverified_header(token)` | `{"kid": "...", ...}` |
| 7 | validate_oauth_jwt | JWKSCache | `_get_jwks_cache()` then `cache.get_signing_key(kid)` | signing key or raises |
| 8 | JWKSCache | Auth0 JWKS | `requests.get(jwks_url, timeout=10)` (on cache miss / TTL expiry) | `{"keys": [...]}` |
| 9 | JWKSCache | — | Store `_keys`, set `_expires_at = utcnow() + timedelta(3600s)` | — |
| 10 | JWKSCache | validate_oauth_jwt | `jwk.construct(key_data)` for matched `kid` | signing key |
| 11 | validate_oauth_jwt | — | `jwt.decode(token, signing_key, algorithms=["RS256"], audience=..., issuer=...)` | JWT payload dict |
| 12 | validate_oauth_jwt | get_current_user | Return `{"user_id": sub, "email": email, "name": name, "auth_method": "oauth"}` | user dict |
| 13 | get_current_user | FastAPI | Return user dict | injected into handler |
| 14 | FastAPI | Client | Endpoint handler response | `200 OK` |
| B-5 | get_current_user | — | `token == bearer_token` (bearer path, `FMCP_SECURE_MODE=true`) | bool |
| B-6 | get_current_user | FastAPI | Return `{"user_id": "bearer_{token[:8]}", "email": None, "name": "Bearer User ...", "auth_method": "bearer"}` | user dict |
| KR-3 | validate_oauth_jwt | JWKSCache | `cache._keys = None; cache._expires_at = None` (force-invalidate on key rotation) | — |
| KR-4 | validate_oauth_jwt | validate_oauth_jwt | `await validate_oauth_jwt(token, retry_on_key_error=False)` (recursive retry) | user dict or raises |
