"""Request-scoped context storage using contextvars."""
from contextvars import ContextVar
from typing import Optional

# Trace context (from OTEL spans)
_trace_id: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
_span_id: ContextVar[Optional[str]] = ContextVar("span_id", default=None)

# Business context (from request handlers)
_user_id: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
_server_id: ContextVar[Optional[str]] = ContextVar("server_id", default=None)


# Getters
def get_trace_id() -> Optional[str]:
    """Get current trace ID from context."""
    return _trace_id.get()


def get_span_id() -> Optional[str]:
    """Get current span ID from context."""
    return _span_id.get()


def get_user_id() -> Optional[str]:
    """Get current user ID from context."""
    return _user_id.get()


def get_server_id() -> Optional[str]:
    """Get current server ID from context."""
    return _server_id.get()


# Setters
def set_trace_id(trace_id: Optional[str]) -> None:
    """Set trace ID in context."""
    _trace_id.set(trace_id)


def set_span_id(span_id: Optional[str]) -> None:
    """Set span ID in context."""
    _span_id.set(span_id)


def set_user_id(user_id: Optional[str]) -> None:
    """Set user ID in context."""
    _user_id.set(user_id)


def set_server_id(server_id: Optional[str]) -> None:
    """Set server ID in context."""
    _server_id.set(server_id)


# Cleanup
def clear_context() -> None:
    """Clear all context variables."""
    _trace_id.set(None)
    _span_id.set(None)
    _user_id.set(None)
    _server_id.set(None)
