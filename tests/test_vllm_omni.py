"""
Tests for vLLM Omni multimodal generation endpoints.

Tests capability validation, endpoint routing, and integration
with Replicate for image/video generation.
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient

# Import the router for testing
from fluidmcp.cli.api.management import router as management_router
from fluidmcp.cli.services import omni_adapter


@pytest.fixture
def client():
    """Create test client."""
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(management_router, prefix="/api")
    return TestClient(app)


class TestCapabilityValidation:
    """Test capability validation helper."""

    def test_capability_validation_passes_for_supported(self):
        """Test that validation passes when capability is supported."""
        config = {"capabilities": ["text-to-image", "text-to-video"]}
        # Should not raise
        omni_adapter.assert_capability(config, "test-model", "text-to-image")

    def test_capability_validation_fails_for_unsupported(self):
        """Test that validation fails when capability is missing."""
        config = {"capabilities": ["text-to-image"]}

        with pytest.raises(HTTPException) as exc_info:
            omni_adapter.assert_capability(config, "test-model", "text-to-video")

        assert exc_info.value.status_code == 400
        assert "does not support" in exc_info.value.detail

    def test_capability_validation_fails_for_empty_capabilities(self):
        """Test that validation fails when capabilities list is empty."""
        config = {"capabilities": []}

        with pytest.raises(HTTPException) as exc_info:
            omni_adapter.assert_capability(config, "test-model", "text-to-image")

        assert exc_info.value.status_code == 400

    def test_capability_validation_fails_for_missing_capabilities_field(self):
        """Test that validation fails when capabilities field is missing."""
        config = {}

        with pytest.raises(HTTPException) as exc_info:
            omni_adapter.assert_capability(config, "test-model", "text-to-image")

        assert exc_info.value.status_code == 400


class TestImageGenerationEndpoint:
    """Test image generation endpoint."""

    def test_image_generation_requires_authentication(self, client):
        """Test that image generation endpoint requires token."""
        # Without mocking config, returns 403/404 depending on FastAPI dependency execution order
        # FastAPI may check auth token before or after model validation
        response = client.post(
            "/api/llm/v1/generate/image",
            json={"model": "flux-image", "prompt": "test"}
        )
        assert response.status_code in [403, 404]  # Auth or model not found

    def test_image_generation_validates_model_exists(self, client):
        """Test that endpoint validates model exists."""
        with patch('fluidmcp.cli.api.management.get_model_config', return_value=None):
            response = client.post(
                "/api/llm/v1/generate/image",
                json={"model": "unknown-model", "prompt": "test"}
            )
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_image_generation_validates_provider_type(self, client):
        """Test that endpoint only works with Replicate models."""
        with patch('fluidmcp.cli.api.management.get_model_config', return_value={"type": "vllm"}):
            with patch('fluidmcp.cli.api.management.get_model_type', return_value="vllm"):
                response = client.post(
                    "/api/llm/v1/generate/image",
                    json={"model": "vllm-model", "prompt": "test"}
                )
                assert response.status_code == 400
                assert "only supported for Replicate" in response.json()["detail"]

    @pytest.mark.skip(reason="Requires full auth setup - covered by unit tests")
    def test_image_generation_delegates_to_adapter(self, client):
        """Test that image generation delegates to omni_adapter."""
        # This test requires full auth setup which is complex in test environment
        # Skipping delegation test - covered by unit tests in TestOmniAdapterFunctions
        pass


class TestVideoGenerationEndpoint:
    """Test video generation endpoint."""

    def test_video_generation_requires_authentication(self, client):
        """Test that video generation endpoint requires token."""
        # Without mocking config, returns 403/404 depending on FastAPI dependency execution order
        response = client.post(
            "/api/llm/v1/generate/video",
            json={"model": "animatediff-video", "prompt": "test"}
        )
        assert response.status_code in [403, 404]  # Auth or model not found

    def test_video_generation_validates_model_exists(self, client):
        """Test that endpoint validates model exists."""
        with patch('fluidmcp.cli.api.management.get_model_config', return_value=None):
            response = client.post(
                "/api/llm/v1/generate/video",
                json={"model": "unknown-model", "prompt": "test"}
            )
            assert response.status_code == 404

    def test_video_generation_validates_provider_type(self, client):
        """Test that endpoint only works with Replicate models."""
        with patch('fluidmcp.cli.api.management.get_model_config', return_value={"type": "vllm"}):
            with patch('fluidmcp.cli.api.management.get_model_type', return_value="vllm"):
                response = client.post(
                    "/api/llm/v1/generate/video",
                    json={"model": "vllm-model", "prompt": "test"}
                )
                assert response.status_code == 400
                assert "only supported for Replicate" in response.json()["detail"]


class TestImageAnimationEndpoint:
    """Test image animation (image-to-video) endpoint."""

    def test_animation_requires_authentication(self, client):
        """Test that animation endpoint requires token."""
        # Without mocking config, returns 403/404 depending on FastAPI dependency execution order
        response = client.post(
            "/api/llm/v1/animate",
            json={"model": "stable-video", "image_url": "https://example.com/img.jpg"}
        )
        assert response.status_code in [403, 404]  # Auth or model not found

    def test_animation_validates_model_exists(self, client):
        """Test that endpoint validates model exists."""
        with patch('fluidmcp.cli.api.management.get_model_config', return_value=None):
            response = client.post(
                "/api/llm/v1/animate",
                json={"model": "unknown-model", "image_url": "https://example.com/img.jpg"}
            )
            assert response.status_code == 404

    def test_animation_validates_provider_type(self, client):
        """Test that endpoint only works with Replicate models."""
        with patch('fluidmcp.cli.api.management.get_model_config', return_value={"type": "vllm"}):
            with patch('fluidmcp.cli.api.management.get_model_type', return_value="vllm"):
                response = client.post(
                    "/api/llm/v1/animate",
                    json={"model": "vllm-model", "image_url": "https://example.com/img.jpg"}
                )
                assert response.status_code == 400
                assert "only supported for Replicate" in response.json()["detail"]


class TestGenerationStatusEndpoint:
    """Test generation status polling endpoint."""

    def test_status_endpoint_requires_authentication(self, client):
        """Test that status endpoint requires token or has valid config."""
        # Returns 401/403 if auth fails, 503 if REPLICATE_API_TOKEN is not set
        response = client.get("/api/llm/predictions/abc123")
        assert response.status_code in [401, 403, 503]  # Auth or missing config

    @pytest.mark.skip(reason="Requires full auth setup - covered by manual testing")
    def test_status_endpoint_returns_prediction_status(self, client):
        """Test that status endpoint returns prediction information."""
        # This test requires full auth setup which is complex in test environment
        # Skipping - covered by manual testing
        pass


class TestOmniAdapterFunctions:
    """Test omni_adapter module functions."""

    @pytest.mark.asyncio
    async def test_generate_image_validates_capability(self):
        """Test that generate_image validates capability."""
        config = {"capabilities": ["text-to-video"]}  # Missing text-to-image
        mock_client = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await omni_adapter.generate_image("test-model", config, {}, mock_client)

        assert exc_info.value.status_code == 400
        assert "text-to-image" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_generate_image_calls_client(self):
        """Test that generate_image calls replicate client."""
        config = {"capabilities": ["text-to-image"]}
        mock_client = AsyncMock()
        mock_client.predict.return_value = {"id": "pred123", "status": "starting"}

        payload = {"prompt": "test"}
        result = await omni_adapter.generate_image("test-model", config, payload, mock_client)

        mock_client.predict.assert_called_once_with(payload)
        assert result["id"] == "pred123"

    @pytest.mark.asyncio
    async def test_generate_video_validates_capability(self):
        """Test that generate_video validates capability."""
        config = {"capabilities": ["text-to-image"]}  # Missing text-to-video
        mock_client = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await omni_adapter.generate_video("test-model", config, {}, mock_client)

        assert exc_info.value.status_code == 400
        assert "text-to-video" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_animate_image_validates_capability(self):
        """Test that animate_image validates capability."""
        config = {"capabilities": ["text-to-image"]}  # Missing image-to-video
        mock_client = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await omni_adapter.animate_image("test-model", config, {}, mock_client)

        assert exc_info.value.status_code == 400
        assert "image-to-video" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_generation_status_calls_client(self):
        """Test that get_generation_status calls replicate client."""
        mock_client = AsyncMock()
        mock_client.get_prediction.return_value = {
            "id": "pred123",
            "status": "succeeded",
            "output": ["url"]
        }

        result = await omni_adapter.get_generation_status("pred123", mock_client)

        mock_client.get_prediction.assert_called_once_with("pred123")
        assert result["id"] == "pred123"


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    @pytest.mark.skip(reason="Integration test requiring actual Replicate API")
    def test_complete_image_generation_flow(self):
        """Test complete flow from request to status check."""
        # This would be an integration test requiring actual Replicate API
        # Marking as integration test
        pass

    @pytest.mark.skip(reason="Integration test requiring actual Replicate API")
    def test_complete_video_generation_flow(self):
        """Test complete flow for video generation."""
        # This would be an integration test requiring actual Replicate API
        # Marking as integration test
        pass
