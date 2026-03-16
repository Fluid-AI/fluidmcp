import uuid
import asyncio
import time
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from loguru import logger

from ..services.inspector_session import InspectorSession

router = APIRouter()

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
    chat_history: Optional[list] = []

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
    Chat endpoint that selects which tool to run.
    It DOES NOT execute the tool — frontend does that.
    """

    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")

    session.last_used = time.time()

    try:
        tools = await session.list_tools()

        if not tools:
            return {
                "clarification_needed": True,
                "message": "No tools available on this server."
            }

        message = body.message.lower()

        # Simple heuristic: choose tool whose name appears in message
        chosen_tool = None
        for tool in tools:
            if tool["name"].lower() in message:
                chosen_tool = tool
                break

        # fallback to first tool
        if not chosen_tool:
            chosen_tool = tools[0]

        params = {}

        # Example heuristic for time tools
        if "timezone" in str(chosen_tool.get("inputSchema", {})).lower():

            # naive extraction
            if "tokyo" in message:
                params["timezone"] = "Asia/Tokyo"
            elif "london" in message:
                params["timezone"] = "Europe/London"
            elif "new york" in message:
                params["timezone"] = "America/New_York"

        session.add_log(
            "chat",
            f"User: {body.message} → tool selected: {chosen_tool['name']}"
        )

        return {
            "tool_name": chosen_tool["name"],
            "params": params
        }

    except Exception as e:
        logger.error(f"Inspector chat error: {e}")

        return {
            "clarification_needed": True,
            "message": "Unable to determine which tool to run."
        }