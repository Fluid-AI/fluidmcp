import os
import json
import asyncio
from loguru import logger


def format_tools_for_prompt(tools):
    """
    Convert MCP tools into a readable prompt format.
    This remains dynamic → supports ANY MCP.
    """

    formatted = []

    for tool in tools:
        name = tool.get("name")
        description = tool.get("description", "No description")

        schema = tool.get("inputSchema", {})
        props = schema.get("properties", {})

        params = []
        for param_name, param_info in props.items():
            param_type = param_info.get("type", "string")
            params.append(f"- {param_name} ({param_type})")

        param_text = "\n".join(params) if params else "None"

        formatted.append(
            f"""
Tool: {name}
Description: {description}
Parameters:
{param_text}
"""
        )

    return "\n".join(formatted)


async def choose_tool_with_llm(message: str, tools: list):
    """
    Universal MCP agent powered by Groq.

    Imports and initialises the Groq client lazily so the server can start
    even when GROQ_API_KEY is absent — the error surfaces only when the chat
    endpoint is actually called.
    """

    if not tools:
        raise RuntimeError("No tools available")

    logger.info(f"Inspector chat message: {message}")

    # Lazy imports — avoids startup failure when GROQ_API_KEY is absent
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv()

    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        raise RuntimeError("GROQ_API_KEY not configured")

    # Build client inside the function — no module-level side effects
    client = OpenAI(
        api_key=groq_api_key,
        base_url="https://api.groq.com/openai/v1"
    )

    tool_description = format_tools_for_prompt(tools)

    prompt = f"""
Available tools:
{tool_description}

User request:
{message}

Instructions:
1. Choose the BEST tool to fulfill the request.
2. Extract parameters from the request.
3. If parameters are missing:
   - Infer reasonable defaults OR leave them empty
   - DO NOT explain anything

Return ONLY JSON.
"""

    try:
        # The OpenAI client is synchronous — run in a thread to avoid blocking
        # the event loop.
        def _call_llm():
            return client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {
                        "role": "system",
                        "content": """
You are a strict JSON API for MCP tool selection.

You MUST return ONLY valid JSON.

Format:
{
  "tool_name": string,
  "params": object
}

Rules:
- No explanation
- No markdown
- No extra text
- Always return JSON
"""
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0,
                max_tokens=200,
                stop=["\n\n"]
            )

        response = await asyncio.to_thread(_call_llm)

        content = response.choices[0].message.content.strip()

        logger.info(f"LLM raw response: {repr(content)}")

        # First attempt: direct parse
        try:
            result = json.loads(content)
            logger.info(f"LLM parsed result (direct): {result}")
            return result

        except json.JSONDecodeError:
            logger.warning("Direct JSON parse failed, attempting extraction...")

            # Fallback: extract JSON block
            start = content.find("{")
            end = content.rfind("}") + 1

            if start == -1 or end == 0:
                raise ValueError(f"No JSON found in LLM response: {content}")

            json_str = content[start:end]

            try:
                result = json.loads(json_str)
                logger.info(f"LLM parsed result (extracted): {result}")
                return result

            except Exception as e:
                raise ValueError(
                    f"Failed to parse extracted JSON.\nRaw response: {content}\nExtracted: {json_str}"
                ) from e

    except Exception as e:
        logger.error(f"Groq agent error: {e}")
        raise
