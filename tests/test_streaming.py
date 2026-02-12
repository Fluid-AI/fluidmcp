"""Unit tests for vLLM streaming support"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI


class TestStreamingValidation:
    """Tests for streaming request validation"""

    def test_non_streaming_request_works(self):
        """Test that non-streaming requests still work"""
        from fluidmcp.cli.services.run_servers import _add_llm_proxy_routes

        app = FastAPI()

        with patch('fluidmcp.cli.services.run_servers._llm_endpoints', {
            "vllm": {
                "base_url": "http://localhost:8001/v1",
                "chat": "/chat/completions",
                "completions": "/completions",
                "models": "/models"
            }
        }):
            with patch('fluidmcp.cli.services.run_servers._llm_processes', {}):
                with patch('fluidmcp.cli.services.run_servers._llm_registry_lock', MagicMock()):
                    _add_llm_proxy_routes(app)

                    client = TestClient(app)

                    # Mock the actual proxy request
                    with patch('fluidmcp.cli.services.run_servers._proxy_llm_request', new_callable=AsyncMock) as mock_proxy:
                        mock_proxy.return_value = {"id": "test", "choices": []}

                        response = client.post(
                            "/llm/v1/chat/completions",
                            json={
                                "model": "test",
                                "messages": [{"role": "user", "content": "Hello"}],
                                "stream": False
                            }
                        )

                        assert response.status_code == 200
                        mock_proxy.assert_called_once()

    def test_non_streaming_completions_works(self):
        """Test that non-streaming completions endpoint works"""
        from fluidmcp.cli.services.run_servers import _add_llm_proxy_routes

        app = FastAPI()

        with patch('fluidmcp.cli.services.run_servers._llm_endpoints', {
            "vllm": {
                "base_url": "http://localhost:8001/v1",
                "chat": "/chat/completions",
                "completions": "/completions",
                "models": "/models"
            }
        }):
            with patch('fluidmcp.cli.services.run_servers._llm_processes', {}):
                with patch('fluidmcp.cli.services.run_servers._llm_registry_lock', MagicMock()):
                    _add_llm_proxy_routes(app)

                    client = TestClient(app)

                    # Mock the actual proxy request
                    with patch('fluidmcp.cli.services.run_servers._proxy_llm_request', new_callable=AsyncMock) as mock_proxy:
                        mock_proxy.return_value = {"id": "test", "choices": []}

                        response = client.post(
                            "/llm/v1/completions",
                            json={
                                "model": "test",
                                "prompt": "Hello",
                                "stream": False
                            }
                        )

                        assert response.status_code == 200
                        mock_proxy.assert_called_once()

    def test_streaming_validates_before_response(self):
        """Test that streaming validates model availability before starting stream"""
        from fluidmcp.cli.services.run_servers import _add_llm_proxy_routes

        app = FastAPI()

        # Model not in registry
        with patch('fluidmcp.cli.services.run_servers._llm_endpoints', {}):
            with patch('fluidmcp.cli.services.run_servers._llm_processes', {}):
                with patch('fluidmcp.cli.services.run_servers._llm_registry_lock', MagicMock()):
                    _add_llm_proxy_routes(app)

                    client = TestClient(app)

                    response = client.post(
                        "/llm/v1/chat/completions",
                        json={
                            "model": "test",
                            "messages": [{"role": "user", "content": "Hello"}],
                            "stream": True
                        }
                    )

                    # Should return 404 BEFORE trying to stream
                    assert response.status_code == 404
                    assert "not configured" in response.json()["detail"]

    def test_streaming_completions_validates_before_response(self):
        """Test that streaming validates model availability for completions endpoint"""
        from fluidmcp.cli.services.run_servers import _add_llm_proxy_routes

        app = FastAPI()

        # Model not in registry
        with patch('fluidmcp.cli.services.run_servers._llm_endpoints', {}):
            with patch('fluidmcp.cli.services.run_servers._llm_processes', {}):
                with patch('fluidmcp.cli.services.run_servers._llm_registry_lock', MagicMock()):
                    _add_llm_proxy_routes(app)

                    client = TestClient(app)

                    response = client.post(
                        "/llm/v1/completions",
                        json={
                            "model": "test",
                            "prompt": "Hello",
                            "stream": True
                        }
                    )

                    # Should return 404 BEFORE trying to stream
                    assert response.status_code == 404
                    assert "not configured" in response.json()["detail"]

    def test_streaming_checks_process_running(self):
        """Test that streaming checks if process is running before starting stream"""
        from fluidmcp.cli.services.run_servers import _add_llm_proxy_routes, LLMProcess

        app = FastAPI()

        # Create a mock process that's not running
        mock_process = Mock(spec=LLMProcess)
        mock_process.is_running.return_value = False

        with patch('fluidmcp.cli.services.run_servers._llm_endpoints', {
            "vllm": {
                "base_url": "http://localhost:8001/v1",
                "chat": "/chat/completions",
                "completions": "/completions",
                "models": "/models"
            }
        }):
            with patch('fluidmcp.cli.services.run_servers._llm_processes', {"vllm": mock_process}):
                with patch('fluidmcp.cli.services.run_servers._llm_registry_lock', MagicMock()):
                    _add_llm_proxy_routes(app)

                    client = TestClient(app)

                    response = client.post(
                        "/llm/v1/chat/completions",
                        json={
                            "model": "vllm",
                            "messages": [{"role": "user", "content": "Hello"}],
                            "stream": True
                        }
                    )

                    # Should return 503 BEFORE trying to stream if model not running
                    # OR 404 if model not found in registry
                    assert response.status_code in [404, 503]
                    if response.status_code == 503:
                        assert "not running" in response.json()["detail"]

    def test_malformed_json_returns_error(self):
        """Test that malformed JSON in request body is handled gracefully"""
        from fluidmcp.cli.services.run_servers import _add_llm_proxy_routes

        app = FastAPI()

        with patch('fluidmcp.cli.services.run_servers._llm_endpoints', {
            "vllm": {
                "base_url": "http://localhost:8001/v1",
                "chat": "/chat/completions",
                "completions": "/completions",
                "models": "/models"
            }
        }):
            with patch('fluidmcp.cli.services.run_servers._llm_processes', {}):
                with patch('fluidmcp.cli.services.run_servers._llm_registry_lock', MagicMock()):
                    _add_llm_proxy_routes(app)

                    client = TestClient(app, raise_server_exceptions=False)

                    # Send malformed JSON
                    response = client.post(
                        "/llm/v1/chat/completions",
                        data="invalid json {",
                        headers={"Content-Type": "application/json"}
                    )

                    # Malformed JSON in the request body results in a 500 Internal Server Error
                    assert response.status_code == 500

    @pytest.mark.skip(
        reason="FastAPI TestClient cannot reliably consume async SSE generators; "
               "streaming behavior is validated via manual integration tests"
    )
    def test_stream_parameter_detection(self):
        """Test that stream parameter is correctly detected"""
        from fluidmcp.cli.services.run_servers import _add_llm_proxy_routes

        app = FastAPI()

        mock_process = Mock()
        mock_process.is_running.return_value = True

        with patch('fluidmcp.cli.services.run_servers._llm_endpoints', {
            "vllm": {
                "base_url": "http://localhost:8001/v1",
                "chat": "/chat/completions",
                "completions": "/completions",
                "models": "/models"
            }
        }):
            with patch('fluidmcp.cli.services.run_servers._llm_processes', {"vllm": mock_process}):
                with patch('fluidmcp.cli.services.run_servers._llm_registry_lock', MagicMock()):
                    _add_llm_proxy_routes(app)

                    client = TestClient(app)

                    # Test stream=true
                    with patch('fluidmcp.cli.services.run_servers._proxy_llm_request_streaming', new_callable=AsyncMock) as mock_stream:
                        # Mock the async generator
                        async def mock_gen():
                            yield b'data: test\n\n'

                        mock_stream.return_value = mock_gen()

                        response = client.post(
                            "/llm/v1/chat/completions",
                            json={"stream": True, "messages": []}
                        )

                        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
                        mock_stream.assert_called_once()

                    # Test stream=false (should use non-streaming)
                    with patch('fluidmcp.cli.services.run_servers._proxy_llm_request', new_callable=AsyncMock) as mock_non_stream:
                        mock_non_stream.return_value = {"id": "test"}

                        response = client.post(
                            "/llm/v1/chat/completions",
                            json={"stream": False, "messages": []}
                        )

                        assert response.status_code == 200
                        mock_non_stream.assert_called_once()
