"""Unit tests for github_utils.py"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from fluidai_mcp.services.github_utils import (
    extract_json_from_readme,
    normalize_github_repo,
    validate_mcp_metadata,
)


class TestExtractJsonFromReadme:
    """Unit tests for extract_json_from_readme function"""

    def test_extracts_json_with_mcpservers_key(self):
        """Test extraction of JSON block containing mcpServers key"""
        readme_content = """
# MCP Server

This is a test server.

## Configuration

```json
{
  "mcpServers": {
    "test-server": {
      "command": "uv",
      "args": ["run", "server.py"],
      "env": {}
    }
  }
}
```

## Usage

Run the server...
"""
        result = extract_json_from_readme(readme_content)

        assert result is not None, "Should extract JSON from README"
        assert "mcpServers" in result, "Should contain mcpServers key"
        assert "test-server" in result["mcpServers"], "Should contain server config"
        assert result["mcpServers"]["test-server"]["command"] == "uv"
        assert result["mcpServers"]["test-server"]["args"] == ["run", "server.py"]

    def test_prioritizes_mcpservers_over_generic_json(self):
        """Test that blocks with mcpServers are prioritized over generic JSON"""
        readme_content = """
# Server

First block:
```json
{
  "generic": "config",
  "not": "relevant"
}
```

Second block with mcpServers:
```json
{
  "mcpServers": {
    "main": {
      "command": "python",
      "args": ["-m", "server"]
    }
  }
}
```
"""
        result = extract_json_from_readme(readme_content)

        assert result is not None
        assert "mcpServers" in result, "Should extract the mcpServers block"
        assert "generic" not in result, "Should not extract generic JSON"

    def test_raises_error_for_no_json_blocks(self):
        """Test that ValueError is raised when no JSON blocks are found"""
        readme_content = """
# Server

This is plain text with no JSON blocks.
"""
        with pytest.raises(ValueError, match="No valid JSON configuration found"):
            extract_json_from_readme(readme_content)

    def test_raises_error_for_invalid_json(self):
        """Test that ValueError is raised when JSON is malformed"""
        readme_content = """
```json
{
  "invalid": "json"
  missing comma
}
```
"""
        with pytest.raises(ValueError, match="No valid JSON configuration found"):
            extract_json_from_readme(readme_content)

    def test_handles_code_block_without_json_marker(self):
        """Test extraction from code blocks without explicit 'json' marker"""
        readme_content = """
Configuration:
```
{
  "mcpServers": {
    "server": {
      "command": "node",
      "args": ["index.js"]
    }
  }
}
```
"""
        result = extract_json_from_readme(readme_content)

        assert result is not None
        assert "mcpServers" in result

    def test_handles_multiple_mcpservers_blocks(self):
        """Test that the first mcpServers block is used when multiple exist"""
        readme_content = """
First config:
```json
{
  "mcpServers": {
    "first": {
      "command": "echo",
      "args": ["first"]
    }
  }
}
```

Second config:
```json
{
  "mcpServers": {
    "second": {
      "command": "echo",
      "args": ["second"]
    }
  }
}
```
"""
        result = extract_json_from_readme(readme_content)

        assert result is not None
        assert "first" in result["mcpServers"]
        # Should prioritize first mcpServers block
        assert "second" not in result["mcpServers"]


class TestNormalizeGithubRepo:
    """Unit tests for normalize_github_repo function"""

    def test_normalizes_full_url(self):
        """Test normalization of full GitHub URL"""
        url = "https://github.com/owner/repo"
        owner, repo = normalize_github_repo(url)
        assert owner == "owner"
        assert repo == "repo"

    def test_normalizes_https_url_with_git_extension(self):
        """Test normalization of HTTPS URL with .git extension"""
        url = "https://github.com/owner/repo.git"
        owner, repo = normalize_github_repo(url)
        assert owner == "owner"
        assert repo == "repo"

    def test_raises_error_for_invalid_format(self):
        """Test that invalid formats raise ValueError"""
        url = "git://github.com/owner/repo.git"
        with pytest.raises(ValueError, match="must be in the form 'owner/repo'"):
            normalize_github_repo(url)

    def test_keeps_simple_path_unchanged(self):
        """Test that simple owner/repo format is parsed correctly"""
        path = "owner/repo"
        owner, repo = normalize_github_repo(path)
        assert owner == "owner"
        assert repo == "repo"

    def test_raises_error_for_trailing_slash(self):
        """Test that trailing slashes cause an error (path is malformed)"""
        url = "https://github.com/owner/repo/"
        with pytest.raises(ValueError, match="must be in the form 'owner/repo'"):
            normalize_github_repo(url)


class TestValidateMcpMetadata:
    """Unit tests for validate_mcp_metadata function"""

    def test_validates_correct_metadata(self):
        """Test that valid metadata passes validation"""
        metadata = {
            "mcpServers": {
                "server": {
                    "command": "python",
                    "args": ["-m", "server"],
                    "env": {}
                }
            }
        }
        # Should not raise an exception
        assert validate_mcp_metadata(metadata) is True

    def test_raises_error_for_missing_mcpservers_key(self):
        """Test that metadata without mcpServers raises ValueError"""
        metadata = {
            "invalid": "structure"
        }
        with pytest.raises(ValueError, match="must contain 'mcpServers' key"):
            validate_mcp_metadata(metadata)

    def test_raises_error_for_empty_mcpservers(self):
        """Test that empty mcpServers dict raises ValueError"""
        metadata = {
            "mcpServers": {}
        }
        with pytest.raises(ValueError, match="must be a non-empty dictionary"):
            validate_mcp_metadata(metadata)

    def test_raises_error_for_server_without_command(self):
        """Test that server config without command raises ValueError"""
        metadata = {
            "mcpServers": {
                "server": {
                    "args": ["test"],
                    "env": {}
                }
            }
        }
        with pytest.raises(ValueError, match="must have 'command' field"):
            validate_mcp_metadata(metadata)

    def test_raises_error_for_server_without_args(self):
        """Test that server config without args raises ValueError"""
        metadata = {
            "mcpServers": {
                "server": {
                    "command": "python",
                    "env": {}
                }
            }
        }
        with pytest.raises(ValueError, match="must have 'args' field"):
            validate_mcp_metadata(metadata)

    def test_accepts_server_without_env(self):
        """Test that server config without env key is accepted (env is optional)"""
        metadata = {
            "mcpServers": {
                "server": {
                    "command": "python",
                    "args": ["-m", "server"]
                }
            }
        }
        # env is optional, so this should be valid
        assert validate_mcp_metadata(metadata) is True

    def test_accepts_multiple_servers(self):
        """Test that metadata with multiple servers is validated"""
        metadata = {
            "mcpServers": {
                "server1": {
                    "command": "python",
                    "args": ["server1.py"]
                },
                "server2": {
                    "command": "node",
                    "args": ["server2.js"]
                }
            }
        }
        assert validate_mcp_metadata(metadata) is True
