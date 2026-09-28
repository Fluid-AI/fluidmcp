import json, os
from pathlib import Path
from fluidai_mcp.cli import extract_config_from_file
from fluidai_mcp.services.package_launcher import launch_mcp_using_fastapi_proxy
from fastapi import FastAPI, Request, APIRouter, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import requests as req_lib
import uvicorn

config = extract_config_from_file('/app/config.json')

app = FastAPI(title="FluidMCP + Qwen vLLM", description="FluidMCP with Qwen vLLM integrated")

# Pydantic Models
class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str = "Qwen/Qwen2.5-7B-Instruct"
    messages: List[Message]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 512

# Qwen vLLM Router
qwen_url = os.environ.get("VLLM_BASE_URL", "http://qwen-7b:8000/v1")
qwen_router = APIRouter(prefix="/qwen", tags=["Qwen vLLM"])

@qwen_router.post("/v1/chat/completions")
async def qwen_chat(chat_request: ChatRequest):
    """Send a message to Qwen vLLM model"""
    response = req_lib.post(
        f"{qwen_url}/chat/completions",
        json=chat_request.model_dump()
    )
    return JSONResponse(content=response.json())

@qwen_router.get("/v1/models")
async def qwen_models():
    """List available Qwen models"""
    response = req_lib.get(f"{qwen_url}/models")
    return JSONResponse(content=response.json())

app.include_router(qwen_router)

# MCP Servers
for server_name, server_config in config["mcpServers"].items():
    install_path = Path(server_config["install_path"])
    print(f"Launching {server_name}...")
    pkg_name, router = launch_mcp_using_fastapi_proxy(install_path)
    app.include_router(router)
    print(f"✅ {server_name} ready")

print("🚀 Starting FluidMCP server...")
uvicorn.run(app, host="0.0.0.0", port=8099)
