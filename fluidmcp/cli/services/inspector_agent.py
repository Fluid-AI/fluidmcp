import os
import json
from loguru import logger
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY not found in environment")

# Groq client (OpenAI compatible)
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)


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
    """

    if not tools:
        raise RuntimeError("No tools available")

    logger.info(f"Inspector chat message: {message}")

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

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You select MCP tools."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=120
        )

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