#!/usr/bin/env python3
"""
Mock vLLM Server for Testing FluidMCP Integration
Simulates vLLM's OpenAI-compatible API without requiring GPU
"""

from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uvicorn
import time
import json

app = FastAPI(title="Mock vLLM Server")

class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    messages: List[Message]
    model: Optional[str] = "mock-model"
    max_tokens: Optional[int] = 100
    temperature: Optional[float] = 0.7
    stream: Optional[bool] = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[str] = None

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """Mock chat completion endpoint"""

    # Simulate processing time
    time.sleep(0.1)

    # Get the last user message
    user_message = ""
    for msg in reversed(request.messages):
        if msg.role == "user":
            user_message = msg.content
            break

    # Generate a mock response
    mock_response = f"Mock response to: {user_message[:50]}..."

    if request.stream:
        # Return streaming response format
        return {
            "id": "chatcmpl-mock123",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": request.model,
            "choices": [{
                "index": 0,
                "delta": {"content": mock_response},
                "finish_reason": None
            }]
        }
    else:
        # Return standard completion format
        return {
            "id": "chatcmpl-mock123",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": mock_response
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30
            }
        }

@app.get("/v1/models")
async def list_models():
    """Mock models endpoint"""
    return {
        "object": "list",
        "data": [
            {
                "id": "mock-model",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "mock"
            }
        ]
    }

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}

if __name__ == "__main__":
    print("Starting Mock vLLM Server on port 8001...")
    print("This simulates vLLM without requiring GPU")
    print("\nTest with:")
    print("  curl http://localhost:8001/v1/models")
    print("  curl -X POST http://localhost:8001/v1/chat/completions \\")
    print("    -H 'Content-Type: application/json' \\")
    print("    -d '{\"messages\": [{\"role\": \"user\", \"content\": \"Hello\"}]}'")

    uvicorn.run(app, host="0.0.0.0", port=8001)
