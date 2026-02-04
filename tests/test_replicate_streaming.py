"""
Tests for Replicate streaming SSE functionality.

Tests the replicate_chat_completion_stream function which polls
Replicate predictions and yields OpenAI-format SSE chunks.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch
from fluidmcp.cli.services.replicate_openai_adapter import replicate_chat_completion_stream


@pytest.mark.asyncio
class TestReplicateStreaming:
    """Test suite for Replicate streaming chat completions."""

    async def test_stream_success_single_chunk(self):
        """Test successful streaming with complete output in one poll."""
        # Mock Replicate client
        mock_client = Mock()
        mock_client.predict = AsyncMock(return_value={
            "id": "pred_test123",
            "status": "starting"
        })

        # Simulate prediction completing immediately
        mock_client.get_prediction = AsyncMock(return_value={
            "id": "pred_test123",
            "status": "succeeded",
            "output": "Hello, world!"
        })

        with patch('fluidmcp.cli.services.replicate_openai_adapter.get_replicate_client', return_value=mock_client):
            chunks = []
            async for chunk in replicate_chat_completion_stream(
                "test-model",
                {"messages": [{"role": "user", "content": "Hi"}]},
                timeout=30
            ):
                chunks.append(chunk)

        # Should have 2 chunks: content + final with finish_reason
        assert len(chunks) >= 2

        # Parse SSE chunks
        parsed_chunks = []
        for chunk in chunks:
            if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
                data = chunk.replace("data: ", "").strip()
                if data:
                    parsed_chunks.append(json.loads(data))

        # Check content chunk
        content_chunk = parsed_chunks[0]
        assert content_chunk["choices"][0]["delta"]["content"] == "Hello, world!"
        assert content_chunk["object"] == "chat.completion.chunk"

        # Check final chunk
        final_chunk = parsed_chunks[1]
        assert final_chunk["choices"][0]["finish_reason"] == "stop"
        assert final_chunk["choices"][0]["delta"] == {}


    async def test_stream_incremental_updates(self):
        """Test streaming with incremental output updates."""
        mock_client = Mock()
        mock_client.predict = AsyncMock(return_value={
            "id": "pred_incremental",
            "status": "starting"
        })

        # Simulate incremental output updates
        call_count = 0
        async def get_prediction_incremental(pred_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"id": pred_id, "status": "processing", "output": "Hello"}
            elif call_count == 2:
                return {"id": pred_id, "status": "processing", "output": "Hello, world"}
            else:
                return {"id": pred_id, "status": "succeeded", "output": "Hello, world!"}

        mock_client.get_prediction = get_prediction_incremental

        with patch('fluidmcp.cli.services.replicate_openai_adapter.get_replicate_client', return_value=mock_client):
            chunks = []
            async for chunk in replicate_chat_completion_stream(
                "test-model",
                {"messages": [{"role": "user", "content": "Hi"}]},
                timeout=30
            ):
                chunks.append(chunk)

        # Parse content chunks
        content_deltas = []
        for chunk in chunks:
            if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
                data = chunk.replace("data: ", "").strip()
                if data:
                    parsed = json.loads(data)
                    if "content" in parsed["choices"][0]["delta"]:
                        content_deltas.append(parsed["choices"][0]["delta"]["content"])

        # Should have multiple deltas
        assert len(content_deltas) > 1
        # Concatenated should equal full output
        assert "".join(content_deltas) == "Hello, world!"


    async def test_stream_error_handling_failed_prediction(self):
        """Test streaming handles failed predictions gracefully."""
        mock_client = Mock()
        mock_client.predict = AsyncMock(return_value={
            "id": "pred_failed",
            "status": "starting"
        })

        mock_client.get_prediction = AsyncMock(return_value={
            "id": "pred_failed",
            "status": "failed",
            "error": "Model crashed"
        })

        with patch('fluidmcp.cli.services.replicate_openai_adapter.get_replicate_client', return_value=mock_client):
            chunks = []
            async for chunk in replicate_chat_completion_stream(
                "test-model",
                {"messages": [{"role": "user", "content": "Hi"}]},
                timeout=30
            ):
                chunks.append(chunk)

        # Should have error chunk
        assert len(chunks) > 0

        # Parse error chunk
        error_chunk = None
        for chunk in chunks:
            if chunk.startswith("data: "):
                data = chunk.replace("data: ", "").strip()
                if data:
                    parsed = json.loads(data)
                    if "error" in parsed:
                        error_chunk = parsed
                        break

        assert error_chunk is not None
        assert "error" in error_chunk
        assert "Model crashed" in error_chunk["error"]["message"]
        assert error_chunk["error"]["code"] == "prediction_failed"


    async def test_stream_timeout(self):
        """Test streaming times out correctly."""
        mock_client = Mock()
        mock_client.predict = AsyncMock(return_value={
            "id": "pred_timeout",
            "status": "starting"
        })

        # Always return processing status
        mock_client.get_prediction = AsyncMock(return_value={
            "id": "pred_timeout",
            "status": "processing",
            "output": ""
        })

        with patch('fluidmcp.cli.services.replicate_openai_adapter.get_replicate_client', return_value=mock_client):
            chunks = []
            async for chunk in replicate_chat_completion_stream(
                "test-model",
                {"messages": [{"role": "user", "content": "Hi"}]},
                timeout=1  # Very short timeout
            ):
                chunks.append(chunk)

        # Should have timeout error chunk
        error_chunk = None
        for chunk in chunks:
            if chunk.startswith("data: "):
                data = chunk.replace("data: ", "").strip()
                if data:
                    parsed = json.loads(data)
                    if "error" in parsed:
                        error_chunk = parsed
                        break

        assert error_chunk is not None
        assert "timed out" in error_chunk["error"]["message"].lower()
        assert error_chunk["error"]["code"] == "prediction_timeout"


    async def test_stream_canceled_prediction(self):
        """Test streaming handles canceled predictions."""
        mock_client = Mock()
        mock_client.predict = AsyncMock(return_value={
            "id": "pred_canceled",
            "status": "starting"
        })

        mock_client.get_prediction = AsyncMock(return_value={
            "id": "pred_canceled",
            "status": "canceled",
            "output": ""
        })

        with patch('fluidmcp.cli.services.replicate_openai_adapter.get_replicate_client', return_value=mock_client):
            chunks = []
            async for chunk in replicate_chat_completion_stream(
                "test-model",
                {"messages": [{"role": "user", "content": "Hi"}]},
                timeout=30
            ):
                chunks.append(chunk)

        # Should have canceled error chunk
        error_chunk = None
        for chunk in chunks:
            if chunk.startswith("data: "):
                data = chunk.replace("data: ", "").strip()
                if data:
                    parsed = json.loads(data)
                    if "error" in parsed:
                        error_chunk = parsed
                        break

        assert error_chunk is not None
        assert "canceled" in error_chunk["error"]["message"].lower()
        assert error_chunk["error"]["code"] == "prediction_canceled"


    async def test_stream_creation_failure(self):
        """Test streaming handles prediction creation failure."""
        mock_client = Mock()
        mock_client.predict = AsyncMock(side_effect=Exception("API rate limit exceeded"))

        with patch('fluidmcp.cli.services.replicate_openai_adapter.get_replicate_client', return_value=mock_client):
            chunks = []
            async for chunk in replicate_chat_completion_stream(
                "test-model",
                {"messages": [{"role": "user", "content": "Hi"}]},
                timeout=30
            ):
                chunks.append(chunk)

        # Should have error chunk
        error_chunk = None
        for chunk in chunks:
            if chunk.startswith("data: "):
                data = chunk.replace("data: ", "").strip()
                if data:
                    parsed = json.loads(data)
                    if "error" in parsed:
                        error_chunk = parsed
                        break

        assert error_chunk is not None
        assert "API rate limit exceeded" in error_chunk["error"]["message"]
        assert error_chunk["error"]["code"] == "prediction_creation_failed"


    async def test_stream_sse_format_compliance(self):
        """Test that SSE chunks follow OpenAI format spec."""
        mock_client = Mock()
        mock_client.predict = AsyncMock(return_value={
            "id": "pred_format",
            "status": "starting"
        })

        mock_client.get_prediction = AsyncMock(return_value={
            "id": "pred_format",
            "status": "succeeded",
            "output": "Test output"
        })

        with patch('fluidmcp.cli.services.replicate_openai_adapter.get_replicate_client', return_value=mock_client):
            chunks = []
            async for chunk in replicate_chat_completion_stream(
                "test-model",
                {"messages": [{"role": "user", "content": "Hi"}]},
                timeout=30
            ):
                chunks.append(chunk)

        # Parse all chunks
        for chunk in chunks:
            if chunk.startswith("data: [DONE]"):
                # Final marker
                assert chunk == "data: [DONE]\n\n"
            elif chunk.startswith("data: "):
                # Must be valid JSON
                data = chunk.replace("data: ", "").strip()
                parsed = json.loads(data)

                # Check required fields
                if "error" not in parsed:
                    assert "id" in parsed
                    assert "object" in parsed
                    assert parsed["object"] == "chat.completion.chunk"
                    assert "created" in parsed
                    assert "model" in parsed
                    assert "choices" in parsed
                    assert len(parsed["choices"]) > 0

                    choice = parsed["choices"][0]
                    assert "index" in choice
                    assert "delta" in choice
                    assert choice["index"] == 0


    async def test_stream_preserves_completion_id(self):
        """Test that all chunks in a stream share the same completion ID."""
        mock_client = Mock()
        mock_client.predict = AsyncMock(return_value={
            "id": "pred_id_test",
            "status": "starting"
        })

        # Multiple polls to get multiple chunks
        call_count = 0
        async def get_prediction_multi(pred_id):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return {"id": pred_id, "status": "processing", "output": f"Chunk {call_count}"}
            else:
                return {"id": pred_id, "status": "succeeded", "output": "Chunk 1Chunk 2 Final"}

        mock_client.get_prediction = get_prediction_multi

        with patch('fluidmcp.cli.services.replicate_openai_adapter.get_replicate_client', return_value=mock_client):
            chunks = []
            async for chunk in replicate_chat_completion_stream(
                "test-model",
                {"messages": [{"role": "user", "content": "Hi"}]},
                timeout=30
            ):
                chunks.append(chunk)

        # Parse all completion IDs
        completion_ids = set()
        for chunk in chunks:
            if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
                data = chunk.replace("data: ", "").strip()
                if data:
                    parsed = json.loads(data)
                    if "id" in parsed:
                        completion_ids.add(parsed["id"])

        # All chunks should have same completion ID
        assert len(completion_ids) == 1
        completion_id = list(completion_ids)[0]
        assert completion_id.startswith("chatcmpl-")
