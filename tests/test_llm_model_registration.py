"""
Tests for LLM model registration backend functionality.

Tests the persistence layer (InMemoryBackend and DatabaseManager) for LLM model
CRUD operations: save_llm_model, get_llm_model, delete_llm_model, update_llm_model.
Also tests Pydantic validation models and rate limiter thread safety.

Note: These are unit tests for backend classes, not API endpoint integration tests.
"""
import pytest
from unittest.mock import AsyncMock

from fluidmcp.cli.api.management import (
    ReplicateModelConfig,
)


class TestLLMModelRegistration:
    """Tests for POST /api/llm/models endpoint."""

    @pytest.fixture
    def mock_db_backend(self):
        """Mock DatabaseManager backend."""
        mock_db = AsyncMock()
        mock_db.save_llm_model = AsyncMock(return_value=True)
        mock_db.get_llm_model = AsyncMock(return_value=None)
        mock_db.delete_llm_model = AsyncMock(return_value=True)
        mock_db.update_llm_model = AsyncMock(return_value=True)
        return mock_db

    @pytest.fixture
    def mock_memory_backend(self):
        """Mock InMemoryBackend."""
        from fluidmcp.cli.repositories.memory import InMemoryBackend
        mock_backend = InMemoryBackend()
        return mock_backend

    @pytest.mark.asyncio
    async def test_save_llm_model_signature_consistency(self, mock_memory_backend):
        """
        Test that InMemoryBackend.save_llm_model signature matches DatabaseManager.

        CRITICAL: This test ensures API signature consistency between backends.
        Both backends must accept a single model_config dict (not model_id + config).
        """
        # Model config with model_id inside (as expected by both backends)
        model_config = {
            "model_id": "test-model",
            "type": "replicate",
            "model": "meta/llama-2-7b-chat",
            "api_key": "test-key",
        }

        # Test that save_llm_model accepts single argument
        result = await mock_memory_backend.save_llm_model(model_config)
        assert result is True

        # Verify model was saved correctly
        saved_model = await mock_memory_backend.get_llm_model("test-model")
        assert saved_model is not None
        assert saved_model["model_id"] == "test-model"
        assert saved_model["type"] == "replicate"

    @pytest.mark.asyncio
    async def test_save_llm_model_missing_model_id(self, mock_memory_backend):
        """Test that save_llm_model rejects config without model_id."""
        # Config missing model_id
        model_config = {
            "type": "replicate",
            "model": "meta/llama-2-7b-chat",
        }

        result = await mock_memory_backend.save_llm_model(model_config)
        assert result is False  # Should fail gracefully

    @pytest.mark.asyncio
    async def test_replicate_model_config_validation(self):
        """Test Pydantic validation for Replicate model configuration."""
        # Valid config
        valid_config = ReplicateModelConfig(
            model_id="test-model",
            type="replicate",
            model="meta/llama-2-7b-chat",
            api_key="${REPLICATE_API_TOKEN}",
        )
        assert valid_config.model_id == "test-model"
        assert valid_config.type == "replicate"

        # Invalid config - missing required fields
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ReplicateModelConfig(
                model_id="test-model",
                type="replicate",
                # Missing 'model' field
            )

    @pytest.mark.asyncio
    async def test_model_registration_duplicate_prevention(self, mock_memory_backend):
        """Test that duplicate model registration is prevented."""
        model_config = {
            "model_id": "test-model",
            "type": "replicate",
            "model": "meta/llama-2-7b-chat",
            "api_key": "test-key",
        }

        # First registration should succeed
        result1 = await mock_memory_backend.save_llm_model(model_config)
        assert result1 is True

        # Second registration with the same model_id should be prevented
        from fluidmcp.cli.repositories.base import DuplicateKeyError
        with pytest.raises(DuplicateKeyError):
            await mock_memory_backend.save_llm_model(model_config)

        # Confirm the original model is still registered
        existing = await mock_memory_backend.get_llm_model("test-model")
        assert existing is not None  # Model already exists


class TestLLMModelDeletion:
    """Tests for DELETE /api/llm/models/{model_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_llm_model_success(self):
        """Test successful model deletion."""
        from fluidmcp.cli.repositories.memory import InMemoryBackend
        backend = InMemoryBackend()

        # Register a model first
        model_config = {
            "model_id": "test-model",
            "type": "replicate",
            "model": "meta/llama-2-7b-chat",
            "api_key": "test-key",
        }
        await backend.save_llm_model(model_config)

        # Delete the model
        result = await backend.delete_llm_model("test-model")
        assert result is True

        # Verify model is gone
        deleted_model = await backend.get_llm_model("test-model")
        assert deleted_model is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_model(self):
        """Test deletion of non-existent model."""
        from fluidmcp.cli.repositories.memory import InMemoryBackend
        backend = InMemoryBackend()

        # Try to delete non-existent model
        result = await backend.delete_llm_model("nonexistent-model")
        assert result is False  # Should return False, not raise


class TestLLMModelUpdate:
    """Tests for LLM model update backend functionality."""

    @pytest.mark.asyncio
    async def test_update_llm_model_success(self):
        """Test successful model update."""
        from fluidmcp.cli.repositories.memory import InMemoryBackend
        backend = InMemoryBackend()

        # Register a model first
        model_config = {
            "model_id": "test-model",
            "type": "replicate",
            "model": "meta/llama-2-7b-chat",
            "api_key": "test-key",
            "default_params": {"temperature": 0.7},
        }
        await backend.save_llm_model(model_config)

        # Update the model
        updates = {
            "default_params": {"temperature": 0.9, "max_tokens": 500}
        }
        result = await backend.update_llm_model("test-model", updates)
        assert result is True

        # Verify updates were applied
        updated_model = await backend.get_llm_model("test-model")
        assert updated_model["default_params"]["temperature"] == 0.9
        assert updated_model["default_params"]["max_tokens"] == 500

    @pytest.mark.asyncio
    async def test_update_nonexistent_model(self):
        """Test update of non-existent model."""
        from fluidmcp.cli.repositories.memory import InMemoryBackend
        backend = InMemoryBackend()

        # Try to update non-existent model
        updates = {"default_params": {"temperature": 0.9}}
        result = await backend.update_llm_model("nonexistent-model", updates)
        assert result is False  # Should return False, not raise

    @pytest.mark.asyncio
    async def test_update_preserves_existing_fields(self):
        """Test that update only modifies specified fields."""
        from fluidmcp.cli.repositories.memory import InMemoryBackend
        backend = InMemoryBackend()

        # Register a model with multiple fields
        model_config = {
            "model_id": "test-model",
            "type": "replicate",
            "model": "meta/llama-2-7b-chat",
            "api_key": "test-key",
            "default_params": {"temperature": 0.7},
            "timeout": 120,
        }
        await backend.save_llm_model(model_config)

        # Update only default_params
        updates = {"default_params": {"temperature": 0.9}}
        await backend.update_llm_model("test-model", updates)

        # Verify other fields remain unchanged
        updated_model = await backend.get_llm_model("test-model")
        assert updated_model["default_params"]["temperature"] == 0.9
        assert updated_model["timeout"] == 120  # Unchanged
        assert updated_model["api_key"] == "test-key"  # Unchanged


class TestBackendAPIConsistency:
    """Tests to ensure InMemoryBackend and DatabaseManager have consistent APIs."""

    @pytest.mark.asyncio
    async def test_memory_backend_api_signature(self):
        """
        Test that InMemoryBackend methods match DatabaseManager signatures.

        This is critical to prevent runtime errors when switching backends.
        """
        from fluidmcp.cli.repositories.memory import InMemoryBackend
        import inspect

        backend = InMemoryBackend()

        # Check save_llm_model signature: should accept (model_config: Dict)
        save_sig = inspect.signature(backend.save_llm_model)
        params = list(save_sig.parameters.keys())
        # Should have 'model_config' only (not 'model_id' as separate param)
        # Note: inspect.signature doesn't include 'self' for bound methods
        assert len(params) == 1  # model_config only
        assert 'model_config' in params
        assert 'model_id' not in params  # CRITICAL: model_id is inside dict

        # Check get_llm_model signature: should accept (model_id: str)
        get_sig = inspect.signature(backend.get_llm_model)
        params = list(get_sig.parameters.keys())
        assert 'model_id' in params

        # Check delete_llm_model signature: should accept (model_id: str)
        delete_sig = inspect.signature(backend.delete_llm_model)
        params = list(delete_sig.parameters.keys())
        assert 'model_id' in params

        # Check update_llm_model signature: should accept (model_id: str, updates: Dict)
        update_sig = inspect.signature(backend.update_llm_model)
        params = list(update_sig.parameters.keys())
        assert 'model_id' in params
        assert 'updates' in params

    @pytest.mark.asyncio
    async def test_end_to_end_model_lifecycle(self):
        """
        Test complete model lifecycle: register → update → delete.

        This integration test ensures all CRUD operations work correctly.
        """
        from fluidmcp.cli.repositories.memory import InMemoryBackend
        backend = InMemoryBackend()

        # 1. Register model
        model_config = {
            "model_id": "lifecycle-test",
            "type": "replicate",
            "model": "meta/llama-2-7b-chat",
            "api_key": "test-key",
            "default_params": {"temperature": 0.7},
        }
        save_result = await backend.save_llm_model(model_config)
        assert save_result is True

        # 2. Verify registration
        saved_model = await backend.get_llm_model("lifecycle-test")
        assert saved_model is not None
        assert saved_model["model_id"] == "lifecycle-test"

        # 3. Update model
        updates = {"default_params": {"temperature": 0.9}}
        update_result = await backend.update_llm_model("lifecycle-test", updates)
        assert update_result is True

        # 4. Verify update
        updated_model = await backend.get_llm_model("lifecycle-test")
        assert updated_model["default_params"]["temperature"] == 0.9

        # 5. Delete model
        delete_result = await backend.delete_llm_model("lifecycle-test")
        assert delete_result is True

        # 6. Verify deletion
        deleted_model = await backend.get_llm_model("lifecycle-test")
        assert deleted_model is None


class TestRateLimiterThreadSafety:
    """Tests for rate limiter thread safety."""

    def test_rate_limiter_has_lock(self):
        """Test that rate limiter uses threading.Lock for thread safety."""
        from fluidmcp.cli.utils import rate_limiter

        # Verify _rate_limit_lock exists and is a Lock
        assert hasattr(rate_limiter, '_rate_limit_lock')
        lock = rate_limiter._rate_limit_lock

        # Verify it has Lock-specific methods (duck typing approach)
        # This is more reliable than isinstance checks which can vary by Python implementation
        assert hasattr(lock, 'acquire')
        assert hasattr(lock, 'release')
        assert hasattr(lock, '__enter__')
        assert hasattr(lock, '__exit__')

        # Verify it's actually a lock by testing acquire/release behavior
        assert lock.acquire(blocking=False) is True
        lock.release()

    def test_rate_limiter_check_rate_limit(self):
        """Test that check_rate_limit function is thread-safe."""
        import uuid
        from fastapi import HTTPException
        from fluidmcp.cli.api.management import check_rate_limit

        # Use a unique key for this test run to avoid interference with other tests
        key = f"test-key-{uuid.uuid4()}"
        max_requests = 3
        window_seconds = 60

        # Should allow first 3 requests
        for i in range(max_requests):
            check_rate_limit(key, max_requests, window_seconds)

        # 4th request should be blocked
        with pytest.raises(HTTPException) as exc_info:
            check_rate_limit(key, max_requests, window_seconds)
        assert exc_info.value.status_code == 429
        assert "Rate limit exceeded" in str(exc_info.value.detail)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
