"""
Minimal unit tests for environment utilities.

Tests placeholder detection from PR #281 review feedback.
"""

import pytest
from fluidmcp.cli.utils.env_utils import is_placeholder


class TestPlaceholderDetection:
    """Test is_placeholder() function."""

    def test_obvious_placeholders_detected(self):
        """Test that obvious placeholders are detected."""
        assert is_placeholder("your_api_key_here")
        assert is_placeholder("YOUR_SECRET_TOKEN")
        assert is_placeholder("<your-key-here>")
        assert is_placeholder("xxxxxxxxxxxx")
        assert is_placeholder("XXXXXXXX")

    def test_valid_api_keys_not_flagged(self):
        """Test that valid API keys are NOT flagged as placeholders."""
        # API key patterns (fake examples for testing)
        assert not is_placeholder("sk-1234567890abcdef")  # OpenAI style
        assert not is_placeholder("AIzaSyDf8g7h9j0k1l2m3n4o5p6q7r8s9t0u1v2")  # Google style
        assert not is_placeholder("ghp_1234567890abcdefghijklmnopqrstuv")  # GitHub style
        assert not is_placeholder("fake-token-1234567890-9876543210-example")  # Generic token

    def test_mixed_case_placeholders(self):
        """Test mixed case placeholder detection."""
        assert is_placeholder("Your_Api_Key")
        assert is_placeholder("YOUR_SECRET")

    def test_empty_and_short_strings(self):
        """Test edge cases - empty and short strings."""
        assert is_placeholder("")  # Empty is placeholder
        assert not is_placeholder("a")  # Single char not placeholder
        assert not is_placeholder("ab")  # Two chars not placeholder

    def test_repeated_characters(self):
        """Test repeated character detection (6+ consecutive x's)."""
        assert is_placeholder("xxxxxxxxxx")  # 10 x's
        assert is_placeholder("XXXXXXXXXX")  # 10 X's
        assert is_placeholder("xxxxxx")  # 6 x's (at threshold)
        assert not is_placeholder("xxxxx")  # Only 5 x's (below threshold)

    def test_angle_bracket_patterns(self):
        """Test angle bracket placeholder patterns."""
        assert is_placeholder("<api_key>")
        assert is_placeholder("<YOUR_TOKEN>")
        assert is_placeholder("<insert-key-here>")

    def test_special_values(self):
        """Test special placeholder values."""
        assert is_placeholder("none")
        assert is_placeholder("null")
        assert is_placeholder("TODO")
        assert is_placeholder("TBD")
        assert is_placeholder("CHANGEME")
