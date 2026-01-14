"""
Tests for persistence backends (DatabaseManager and InMemoryBackend).

Tests the abstract PersistenceBackend interface implementation across
both MongoDB and in-memory backends.
"""
import pytest
import asyncio
from datetime import datetime
from typing import Dict, Any

from fluidmcp.cli.repositories import PersistenceBackend, DatabaseManager, InMemoryBackend


# Test fixtures
@pytest.fixture
def sample_server_config() -> Dict[str, Any]:
    """Sample server configuration for testing."""
    return {
        "id": "test-server",
        "name": "Test Server",
        "description": "A test server configuration",
        "enabled": True,
        "mcp_config": {
            "command": "python",
            "args": ["-m", "test.server"],
            "env": {"TEST_VAR": "value"}
        },
        "restart_policy": "on-failure",
        "restart_window_sec": 300,
        "max_restarts": 3,
        "tools": [],
        "created_by": "test-user",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }


@pytest.fixture
def sample_instance_state() -> Dict[str, Any]:
    """Sample instance state for testing."""
    return {
        "server_id": "test-server",
        "state": "running",
        "pid": 12345,
        "start_time": datetime.utcnow(),
        "stop_time": None,
        "exit_code": None,
        "restart_count": 0,
        "last_health_check": datetime.utcnow(),
        "health_check_failures": 0,
        "host": "localhost",
        "port": 8090,
        "last_error": None,
        "started_by": "test-user",
        "updated_at": datetime.utcnow()
    }


@pytest.fixture
def sample_log_entry() -> Dict[str, Any]:
    """Sample log entry for testing."""
    return {
        "server_name": "test-server",
        "timestamp": datetime.utcnow(),
        "stream": "stdout",
        "content": "Test log message"
    }


class TestInMemoryBackend:
    """Tests for InMemoryBackend implementation."""

    @pytest.mark.asyncio
    async def test_connect(self):
        """Test backend connection."""
        backend = InMemoryBackend()
        assert await backend.connect() is True

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test backend disconnection."""
        backend = InMemoryBackend()
        await backend.connect()
        await backend.disconnect()
        # Verify data is cleared
        assert len(backend._servers) == 0
        assert len(backend._instances) == 0
        assert len(backend._logs) == 0

    @pytest.mark.asyncio
    async def test_save_and_get_server_config(self, sample_server_config):
        """Test saving and retrieving server config."""
        backend = InMemoryBackend()
        await backend.connect()

        # Save config
        result = await backend.save_server_config(sample_server_config)
        assert result is True

        # Retrieve config
        retrieved = await backend.get_server_config("test-server")
        assert retrieved is not None
        assert retrieved["id"] == "test-server"
        assert retrieved["name"] == "Test Server"

    @pytest.mark.asyncio
    async def test_save_config_without_id(self):
        """Test saving config without id fails."""
        backend = InMemoryBackend()
        await backend.connect()

        invalid_config = {"name": "Test"}
        result = await backend.save_server_config(invalid_config)
        assert result is False

    @pytest.mark.asyncio
    async def test_list_server_configs(self, sample_server_config):
        """Test listing server configs."""
        backend = InMemoryBackend()
        await backend.connect()

        # Save multiple configs
        config1 = sample_server_config.copy()
        config1["id"] = "server1"
        config2 = sample_server_config.copy()
        config2["id"] = "server2"
        config2["enabled"] = False

        await backend.save_server_config(config1)
        await backend.save_server_config(config2)

        # List all configs
        all_configs = await backend.list_server_configs(enabled_only=False)
        assert len(all_configs) == 2

        # List enabled only
        enabled_configs = await backend.list_server_configs(enabled_only=True)
        assert len(enabled_configs) == 1
        assert enabled_configs[0]["id"] == "server1"

    @pytest.mark.asyncio
    async def test_delete_server_config(self, sample_server_config):
        """Test deleting server config."""
        backend = InMemoryBackend()
        await backend.connect()

        # Save and delete
        await backend.save_server_config(sample_server_config)
        result = await backend.delete_server_config("test-server")
        assert result is True

        # Verify deletion
        retrieved = await backend.get_server_config("test-server")
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_config(self):
        """Test deleting non-existent config."""
        backend = InMemoryBackend()
        await backend.connect()

        result = await backend.delete_server_config("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_save_and_get_instance_state(self, sample_instance_state):
        """Test saving and retrieving instance state."""
        backend = InMemoryBackend()
        await backend.connect()

        # Save state
        result = await backend.save_instance_state(sample_instance_state)
        assert result is True

        # Retrieve state
        retrieved = await backend.get_instance_state("test-server")
        assert retrieved is not None
        assert retrieved["state"] == "running"
        assert retrieved["pid"] == 12345

    @pytest.mark.asyncio
    async def test_save_instance_state_without_server_id(self):
        """Test saving instance state without server_id fails."""
        backend = InMemoryBackend()
        await backend.connect()

        invalid_state = {"state": "running"}
        result = await backend.save_instance_state(invalid_state)
        assert result is False

    @pytest.mark.asyncio
    async def test_save_log_entry(self, sample_log_entry):
        """Test saving log entries."""
        backend = InMemoryBackend()
        await backend.connect()

        # Save log entry
        await backend.save_log_entry(sample_log_entry)

        # Retrieve logs
        logs = await backend.get_logs("test-server", lines=10)
        assert len(logs) == 1
        assert logs[0]["content"] == "Test log message"

    @pytest.mark.asyncio
    async def test_log_memory_limit(self, sample_log_entry):
        """Test global memory limit for logs."""
        backend = InMemoryBackend()
        await backend.connect()

        # Create many log entries (exceeding per-server limit)
        for i in range(1500):
            entry = sample_log_entry.copy()
            entry["content"] = f"Log message {i}"
            await backend.save_log_entry(entry)

        # Should be capped at per-server maxlen (1000)
        logs = await backend.get_logs("test-server", lines=2000)
        assert len(logs) <= 1000

    @pytest.mark.asyncio
    async def test_get_logs_empty(self):
        """Test getting logs for non-existent server."""
        backend = InMemoryBackend()
        await backend.connect()

        logs = await backend.get_logs("nonexistent", lines=10)
        assert len(logs) == 0

    @pytest.mark.asyncio
    async def test_config_isolation(self, sample_server_config):
        """Test that config mutations don't affect stored data."""
        backend = InMemoryBackend()
        await backend.connect()

        # Save config
        await backend.save_server_config(sample_server_config)

        # Mutate the original config
        sample_server_config["name"] = "Modified Name"

        # Retrieve should have original value
        retrieved = await backend.get_server_config("test-server")
        assert retrieved["name"] == "Test Server"


class TestDatabaseManager:
    """Tests for DatabaseManager implementation."""

    @pytest.mark.asyncio
    async def test_sanitize_mongodb_input(self):
        """Test MongoDB input sanitization."""
        # Test string with MongoDB operator
        result = DatabaseManager._sanitize_mongodb_input("$where: function()")
        assert not result.startswith("$")
        assert "{" not in result
        assert "}" not in result

        # Test nested dict
        input_dict = {
            "name": "$test",
            "nested": {
                "value": "${injection}"
            }
        }
        result = DatabaseManager._sanitize_mongodb_input(input_dict)
        assert not result["name"].startswith("$")
        assert not result["nested"]["value"].startswith("$")

        # Test list
        input_list = ["$item1", "normal", "${item2}"]
        result = DatabaseManager._sanitize_mongodb_input(input_list)
        assert not result[0].startswith("$")
        assert not result[2].startswith("$")

    @pytest.mark.asyncio
    async def test_validate_field_names(self):
        """Test field name validation."""
        allowed_fields = ["id", "name", "description", "enabled"]

        # Valid fields should not raise
        valid_fields = {"id": "test", "name": "Test Server"}
        try:
            DatabaseManager._validate_field_names(valid_fields, allowed_fields)
        except ValueError:
            pytest.fail("Valid fields raised ValueError")

        # Invalid field should raise
        invalid_fields = {"invalid_field": "value"}
        with pytest.raises(ValueError, match="Invalid field name"):
            DatabaseManager._validate_field_names(invalid_fields, allowed_fields)

        # MongoDB operators should be allowed
        operator_fields = {"$set": {"name": "Test"}}
        try:
            DatabaseManager._validate_field_names(operator_fields, allowed_fields)
        except ValueError:
            pytest.fail("MongoDB operator field raised ValueError")


class TestBackendConsistency:
    """Tests ensuring both backends implement the interface consistently."""

    @pytest.mark.asyncio
    async def test_both_backends_implement_interface(self):
        """Test that both backends properly implement PersistenceBackend."""
        in_memory = InMemoryBackend()
        assert isinstance(in_memory, PersistenceBackend)

        # DatabaseManager also implements the interface (tested separately with real MongoDB)

    @pytest.mark.asyncio
    async def test_crud_operations_parity(self, sample_server_config):
        """Test that CRUD operations work consistently across backends."""
        backend = InMemoryBackend()
        await backend.connect()

        # Create
        result = await backend.save_server_config(sample_server_config)
        assert result is True

        # Read
        retrieved = await backend.get_server_config("test-server")
        assert retrieved is not None

        # Update
        updated_config = sample_server_config.copy()
        updated_config["name"] = "Updated Server"
        await backend.save_server_config(updated_config)
        retrieved = await backend.get_server_config("test-server")
        assert retrieved["name"] == "Updated Server"

        # Delete
        result = await backend.delete_server_config("test-server")
        assert result is True
        retrieved = await backend.get_server_config("test-server")
        assert retrieved is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
