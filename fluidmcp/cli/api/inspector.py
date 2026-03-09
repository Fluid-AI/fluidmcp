import uuid
import asyncio
import time
from typing import Dict, Any

from fastapi import APIRouter, HTTPException

from ..services.inspector_session import InspectorSession

router = APIRouter()

sessions: Dict[str, InspectorSession] = {}

SESSION_TTL = 1800
CLEANUP_INTERVAL = 300


async def cleanup_sessions():
    """Remove expired inspector sessions."""
    while True:
        now = time.time()

        expired = [
            sid for sid, session in sessions.items()
            if now - session.last_used > SESSION_TTL
        ]

        for sid in expired:
            try:
                await sessions[sid].close()
            except Exception:
                pass

            del sessions[sid]

        await asyncio.sleep(CLEANUP_INTERVAL)


@router.post("/inspector/connect")
async def connect_server(body: Dict[str, Any]):

    url = body.get("url")
    transport = body.get("transport", "http")

    if not url:
        raise HTTPException(400, "url is required")

    # TODO: replace with real MCP client creation
    client = None

    try:

        # Example placeholder
        server_info = {
            "name": "Unknown MCP Server",
            "version": "unknown"
        }

        session_id = str(uuid.uuid4())

        session = InspectorSession(client, url, transport)
        sessions[session_id] = session

        tools = []

        return {
            "session_id": session_id,
            "server_info": server_info,
            "tools": tools
        }

    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/inspector/{session_id}/tools")
async def list_tools(session_id: str):

    session = sessions.get(session_id)

    if not session:
        raise HTTPException(404, "Session not found")

    try:
        tools = await session.list_tools()
        return tools
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/inspector/{session_id}/tools/{tool_name}/run")
async def run_tool(session_id: str, tool_name: str, params: Dict[str, Any]):

    session = sessions.get(session_id)

    if not session:
        raise HTTPException(404, "Session not found")

    try:
        result = await session.call_tool(tool_name, params)
        return result
    except Exception as e:
        return {
            "error": True,
            "message": str(e)
        }


@router.delete("/inspector/{session_id}")
async def disconnect(session_id: str):

    session = sessions.get(session_id)

    if not session:
        raise HTTPException(404, "Session not found")

    try:
        await session.close()
    finally:
        del sessions[session_id]

    return {"status": "disconnected"}