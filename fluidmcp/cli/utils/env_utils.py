"""
Utility functions for environment variable handling.

Shared utilities used across database, API, and service layers.
"""


def is_placeholder(value: str) -> bool:
    """
    Detect if an environment variable value is a placeholder.

    Uses multiple heuristics to identify placeholder values while minimizing false positives.
    Real API keys/tokens are typically long, random, and lack obvious placeholder patterns.

    Common placeholder patterns detected:
    - Wrapped in angle brackets: <your-username>, <password>
    - Contains repeated 'x' characters (6+): xxxxxx-xxxx, XXXXXXXX
    - Contains 'placeholder' keyword
    - Generic instruction patterns: 'your-*', 'my-*', 'insert-*', 'enter-*'
    - Common placeholder values: 'changeme', 'replace_me', 'todo', 'none', 'null'
    - Too short for real credentials (< 8 chars) with placeholder keywords

    Args:
        value: The environment variable value to check

    Returns:
        True if the value appears to be a placeholder, False otherwise

    Examples:
        >>> is_placeholder("YOUR_API_KEY_HERE")
        True
        >>> is_placeholder("<your-token>")
        True
        >>> is_placeholder("xxxx-xxxx-xxxx")
        True
        >>> is_placeholder("my-api-key-abc123def456ghi789")
        False  # Too long and complex to be placeholder
        >>> is_placeholder("sk-1234567890abcdef")
        False  # Looks like real API key
    """
    if not isinstance(value, str):
        return False

    value_lower = value.lower()
    value_stripped = value.strip()

    # Empty or whitespace-only values
    if not value_stripped:
        return True

    # Wrapped in angle brackets: <value>, <your-key>
    if value_stripped.startswith('<') and value_stripped.endswith('>'):
        return True

    # Contains placeholder keyword
    if 'placeholder' in value_lower:
        return True

    # Repeated 'x' characters (6+ consecutive x's)
    if 'xxxxxx' in value_lower or 'XXXXXX' in value:
        return True

    # Common placeholder values (exact match)
    common_placeholders = [
        'changeme', 'change_me', 'change-me',
        'replace_me', 'replace-me', 'replaceme',
        'todo', 'tbd', 'fixme',
        'none', 'null',  # Special null-like values
        'example', 'sample', 'test',
        'your_key', 'your_token', 'your_password',
        'my_key', 'my_token', 'my_password',
    ]
    if value_lower in common_placeholders:
        return True

    # Generic instruction patterns (at start of value)
    # Only flag if relatively short (< 30 chars) to avoid false positives
    if len(value) < 30:
        instruction_prefixes = ['your-', 'your_', 'my-', 'my_', 'insert-', 'enter-', 'add-', 'set-']
        if any(value_lower.startswith(prefix) for prefix in instruction_prefixes):
            return True

    # All caps with underscores and "HERE" or "YOUR" (classic placeholder pattern)
    if value.isupper() and ('_HERE' in value or '_YOUR_' in value or value.startswith('YOUR_')):
        return True

    # If it's very short (< 8 chars) and contains common placeholder words
    if len(value) < 8:
        short_indicators = ['key', 'token', 'pass', 'secret', 'your', 'my']
        if any(indicator in value_lower for indicator in short_indicators):
            return True

    return False
