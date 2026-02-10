"""
Pytest configuration and fixtures for FluidMCP test suite.
"""

import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end integration test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test requiring external services"
    )
