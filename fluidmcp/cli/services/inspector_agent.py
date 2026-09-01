import os
import json
import asyncio
from loguru import logger


def format_tools_for_prompt(tools):
    """
    Convert MCP tool schemas into a simple prompt-friendly format.
    """
    tool_lines = []

    for tool in tools:
        name = tool.get("name")
        desc = tool.get("description", "")
        schema = tool.get("inputSchema", {})
        props = schema.get("properties", {})

        params = ", ".join(props.keys())

        tool_lines.append(
            f"{name}({params}) - {desc}"
        )

    return "\n".join(tool_lines)


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
You are an AI agent that selects which MCP tool to run.

Available tools:
{tool_description}

User request:
{message}

Respond ONLY with JSON.

Example:
{{"tool_name": "get_current_time", "params": {{"timezone": "Asia/Tokyo"}}}}
"""

    try:
        # The OpenAI client is synchronous — run in a thread to avoid blocking
        # the event loop.
        def _call_llm():
            return client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "You select MCP tools."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                max_tokens=120
            )

        response = await asyncio.to_thread(_call_llm)

        content = response.choices[0].message.content.strip()

        logger.info(f"LLM raw response: {content}")

        # Try parsing JSON safely
        try:
            result = json.loads(content)
        except json.JSONDecodeError:

            # Attempt JSON extraction
            start = content.find("{")
            end = content.rfind("}") + 1
            result = json.loads(content[start:end])

        logger.info(f"LLM parsed result: {result}")

        return result

    except Exception as e:
        logger.error(f"Groq agent error: {e}")
        raise
