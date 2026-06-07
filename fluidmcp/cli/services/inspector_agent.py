import os
import json
import asyncio
from loguru import logger


# Default models per provider
PROVIDER_DEFAULTS = {
    "groq":      {"label": "Groq",      "model": "llama-3.1-8b-instant", "base_url": "https://api.groq.com/openai/v1"},
    "openai":    {"label": "OpenAI",    "model": "gpt-4o-mini",           "base_url": "https://api.openai.com/v1"},
    "gemini":    {"label": "Gemini",    "model": "gemini-2.0-flash",      "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/"},
    "anthropic": {"label": "Anthropic", "model": "claude-haiku-4-5-20251001", "base_url": None},
}


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


async def choose_tool_with_llm(
    message: str,
    tools: list,
    chat_history: list | None = None,
    provider: str = "groq",
    model: str | None = None,
    api_key: str | None = None,
    system_prompt: str | None = None,
):
    """
    Universal MCP agent with multi-provider support.

    Supported providers: groq, openai, anthropic, gemini
    - groq/openai/gemini: use the openai-compatible client
    - anthropic: use the anthropic SDK directly

    API keys are passed in from the frontend (stored in localStorage per provider).
    Falls back to environment variables if no key is provided.
    """

    if chat_history is None:
        chat_history = []

    if not tools:
        raise RuntimeError("No tools available")

    provider = provider.lower()
    logger.info(f"Inspector chat — provider={provider}, message={message!r}")

    tool_description = format_tools_for_prompt(tools)

    prompt = f"""
Available tools:
{tool_description}

User request: {message}

Instructions:
1. Choose the BEST tool to fulfill the request.
2. Extract parameters from the request.
3. If parameters are missing, infer reasonable defaults or leave them empty. DO NOT explain anything.

Return ONLY JSON.
"""

    sys_content = system_prompt.strip() if system_prompt and system_prompt.strip() else """
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

    history_messages = [
        {"role": "user" if m.get("type") == "user" else "assistant",
         "content": str(m.get("content", ""))}
        for m in chat_history
        if m.get("type") in ("user", "assistant") and m.get("content")
    ]

    if provider == "anthropic":
        return await _call_anthropic(
            message=prompt,
            sys_content=sys_content,
            history_messages=history_messages,
            model=model,
            api_key=api_key,
        )
    else:
        return await _call_openai_compatible(
            message=prompt,
            sys_content=sys_content,
            history_messages=history_messages,
            provider=provider,
            model=model,
            api_key=api_key,
        )


async def _call_openai_compatible(
    message: str,
    sys_content: str,
    history_messages: list,
    provider: str,
    model: str | None,
    api_key: str | None,
):
    """Call Groq, OpenAI, or Gemini via the OpenAI-compatible client."""
    from openai import OpenAI
    from dotenv import load_dotenv

    load_dotenv()

    defaults = PROVIDER_DEFAULTS.get(provider)
    if not defaults:
        raise RuntimeError(f"Unknown provider: {provider!r}")

    resolved_model = model or defaults["model"]
    base_url = defaults["base_url"]

    # Key resolution: explicit > env var
    env_key_names = {
        "groq":   "GROQ_API_KEY",
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }
    resolved_key = api_key or os.getenv(env_key_names.get(provider, ""), "")
    if not resolved_key:
        raise RuntimeError(
            f"No API key provided for {defaults['label']}. "
            "Please add your API key in the LLM settings."
        )

    # Gemini's OpenAI-compatible endpoint requires the key as a query param.
    # Use default_query so the OpenAI client appends ?key=... to every request
    # without corrupting the path (appending to base_url breaks path construction).
    if provider == "gemini":
        client = OpenAI(api_key="not-used", base_url=base_url, default_query={"key": resolved_key})
    else:
        client = OpenAI(api_key=resolved_key, base_url=base_url)

    def _call():
        return client.chat.completions.create(
            model=resolved_model,
            messages=[
                {"role": "system", "content": sys_content},
                *history_messages,
                {"role": "user", "content": message},
            ],
            temperature=0,
            max_tokens=200,
        )

    response = await asyncio.to_thread(_call)
    content = response.choices[0].message.content.strip()
    logger.info(f"[{provider}] raw response: {repr(content)}")
    return _parse_json_response(content)


async def _call_anthropic(
    message: str,
    sys_content: str,
    history_messages: list,
    model: str | None,
    api_key: str | None,
):
    """Call Anthropic Claude via the anthropic SDK."""
    from anthropic import Anthropic
    from dotenv import load_dotenv

    load_dotenv()

    resolved_model = model or "claude-haiku-4-5-20251001"
    resolved_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
    if not resolved_key:
        raise RuntimeError(
            "No API key provided for Anthropic. "
            "Please add your API key in the LLM settings."
        )

    client = Anthropic(api_key=resolved_key)

    # Anthropic uses system param separately; convert history
    anthropic_messages = []
    for m in history_messages:
        anthropic_messages.append({"role": m["role"], "content": m["content"]})
    anthropic_messages.append({"role": "user", "content": message})

    def _call():
        return client.messages.create(
            model=resolved_model,
            system=sys_content,
            messages=anthropic_messages,
            temperature=0,
            max_tokens=200,
        )

    response = await asyncio.to_thread(_call)
    content = response.content[0].text.strip()
    logger.info(f"[anthropic] raw response: {repr(content)}")
    return _parse_json_response(content)


def _parse_json_response(content: str) -> dict:
    """Parse JSON from LLM response, with fallback extraction."""
    try:
        result = json.loads(content)
        logger.info(f"LLM parsed result (direct): {result}")
        return result
    except json.JSONDecodeError:
        logger.warning("Direct JSON parse failed, attempting extraction...")

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
            f"Failed to parse extracted JSON.\nRaw: {content}\nExtracted: {json_str}"
        ) from e
