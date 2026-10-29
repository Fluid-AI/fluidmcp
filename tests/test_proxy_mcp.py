"""Tests for proxy MCP servers (type: "proxy").

A proxy MCP answers tools/list from its config and forwards tools/call
arguments to an HTTP endpoint. Upstream calls go through httpx.MockTransport.
"""
import json

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from fluidmcp.cli.api.management import validate_server_config as validate_api_server_config
from fluidmcp.cli.repositories import InMemoryBackend
from fluidmcp.cli.services.package_launcher import create_dynamic_router
from fluidmcp.cli.services.proxy_mcp import (
    ProxyHandle,
    extract_path,
    resolve_headers,
    validate_proxy_config,
)
from fluidmcp.cli.services.server_manager import ServerManager
from fluidmcp.cli.services.validators import validate_mcpservers_config

ENDPOINT = "https://api.openai.com/v1/chat/completions"

CHAT_RESPONSE = {
    "id": "chatcmpl-1",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello there"}}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
}


def proxy_config(**overrides):
    config = {
        "type": "proxy",
        "endpoint": ENDPOINT,
        "headers": {"Authorization": "Bearer ${OPENAI_API_KEY}"},
        "tool": {
            "name": "chat_completion",
            "description": "Send a chat completion request",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "messages": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["model", "messages"],
            },
        },
    }
    config.update(overrides)
    return config


def make_handle(handler, **overrides) -> ProxyHandle:
    handle = ProxyHandle("openai", proxy_config(**overrides), {"OPENAI_API_KEY": "sk-test"})
    handle._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return handle


def call(arguments, name="chat_completion"):
    return {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": name, "arguments": arguments}}


CHAT_ARGS = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Hi"}]}


# ── Config validation ───────────────────────────────────────────────────────

class TestValidateProxyConfig:
    def test_valid_config(self):
        assert validate_proxy_config(proxy_config()) == []

    @pytest.mark.parametrize("overrides, expected", [
        ({"endpoint": None}, "Missing required field: endpoint"),
        ({"endpoint": "ftp://example.com"}, "http:// or https://"),
        ({"method": "TRACE"}, "Field 'method' must be one of"),
        ({"headers": {"X-Bad": "a\r\nInjected: 1"}}, "must not contain line breaks"),
        ({"timeout": 0}, "Field 'timeout' must be a positive number"),
        ({"timeout": True}, "Field 'timeout' must be a positive number"),
        ({"response_path": ""}, "Field 'response_path' must be a non-empty string"),
        ({"tool": None}, "Missing required field: tool"),
        ({"tool": {"name": "has space", "inputSchema": {"type": "object"}}}, "Field 'tool.name'"),
        ({"tool": {"name": "ok", "inputSchema": {"type": "string"}}}, "Field 'tool.inputSchema'"),
    ])
    def test_invalid_config(self, overrides, expected):
        errors = validate_proxy_config(proxy_config(**overrides))
        assert any(expected in e for e in errors), errors

    def test_mcpservers_validator_accepts_proxy_without_command(self):
        assert validate_mcpservers_config({"mcpServers": {"openai": proxy_config()}}) == []

    def test_api_validator_accepts_proxy(self):
        validate_api_server_config({"id": "openai", "name": "OpenAI", **proxy_config()})

    def test_api_validator_rejects_invalid_proxy(self):
        with pytest.raises(HTTPException) as exc:
            validate_api_server_config({"id": "openai", "name": "OpenAI", **proxy_config(endpoint="nope")})
        assert exc.value.status_code == 400


class TestResolveHeaders:
    def test_substitutes_variables(self):
        headers = resolve_headers({"Authorization": "Bearer ${KEY}", "X-Static": "v"}, {"KEY": "abc"})
        assert headers == {"Authorization": "Bearer abc", "X-Static": "v"}

    def test_missing_variable_names_it(self):
        with pytest.raises(ValueError, match=r"\$\{KEY\}"):
            resolve_headers({"Authorization": "Bearer ${KEY}"}, {})


class TestExtractPath:
    def test_follows_keys_and_indexes(self):
        assert extract_path(CHAT_RESPONSE, "choices.0.message.content") == "Hello there"

    @pytest.mark.parametrize("path", ["choices.1.message", "missing", "choices.x"])
    def test_missing_path_raises(self, path):
        with pytest.raises(KeyError):
            extract_path(CHAT_RESPONSE, path)


# ── MCP protocol ────────────────────────────────────────────────────────────

class TestProxyHandle:
    @pytest.mark.asyncio
    async def test_tools_list_returns_configured_tool(self):
        handle = make_handle(lambda request: pytest.fail("tools/list must not call upstream"))
        response = await handle.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert response["result"]["tools"] == [{
            "name": "chat_completion",
            "description": "Send a chat completion request",
            "inputSchema": proxy_config()["tool"]["inputSchema"],
        }]

    @pytest.mark.asyncio
    async def test_tools_call_forwards_arguments_and_headers(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["method"] = request.method
            seen["url"] = str(request.url)
            seen["auth"] = request.headers["authorization"]
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json=CHAT_RESPONSE)

        response = await make_handle(handler).handle(call(CHAT_ARGS))

        assert seen == {"method": "POST", "url": ENDPOINT, "auth": "Bearer sk-test", "body": CHAT_ARGS}
        assert response["id"] == 7
        result = response["result"]
        assert result["isError"] is False
        assert json.loads(result["content"][0]["text"]) == CHAT_RESPONSE

    @pytest.mark.asyncio
    async def test_response_path_extracts_value(self):
        handle = make_handle(lambda r: httpx.Response(200, json=CHAT_RESPONSE),
                             response_path="choices.0.message.content")
        result = (await handle.handle(call(CHAT_ARGS)))["result"]
        assert result == {"content": [{"type": "text", "text": "Hello there"}], "isError": False}

    @pytest.mark.asyncio
    async def test_response_path_non_string_is_json_encoded(self):
        handle = make_handle(lambda r: httpx.Response(200, json=CHAT_RESPONSE), response_path="usage")
        result = (await handle.handle(call(CHAT_ARGS)))["result"]
        assert json.loads(result["content"][0]["text"]) == CHAT_RESPONSE["usage"]

    @pytest.mark.asyncio
    async def test_response_path_missing_is_tool_error(self):
        handle = make_handle(lambda r: httpx.Response(200, json={"other": 1}),
                             response_path="choices.0.message.content")
        result = (await handle.handle(call(CHAT_ARGS)))["result"]
        assert result["isError"] is True
        assert "choices.0.message.content" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_upstream_http_error_is_tool_error(self):
        handle = make_handle(lambda r: httpx.Response(401, json={"error": {"message": "Incorrect API key"}}))
        response = await handle.handle(call(CHAT_ARGS))
        assert "error" not in response
        result = response["result"]
        assert result["isError"] is True
        assert "HTTP 401" in result["content"][0]["text"]
        assert "Incorrect API key" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_upstream_timeout_is_tool_error(self):
        def handler(request):
            raise httpx.ReadTimeout("slow", request=request)

        result = (await make_handle(handler, timeout=5).handle(call(CHAT_ARGS)))["result"]
        assert result["isError"] is True
        assert "timed out after 5s" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_upstream_unreachable_is_tool_error(self):
        def handler(request):
            raise httpx.ConnectError("refused", request=request)

        result = (await make_handle(handler).handle(call(CHAT_ARGS)))["result"]
        assert result["isError"] is True
        assert "ConnectError" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_get_sends_arguments_as_query(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["query"] = dict(request.url.params)
            seen["body"] = request.content
            return httpx.Response(200, text="ok")

        await make_handle(handler, method="GET").handle(call({"q": "weather"}))
        assert seen == {"query": {"q": "weather"}, "body": b""}

    @pytest.mark.asyncio
    async def test_get_rejects_object_arguments(self):
        handle = make_handle(lambda r: pytest.fail("must not call upstream"), method="GET")
        result = (await handle.handle(call({"filter": {"a": 1}})))["result"]
        assert result["isError"] is True

    @pytest.mark.asyncio
    async def test_non_object_params_is_handled(self):
        handle = make_handle(lambda r: pytest.fail("must not call upstream"))
        response = await handle.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": [1]})
        assert response["error"]["code"] == -32602

    @pytest.mark.asyncio
    async def test_unknown_tool_is_invalid_params(self):
        handle = make_handle(lambda r: pytest.fail("must not call upstream"))
        response = await handle.handle(call(CHAT_ARGS, name="other"))
        assert response["error"]["code"] == -32602

    @pytest.mark.asyncio
    async def test_unknown_method_is_method_not_found(self):
        handle = make_handle(lambda r: pytest.fail("must not call upstream"))
        response = await handle.handle({"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
        assert response["error"]["code"] == -32601

    @pytest.mark.asyncio
    async def test_notification_has_no_response(self):
        handle = make_handle(lambda r: pytest.fail("must not call upstream"))
        assert await handle.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None

    def test_lifecycle_matches_popen(self):
        handle = make_handle(lambda r: httpx.Response(200))
        assert handle.poll() is None
        handle.terminate()
        assert handle.poll() == 0
        assert handle.wait() == 0

    def test_missing_header_variable_fails_construction(self):
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            ProxyHandle("openai", proxy_config(), {})


# ── ServerManager and gateway router ────────────────────────────────────────

class TestServerManagerProxy:
    @pytest.mark.asyncio
    async def test_start_status_and_stop(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
        manager = ServerManager(InMemoryBackend())
        config = {"id": "openai", "name": "OpenAI", **proxy_config()}
        await manager.db.save_server_config(config)

        assert await manager.start_server("openai", config) is True
        handle = manager.processes["openai"]
        assert isinstance(handle, ProxyHandle)
        assert handle.headers["Authorization"] == "Bearer sk-env"

        status = await manager.get_server_status("openai")
        assert (status["state"], status["transport"], status["url"]) == ("running", "proxy", ENDPOINT)

        stored = await manager.db.get_server_config("openai")
        assert [t["name"] for t in stored["tools"]] == ["chat_completion"]

        [listed] = await manager.list_servers()
        assert listed["config"] == {"transport": "proxy", "endpoint": ENDPOINT, "method": "POST"}

        assert await manager.stop_server("openai") is True
        assert "openai" not in manager.processes
        assert (await manager.get_server_status("openai"))["state"] == "stopped"

    @pytest.mark.asyncio
    async def test_instance_env_resolves_headers(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        manager = ServerManager(InMemoryBackend())
        config = {"id": "openai", "name": "OpenAI", **proxy_config()}
        await manager.db.save_server_config(config)
        await manager.db.save_instance_state({"server_id": "openai", "env": {"OPENAI_API_KEY": "sk-instance"}})

        assert await manager.start_server("openai", config) is True
        assert manager.processes["openai"].headers["Authorization"] == "Bearer sk-instance"

    @pytest.mark.asyncio
    async def test_start_fails_when_header_variable_missing(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        manager = ServerManager(InMemoryBackend())
        config = {"id": "openai", "name": "OpenAI", **proxy_config()}

        assert await manager.start_server("openai", config) is False
        assert "openai" not in manager.processes


class TestGatewayRouter:
    """Requests shaped the way FluidGPT sends them: one stateless POST, no initialize first."""

    @pytest.fixture
    def manager(self, monkeypatch):
        monkeypatch.delenv("FMCP_SECURE_MODE", raising=False)
        manager = ServerManager(InMemoryBackend())
        manager.processes["openai"] = make_handle(
            lambda r: httpx.Response(200, json=CHAT_RESPONSE),
            response_path="choices.0.message.content",
        )
        return manager

    @pytest.fixture
    def client(self, manager):
        app = FastAPI()
        app.include_router(create_dynamic_router(manager))
        return TestClient(app)

    def test_tools_list_without_initialize(self, client):
        resp = client.post("/openai/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert resp.status_code == 200
        assert [t["name"] for t in resp.json()["result"]["tools"]] == ["chat_completion"]

    def test_tools_call_returns_upstream_answer(self, client):
        resp = client.post("/openai/mcp", json=call(CHAT_ARGS))
        assert resp.status_code == 200
        assert resp.json()["result"]["content"][0]["text"] == "Hello there"

    def test_notification_is_acknowledged(self, client):
        resp = client.post("/openai/mcp", json={"jsonrpc": "2.0", "method": "notifications/cancelled"})
        assert resp.status_code == 202

    @pytest.mark.asyncio
    async def test_concurrency_limit_applies(self, manager, client):
        manager.configs["openai"] = {"id": "openai", "max_concurrent_requests": 1}
        sem = manager.get_concurrency_semaphore("openai")
        await sem.acquire()
        try:
            resp = client.post("/openai/mcp", json=call(CHAT_ARGS))
        finally:
            sem.release()
        assert resp.status_code == 429

    def test_rest_tools_call(self, client):
        resp = client.post("/openai/mcp/tools/call", json={"name": "chat_completion", "arguments": CHAT_ARGS})
        assert resp.status_code == 200
        assert resp.json()["result"]["content"][0]["text"] == "Hello there"
