"""Unit tests for package_installer.py

Test Organization:
    - Valid formats: Full and partial package specifications
    - Version variations: Semantic versioning, pre-release, build metadata
    - Special characters: Hyphens, underscores, numbers, dots, Unicode in names
    - Edge cases: Very long names (up to 500 chars), multiple special chars, whitespace
    - Invalid formats: Error cases that should raise ValueError
    - Real-world examples: Production package strings
    - Type validation: Return type, keys, values, defaults

Note on Test Coverage:
    Some tests may appear to overlap or be redundant (e.g., multiple slash handling
    tests, various length tests). This is intentional and serves several purposes:

    1. Clarity: Each test focuses on one specific aspect or edge case
    2. Robustness: Comprehensive coverage ensures regex handles all scenarios
    3. Documentation: Tests serve as examples of expected behavior
    4. Regression Prevention: Multiple similar tests catch subtle bugs

    While consolidation could reduce test count, the current approach prioritizes
    thorough coverage and explicit testing of edge cases over brevity.

Unicode Support:
    Tests include Unicode/non-ASCII characters (Chinese, Japanese, Cyrillic, Arabic,
    emoji) to verify the regex pattern handles international package names correctly.
    This is important for global package registries.

Whitespace Handling:
    The function does NOT strip whitespace. Production code should call .strip() on
    user inputs before passing to parse_package_string(). See test_recommended_whitespace_handling
    for the recommended usage pattern.
"""

import pytest
from fluidai_mcp.services.package_installer import parse_package_string


class TestParsePackageString:
    """Unit tests for parse_package_string function"""

    # Valid package strings - Full specifications
    def test_full_specification_with_version(self):
        """Test parsing full package specification: author/name@version"""
        result = parse_package_string("fluidai/filesystem@1.0.0")

        assert result["author"] == "fluidai"
        assert result["package_name"] == "filesystem"
        assert result["version"] == "1.0.0"

    def test_full_specification_with_latest(self):
        """Test parsing full package specification with 'latest' version"""
        result = parse_package_string("fluidai/filesystem@latest")

        assert result["author"] == "fluidai"
        assert result["package_name"] == "filesystem"
        assert result["version"] == "latest"

    # Valid package strings - Partial specifications with defaults
    def test_author_and_name_defaults_to_latest(self):
        """Test parsing author/name without version defaults to 'latest'"""
        result = parse_package_string("fluidai/filesystem")

        assert result["author"] == "fluidai"
        assert result["package_name"] == "filesystem"
        assert result["version"] == "latest"

    def test_name_with_version_defaults_author(self):
        """Test parsing name@version without author defaults to 'default'"""
        result = parse_package_string("filesystem@1.0.0")

        assert result["author"] == "default"
        assert result["package_name"] == "filesystem"
        assert result["version"] == "1.0.0"

    def test_name_only_defaults_both(self):
        """Test parsing name only defaults author to 'default' and version to 'latest'"""
        result = parse_package_string("filesystem")

        assert result["author"] == "default"
        assert result["package_name"] == "filesystem"
        assert result["version"] == "latest"

    # Version format variations
    def test_semantic_version_major_minor_patch(self):
        """Test parsing with semantic versioning (major.minor.patch)"""
        result = parse_package_string("author/package@2.1.3")

        assert result["version"] == "2.1.3"

    def test_version_with_prerelease(self):
        """Test parsing version with pre-release identifier"""
        result = parse_package_string("author/package@1.0.0-alpha.1")

        assert result["version"] == "1.0.0-alpha.1"

    def test_version_with_build_metadata(self):
        """Test parsing version with build metadata"""
        result = parse_package_string("author/package@1.0.0+20130313144700")

        assert result["version"] == "1.0.0+20130313144700"

    def test_version_with_complex_semver(self):
        """Test parsing version with complex semver format"""
        result = parse_package_string("author/package@1.0.0-beta.2+exp.sha.5114f85")

        assert result["version"] == "1.0.0-beta.2+exp.sha.5114f85"

    def test_version_with_v_prefix(self):
        """Test parsing version with 'v' prefix (common in git tags)"""
        result = parse_package_string("author/package@v1.0.0")

        assert result["version"] == "v1.0.0"

    def test_version_with_single_number(self):
        """Test parsing version with single number"""
        result = parse_package_string("author/package@1")

        assert result["version"] == "1"

    def test_version_with_unicode(self):
        """Test parsing version with Unicode characters (rare but possible)"""
        result = parse_package_string("author/package@版本-1.0.0")

        assert result["version"] == "版本-1.0.0"

    # Special characters in names
    def test_package_name_with_hyphen(self):
        """Test parsing package name containing hyphens"""
        result = parse_package_string("author/my-package@1.0.0")

        assert result["package_name"] == "my-package"

    def test_package_name_with_underscore(self):
        """Test parsing package name containing underscores"""
        result = parse_package_string("author/my_package@1.0.0")

        assert result["package_name"] == "my_package"

    def test_package_name_with_numbers(self):
        """Test parsing package name containing numbers"""
        result = parse_package_string("author/package123@1.0.0")

        assert result["package_name"] == "package123"

    def test_package_name_with_dots(self):
        """Test parsing package name containing dots"""
        result = parse_package_string("author/my.package.name@1.0.0")

        assert result["package_name"] == "my.package.name"

    def test_author_with_hyphen(self):
        """Test parsing author name containing hyphens"""
        result = parse_package_string("my-org/package@1.0.0")

        assert result["author"] == "my-org"

    def test_author_with_underscore(self):
        """Test parsing author name containing underscores"""
        result = parse_package_string("my_org/package@1.0.0")

        assert result["author"] == "my_org"

    def test_numeric_author_name(self):
        """Test parsing with numeric author name"""
        result = parse_package_string("123/package@1.0.0")

        assert result["author"] == "123"

    def test_numeric_package_name(self):
        """Test parsing with numeric package name"""
        result = parse_package_string("author/456@1.0.0")

        assert result["package_name"] == "456"

    def test_unicode_author_name(self):
        """Test parsing with Unicode/non-ASCII characters in author name"""
        result = parse_package_string("组织/package@1.0.0")

        assert result["author"] == "组织"
        assert result["package_name"] == "package"
        assert result["version"] == "1.0.0"

    def test_unicode_package_name(self):
        """Test parsing with Unicode/non-ASCII characters in package name"""
        result = parse_package_string("author/パッケージ@1.0.0")

        assert result["author"] == "author"
        assert result["package_name"] == "パッケージ"
        assert result["version"] == "1.0.0"

    def test_unicode_mixed_characters(self):
        """Test parsing with mixed Unicode characters (Cyrillic, Arabic, CJK)"""
        result = parse_package_string("компания/пакет-عربي-中文@1.0.0")

        assert result["author"] == "компания"
        assert result["package_name"] == "пакет-عربي-中文"
        assert result["version"] == "1.0.0"

    def test_emoji_in_names(self):
        """Test parsing with emoji characters in names"""
        result = parse_package_string("org🚀/package-😀@1.0.0")

        assert result["author"] == "org🚀"
        assert result["package_name"] == "package-😀"
        assert result["version"] == "1.0.0"

    # Edge cases - Very long names
    def test_very_long_author_name(self):
        """Test parsing with very long author name (100 characters)"""
        long_author = "a" * 100
        result = parse_package_string(f"{long_author}/package@1.0.0")

        assert result["author"] == long_author
        assert len(result["author"]) == 100

    def test_very_long_package_name(self):
        """Test parsing with very long package name (100 characters)"""
        long_package = "p" * 100
        result = parse_package_string(f"author/{long_package}@1.0.0")

        assert result["package_name"] == long_package
        assert len(result["package_name"]) == 100

    def test_very_long_version(self):
        """Test parsing with very long version string (50 characters)"""
        long_version = "1.0.0-" + "x" * 44  # 50 chars total
        result = parse_package_string(f"author/package@{long_version}")

        assert result["version"] == long_version
        assert len(result["version"]) == 50

    def test_extremely_long_version(self):
        """Test parsing with extremely long version string (200 characters)"""
        long_version = "1.0.0-beta." + "x" * 189  # 200 chars total
        result = parse_package_string(f"author/package@{long_version}")

        assert result["version"] == long_version
        assert len(result["version"]) == 200

    def test_absolute_limit_author_name(self):
        """Test parsing with absolute limit author name (500 characters)"""
        long_author = "org-" + "a" * 496  # 500 chars total
        result = parse_package_string(f"{long_author}/package@1.0.0")

        assert result["author"] == long_author
        assert len(result["author"]) == 500

    def test_absolute_limit_package_name(self):
        """Test parsing with absolute limit package name (500 characters)"""
        long_package = "pkg-" + "p" * 496  # 500 chars total
        result = parse_package_string(f"author/{long_package}@1.0.0")

        assert result["package_name"] == long_package
        assert len(result["package_name"]) == 500

    def test_absolute_limit_version(self):
        """Test parsing with absolute limit version string (500 characters)"""
        long_version = "1.0.0-release." + "x" * 486  # 500 chars total (14 + 486)
        result = parse_package_string(f"author/package@{long_version}")

        assert result["version"] == long_version
        assert len(result["version"]) == 500

    # Edge cases - Multiple special characters
    def test_multiple_at_symbols_uses_first(self):
        """Test parsing with multiple @ symbols (everything after first @ is version)"""
        result = parse_package_string("author/package@1.0.0@extra")

        assert result["version"] == "1.0.0@extra"

    def test_multiple_slashes_treats_as_package_name(self):
        """Test parsing with multiple / symbols (everything after first / is package name).

        This complements test_only_slash_parses_with_defaults by showing how multiple
        slashes are handled when there's actual content.
        """
        result = parse_package_string("author/sub/package@1.0.0")

        assert result["author"] == "author"
        assert result["package_name"] == "sub/package"
        assert result["version"] == "1.0.0"

    def test_trailing_at_symbol(self):
        """Test parsing with trailing @ symbol (version defaults to 'latest')"""
        result = parse_package_string("author/package@")

        assert result["author"] == "author"
        assert result["package_name"] == "package"
        assert result["version"] == "latest"  # Empty string defaults to 'latest'

    def test_leading_at_symbol_raises_error(self):
        """Test parsing with leading @ symbol raises ValueError (empty package name)"""
        with pytest.raises(ValueError, match="Invalid package format"):
            parse_package_string("@1.0.0")

    def test_whitespace_in_package_string(self):
        """Test parsing with whitespace (treated as part of names).

        Note: The function does NOT strip whitespace. In production, callers should
        .strip() inputs before passing to parse_package_string() to avoid this behavior.
        """
        result = parse_package_string("author /package @1.0.0")

        assert result["author"] == "author "
        assert result["package_name"] == "package "
        assert result["version"] == "1.0.0"

    def test_recommended_whitespace_handling(self):
        """Test recommended usage pattern: strip whitespace before parsing.

        This demonstrates the production best practice of calling .strip() on user
        input before passing to parse_package_string().
        """
        user_input = "  fluidai/filesystem@1.0.0  "  # User input with surrounding whitespace
        result = parse_package_string(user_input.strip())  # Recommended pattern

        assert result["author"] == "fluidai"
        assert result["package_name"] == "filesystem"
        assert result["version"] == "1.0.0"

    # Invalid formats that should raise ValueError
    def test_empty_string_raises_error(self):
        """Test that empty string raises ValueError"""
        with pytest.raises(ValueError, match="Invalid package format"):
            parse_package_string("")

    def test_only_at_symbol_raises_error(self):
        """Test that only @ symbol raises ValueError"""
        with pytest.raises(ValueError, match="Invalid package format"):
            parse_package_string("@")

    def test_only_slash_parses_with_defaults(self):
        """Test that only / symbol parses with default author and slash as package name"""
        result = parse_package_string("/")

        assert result["author"] == "default"  # Empty author defaults to 'default'
        assert result["package_name"] == "/"  # Single slash becomes the package name
        assert result["version"] == "latest"  # Default version

    def test_leading_slash_without_author(self):
        """Test parsing /package@version with leading slash (empty author defaults to 'default').

        The leading slash becomes part of the package name since there's no content before it.
        """
        result = parse_package_string("/package@1.0.0")

        assert result["author"] == "default"  # Empty string before / defaults to 'default'
        assert result["package_name"] == "/package"  # Leading slash included in package name
        assert result["version"] == "1.0.0"

    # Real-world examples
    def test_real_world_modelcontextprotocol(self):
        """Test real-world example: modelcontextprotocol/filesystem@latest"""
        result = parse_package_string("modelcontextprotocol/filesystem@latest")

        assert result["author"] == "modelcontextprotocol"
        assert result["package_name"] == "filesystem"
        assert result["version"] == "latest"

    def test_real_world_anthropic_claude_code(self):
        """Test real-world example: anthropic/claude-code@2.0.0"""
        result = parse_package_string("anthropic/claude-code@2.0.0")

        assert result["author"] == "anthropic"
        assert result["package_name"] == "claude-code"
        assert result["version"] == "2.0.0"

    def test_real_world_simple_package(self):
        """Test real-world example: package without author or version"""
        result = parse_package_string("myserver")

        assert result["author"] == "default"
        assert result["package_name"] == "myserver"
        assert result["version"] == "latest"

    def test_real_world_fluidai_filesystem(self):
        """Test real-world example from docstring: fluidai/filesystem@1.0.0"""
        result = parse_package_string("fluidai/filesystem@1.0.0")

        assert result["author"] == "fluidai"
        assert result["package_name"] == "filesystem"
        assert result["version"] == "1.0.0"

    # Case sensitivity
    def test_case_sensitivity(self):
        """Test that parsing is case-sensitive"""
        result = parse_package_string("MyAuthor/MyPackage@MyVersion")

        assert result["author"] == "MyAuthor"
        assert result["package_name"] == "MyPackage"
        assert result["version"] == "MyVersion"

    # Return type validation
    def test_returns_dict(self):
        """Test that function returns a dictionary"""
        result = parse_package_string("author/package@1.0.0")

        assert isinstance(result, dict)

    def test_dict_has_all_required_keys(self):
        """Test that returned dict has all required keys"""
        result = parse_package_string("author/package@1.0.0")

        assert "author" in result
        assert "package_name" in result
        assert "version" in result
        assert len(result) == 3  # No extra keys

    def test_all_values_are_strings(self):
        """Test that all returned values are strings"""
        result = parse_package_string("author/package@1.0.0")

        assert isinstance(result["author"], str)
        assert isinstance(result["package_name"], str)
        assert isinstance(result["version"], str)

    # Default value validation
    def test_default_author_is_default(self):
        """Test that missing author defaults to 'default'"""
        result = parse_package_string("package@1.0.0")

        assert result["author"] == "default"

    def test_default_version_is_latest(self):
        """Test that missing version defaults to 'latest'"""
        result = parse_package_string("author/package")

        assert result["version"] == "latest"

    def test_both_defaults_applied(self):
        """Test that both defaults are applied when only package name provided"""
        result = parse_package_string("package")

        assert result["author"] == "default"
        assert result["version"] == "latest"
