"""Unit tests for /metrics endpoint authentication."""

import os
import pytest
from unittest.mock import patch, Mock


class TestMetricsAuthentication:
    """Tests for metrics endpoint authentication in secure mode."""

    def test_metrics_endpoint_public_when_secure_mode_disabled(self):
        """Test that /metrics is publicly accessible when secure mode is disabled."""
        # Import here to avoid circular dependencies
        from fluidmcp.cli.services.run_servers import verify_token
        from fastapi.security import HTTPAuthorizationCredentials

        with patch.dict(os.environ, {"FMCP_SECURE_MODE": "false"}, clear=False):
            # Should return None (allow access) even without credentials
            result = verify_token(credentials=None)
            assert result is None

    def test_metrics_endpoint_requires_token_when_secure_mode_enabled(self):
        """Test that /metrics requires valid token when secure mode is enabled."""
        from fluidmcp.cli.services.run_servers import verify_token
        from fastapi.security import HTTPAuthorizationCredentials
        from fastapi import HTTPException

        with patch.dict(os.environ, {"FMCP_SECURE_MODE": "true", "FMCP_BEARER_TOKEN": "test-token-123"}, clear=False):
            # Missing credentials should raise 401
            with pytest.raises(HTTPException) as exc_info:
                verify_token(credentials=None)
            assert exc_info.value.status_code == 401

            # Invalid token should raise 401
            invalid_creds = Mock(spec=HTTPAuthorizationCredentials)
            invalid_creds.scheme = "Bearer"
            invalid_creds.credentials = "wrong-token"
            with pytest.raises(HTTPException) as exc_info:
                verify_token(credentials=invalid_creds)
            assert exc_info.value.status_code == 401

            # Valid token should succeed
            valid_creds = Mock(spec=HTTPAuthorizationCredentials)
            valid_creds.scheme = "Bearer"
            valid_creds.credentials = "test-token-123"
            result = verify_token(credentials=valid_creds)
            assert result is None  # None means success

    def test_metrics_endpoint_case_insensitive_bearer_scheme(self):
        """Test that bearer scheme check is case-insensitive."""
        from fluidmcp.cli.services.run_servers import verify_token
        from fastapi.security import HTTPAuthorizationCredentials

        with patch.dict(os.environ, {"FMCP_SECURE_MODE": "true", "FMCP_BEARER_TOKEN": "test-token"}, clear=False):
            # Uppercase BEARER should work
            creds = Mock(spec=HTTPAuthorizationCredentials)
            creds.scheme = "BEARER"
            creds.credentials = "test-token"
            result = verify_token(credentials=creds)
            assert result is None

            # Mixed case should work
            creds.scheme = "BeArEr"
            result = verify_token(credentials=creds)
            assert result is None

    def test_server_py_verify_token_public_when_secure_mode_disabled(self):
        """Test that server.py verify_token allows public access when secure mode is disabled."""
        from fluidmcp.cli.server import verify_token

        with patch.dict(os.environ, {"FMCP_SECURE_MODE": "false"}, clear=False):
            result = verify_token(credentials=None)
            assert result is None

    def test_server_py_verify_token_requires_token_when_secure_mode_enabled(self):
        """Test that server.py verify_token requires valid token when secure mode is enabled."""
        from fluidmcp.cli.server import verify_token
        from fastapi.security import HTTPAuthorizationCredentials
        from fastapi import HTTPException

        with patch.dict(os.environ, {"FMCP_SECURE_MODE": "true", "FMCP_BEARER_TOKEN": "test-token-456"}, clear=False):
            # Missing credentials should raise 401
            with pytest.raises(HTTPException) as exc_info:
                verify_token(credentials=None)
            assert exc_info.value.status_code == 401
            assert "WWW-Authenticate" in exc_info.value.headers

            # Valid token should succeed
            valid_creds = Mock(spec=HTTPAuthorizationCredentials)
            valid_creds.scheme = "Bearer"
            valid_creds.credentials = "test-token-456"
            result = verify_token(credentials=valid_creds)
            assert result is None

    def test_misconfigured_secure_mode_without_token(self):
        """Test that secure mode with missing bearer token raises 500 error."""
        from fluidmcp.cli.services.run_servers import verify_token
        from fastapi.security import HTTPAuthorizationCredentials
        from fastapi import HTTPException

        # Secure mode enabled but no bearer token configured
        with patch.dict(os.environ, {"FMCP_SECURE_MODE": "true", "FMCP_BEARER_TOKEN": ""}, clear=False):
            valid_creds = Mock(spec=HTTPAuthorizationCredentials)
            valid_creds.scheme = "Bearer"
            valid_creds.credentials = "any-token"

            # Should raise 500 for server misconfiguration
            with pytest.raises(HTTPException) as exc_info:
                verify_token(credentials=valid_creds)
            assert exc_info.value.status_code == 500
            assert "misconfiguration" in exc_info.value.detail.lower()
