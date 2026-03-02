"""
OpenTelemetry span helpers for MCP operations.

Provides utilities to create explicit spans for MCP operations
beyond the automatic HTTP instrumentation.
"""
import re
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from contextlib import contextmanager
from typing import Optional, Dict, Any
from loguru import logger


_tracer = None

# Blocklist patterns for sensitive attribute keys (case-insensitive)
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(key|token|secret|password|passwd|auth|credential|bearer|cookie|session)",
    re.IGNORECASE,
)
_REDACTED = "***REDACTED***"


def _sanitize_attribute(key: str, value: Any) -> Any:
    """Redact values for attribute keys that match sensitive patterns."""
    if _SENSITIVE_KEY_PATTERN.search(key):
        return _REDACTED
    return value


def get_tracer():
    """
    Get or create OpenTelemetry tracer for FluidMCP.

    Returns:
        Tracer instance for FluidMCP service
    """
    global _tracer
    if _tracer is None:
        _tracer = trace.get_tracer("fluidmcp", "2.0.0")
    return _tracer


@contextmanager
def trace_mcp_operation(
    operation_name: str,
    server_id: str,
    attributes: Optional[Dict[str, Any]] = None
):
    """
    Context manager to trace MCP operations with explicit spans.

    Creates a span for the MCP operation and automatically records
    errors if they occur.

    Args:
        operation_name: Name of MCP operation (e.g., 'tools/list', 'tools/call')
        server_id: MCP server identifier
        attributes: Additional span attributes (optional)

    Yields:
        Span object for the operation

    Example:
        ```python
        with trace_mcp_operation("tools/list", "filesystem", {"user": "alice"}):
            result = await call_mcp_tools_list()
        ```

    Safety:
        - Gracefully handles OpenTelemetry not being initialized
        - Records exceptions as span events
        - Sets error status on span when exception occurs
        - Re-raises exceptions (doesn't swallow them)
    """
    tracer = None
    try:
        tracer = get_tracer()
    except Exception as tracer_error:
        logger.debug(f"Failed to get tracer for {operation_name}: {tracer_error}")

    if tracer is None:
        # OpenTelemetry not available — yield None so caller still works
        yield None
        return

    # Start span
    span_attributes = {
        "mcp.server_id": server_id,
        "mcp.operation": operation_name,
    }

    # Add custom attributes if provided (with sensitive data filtering)
    if attributes:
        for k, v in attributes.items():
            span_attributes[k] = _sanitize_attribute(k, v)

    with tracer.start_as_current_span(
        f"mcp.{operation_name}",
        attributes=span_attributes
    ) as span:
        try:
            yield span
        except Exception as e:
            # Record exception details in span
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            logger.debug(f"MCP operation {operation_name} failed: {e}")
            raise


def set_span_attribute(key: str, value: Any) -> None:
    """
    Set an attribute on the current active span.

    Useful for adding additional context during operation execution.

    Args:
        key: Attribute key
        value: Attribute value

    Example:
        ```python
        with trace_mcp_operation("tools/call", "filesystem"):
            set_span_attribute("tool.name", "read_file")
            set_span_attribute("tool.path", "/tmp/test.txt")
            result = await execute_tool()
        ```

    Safety:
        - Safely handles case where no active span exists
        - Logs debug message on failure
    """
    try:
        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute(key, _sanitize_attribute(key, value))
    except Exception as e:
        logger.debug(f"Failed to set span attribute {key}: {e}")


def record_mcp_error(error: Exception, message: Optional[str] = None) -> None:
    """
    Record an error event on the current active span.

    Args:
        error: Exception that occurred
        message: Optional custom error message

    Example:
        ```python
        try:
            result = await call_mcp_tool()
        except ValueError as e:
            record_mcp_error(e, "Invalid tool parameters")
            raise
        ```

    Safety:
        - Safely handles case where no active span exists
        - Logs debug message on failure
    """
    try:
        span = trace.get_current_span()
        if span and span.is_recording():
            span.record_exception(error)
            if message:
                span.add_event(message, {"error.message": str(error)})
    except Exception as e:
        logger.debug(f"Failed to record error in span: {e}")


def enrich_current_span(
    user_id: Optional[str] = None,
    server_id: Optional[str] = None,
    request_id: Optional[Any] = None,
    **kwargs
) -> None:
    """
    Enrich current active span with business context.

    Args:
        user_id: User identifier (from bearer token)
        server_id: MCP server identifier
        request_id: JSON-RPC request ID
        **kwargs: Additional custom attributes

    Example:
        enrich_current_span(
            user_id="user_abc123",
            server_id="filesystem",
            request_id=1
        )
    """
    try:
        span = trace.get_current_span()
        if span and span.is_recording():
            if user_id:
                span.set_attribute("user.id", user_id)
            if server_id:
                span.set_attribute("mcp.server_id", server_id)
            if request_id is not None:
                span.set_attribute("request.id", str(request_id))

            # Custom attributes (with sensitive data filtering)
            for key, value in kwargs.items():
                if value is not None:
                    span.set_attribute(key, _sanitize_attribute(key, str(value)))
    except Exception as e:
        logger.debug(f"Failed to enrich span: {e}")


def enrich_span_with_error(
    error: Exception,
    user_id: Optional[str] = None,
    server_id: Optional[str] = None,
    message: Optional[str] = None
) -> None:
    """
    Record error on span with business context.

    Args:
        error: Exception that occurred
        user_id: User identifier
        server_id: MCP server identifier
        message: Custom error message

    Example:
        try:
            result = await operation()
        except ValueError as e:
            enrich_span_with_error(e, user_id=user_id, server_id="filesystem")
            raise
    """
    try:
        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_status(Status(StatusCode.ERROR, str(error)))
            span.set_attribute("error", True)

            if user_id:
                span.set_attribute("user.id", user_id)
            if server_id:
                span.set_attribute("mcp.server_id", server_id)

            span.record_exception(error)

            if message:
                span.add_event("error", {
                    "message": message,
                    "error.type": type(error).__name__,
                    "error.message": str(error)
                })
    except Exception as e:
        logger.debug(f"Failed to record error: {e}")
