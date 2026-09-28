"""
Qwen vLLM MCP Integration Server
Exposes Qwen model endpoints through FluidMCP
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import requests
import uvicorn
import os

app = FastAPI(title="Qwen vLLM MCP Server")

QWEN_URL = os.environ.get("VLLM_BASE_URL", "http://172.18.0.6:8000/v1")

@app.post("/qwen/v1/chat/completions")
async def chat(request: Request):
    """Chat completions endpoint - proxies to Qwen vLLM"""
    body = await request.json()
    response = requests.post(f"{QWEN_URL}/chat/completions", json=body)
    return JSONResponse(content=response.json())

@app.get("/qwen/v1/models")
async def models():
    """List available models"""
    response = requests.get(f"{QWEN_URL}/models")
    return JSONResponse(content=response.json())

if __name__ == "__main__":
    port = int(os.environ.get("QWEN_MCP_PORT", "8093"))
    uvicorn.run(app, host="0.0.0.0", port=port)
