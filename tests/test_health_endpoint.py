"""Unit tests for health endpoint in run_servers.py"""

import pytest
import subprocess
from unittest.mock import Mock, patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    """Create a FastAPI app with health endpoint for testing"""
    from fluidmcp.cli.services.run_servers import _add_health_endpoint

    app = FastAPI()
    _add_health_endpoint(app)
    return app


@pytest.fixture
def client(app):
    """Create a test client"""
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for /health endpoint"""

    def test_health_endpoint_exists(self, client):
        """Test that health endpoint is registered"""
        response = client.get("/health")
        assert response.status_code in [200, 503]  # Either healthy or degraded

    def test_health_with_running_servers(self, client):
        """Test health endpoint when servers are running"""
        # Mock _get_server_processes to return running processes
        mock_process = Mock(spec=subprocess.Popen)
        mock_process.poll.return_value = None  # Process is running

        with patch('fluidmcp.cli.services.run_servers._get_server_processes') as mock_get:
            mock_get.return_value = {
                "server1": mock_process,
                "server2": mock_process
            }

            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["servers"] == 2
            assert data["running_servers"] == 2

    def test_health_with_stopped_servers(self, client):
        """Test health endpoint when servers are stopped"""
        # Mock _get_server_processes to return stopped processes
        mock_process = Mock(spec=subprocess.Popen)
        mock_process.poll.return_value = 1  # Process has exited

        with patch('fluidmcp.cli.services.run_servers._get_server_processes') as mock_get:
            mock_get.return_value = {
                "server1": mock_process,
                "server2": mock_process
            }

            response = client.get("/health")

            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "degraded"
            assert data["servers"] == 2
            assert data["running_servers"] == 0

    def test_health_with_mixed_servers(self, client):
        """Test health endpoint with mix of running and stopped servers"""
        # Create one running and one stopped process
        running_process = Mock(spec=subprocess.Popen)
        running_process.poll.return_value = None

        stopped_process = Mock(spec=subprocess.Popen)
        stopped_process.poll.return_value = 1

        with patch('fluidmcp.cli.services.run_servers._get_server_processes') as mock_get:
            mock_get.return_value = {
                "server1": running_process,
                "server2": stopped_process
            }

            response = client.get("/health")

            assert response.status_code == 200  # At least one running
            data = response.json()
            assert data["status"] == "healthy"
            assert data["servers"] == 2
            assert data["running_servers"] == 1

    def test_health_with_no_servers(self, client):
        """Test health endpoint when no servers are registered"""
        with patch('fluidmcp.cli.services.run_servers._get_server_processes') as mock_get:
            mock_get.return_value = {}

            response = client.get("/health")

            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "degraded"
            assert data["servers"] == 0
            assert data["running_servers"] == 0

    def test_health_with_none_processes(self, client):
        """Test health endpoint when _get_server_processes returns None"""
        with patch('fluidmcp.cli.services.run_servers._get_server_processes') as mock_get:
            mock_get.return_value = None

            response = client.get("/health")

            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "degraded"
            assert data["servers"] == 0
            assert data["running_servers"] == 0

    def test_health_with_exception(self, client):
        """Test health endpoint when an exception occurs"""
        with patch('fluidmcp.cli.services.run_servers._get_server_processes') as mock_get:
            mock_get.side_effect = RuntimeError("Unexpected error")

            response = client.get("/health")

            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "unhealthy"
            assert "error" in data
            assert data["servers"] == 0
            assert data["running_servers"] == 0

    def test_health_response_schema(self, client):
        """Test that health endpoint returns correct schema"""
        mock_process = Mock(spec=subprocess.Popen)
        mock_process.poll.return_value = None

        with patch('fluidmcp.cli.services.run_servers._get_server_processes') as mock_get:
            mock_get.return_value = {"server1": mock_process}

            response = client.get("/health")
            data = response.json()

            # Verify required fields
            assert "status" in data
            assert "servers" in data
            assert "running_servers" in data

            # Verify types
            assert isinstance(data["status"], str)
            assert isinstance(data["servers"], int)
            assert isinstance(data["running_servers"], int)

            # Verify status values
            assert data["status"] in ["healthy", "degraded", "unhealthy"]

    def test_health_with_null_process(self, client):
        """Test health endpoint handles None in process list"""
        mock_process = Mock(spec=subprocess.Popen)
        mock_process.poll.return_value = None

        with patch('fluidmcp.cli.services.run_servers._get_server_processes') as mock_get:
            # Mix of valid process and None
            mock_get.return_value = {
                "server1": mock_process,
                "server2": None  # Null process
            }

            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["servers"] == 2
            assert data["running_servers"] == 1  # Only counts valid running processes
