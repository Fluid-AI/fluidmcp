import os
import json
import asyncio
from typing import AsyncGenerator
from loguru import logger


PROVIDER_DEFAULTS = {
    "groq":      {"base_url": "https://api.groq.com/openai/v1",              "model": "llama-3.1-8b-instant"},
    "openai":    {"base_url": "https://api.openai.com/v1",                   "model": "gpt-4o-mini"},
    "gemini":    {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-2.0-flash"},
    "anthropic": {"model": "claude-haiku-4-5-20251001"},
}

ENV_KEY_MAP = {
    "groq":      "GROQ_API_KEY",
    "openai":    "OPENAI_API_KEY",
    "gemini":    "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}

SYSTEM_PROMPT = """
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
- One tool per response only
"""


def format_tools_for_prompt(tools):
    formatted = []
    for tool in tools:
        name = tool.get("name")
        description = tool.get("description", "No description")
        schema = tool.get("inputSchema", {})
        props = schema.get("properties", {})
        params = [f"- {p} ({i.get('type', 'string')})" for p, i in props.items()]
        param_text = "\n".join(params) if params else "None"
        formatted.append(f"\nTool: {name}\nDescription: {description}\nParameters:\n{param_text}\n")
    return "\n".join(formatted)


def _build_messages(message: str, tools: list, chat_history: list, system_prompt: str | None) -> list:
    tool_description = format_tools_for_prompt(tools)
    user_content = f"""Available tools:\n{tool_description}\n\nUser request: {message}\n\nInstructions:\n1. Choose the BEST tool to fulfill the request.\n2. Extract parameters from the request.\n3. If parameters are missing, infer reasonable defaults or leave them empty.\n\nReturn ONLY JSON."""

    history_messages = [
        {"role": "user" if m.get("type") == "user" else "assistant",
         "content": str(m.get("content", ""))}
        for m in chat_history
        if m.get("type") in ("user", "assistant") and m.get("content")
    ]

    sys = system_prompt.strip() if system_prompt and system_prompt.strip() else SYSTEM_PROMPT.strip()

    return [
        {"role": "system", "content": sys},
        *history_messages,
        {"role": "user", "content": user_content},
    ]


def _resolve_api_key(provider: str, api_key: str | None) -> str:
    from dotenv import load_dotenv
    load_dotenv()
    key = api_key or os.getenv(ENV_KEY_MAP.get(provider, ""))
    if not key and provider != "groq":
        raise RuntimeError(f"No API key provided for provider '{provider}'")
    if not key:
        raise RuntimeError("GROQ_API_KEY not configured")
    return key


def _parse_tool_json(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError(f"No JSON found in LLM response: {content}")
        return json.loads(content[start:end])


async def stream_tool_selection(
    message: str,
    tools: list,
    chat_history: list | None = None,
    provider: str = "groq",
    model: str | None = None,
    api_key: str | None = None,
    system_prompt: str | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Async generator that streams LLM tool selection.

    Yields dicts:
      {"type": "token", "content": "..."}
      {"type": "tool_call", "tool_name": "...", "params": {...}}
      {"type": "clarification", "message": "..."}
    """
    if chat_history is None:
        chat_history = []

    logger.info(f"Inspector stream chat — provider={provider} message={message!r}")

    key = _resolve_api_key(provider, api_key)
    defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["groq"])
    resolved_model = model or defaults["model"]
    messages = _build_messages(message, tools, chat_history, system_prompt)

    if provider == "anthropic":
        async for event in _stream_anthropic(key, resolved_model, messages):
            yield event
    else:
        async for event in _stream_openai_compatible(key, resolved_model, messages, defaults["base_url"], provider):
            yield event


async def _stream_openai_compatible(
    api_key: str,
    model: str,
    messages: list,
    base_url: str,
    provider: str,
) -> AsyncGenerator[dict, None]:
    from openai import OpenAI

    extra_kwargs = {}
    if provider == "gemini":
        extra_kwargs["default_query"] = {"key": api_key}

    client = OpenAI(api_key=api_key, base_url=base_url, **extra_kwargs)

    def _collect_tokens() -> list[str]:
        # Runs in a thread — collects all tokens before returning to the event loop.
        # Fine for short JSON tool-selection responses; for true sub-token latency
        # a queue-based approach would be needed.
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
            max_tokens=500,
            stream=True,
        )
        tokens = []
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                tokens.append(delta)
        return tokens

    try:
        tokens = await asyncio.to_thread(_collect_tokens)

        accumulated = ""
        for token in tokens:
            accumulated += token
            yield {"type": "token", "content": token}

        logger.info(f"OpenAI-compatible stream accumulated: {repr(accumulated)}")
        result = _parse_tool_json(accumulated)
        yield {"type": "tool_call", "tool_name": result.get("tool_name"), "params": result.get("params", {})}

    except Exception as e:
        import re as _re
        user_message = str(e)
        user_message = _re.sub(r"(provided|key):\s*\S+", r"\1: [REDACTED]", user_message, flags=_re.IGNORECASE)
        logger.error(f"OpenAI-compatible stream error ({provider}): {user_message}")
        yield {"type": "clarification", "message": user_message}


async def _stream_anthropic(
    api_key: str,
    model: str,
    messages: list,
) -> AsyncGenerator[dict, None]:
    import anthropic

    # Anthropic requires system message separate from messages list
    system_content = SYSTEM_PROMPT.strip()
    filtered = [m for m in messages if m["role"] != "system"]
    for m in messages:
        if m["role"] == "system":
            system_content = m["content"]
            break

    client = anthropic.Anthropic(api_key=api_key)

    def _collect_tokens() -> list[str]:
        tokens = []
        with client.messages.stream(
            model=model,
            max_tokens=500,
            system=system_content,
            messages=filtered,
        ) as stream:
            for event in stream:
                if (
                    hasattr(event, "type")
                    and event.type == "content_block_delta"
                    and hasattr(event, "delta")
                    and hasattr(event.delta, "text")
                ):
                    tokens.append(event.delta.text)
        return tokens

    try:
        tokens = await asyncio.to_thread(_collect_tokens)

        accumulated = ""
        for token in tokens:
            accumulated += token
            yield {"type": "token", "content": token}

        logger.info(f"Anthropic stream accumulated: {repr(accumulated)}")
        result = _parse_tool_json(accumulated)
        yield {"type": "tool_call", "tool_name": result.get("tool_name"), "params": result.get("params", {})}

    except Exception as e:
        import re as _re
        user_message = str(e)
        user_message = _re.sub(r"(provided|key):\s*\S+", r"\1: [REDACTED]", user_message, flags=_re.IGNORECASE)
        logger.error(f"Anthropic stream error: {user_message}")
        yield {"type": "clarification", "message": user_message}


# ─── Non-streaming (kept for fallback) ────────────────────────────────────────

async def choose_tool_with_llm(
    message: str,
    tools: list,
    chat_history: list | None = None,
    provider: str = "groq",
    model: str | None = None,
    api_key: str | None = None,
    system_prompt: str | None = None,
):
    """Non-streaming fallback — collects the full stream and returns a single result dict."""
    if not tools:
        raise RuntimeError("No tools available")

    tool_name = None
    tool_params = {}
    clarification = None

    async for event in stream_tool_selection(
        message=message,
        tools=tools,
        chat_history=chat_history,
        provider=provider,
        model=model,
        api_key=api_key,
        system_prompt=system_prompt,
    ):
        if event["type"] == "tool_call":
            tool_name = event["tool_name"]
            tool_params = event["params"]
        elif event["type"] == "clarification":
            clarification = event["message"]

    if clarification:
        raise ValueError(clarification)

    return {"tool_name": tool_name, "params": tool_params}
