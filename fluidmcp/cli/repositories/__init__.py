"""
Data access layer for FluidMCP.

This package contains repository classes for database operations.
"""
from .base import PersistenceBackend
from .database import DatabaseManager
from .memory import InMemoryBackend

__all__ = ["PersistenceBackend", "DatabaseManager", "InMemoryBackend"]
