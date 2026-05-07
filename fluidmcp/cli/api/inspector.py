import uuid
import asyncio
import time
import json
import ipaddress
import hashlib
import base64
import os
import secrets
from typing import Dict, Any, Optional, AsyncGenerator
from urllib.parse import urlparse, urlencode

import httpx
from fastapi import APIRouter, HTTPException, Body, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from loguru import logger

from ..services.inspector_session import InspectorSession
from ..auth import verify_token

router = APIRouter(dependencies=[Depends(verify_token)])

# In-memory session store: session_id -> InspectorSession
sessions: Dict[str, InspectorSession] = {}

SESSION_TTL = 1800   # 30 minutes in seconds
CLEANUP_INTERVAL = 300  # Run cleanup every 5 minutes

# Pending OAuth exchanges: state -> { verifier, token_url, client_id, redirect_uri, result? }
# Entries expire after OAUTH_STATE_TTL seconds.
oauth_pending: Dict[str, Dict[str, Any]] = {}
OAUTH_STATE_TTL = 600  # 10 minutes


# ─── Request Models ────────────────────────────────────────────────────────────

class AuthConfig(BaseModel):
    type: str = "none"        # "none" | "bearer" | "header" | "oauth"
    token: Optional[str] = None
    # OAuth fields (only used when type == "oauth")
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_at: Optional[float] = None   # Unix timestamp
    token_url: Optional[str] = None      # token endpoint for refresh
    client_id: Optional[str] = None


class OAuthAuthorizeRequest(BaseModel):
    authorization_url: str
    token_url: str
    client_id: str
    redirect_uri: str
    scopes: Optional[str] = ""   # space-separated


class OAuthRefreshRequest(BaseModel):
    pass  # uses credentials stored in the session


class ConnectRequest(BaseModel):
    url: Optional[str] = None        # required for http / sse
    command: Optional[str] = None    # required for stdio
    transport: str = "http"          # "http" | "sse" | "stdio"
    auth: Optional[AuthConfig] = None
    headers: Optional[Dict[str, str]] = None
    env_vars: Optional[Dict[str, str]] = None
    timeout: Optional[int] = 10000  # ms

class ChatRequest(BaseModel):
    message: str
    chat_history: Optional[list] = Field(default_factory=list)
    provider: Optional[str] = "groq"
    model: Optional[str] = None
    api_key: Optional[str] = None
    system_prompt: Optional[str] = None

class ReadResourceRequest(BaseModel):
    uri: str

# ─── URL Validation ────────────────────────────────────────────────────────────

def _validate_mcp_url(url: str) -> None:
    """Block non-HTTP schemes and connections to private/internal network ranges."""
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(400, "Invalid URL")

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, "Only http/https URLs are allowed")

    host = parsed.hostname or ""
    if not host:
        raise HTTPException(400, "URL must include a host")

    try:
        addr = ipaddress.ip_address(host)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            raise HTTPException(400, "Connections to private/internal addresses are not allowed")
    except ValueError:
        pass  # hostname, not a bare IP — DNS rebinding is out of scope here


# ─── TTL Cleanup ───────────────────────────────────────────────────────────────

async def cleanup_sessions():
    """
    Background task: remove sessions that have been idle for SESSION_TTL seconds.
    Runs every CLEANUP_INTERVAL seconds.
    """
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        now = time.time()

        expired = [
            sid for sid, session in list(sessions.items())
            if now - session.last_used > SESSION_TTL
        ]

        for sid in expired:
            try:
                await sessions[sid].close()
                logger.info(f"Inspector: expired session {sid}")
            except Exception:
                pass
            sessions.pop(sid, None)


# ─── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/inspector/connect")
async def connect_server(body: ConnectRequest):
    """
    Connect to an external MCP server temporarily.

    Performs the MCP initialize handshake, fetches the tool list, and returns
    everything in one response so the frontend avoids a second round trip.

    The session is stored in memory and expires after SESSION_TTL seconds of
    inactivity. Nothing is persisted to MongoDB.
    """
    target = body.command if body.transport == "stdio" else body.url

    if body.transport == "stdio":
        if not body.command:
            raise HTTPException(400, "command is required for stdio transport")
    else:
        if not body.url:
            raise HTTPException(400, "url is required")
        _validate_mcp_url(body.url)

    auth_dict = body.auth.model_dump() if body.auth else {}

    session = InspectorSession(
        url=body.url or "stdio://local",
        command=body.command,
        transport=body.transport,
        auth=auth_dict,
        headers=body.headers,
        env_vars=body.env_vars,
        timeout=body.timeout or 10000,
    )

    # Perform MCP initialize handshake
    try:
        server_info = await session.initialize()
    except Exception as e:
        await session.close()
        logger.warning(f"Inspector: failed to connect to {target!r} — {e}")
        raise HTTPException(502, f"Failed to connect to MCP server: {str(e)}")

    # Fetch tools immediately so frontend gets everything in one response
    try:
        tools = await session.list_tools()
    except Exception as e:
        await session.close()
        logger.warning(f"Inspector: connected but failed to list tools for {target!r} — {e}")
        raise HTTPException(502, f"Connected but failed to fetch tools: {str(e)}")

    session_id = str(uuid.uuid4())
    sessions[session_id] = session

    logger.info(f"Inspector: new session {session_id} for {target!r} ({body.transport}), {len(tools)} tools")

    return {
        "session_id": session_id,
        "server_info": server_info,
        "tools": tools
    }


@router.get("/inspector/{session_id}/tools")
async def list_tools(session_id: str):
    """
    Refresh the tool list for an active session.
    Updates last_used to keep the session alive.
    """
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")

    try:
        tools = await session.list_tools()
        return {"tools": tools, "count": len(tools)}
    except Exception as e:
        logger.error(f"Inspector: list_tools failed for session {session_id} — {e}")
        raise HTTPException(500, f"Failed to fetch tools: {str(e)}")


@router.post("/inspector/{session_id}/tools/{tool_name}/run")
async def run_tool(
    session_id: str,
    tool_name: str,
    arguments: Dict[str, Any] = Body(default={})
):
    """
    Execute a tool on the connected MCP server.

    Returns the tool result on success, or a structured error object on failure
    so the frontend OutputViewer can display it gracefully.
    Updates last_used to keep the session alive.
    """
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")

    try:
        result = await session.call_tool(tool_name, arguments)
        return {"success": True, "result": result}
    except Exception as e:
        logger.warning(f"Inspector: tool '{tool_name}' failed on session {session_id} — {e}")
        # Return structured error instead of raising — OutputViewer handles this gracefully
        return {
            "success": False,
            "error": str(e),
            "tool": tool_name
        }


@router.delete("/inspector/{session_id}")
async def disconnect(session_id: str):
    """
    Disconnect from an MCP server and remove the session.
    Called explicitly by the Disconnect button in the UI.
    """
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")

    try:
        await session.close()
    except Exception as e:
        logger.warning(f"Inspector: error closing session {session_id} — {e}")
    finally:
        sessions.pop(session_id, None)

    logger.info(f"Inspector: session {session_id} disconnected")
    return {"status": "disconnected"}


@router.get("/inspector/{session_id}/logs")
async def get_logs(session_id: str):
    """
    Get the execution logs for an active session.
    Updates last_used to keep the session alive.
    """
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")

    session.last_used = time.time()
    return {"logs": session.logs}

@router.get("/inspector/{session_id}/resources")
async def list_resources(session_id: str):
    """
    List all resources available on the connected MCP server.
    Also used to discover widget resources (ui:// URIs).
    """
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")

    resources, templates = [], []
    try:
        resources = await session.list_resources()
    except Exception as e:
        if "Method not found" not in str(e):
            logger.warning(f"Inspector: list_resources failed for session {session_id} — {e}")
    try:
        templates = await session.list_resource_templates()
    except Exception as e:
        if "Method not found" not in str(e):
            logger.warning(f"Inspector: list_resource_templates failed for session {session_id} — {e}")
    combined = resources + templates
    return {"resources": combined, "count": len(combined)}


@router.post("/inspector/{session_id}/resources/read")
async def read_resource(session_id: str, body: ReadResourceRequest):
    """
    Read a resource by URI from the connected MCP server.
    Used to fetch widget HTML for ui:// resource URIs.
    """
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")

    try:
        content = await session.read_resource(body.uri)
        if isinstance(content, dict) and "contents" in content:
            return content
        if isinstance(content, list):
            return {"contents": content}
        return {"contents": [content]}
    except Exception as e:
        logger.error(f"Inspector: read_resource failed for session {session_id} — {e}")
        raise HTTPException(500, f"Failed to read resource: {str(e)}")


class GetPromptRequest(BaseModel):
    name: str
    arguments: Optional[dict] = Field(default_factory=dict)


@router.get("/inspector/{session_id}/prompts")
async def list_prompts(session_id: str):
    """List all prompts available on the connected MCP server."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")
    try:
        prompts = await session.list_prompts()
        return {"prompts": prompts, "count": len(prompts)}
    except Exception as e:
        if "Method not found" in str(e):
            return {"prompts": [], "count": 0}
        logger.error(f"Inspector: list_prompts failed for session {session_id} — {e}")
        raise HTTPException(500, f"Failed to fetch prompts: {str(e)}")


@router.post("/inspector/{session_id}/prompts/get")
async def get_prompt(session_id: str, body: GetPromptRequest):
    """Get a prompt by name with optional arguments."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")
    try:
        result = await session.get_prompt(body.name, body.arguments or {})
        return result
    except Exception as e:
        logger.error(f"Inspector: get_prompt failed for session {session_id} — {e}")
        raise HTTPException(500, f"Failed to get prompt: {str(e)}")


@router.get("/inspector/{session_id}/export")
async def export_server(session_id: str):
    """
    Export server config, tools, resources, and prompts as a JSON snapshot.
    Auth tokens are stripped — only the auth type is included.
    """
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")

    session.last_used = time.time()

    tools, resources, prompts = [], [], []
    try:
        tools = await session.list_tools()
    except Exception:
        pass
    try:
        resources = await session.list_resources()
    except Exception:
        pass
    try:
        prompts = await session.list_prompts()
    except Exception:
        pass

    # Strip auth tokens — only expose the type so the recipient knows what auth is needed
    safe_auth = {"type": session.auth.get("type", "none")} if session.auth else {"type": "none"}

    return {
        "exportedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "serverInfo": getattr(session, "server_info", {}),
        "url": session.url,
        "transport": session.transport,
        "auth": safe_auth,
        "tools": tools,
        "resources": resources,
        "prompts": prompts,
    }


def _pkce_pair() -> tuple[str, str]:
    """Generate a PKCE (code_verifier, code_challenge) pair using S256 method."""
    verifier = base64.urlsafe_b64encode(os.urandom(40)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _validate_oauth_url(url: str, field: str) -> None:
    """Ensure an OAuth endpoint URL is a valid public https URL."""
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(400, f"Invalid {field}")
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, f"{field} must be http/https")
    host = parsed.hostname or ""
    if not host:
        raise HTTPException(400, f"{field} must include a host")
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            raise HTTPException(400, f"{field} must not point to a private/internal address")
    except ValueError:
        pass  # hostname — fine


@router.post("/inspector/oauth/authorize")
async def oauth_authorize(body: OAuthAuthorizeRequest):
    """
    Start an OAuth 2.0 PKCE flow.

    Generates a PKCE verifier/challenge pair and a random state token,
    stores them in oauth_pending, and returns the full authorization URL
    the frontend should open in a popup.
    """
    _validate_oauth_url(body.authorization_url, "authorization_url")
    _validate_oauth_url(body.token_url, "token_url")

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(24)

    oauth_pending[state] = {
        "verifier": verifier,
        "token_url": body.token_url,
        "client_id": body.client_id,
        "redirect_uri": body.redirect_uri,
        "created_at": time.time(),
        "result": None,
    }

    params = {
        "response_type": "code",
        "client_id": body.client_id,
        "redirect_uri": body.redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if body.scopes:
        params["scope"] = body.scopes

    redirect_url = f"{body.authorization_url}?{urlencode(params)}"
    return {"redirect_url": redirect_url, "state": state}


@router.get("/inspector/oauth/callback")
async def oauth_callback(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """
    OAuth 2.0 redirect callback.

    The authorization server redirects here after the user approves or denies
    access.  This endpoint exchanges the authorization code for tokens and
    stores them in oauth_pending so the frontend can poll for the result.

    On success the browser is redirected to /ui/oauth-callback so the popup
    page can read the result via window.opener.postMessage and close itself.
    """
    from fastapi.responses import HTMLResponse

    if error:
        return HTMLResponse(_oauth_popup_html(None, error))

    if not state or not code:
        return HTMLResponse(_oauth_popup_html(None, "missing_code_or_state"))

    entry = oauth_pending.get(state)
    if not entry:
        return HTMLResponse(_oauth_popup_html(None, "invalid_or_expired_state"))

    # Expire stale entries
    if time.time() - entry["created_at"] > OAUTH_STATE_TTL:
        oauth_pending.pop(state, None)
        return HTMLResponse(_oauth_popup_html(None, "state_expired"))

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                entry["token_url"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": entry["redirect_uri"],
                    "client_id": entry["client_id"],
                    "code_verifier": entry["verifier"],
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            token_data = resp.json()
    except Exception as e:
        logger.warning(f"OAuth callback: token exchange failed — {e}")
        oauth_pending.pop(state, None)
        return HTMLResponse(_oauth_popup_html(None, f"token_exchange_failed: {e}"))

    result = {
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token"),
        "expires_at": time.time() + token_data.get("expires_in", 3600),
        "token_url": entry["token_url"],
        "client_id": entry["client_id"],
    }
    entry["result"] = result
    logger.info(f"OAuth callback: token exchange succeeded for state={state[:8]}…")
    return HTMLResponse(_oauth_popup_html(result, None))


@router.get("/inspector/oauth/result/{state}")
async def oauth_result(state: str):
    """
    Poll for an OAuth token result after the popup has completed.

    The frontend opens the authorization URL in a popup.  While the popup is
    open the frontend polls this endpoint until a result appears (max
    OAUTH_STATE_TTL seconds).  Once consumed the entry is removed.
    """
    entry = oauth_pending.get(state)
    if not entry:
        raise HTTPException(404, "OAuth state not found or already consumed")
    if time.time() - entry["created_at"] > OAUTH_STATE_TTL:
        oauth_pending.pop(state, None)
        raise HTTPException(410, "OAuth state expired")
    if entry["result"] is None:
        return {"status": "pending"}
    result = entry.pop("result")
    oauth_pending.pop(state, None)
    return {"status": "complete", "token": result}


@router.post("/inspector/{session_id}/oauth/refresh")
async def oauth_refresh(session_id: str):
    """
    Manually trigger an OAuth token refresh for an active session.
    Useful when the frontend detects imminent expiry and wants to refresh
    before the next tool call.
    """
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")
    if session.auth.get("type") != "oauth":
        raise HTTPException(400, "Session does not use OAuth auth")
    try:
        await session._auto_refresh()
    except Exception as e:
        raise HTTPException(502, f"Token refresh failed: {e}")
    return {
        "access_token": session.auth.get("access_token"),
        "expires_at": session.auth.get("expires_at"),
    }


def _oauth_popup_html(token: Optional[dict], error: Optional[str]) -> str:
    """
    Minimal HTML page returned to the OAuth popup after the callback.
    Posts a message to the opener window then closes the popup.
    """
    if error:
        import html as _html
        payload = json.dumps({"error": _html.escape(str(error))})
    else:
        payload = json.dumps({"token": token})
    return f"""<!DOCTYPE html>
<html>
<head><title>OAuth Callback</title></head>
<body>
<script>
  try {{
    window.opener.postMessage({payload}, window.location.origin);
  }} catch(e) {{}}
  window.close();
</script>
<p>Authentication complete. You may close this window.</p>
</body>
</html>"""


@router.post("/inspector/{session_id}/chat/stream")
async def chat_stream(session_id: str, body: ChatRequest):
    """
    Streaming chat endpoint — returns SSE events as the LLM generates tokens.

    Event types:
      {"type": "thinking"}                          — LLM is deciding which tool to use
      {"type": "token", "content": "..."}           — streamed response token
      {"type": "tool_call", "tool_name": "...", "params": {...}}  — tool selected
      {"type": "clarification", "message": "..."}   — LLM couldn't pick a tool
      {"type": "error", "message": "..."}           — unrecoverable error
      {"type": "done"}                              — stream complete
    """
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")

    session.last_used = time.time()

    async def event_generator() -> AsyncGenerator[str, None]:
        def sse(data: dict) -> str:
            return f"data: {json.dumps(data)}\n\n"

        try:
            from ..services.inspector_agent import stream_tool_selection

            tools = await session.list_tools()

            if not tools:
                yield sse({"type": "clarification", "message": "No tools available on this server."})
                yield sse({"type": "done"})
                return

            yield sse({"type": "thinking"})

            tool_name = None
            tool_params = {}
            clarification = None

            async for event in stream_tool_selection(
                message=body.message,
                tools=tools,
                chat_history=body.chat_history or [],
                provider=body.provider or "groq",
                model=body.model,
                api_key=body.api_key,
                system_prompt=body.system_prompt,
            ):
                event_type = event.get("type")

                if event_type == "token":
                    yield sse(event)

                elif event_type == "tool_call":
                    tool_name = event.get("tool_name")
                    tool_params = event.get("params", {})
                    available_names = {t["name"] for t in tools}
                    if tool_name and tool_name in available_names:
                        yield sse(event)
                    else:
                        clarification = "Could not determine which tool to run."

                elif event_type == "clarification":
                    clarification = event.get("message", "Could not determine which tool to run.")

            if clarification:
                yield sse({"type": "clarification", "message": clarification})
            elif tool_name:
                session.add_log("chat", f"User: {body.message} → tool selected: {tool_name}")

            yield sse({"type": "done"})

        except Exception as e:
            logger.error(f"Inspector chat stream error: {e}")
            yield sse({"type": "error", "message": "Unable to determine which tool to run."})
            yield sse({"type": "done"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/inspector/{session_id}/chat")
async def chat_with_tools(session_id: str, body: ChatRequest):
    """
    Chat endpoint that asks the LLM which tool to run.
    It DOES NOT execute the tool — frontend does that.
    """

    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")

    session.last_used = time.time()

    try:
        from ..services.inspector_agent import choose_tool_with_llm

        tools = await session.list_tools()

        if not tools:
            return {
                "clarification_needed": True,
                "message": "No tools available on this server."
            }

        agent_result = await choose_tool_with_llm(
            body.message,
            tools,
            chat_history=body.chat_history or [],
            provider=body.provider or "groq",
            model=body.model,
            api_key=body.api_key,
            system_prompt=body.system_prompt,
        )

        # Validate the response has the expected fields
        tool_name = agent_result.get("tool_name")
        available_names = {t["name"] for t in tools}
        if not tool_name or not isinstance(tool_name, str) or tool_name not in available_names:
            return {
                "clarification_needed": True,
                "message": "Could not determine which tool to run."
            }

        session.add_log(
            "chat",
            f"User: {body.message} → tool selected: {tool_name}"
        )

        return {
            "tool_name": tool_name,
            "params": agent_result.get("params", {})
        }

    except Exception as e:
        logger.error(f"Inspector chat error: {e}")

        return {
            "clarification_needed": True,
            "message": "Unable to determine which tool to run."
        }
