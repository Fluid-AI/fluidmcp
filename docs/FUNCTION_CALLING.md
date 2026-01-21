# vLLM Function Calling

FluidMCP supports OpenAI-compatible function calling for vLLM models, enabling agents to use tools and execute actions.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Tool Definition](#tool-definition)
- [Configuration](#configuration)
- [Examples](#examples)
- [Safety Controls](#safety-controls)
- [Streaming Support](#streaming-support)
- [Metrics](#metrics)
- [Troubleshooting](#troubleshooting)

## Overview

Function calling allows vLLM models to:
- Request tool execution during conversations
- Receive structured tool results
- Use results to provide informed answers

**Use cases:**
- Search and retrieval
- Data analysis
- API integrations
- Calculator operations
- File system operations (in sandbox)

## Quick Start

### 1. Register a Tool

```python
from fluidmcp.cli.services.tool_registry import get_global_registry

# Get global registry
registry = get_global_registry()

# Define your tool function
def get_weather(city: str) -> dict:
    # Your implementation
    return {"city": city, "temperature": 25, "condition": "sunny"}

# Register the tool
registry.register(
    name="get_weather",
    function=get_weather,
    description="Get current weather for a city",
    parameters={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "City name"
            }
        },
        "required": ["city"]
    }
)
```

### 2. Use in Chat Completion

```python
from fluidmcp.cli.services.function_router import create_function_router

# Create router
router = create_function_router("llama-2-70b", config={
    "allowed_tools": ["get_weather"],
    "timeout_per_tool": 10,
    "max_iterations": 5
})

# Chat with function calling
messages = [
    {"role": "user", "content": "What's the weather in Bangalore?"}
]

response = await router.handle_completion(
    messages=messages,
    vllm_client=vllm_client,
    stream=False
)
```

## Tool Definition

### Tool Schema Format

Tools follow OpenAI's function calling schema:

```python
{
    "name": "tool_name",           # Unique identifier
    "description": "What it does",  # Model uses this to decide when to call
    "parameters": {                 # JSON Schema for parameters
        "type": "object",
        "properties": {
            "param1": {
                "type": "string",
                "description": "Parameter description"
            },
            "param2": {
                "type": "number",
                "description": "Another parameter"
            }
        },
        "required": ["param1"]      # Required parameters
    }
}
```

### Supported Parameter Types

- `string` - Text values
- `number` - Numeric values (int or float)
- `boolean` - True/false
- `array` - Lists
- `object` - Nested objects

### Tool Function Requirements

**Synchronous functions:**
```python
def my_tool(arg1: str, arg2: int) -> dict:
    # Process synchronously
    return {"result": "value"}
```

**Async functions:**
```python
async def my_async_tool(arg1: str) -> dict:
    # Process asynchronously
    await asyncio.sleep(0.1)
    return {"result": "value"}
```

**Return values:**
- Return dict, list, str, or any JSON-serializable type
- Result is converted to string and passed back to model

## Configuration

### Model-Level Configuration

Configure function calling in your vLLM model config:

```json
{
  "llmModels": {
    "llama-2-70b": {
      "command": "vllm",
      "args": ["serve", "meta-llama/Llama-2-70b-chat-hf"],
      "tooling": {
        "enabled": true,
        "allowed_tools": ["get_weather", "calculator", "search"],
        "timeout_per_tool": 10,
        "max_call_depth": 3,
        "max_iterations": 5
      }
    }
  }
}
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | true | Enable function calling |
| `allowed_tools` | list | [] | Whitelist of allowed tools (empty = all allowed) |
| `timeout_per_tool` | int | 10 | Timeout in seconds per tool execution |
| `max_call_depth` | int | 3 | Maximum recursive call depth |
| `max_iterations` | int | 5 | Maximum conversation iterations |

## Examples

### Example 1: Weather Tool

```python
def get_weather(city: str, units: str = "celsius") -> dict:
    """Get weather information for a city."""
    # Implementation (could call weather API)
    return {
        "city": city,
        "temperature": 25,
        "units": units,
        "condition": "sunny",
        "humidity": 65
    }

registry.register(
    name="get_weather",
    function=get_weather,
    description="Get current weather information for any city",
    parameters={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "City name (e.g., 'Bangalore', 'New York')"
            },
            "units": {
                "type": "string",
                "enum": ["celsius", "fahrenheit"],
                "description": "Temperature units"
            }
        },
        "required": ["city"]
    }
)
```

**Usage:**
```
User: "What's the weather in Mumbai?"
Model: [calls get_weather(city="Mumbai")]
Tool: Returns {"city": "Mumbai", "temperature": 28, ...}
Model: "It's currently 28°C and sunny in Mumbai with 65% humidity."
```

### Example 2: Calculator Tool

```python
def calculator(operation: str, x: float, y: float) -> dict:
    """Perform mathematical operations."""
    operations = {
        "add": x + y,
        "subtract": x - y,
        "multiply": x * y,
        "divide": x / y if y != 0 else None
    }

    result = operations.get(operation)
    return {"operation": operation, "result": result}

registry.register(
    name="calculator",
    function=calculator,
    description="Perform basic mathematical calculations",
    parameters={
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["add", "subtract", "multiply", "divide"],
                "description": "Mathematical operation to perform"
            },
            "x": {
                "type": "number",
                "description": "First operand"
            },
            "y": {
                "type": "number",
                "description": "Second operand"
            }
        },
        "required": ["operation", "x", "y"]
    }
)
```

### Example 3: Async Search Tool

```python
import httpx

async def web_search(query: str, max_results: int = 5) -> dict:
    """Search the web for information."""
    async with httpx.AsyncClient() as client:
        # Your search API implementation
        response = await client.get(
            "https://api.search.com/search",
            params={"q": query, "limit": max_results}
        )
        results = response.json()

    return {
        "query": query,
        "results": results["items"],
        "count": len(results["items"])
    }

registry.register(
    name="web_search",
    function=web_search,
    description="Search the web for current information",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results",
                "default": 5
            }
        },
        "required": ["query"]
    }
)
```

## Safety Controls

### 1. Tool Allowlist

Restrict which tools can be called:

```python
config = {
    "allowed_tools": ["get_weather", "calculator"]
    # "search" tool will be rejected even if registered
}
```

### 2. Execution Timeout

Prevent long-running tools from blocking:

```python
config = {
    "timeout_per_tool": 5  # 5 seconds max per tool
}
```

If tool exceeds timeout:
```json
{
  "error": true,
  "message": "Tool execution timeout (5s)"
}
```

### 3. Call Depth Limiting

Prevent infinite recursion:

```python
config = {
    "max_call_depth": 3
}
```

Model cannot call tools more than 3 levels deep.

### 4. Iteration Limiting

Prevent infinite loops:

```python
config = {
    "max_iterations": 5
}
```

Conversation will stop after 5 tool-calling iterations.

## Streaming Support

Function calling works with streaming responses:

```python
response = await router.handle_completion(
    messages=messages,
    vllm_client=vllm_client,
    stream=True  # Enable streaming
)

async for chunk in response:
    # Handle streaming chunks
    if "tool_calls" in chunk:
        # Tool call detected
        pass
    else:
        # Regular content
        print(chunk["choices"][0]["delta"]["content"], end="")
```

**Note:** Tool execution happens between streaming calls. The model streams initial response, tools execute, then model streams final answer.

## Metrics

Function calling integrates with FluidMCP metrics:

### Tool Metrics

- `fluidmcp_tool_calls_total{tool_name, status}` - Total tool calls
- `fluidmcp_tool_execution_seconds{tool_name}` - Tool execution duration
- `fluidmcp_tool_errors_total{tool_name, error_type}` - Tool errors

### Query Metrics

```bash
# View tool execution metrics
curl http://localhost:8099/metrics | grep tool

# Example output:
fluidmcp_tool_calls_total{tool_name="get_weather",status="success"} 42
fluidmcp_tool_execution_seconds{tool_name="get_weather",quantile="0.5"} 0.12
fluidmcp_tool_errors_total{tool_name="calculator",error_type="timeout"} 2
```

### Grafana Dashboard

Import `examples/grafana-dashboard.json` for visualization:
- Tool call rates
- Tool execution latency
- Tool error rates
- Most used tools

## Troubleshooting

### Tool Not Being Called

**Symptom:** Model doesn't call tool even when appropriate.

**Solutions:**
1. Check tool description is clear and specific
2. Verify tool is in `allowed_tools` list (if configured)
3. Ensure model supports function calling (not all vLLM models do)
4. Try more explicit user prompts

### Tool Execution Timeout

**Symptom:** `Tool execution timeout` error.

**Solutions:**
1. Increase `timeout_per_tool` in config
2. Optimize tool function performance
3. Use async functions for I/O-bound operations
4. Add caching if tool fetches external data

### Invalid Arguments Error

**Symptom:** `Invalid JSON arguments` error.

**Solutions:**
1. Verify parameter schema matches function signature
2. Check required fields are marked correctly
3. Add parameter descriptions to guide model
4. Validate model is passing correct JSON

### Max Iterations Exceeded

**Symptom:** Loop stops after 5 iterations.

**Solutions:**
1. Increase `max_iterations` in config
2. Review tool descriptions (model may be confused)
3. Add more specific prompts to guide model
4. Check if tool results are informative enough

### Tool Not Found

**Symptom:** `Tool 'tool_name' not found` error.

**Solutions:**
1. Verify tool is registered before use
2. Check spelling of tool name
3. Ensure registry is using global instance
4. Confirm tool wasn't unregistered

## Best Practices

### 1. Clear Tool Descriptions

```python
# ❌ Bad
description="Get data"

# ✅ Good
description="Get current weather data including temperature, humidity, and conditions for any city worldwide"
```

### 2. Specific Parameter Descriptions

```python
# ❌ Bad
"city": {"type": "string"}

# ✅ Good
"city": {
    "type": "string",
    "description": "City name in English (e.g., 'San Francisco', 'Tokyo', 'London')"
}
```

### 3. Handle Errors Gracefully

```python
def my_tool(param: str) -> dict:
    try:
        result = potentially_failing_operation(param)
        return {"success": True, "result": result}
    except Exception as e:
        # Return error as dict, not exception
        return {"success": False, "error": str(e)}
```

### 4. Use Async for I/O

```python
# ✅ Good for API calls, database queries, file I/O
async def fetch_data(url: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()
```

### 5. Validate Input

```python
def calculator(operation: str, x: float, y: float) -> dict:
    if operation not in ["add", "subtract", "multiply", "divide"]:
        return {"error": f"Unknown operation: {operation}"}

    if operation == "divide" and y == 0:
        return {"error": "Division by zero"}

    # Proceed with calculation
    ...
```

## API Reference

### ToolRegistry

```python
from fluidmcp.cli.services.tool_registry import ToolRegistry, get_global_registry

registry = get_global_registry()
registry.register(name, function, description, parameters)
registry.unregister(name)
registry.get_tool(name)
registry.list_tool_schemas()
```

### ToolExecutor

```python
from fluidmcp.cli.services.tool_executor import ToolExecutor

executor = ToolExecutor(registry, model_id, config)
result = await executor.execute_tool_call(tool_call, depth=0)
results = await executor.execute_tool_calls(tool_calls, depth=0)
```

### FunctionRouter

```python
from fluidmcp.cli.services.function_router import create_function_router

router = create_function_router(model_id, config)
response = await router.handle_completion(
    messages, vllm_client, tools, tool_choice, stream
)
```

## Further Reading

- [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling)
- [vLLM Documentation](https://docs.vllm.ai/)
- [FluidMCP Monitoring Guide](MONITORING.md)
- [MCP Specification](https://modelcontextprotocol.io/)
