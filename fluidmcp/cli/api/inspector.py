import uuid
import asyncio
import time
import ipaddress
from typing import Dict, Any, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Body, Depends
from pydantic import BaseModel, Field
from loguru import logger

from ..services.inspector_session import InspectorSession
from ..auth import verify_token
from ..services.inspector_agent import choose_tool_with_llm

router = APIRouter(dependencies=[Depends(verify_token)])

# In-memory session store: session_id -> InspectorSession
sessions: Dict[str, InspectorSession] = {}

SESSION_TTL = 1800   # 30 minutes in seconds
CLEANUP_INTERVAL = 300  # Run cleanup every 5 minutes


# ─── Request Models ────────────────────────────────────────────────────────────

class AuthConfig(BaseModel):
    type: str = "none"        # "none" | "bearer"
    token: Optional[str] = None


class ConnectRequest(BaseModel):
    url: str
    transport: str = "http"   # "http" | "sse" | "stdio"
    auth: Optional[AuthConfig] = None
    headers: Optional[Dict[str, str]] = None
    env_vars: Optional[Dict[str, str]] = None
    timeout: Optional[int] = 10000  # ms

class ChatRequest(BaseModel):
    message: str
    chat_history: Optional[list] = Field(default_factory=list)

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
    if not body.url:
        raise HTTPException(400, "url is required")

    _validate_mcp_url(body.url)

    auth_dict = body.auth.model_dump() if body.auth else {}

    session = InspectorSession(
        url=body.url,
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
        logger.warning(f"Inspector: failed to connect to {body.url} — {e}")
        raise HTTPException(502, f"Failed to connect to MCP server: {str(e)}")

    # Fetch tools immediately so frontend gets everything in one response
    try:
        tools = await session.list_tools()
    except Exception as e:
        await session.close()
        logger.warning(f"Inspector: connected but failed to list tools for {body.url} — {e}")
        raise HTTPException(502, f"Connected but failed to fetch tools: {str(e)}")

    session_id = str(uuid.uuid4())
    sessions[session_id] = session

    logger.info(f"Inspector: new session {session_id} for {body.url} ({body.transport}), {len(tools)} tools")

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
        # Lazy import — avoids server startup failure when GROQ_API_KEY is absent
        from ..services.inspector_agent import choose_tool_with_llm

        tools = await session.list_tools()

        if not tools:
            return {
                "clarification_needed": True,
                "message": "No tools available on this server."
            }

        # Call the Groq agent, passing chat history for multi-turn context
        agent_result = await choose_tool_with_llm(
            body.message, tools, chat_history=body.chat_history or []
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
