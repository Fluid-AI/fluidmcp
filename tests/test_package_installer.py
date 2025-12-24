"""Unit tests for package_installer.py"""

import pytest
from fluidai_mcp.services.package_installer import parse_package_string


class TestParsePackageString:
    """Unit tests for parse_package_string function"""

    # Valid package strings
    def test_parses_author_package_with_version(self):
        """Test Author/Package@1.0.0 format"""
        result = parse_package_string("Author/Package@1.0.0")
        assert result["author"] == "Author"
        assert result["package_name"] == "Package"
        assert result["version"] == "1.0.0"

    def test_parses_author_package_with_latest(self):
        """Test Author/Package@latest format"""
        result = parse_package_string("Author/Package@latest")
        assert result["author"] == "Author"
        assert result["package_name"] == "Package"
        assert result["version"] == "latest"

    def test_parses_lowercase_author_package(self):
        """Test lowercase author/package@1.0.0"""
        result = parse_package_string("author/package@1.0.0")
        assert result["author"] == "author"
        assert result["package_name"] == "package"
        assert result["version"] == "1.0.0"

    def test_parses_author_package_without_version_defaults_to_latest(self):
        """Test Author/Package defaults to latest"""
        result = parse_package_string("Author/Package")
        assert result["author"] == "Author"
        assert result["package_name"] == "Package"
        assert result["version"] == "latest"
        
    # Invalid formats using parametrize
    @pytest.mark.parametrize("invalid_str", [
        pytest.param("", id="empty_string"),
        pytest.param("/", id="only_slash"),
        pytest.param("@", id="only_at_sign"),
        pytest.param("Author/Package@", id="missing_version_after_at"),
        pytest.param("/Package@1.0.0", id="missing_author"),
        pytest.param("Author/@1.0.0", id="missing_package_name"),
        pytest.param("Author!/Package@1.0.0", id="invalid_characters")
    ])
    def test_invalid_formats_raise_value_error(self, invalid_str):
        """Test that invalid package formats raise ValueError"""
        with pytest.raises(ValueError, match="Invalid package format"):
            parse_package_string(invalid_str)

    # Edge cases
    def test_handles_hyphens_in_names(self):
        """Test hyphens in author and package names"""
        result = parse_package_string("my-author/my-package@1.0.0")
        assert result["author"] == "my-author"
        assert result["package_name"] == "my-package"

    def test_handles_underscores_in_names(self):
        """Test underscores in names"""
        result = parse_package_string("my_author/my_package@1.0.0")
        assert result["author"] == "my_author"
        assert result["package_name"] == "my_package"

    def test_handles_dots_in_package_name(self):
        """Test dots in package name"""
        result = parse_package_string("author/package.name@1.0.0")
        assert result["package_name"] == "package.name"

    def test_handles_numbers_in_names(self):
        """Test numbers in author and package names"""
        result = parse_package_string("author123/package456@1.0.0")
        assert result["author"] == "author123"
        assert result["package_name"] == "package456"

    def test_handles_complex_semantic_version(self):
        """Test complex semver string"""
        result = parse_package_string("author/pkg@1.2.3-beta.4+build.567")
        assert result["version"] == "1.2.3-beta.4+build.567"

    def test_handles_very_long_author_name(self):
        """Test 100-character author name"""
        long_author = "a" * 100
        result = parse_package_string(f"{long_author}/package@1.0.0")
        assert result["author"] == long_author

    def test_handles_very_long_package_name(self):
        """Test 100-character package name"""
        long_package = "p" * 100
        result = parse_package_string(f"author/{long_package}@1.0.0")
        assert result["package_name"] == long_package

    def test_handles_very_long_version_string(self):
        """Test 100-character version string"""
        long_version = "1" * 100
        result = parse_package_string(f"author/package@{long_version}")
        assert result["version"] == long_version