"""Request-scoped context storage (trace IDs, server ID) via contextvars."""
from contextvars import ContextVar
from typing import Optional

_trace_id: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
_span_id: ContextVar[Optional[str]] = ContextVar("span_id", default=None)
_server_id: ContextVar[Optional[str]] = ContextVar("server_id", default=None)


def get_trace_id() -> Optional[str]:
    return _trace_id.get()


def get_span_id() -> Optional[str]:
    return _span_id.get()


def get_server_id() -> Optional[str]:
    return _server_id.get()


def set_trace_id(value: Optional[str]) -> None:
    _trace_id.set(value)


def set_span_id(value: Optional[str]) -> None:
    _span_id.set(value)


def set_server_id(value: Optional[str]) -> None:
    _server_id.set(value)


def clear_context() -> None:
    _trace_id.set(None)
    _span_id.set(None)
    _server_id.set(None)
