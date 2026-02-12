# vLLM Function Calling (OpenAI-Compatible Pass-Through)

FluidMCP supports OpenAI-compatible function calling for vLLM models by passing tool schemas and responses transparently between clients and the vLLM inference server.

## Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Quick Start](#quick-start)
- [Request Format](#request-format)
- [Response Format](#response-format)
- [Complete Example](#complete-example)
- [MCP Tools Integration](#mcp-tools-integration)
- [Streaming Support](#streaming-support)
- [Troubleshooting](#troubleshooting)

---

## Overview

FluidMCP's vLLM proxy provides **transparent pass-through** of OpenAI function calling parameters:

1. **Client sends** `tools` parameter with function schemas
2. **FluidMCP forwards** the request directly to vLLM
3. **vLLM returns** `tool_calls` in the response
4. **Client receives** the tool_calls and **manually executes** them
5. **Client sends** tool results back in the next message

**What FluidMCP does:**
- ✅ Forwards `tools`, `tool_choice`, and other OpenAI parameters to vLLM
- ✅ Returns vLLM's response including `tool_calls` unchanged
- ✅ Supports streaming mode with function calling

**What FluidMCP does NOT do:**
- ❌ Does not automatically execute tools
- ❌ Does not maintain an agent loop
- ❌ Does not orchestrate multi-step workflows

This follows the standard OpenAI function calling pattern where **the client is responsible for tool execution**.

---

## How It Works

### Architecture

```
┌──────────┐         ┌─────────────┐         ┌──────────┐
│  Client  │────1───▶│  FluidMCP   │────2───▶│   vLLM   │
│          │         │    Proxy    │         │  Server  │
│          │◀───4────│             │◀───3────│          │
└──────────┘         └─────────────┘         └──────────┘
     │
     └────────5 (manual execution)───────────┘
```

1. Client sends request with `tools` parameter
2. FluidMCP forwards entire request body to vLLM
3. vLLM returns response with `tool_calls`
4. FluidMCP forwards response to client
5. Client executes tool and sends result in next request

### Request Flow

```json
POST /llm/v1/chat/completions
{
  "model": "hermes-3-llama-3.1-8b",
  "messages": [...],
  "tools": [...]  // ← Passed through to vLLM
}
```

FluidMCP proxy code ([run_servers.py:809-830](../fluidmcp/cli/services/run_servers.py#L809-L830)):
```python
@app.post("/llm/v1/chat/completions", tags=["llm"])
async def proxy_chat_completions(request: Request):
    body = await request.json()

    # Extract model_id from request body (OpenAI-style)
    model_id = body.get("model")
    if not model_id:
        raise HTTPException(status_code=400, detail="Missing required field 'model' in request body")

    # Check if streaming is requested
    if body.get("stream", False):
        _validate_streaming_request(model_id, "chat")
        return StreamingResponse(
            _proxy_llm_request_streaming(model_id, "chat", body),
            media_type="text/event-stream"
        )

    # Non-streaming request
    return await _proxy_llm_request(model_id, "chat", "POST", body)
```

The request body (including `tools`, `tool_choice`, etc.) is forwarded **verbatim** to vLLM.

---

## Quick Start

### 1. Start FluidMCP with vLLM Model

Configure a vLLM model with function calling support:

```json
{
  "llmModels": {
    "llama-3-70b": {
      "command": "vllm",
      "args": ["serve", "meta-llama/Meta-Llama-3-70B-Instruct"],
      "endpoints": {
        "base_url": "http://localhost:8000",
        "chat": "/v1/chat/completions"
      }
    }
  }
}
```

Start FluidMCP:
```bash
fluidmcp run config.json --file --start-server
```

### 2. Send Request with Tools

```bash
curl -X POST http://localhost:8099/llm/llama-3-70b/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is the weather in San Francisco?"}
    ],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "get_weather",
          "description": "Get current weather for a city",
          "parameters": {
            "type": "object",
            "properties": {
              "city": {"type": "string", "description": "City name"}
            },
            "required": ["city"]
          }
        }
      }
    ],
    "tool_choice": "auto"
  }'
```

### 3. Handle Response with tool_calls

vLLM returns (via FluidMCP):
```json
{
  "id": "chatcmpl-123",
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": null,
        "tool_calls": [
          {
            "id": "call_abc123",
            "type": "function",
            "function": {
              "name": "get_weather",
              "arguments": "{\"city\": \"San Francisco\"}"
            }
          }
        ]
      },
      "finish_reason": "tool_calls"
    }
  ]
}
```

### 4. Execute Tool Manually

Your client code:
```python
# Parse tool call
tool_call = response["choices"][0]["message"]["tool_calls"][0]
function_name = tool_call["function"]["name"]
arguments = json.loads(tool_call["function"]["arguments"])

# Execute tool (YOUR code, not FluidMCP)
if function_name == "get_weather":
    result = get_weather(arguments["city"])
    # result = {"temperature": 18, "condition": "foggy"}
```

### 5. Send Tool Result Back

```bash
curl -X POST http://localhost:8099/llm/llama-3-70b/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is the weather in San Francisco?"},
      {
        "role": "assistant",
        "content": null,
        "tool_calls": [
          {
            "id": "call_abc123",
            "type": "function",
            "function": {
              "name": "get_weather",
              "arguments": "{\"city\": \"San Francisco\"}"
            }
          }
        ]
      },
      {
        "role": "tool",
        "tool_call_id": "call_abc123",
        "content": "{\"temperature\": 18, \"condition\": \"foggy\"}"
      }
    ]
  }'
```

vLLM responds with final answer:
```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "It's currently 18°C and foggy in San Francisco."
      },
      "finish_reason": "stop"
    }
  ]
}
```

---

## Request Format

### Full Request Schema

```json
{
  "messages": [
    {"role": "user", "content": "Your question"}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "tool_name",
        "description": "What the tool does (helps model decide when to call)",
        "parameters": {
          "type": "object",
          "properties": {
            "param1": {
              "type": "string",
              "description": "Parameter description"
            }
          },
          "required": ["param1"]
        }
      }
    }
  ],
  "tool_choice": "auto",  // "auto", "none", or {"type": "function", "function": {"name": "tool_name"}}
  "temperature": 0.7,
  "max_tokens": 1000,
  "stream": false
}
```

### Tool Definition

Each tool follows OpenAI's schema:

```python
{
  "type": "function",
  "function": {
    "name": "function_name",           # Unique identifier (snake_case recommended)
    "description": "Clear description of what the function does and when to use it",
    "parameters": {
      "type": "object",
      "properties": {
        "param_name": {
          "type": "string" | "number" | "boolean" | "array" | "object",
          "description": "What this parameter represents",
          "enum": ["option1", "option2"]  # Optional: restrict to specific values
        }
      },
      "required": ["param_name"]        # List of required parameters
    }
  }
}
```

### Supported Parameter Types

- `string` - Text values
- `number` - Numeric values (integer or float)
- `boolean` - `true` or `false`
- `array` - Lists of values
- `object` - Nested objects

### tool_choice Values

- `"auto"` (default) - Model decides whether to call a tool
- `"none"` - Model will not call any tools
- `{"type": "function", "function": {"name": "tool_name"}}` - Force specific tool call

---

## Response Format

### Response with tool_calls

When vLLM decides to call a tool:

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1677652288,
  "model": "llama-3-70b",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": null,
        "tool_calls": [
          {
            "id": "call_xyz789",
            "type": "function",
            "function": {
              "name": "function_name",
              "arguments": "{\"param\": \"value\"}"  // JSON string
            }
          }
        ]
      },
      "finish_reason": "tool_calls"
    }
  ],
  "usage": {
    "prompt_tokens": 50,
    "completion_tokens": 20,
    "total_tokens": 70
  }
}
```

**Key fields:**
- `finish_reason: "tool_calls"` - Indicates tool call was made
- `content: null` - No text content when making tool call
- `tool_calls` - Array of function calls to execute
- `arguments` - JSON string (you must parse it)

### Response without tool_calls

When model responds normally:

```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "Here is my answer based on the information..."
      },
      "finish_reason": "stop"
    }
  ]
}
```

---

## Complete Example

### Python Client Example

```python
import httpx
import json

FLUIDMCP_URL = "http://localhost:8099"
MODEL_ID = "llama-3-70b"

# Define tool schema
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name (e.g., 'San Francisco', 'Tokyo')"
                    },
                    "units": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "Temperature units"
                    }
                },
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Perform basic mathematical operations",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["add", "subtract", "multiply", "divide"]
                    },
                    "x": {"type": "number"},
                    "y": {"type": "number"}
                },
                "required": ["operation", "x", "y"]
            }
        }
    }
]

# Tool implementations
def get_weather(city: str, units: str = "celsius") -> dict:
    # Your implementation (call weather API, etc.)
    return {
        "city": city,
        "temperature": 18 if units == "celsius" else 64,
        "condition": "foggy",
        "units": units
    }

def calculator(operation: str, x: float, y: float) -> dict:
    ops = {
        "add": x + y,
        "subtract": x - y,
        "multiply": x * y,
        "divide": x / y if y != 0 else None
    }
    return {"result": ops.get(operation)}

# Function calling loop
async def chat_with_tools(user_message: str):
    messages = [{"role": "user", "content": user_message}]

    async with httpx.AsyncClient() as client:
        # Step 1: Send initial request with tools
        response = await client.post(
            f"{FLUIDMCP_URL}/llm/v1/chat/completions",
            json={
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto"
            }
        )
        data = response.json()
        message = data["choices"][0]["message"]

        # Step 2: Check if model wants to call tools
        if message.get("tool_calls"):
            # Add assistant message with tool calls
            messages.append(message)

            # Step 3: Execute each tool call
            for tool_call in message["tool_calls"]:
                function_name = tool_call["function"]["name"]
                arguments = json.loads(tool_call["function"]["arguments"])

                # Execute tool
                if function_name == "get_weather":
                    result = get_weather(**arguments)
                elif function_name == "calculator":
                    result = calculator(**arguments)
                else:
                    result = {"error": "Unknown function"}

                # Add tool result message
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result)
                })

            # Step 4: Send tool results back to model
            response = await client.post(
                f"{FLUIDMCP_URL}/llm/v1/chat/completions",
                json={"model": model_id, "messages": messages}
            )
            data = response.json()
            final_message = data["choices"][0]["message"]["content"]
            return final_message
        else:
            # No tool calls, return direct response
            return message["content"]

# Usage
import asyncio
result = asyncio.run(chat_with_tools("What's 25 * 4?"))
print(result)  # Model calls calculator tool and responds: "25 * 4 equals 100"
```

---

## MCP Tools Integration

### Option 1: Manual MCP Tool Execution

If you have FluidMCP MCP servers running, you can call them from your tool functions:

```python
import httpx

async def filesystem_read(path: str) -> dict:
    """Read file using FluidMCP filesystem MCP server."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8099/filesystem/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "read_file",
                    "arguments": {"path": path}
                }
            }
        )
        result = response.json()
        return result.get("result", {})

# Register as tool
tools = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read contents of a file from the filesystem",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"}
                },
                "required": ["path"]
            }
        }
    }
]

# In your tool execution:
if function_name == "read_file":
    result = await filesystem_read(arguments["path"])
```

### Option 2: Dynamic Tool Discovery

Fetch available MCP tools and convert to OpenAI schema:

```python
async def get_mcp_tools_schema() -> list:
    """Convert MCP tools to OpenAI function calling schema."""
    async with httpx.AsyncClient() as client:
        # List available MCP tools
        response = await client.post(
            "http://localhost:8099/filesystem/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        )
        mcp_tools = response.json()["result"]["tools"]

        # Convert to OpenAI schema
        openai_tools = []
        for tool in mcp_tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["inputSchema"]
                }
            })

        return openai_tools

# Usage:
tools = await get_mcp_tools_schema()
# Now use these tools in your chat completion request
```

**Note:** Future versions of FluidMCP may include automatic MCP tool execution (agent mode). This would eliminate the need for manual tool execution loops. See [Future: Automatic Tool Execution](#future-automatic-tool-execution).

---

## Streaming Support

Function calling works with streaming mode:

```python
async def chat_with_streaming(user_message: str):
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            f"{FLUIDMCP_URL}/llm/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": user_message}],
                "tools": tools,
                "stream": True
            }
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]  # Remove "data: " prefix
                    if data_str == "[DONE]":
                        break

                    chunk = json.loads(data_str)
                    delta = chunk["choices"][0]["delta"]

                    # Check for tool calls
                    if "tool_calls" in delta:
                        print(f"Tool call: {delta['tool_calls']}")

                    # Check for content
                    if "content" in delta:
                        print(delta["content"], end="", flush=True)
```

**Streaming behavior:**
- Model streams text content chunk-by-chunk
- When making tool call, `finish_reason` becomes `"tool_calls"`
- Tool calls appear in final chunk
- You must stop, execute tools, and send results in a new request

---

## Troubleshooting

### Model doesn't call tools

**Symptoms:**
- Model responds with text instead of calling function
- `tool_calls` not present in response

**Solutions:**

1. **Check model compatibility**: Not all vLLM models support function calling. Use models trained for tool use:
   - Meta-Llama-3-70B-Instruct
   - Mistral-7B-Instruct-v0.3 (or later)
   - Any model fine-tuned on function calling data

2. **Improve tool descriptions**:
   ```python
   # ❌ Bad
   "description": "Get weather"

   # ✅ Good
   "description": "Get current weather information including temperature, conditions, and humidity for any city worldwide. Use this when user asks about weather, temperature, or climate in a specific location."
   ```

3. **Use more explicit prompts**:
   ```python
   # ❌ Vague
   "What's the weather?"

   # ✅ Explicit
   "What's the current weather in San Francisco? Use the get_weather tool."
   ```

4. **Try forcing tool call**:
   ```python
   "tool_choice": {
       "type": "function",
       "function": {"name": "get_weather"}
   }
   ```

### Invalid arguments error

**Symptoms:**
- vLLM returns error about invalid JSON
- Arguments string cannot be parsed

**Solutions:**

1. **Check parameter schema matches expected format**:
   ```python
   # Schema must exactly match what you expect
   "parameters": {
       "type": "object",
       "properties": {
           "city": {"type": "string"}  # Not "city_name" or "location"
       }
   }
   ```

2. **Add parameter descriptions to guide model**:
   ```python
   "city": {
       "type": "string",
       "description": "City name in English, e.g., 'San Francisco' or 'Tokyo'"
   }
   ```

3. **Handle parse errors gracefully**:
   ```python
   try:
       arguments = json.loads(tool_call["function"]["arguments"])
   except json.JSONDecodeError:
       print(f"Invalid JSON: {tool_call['function']['arguments']}")
       # Send error back to model
   ```

### vLLM not responding

**Symptoms:**
- Request times out
- 502 Bad Gateway error

**Solutions:**

1. **Check vLLM server is running**:
   ```bash
   curl http://localhost:8000/health
   ```

2. **Verify endpoint configuration**:
   ```json
   {
     "endpoints": {
       "base_url": "http://localhost:8000",  // Correct port?
       "chat": "/v1/chat/completions"        // Correct path?
     }
   }
   ```

3. **Check vLLM logs** for errors:
   ```bash
   # If running vLLM directly
   tail -f vllm.log
   ```

### Tool result not affecting response

**Symptoms:**
- Model ignores tool results
- Response doesn't incorporate tool data

**Solutions:**

1. **Ensure tool result message is properly formatted**:
   ```python
   {
       "role": "tool",
       "tool_call_id": "call_abc123",  # Must match tool_call.id
       "content": json.dumps(result)   # Must be JSON string
   }
   ```

2. **Include complete conversation history**:
   ```python
   messages = [
       {"role": "user", "content": "..."},
       {"role": "assistant", "content": None, "tool_calls": [...]},
       {"role": "tool", "tool_call_id": "...", "content": "..."}
   ]
   ```

3. **Return informative tool results**:
   ```python
   # ❌ Bad
   return "18"

   # ✅ Good
   return json.dumps({
       "temperature": 18,
       "units": "celsius",
       "condition": "foggy",
       "city": "San Francisco"
   })
   ```

---

## Best Practices

### 1. Clear, Descriptive Tool Names

```python
# ❌ Bad
"name": "func1"
"name": "get"

# ✅ Good
"name": "get_weather"
"name": "calculate_mortgage_payment"
```

### 2. Comprehensive Descriptions

```python
# ❌ Bad
"description": "Gets data"

# ✅ Good
"description": "Retrieves current weather data including temperature (°C), humidity (%), conditions, and wind speed for any city worldwide. Use when user asks about weather, climate, or temperature in a specific location."
```

### 3. Detailed Parameter Descriptions

```python
# ❌ Bad
"city": {"type": "string"}

# ✅ Good
"city": {
    "type": "string",
    "description": "City name in English (e.g., 'San Francisco', 'London', 'Tokyo'). Use common English names, not local spellings."
}
```

### 4. Use Enums for Constrained Values

```python
"units": {
    "type": "string",
    "enum": ["celsius", "fahrenheit"],
    "description": "Temperature units to return"
}
```

### 5. Return Structured Data

```python
# ❌ Bad
return "It's 18 degrees and foggy"

# ✅ Good
return {
    "temperature": 18,
    "units": "celsius",
    "condition": "foggy",
    "humidity": 85,
    "wind_speed": 12
}
```

### 6. Handle Errors Gracefully

```python
def get_weather(city: str) -> dict:
    try:
        data = fetch_weather_api(city)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### 7. Limit Conversation Length

Avoid infinite loops:

```python
MAX_ITERATIONS = 5

for iteration in range(MAX_ITERATIONS):
    response = await client.post(...)
    if not response.get("tool_calls"):
        break  # Model finished
    # Execute tools and continue
```

---

## Future: Automatic Tool Execution

FluidMCP may add **agent mode** in a future release, which would automatically:
- Execute MCP tools when model requests them
- Handle multi-step tool orchestration
- Maintain conversation state
- Provide safety controls (timeouts, allowlists)

This would eliminate the need for manual tool execution loops.

**Proposed usage** (future):
```json
{
  "llmModels": {
    "llama-3-70b": {
      "command": "vllm",
      "args": ["serve", "meta-llama/Meta-Llama-3-70B-Instruct"],
      "agent_mode": {
        "enabled": true,
        "auto_execute_mcp_tools": true,
        "allowed_tools": ["filesystem", "weather"],
        "max_iterations": 5
      }
    }
  }
}
```

For now, use the manual execution pattern documented above.

---

## API Reference

### Endpoint

```
POST /llm/v1/chat/completions
```

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `messages` | array | Yes | Conversation history |
| `tools` | array | No | Function definitions (OpenAI schema) |
| `tool_choice` | string/object | No | `"auto"`, `"none"`, or force specific tool |
| `temperature` | number | No | Sampling temperature (0-2) |
| `max_tokens` | number | No | Maximum tokens to generate |
| `stream` | boolean | No | Enable streaming (default: false) |

### Response Body

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique completion ID |
| `choices` | array | Array of completion choices |
| `choices[].message.role` | string | Always `"assistant"` |
| `choices[].message.content` | string/null | Text response (null if tool_calls) |
| `choices[].message.tool_calls` | array | Tools to execute (if any) |
| `choices[].finish_reason` | string | `"stop"`, `"tool_calls"`, or `"length"` |
| `usage` | object | Token usage statistics |

---

## Further Reading

- **OpenAI Function Calling**: https://platform.openai.com/docs/guides/function-calling
- **vLLM Documentation**: https://docs.vllm.ai/
- **MCP Specification**: https://modelcontextprotocol.io/
- **FluidMCP Monitoring**: [MONITORING.md](MONITORING.md)

---

**Questions or issues?** Open an issue: https://github.com/Fluid-AI/fluidmcp/issues
