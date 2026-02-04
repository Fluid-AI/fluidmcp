"""
Error handling utilities for FluidMCP.

Provides functions for sanitizing and truncating error messages
to prevent information leakage and client issues.
"""


def truncate_error_message(msg: str, max_len: int = 1000) -> str:
    """
    Truncate error messages to prevent information leakage and client issues.

    Args:
        msg: Error message to truncate
        max_len: Maximum length (default: 1000 characters)

    Returns:
        Truncated message with indicator if truncated
    """
    if len(msg) <= max_len:
        return msg
    return msg[:max_len] + "... [truncated]"
