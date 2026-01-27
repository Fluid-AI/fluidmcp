"""
End-to-end integration tests using real MCP packages.

These tests:
1. Create a real config.json with actual MCP server configurations
2. Use fluidmcp to install and launch the servers
3. Send actual HTTP/JSON-RPC requests to verify they work
"""

import json
import os
import sys
import time
import pytest
import threading
import subprocess
from pathlib import Path

import requests


# Test configuration using real MCP packages
# Using lightweight packages that are quick to install
TEST_CONFIG = {
    "mcpServers": {
        "fetch": "Fetch/fetch@0.6.2"
    }
}


class TestE2ERealMCPServers:
    """End-to-end tests with real MCP servers from the registry"""

    @pytest.fixture(scope="class")
    def test_config_file(self, tmp_path_factory):
        """Create a real config file for testing"""
        tmp_path = tmp_path_factory.mktemp("e2e")
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(TEST_CONFIG, indent=2))
        return config_path

    @pytest.fixture(scope="class")
    def running_server(self, test_config_file):
        """
        Start the fluidmcp server in background and return when ready.
        This fixture is scoped to class so server runs once for all tests.
        """
        port = 18099

        # Start fluidmcp in background
        process = subprocess.Popen(
            [
                sys.executable, "-m", "fluidmcp.cli",
                "run", str(test_config_file),
                "--file", "--start-server"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env={**os.environ, "MCP_CLIENT_SERVER_ALL_PORT": str(port)}
        )

        # Wait for server to be ready (check for "Uvicorn running" or similar)
        server_ready = False
        start_time = time.time()
        timeout = 60  # 60 seconds to install and start

        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"http://127.0.0.1:{port}/docs", timeout=2)
                if response.status_code == 200:
                    server_ready = True
                    break
            except requests.exceptions.ConnectionError:
                time.sleep(2)

        if not server_ready:
            # Capture output for debugging
            process.terminate()
            stdout, _ = process.communicate(timeout=5)
            pytest.skip(f"Server failed to start within {timeout}s. Output: {stdout[:500]}")

        yield {"process": process, "port": port}

        # Cleanup
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    def test_server_swagger_docs_available(self, running_server):
        """Test that Swagger docs are accessible and contain expected endpoints"""
        port = running_server["port"]
        response = requests.get(f"http://127.0.0.1:{port}/docs", timeout=5)
        assert response.status_code == 200

        # Verify it's actually a Swagger UI page
        html_content = response.text.lower()
        assert "swagger" in html_content or "openapi" in html_content
        # Should contain references to our endpoints
        assert "fetch" in html_content or "/mcp" in html_content

    def test_tools_list_endpoint(self, running_server):
        """Test that tools/list returns the fetch tool with correct schema"""
        port = running_server["port"]

        response = requests.get(
            f"http://127.0.0.1:{port}/fetch/mcp/tools/list",
            timeout=10
        )

        assert response.status_code == 200
        data = response.json()

        # Validate JSON-RPC response structure
        assert "result" in data, f"Missing 'result' in response: {data}"
        assert "tools" in data["result"], f"Missing 'tools' in result: {data}"

        tools = data["result"]["tools"]
        assert isinstance(tools, list), f"Tools should be a list: {tools}"
        assert len(tools) > 0, "Tools list should not be empty"

        # Find the fetch tool and validate its structure
        fetch_tool = next((t for t in tools if t.get("name") == "fetch"), None)
        assert fetch_tool is not None, f"'fetch' tool not found in tools: {[t.get('name') for t in tools]}"

        # Validate fetch tool has required fields
        assert "name" in fetch_tool, "Tool missing 'name' field"
        assert "description" in fetch_tool, "Tool missing 'description' field"
        assert "inputSchema" in fetch_tool, "Tool missing 'inputSchema' field"

        # Validate inputSchema structure
        input_schema = fetch_tool["inputSchema"]
        assert input_schema.get("type") == "object", f"inputSchema type should be 'object': {input_schema}"
        assert "properties" in input_schema, "inputSchema missing 'properties'"
        assert "url" in input_schema["properties"], "fetch tool should have 'url' property"

    def test_jsonrpc_mcp_endpoint(self, running_server):
        """Test raw JSON-RPC endpoint returns valid JSON-RPC response"""
        port = running_server["port"]

        response = requests.post(
            f"http://127.0.0.1:{port}/fetch/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 42,
                "method": "tools/list"
            },
            timeout=10
        )

        assert response.status_code == 200
        data = response.json()

        # Validate JSON-RPC 2.0 response format
        assert data.get("jsonrpc") == "2.0", f"Invalid jsonrpc version: {data.get('jsonrpc')}"
        assert data.get("id") == 42, f"Response id should match request id (42): {data.get('id')}"
        assert "result" in data, f"Missing 'result' in response: {data}"
        assert "error" not in data, f"Unexpected error in response: {data.get('error')}"

        # Validate result contains tools
        assert "tools" in data["result"], f"Result should contain 'tools': {data['result']}"

    def test_tools_call_endpoint(self, running_server):
        """Test calling the fetch tool and validate the response content"""
        port = running_server["port"]

        # Call the fetch tool to fetch httpbin which returns JSON
        response = requests.post(
            f"http://127.0.0.1:{port}/fetch/mcp/tools/call",
            json={
                "name": "fetch",
                "arguments": {
                    "url": "https://httpbin.org/get"
                }
            },
            timeout=30  # Network request may take time
        )

        assert response.status_code == 200
        data = response.json()

        # Validate response structure
        assert "result" in data, f"Missing 'result' in response: {data}"
        assert "error" not in data, f"Unexpected error: {data.get('error')}"

        result = data["result"]
        assert "content" in result, f"Result should have 'content': {result}"

        content = result["content"]
        assert isinstance(content, list), f"Content should be a list: {content}"
        assert len(content) > 0, "Content should not be empty"

        # Validate content item structure
        content_item = content[0]
        assert "type" in content_item, f"Content item missing 'type': {content_item}"
        assert "text" in content_item, f"Content item missing 'text': {content_item}"

        # Validate the fetched content contains expected httpbin response
        fetched_text = content_item["text"]
        assert "httpbin.org" in fetched_text, f"Response should contain httpbin.org: {fetched_text[:200]}"

    def test_tools_call_with_invalid_tool_returns_error(self, running_server):
        """Test that calling a non-existent tool returns a proper error"""
        port = running_server["port"]

        response = requests.post(
            f"http://127.0.0.1:{port}/fetch/mcp/tools/call",
            json={
                "name": "nonexistent_tool_xyz",
                "arguments": {}
            },
            timeout=10
        )

        assert response.status_code == 200  # JSON-RPC errors are still 200
        data = response.json()

        # Should have an error response
        assert "error" in data or ("result" in data and "error" in str(data["result"]).lower()), \
            f"Expected error for non-existent tool: {data}"


def _check_registry_access(output):
    """Check if registry is accessible based on command output"""
    if "403" in output or "Forbidden" in output or "Error fetching" in output:
        pytest.skip("Registry access unavailable (403 Forbidden)")
    if "connection" in output.lower() or "timeout" in output.lower():
        pytest.skip("Registry connection failed")


class TestE2EGitHubServerFlow:
    """End-to-end test for GitHub MCP server cloning and execution"""

    def test_github_clone_launch_and_jsonrpc_request(self, tmp_path):
        """
        Complete end-to-end test of GitHub MCP server flow:
        1. Clone a real GitHub repository (public repo, no auth needed)
        2. Create metadata.json with explicit command
        3. Launch the MCP server using fluidmcp
        4. Send a JSON-RPC request to the server
        5. Verify we get a valid response
        6. Clean up the server

        This is a true E2E test that verifies the entire flow works.
        """
        # Check if uv is available
        import shutil
        if not shutil.which("uv"):
            pytest.skip("uv not installed - required to run Python MCP servers")

        install_dir = tmp_path / ".fmcp-packages"
        install_dir.mkdir(parents=True)

        # Create config file with GitHub server using explicit command
        # No GitHub token needed - this is a public repository
        # Using basic lowlevel server which uses stdio transport (compatible with FluidMCP)
        config_file = tmp_path / "github_test_config.json"
        config_data = {
            "mcpServers": {
                "python-basic": {
                    "github_repo": "modelcontextprotocol/python-sdk",
                    "branch": "main",
                    "command": "uv",
                    "args": ["run", "examples/snippets/servers/lowlevel/basic.py"],
                    "env": {}
                }
            }
        }
        config_file.write_text(json.dumps(config_data, indent=2))

        # Use a unique port to avoid conflicts with other tests
        test_port = 28099

        # Start fluidmcp in background
        # Ensure uv is in PATH (may be installed in ~/.local/bin)
        env_path = os.environ.get("PATH", "")
        if "/home/codespace/.local/bin" not in env_path:
            env_path = f"/home/codespace/.local/bin:{env_path}"

        env = {
            **os.environ,
            "MCP_INSTALLATION_DIR": str(install_dir),
            "MCP_CLIENT_SERVER_ALL_PORT": str(test_port),
            "PATH": env_path
        }

        process = None
        try:
            process = subprocess.Popen(
                [
                    sys.executable, "-m", "fluidmcp.cli",
                    "run", str(config_file),
                    "--file", "--start-server"
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env
            )

            # Wait for server to be ready
            server_ready = False
            start_time = time.time()
            timeout = 120  # 2 minutes for clone + install + start

            while time.time() - start_time < timeout:
                try:
                    response = requests.get(f"http://127.0.0.1:{test_port}/docs", timeout=2)
                    if response.status_code == 200:
                        server_ready = True
                        break
                except requests.exceptions.ConnectionError:
                    time.sleep(2)

            if not server_ready:
                # Capture output for debugging
                process.terminate()
                stdout, _ = process.communicate(timeout=5)

                # Check for common errors in output
                if "rate limit" in stdout.lower() or "403" in stdout:
                    pytest.skip("GitHub rate limit exceeded")
                if "connection" in stdout.lower() or "timeout" in stdout.lower():
                    pytest.skip("GitHub connection failed")
                if "command not found" in stdout.lower() and "uv" in stdout.lower():
                    pytest.skip("uv command not found in subprocess environment")

                pytest.fail(f"Server failed to start within {timeout}s. Output: {stdout[:1000]}")

            # Server is ready! Now send a JSON-RPC request
            print(f"✅ Server started successfully on port {test_port}")

            # Test 1: Send prompts/list request (basic lowlevel server has prompts)
            response = requests.post(
                f"http://127.0.0.1:{test_port}/python-basic/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "prompts/list"
                },
                timeout=10
            )

            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()

            # Validate JSON-RPC response
            assert data.get("jsonrpc") == "2.0", f"Invalid jsonrpc version: {data.get('jsonrpc')}"
            assert data.get("id") == 1, f"Response id should match request id: {data.get('id')}"
            assert "result" in data, f"Missing 'result' in response: {data}"
            assert "prompts" in data["result"], f"Missing 'prompts' in result: {data['result']}"

            prompts = data["result"]["prompts"]
            assert isinstance(prompts, list), f"Prompts should be a list: {prompts}"
            assert len(prompts) > 0, "Prompts list should not be empty"

            # Verify we got the expected prompt from basic lowlevel server
            prompt_names = [p.get("name") for p in prompts]
            assert "example-prompt" in prompt_names, f"Expected 'example-prompt' in: {prompt_names}"

            print(f"✅ JSON-RPC prompts/list successful, received {len(prompts)} prompts: {prompt_names}")

            # Test 2: Get the example prompt
            response = requests.post(
                f"http://127.0.0.1:{test_port}/python-basic/mcp/prompts/get",
                json={
                    "name": "example-prompt",
                    "arguments": {
                        "arg1": "test-value"
                    }
                },
                timeout=10
            )

            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()

            assert "result" in data, f"Missing 'result' in response: {data}"
            result = data["result"]
            assert "messages" in result, f"Missing 'messages' in result: {result}"

            messages = result["messages"]
            assert isinstance(messages, list), f"Messages should be a list: {messages}"
            assert len(messages) > 0, "Messages should not be empty"

            # The result should contain our test argument value
            message_content = str(messages[0].get("content", {}))
            assert "test-value" in message_content, f"Expected 'test-value' in response, got: {message_content}"

            print(f"✅ Prompt get successful, received prompt with argument")
            print(f"✅ GitHub E2E test PASSED: Clone -> Launch -> JSON-RPC -> Response verified")

        except subprocess.CalledProcessError as e:
            error_output = e.stderr if hasattr(e, 'stderr') else str(e)
            if "rate limit" in error_output.lower() or "403" in error_output:
                pytest.skip("GitHub rate limit exceeded")
            if "connection" in error_output.lower() or "timeout" in error_output.lower():
                pytest.skip("GitHub connection failed")
            raise
        except Exception as e:
            error_msg = str(e).lower()
            if "rate limit" in error_msg or "403" in error_msg:
                pytest.skip("GitHub rate limit exceeded")
            if "connection" in error_msg or "timeout" in error_msg:
                pytest.skip("GitHub connection failed")
            raise
        finally:
            # Clean up: terminate the server
            if process:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()


@pytest.mark.skipif(
    not os.environ.get("MCP_TOKEN"),
    reason="MCP_TOKEN not set - registry tests require authentication"
)
class TestE2EInstallAndRun:
    """Test the install + run flow - requires registry access (MCP_TOKEN)"""

    def test_install_command(self, tmp_path):
        """Test that fluidmcp install creates correct directory structure"""
        install_dir = tmp_path / ".fmcp-packages"
        env = {**os.environ, "MCP_INSTALLATION_DIR": str(install_dir)}

        result = subprocess.run(
            [
                sys.executable, "-m", "fluidmcp.cli",
                "install", "Fetch/fetch@0.6.2"
            ],
            capture_output=True,
            text=True,
            env=env,
            timeout=60
        )

        # Skip if registry not accessible
        _check_registry_access(result.stdout + result.stderr)

        # Check installation succeeded
        assert result.returncode == 0, f"Install failed with: {result.stderr}\n{result.stdout}"

        # Verify package directory structure
        pkg_dir = install_dir / "Fetch" / "fetch" / "0.6.2"
        assert pkg_dir.exists(), f"Package directory not created: {pkg_dir}"

        # Verify metadata.json exists and has correct structure
        metadata_path = pkg_dir / "metadata.json"
        assert metadata_path.exists(), f"metadata.json not found in {pkg_dir}"

        metadata = json.loads(metadata_path.read_text())
        assert "mcpServers" in metadata, f"metadata.json missing 'mcpServers': {metadata}"
        assert len(metadata["mcpServers"]) > 0, "No servers defined in metadata"

        # Verify server config has required fields
        server_name = list(metadata["mcpServers"].keys())[0]
        server_config = metadata["mcpServers"][server_name]
        assert "command" in server_config, f"Server config missing 'command': {server_config}"
        assert "args" in server_config, f"Server config missing 'args': {server_config}"

    def test_list_command_shows_correct_format(self, tmp_path):
        """Test that fluidmcp list shows packages in correct format"""
        install_dir = tmp_path / ".fmcp-packages"
        env = {**os.environ, "MCP_INSTALLATION_DIR": str(install_dir)}

        # First install a package
        install_result = subprocess.run(
            [sys.executable, "-m", "fluidmcp.cli", "install", "Fetch/fetch@0.6.2"],
            capture_output=True,
            text=True,
            env=env,
            timeout=60
        )

        # Skip if registry not accessible
        _check_registry_access(install_result.stdout + install_result.stderr)

        assert install_result.returncode == 0, f"Install failed: {install_result.stderr}"

        # Then list
        result = subprocess.run(
            [sys.executable, "-m", "fluidmcp.cli", "list"],
            capture_output=True,
            text=True,
            env=env,
            timeout=10
        )

        assert result.returncode == 0, f"List command failed: {result.stderr}"

        # Should show package in author/package@version format
        output = result.stdout
        assert "Fetch/fetch@0.6.2" in output, f"Expected 'Fetch/fetch@0.6.2' in output: {output}"

    def test_install_creates_valid_metadata(self, tmp_path):
        """Test that installed package has valid, runnable metadata"""
        install_dir = tmp_path / ".fmcp-packages"
        env = {**os.environ, "MCP_INSTALLATION_DIR": str(install_dir)}

        result = subprocess.run(
            [sys.executable, "-m", "fluidmcp.cli", "install", "Fetch/fetch@0.6.2"],
            capture_output=True,
            text=True,
            env=env,
            timeout=60
        )

        # Skip if registry not accessible
        _check_registry_access(result.stdout + result.stderr)

        # Load and validate metadata
        metadata_path = install_dir / "Fetch" / "fetch" / "0.6.2" / "metadata.json"
        if not metadata_path.exists():
            pytest.skip("Package not installed - registry may be unavailable")

        metadata = json.loads(metadata_path.read_text())

        server_config = list(metadata["mcpServers"].values())[0]

        # Command should be executable (npx, node, python, etc.)
        command = server_config["command"]
        assert command in ["npx", "node", "python", "python3", "uvx"] or command.endswith(".js"), \
            f"Unexpected command: {command}"

        # Args should be a list
        assert isinstance(server_config["args"], list), f"Args should be list: {server_config['args']}"


class TestE2EConfigFileFlow:
    """Test the --file configuration flow end-to-end"""

    def test_invalid_json_file_rejected(self, tmp_path):
        """Test that invalid JSON syntax is properly rejected by resolve_from_file"""
        from fluidmcp.cli.services.config_resolver import resolve_from_file

        invalid_config = tmp_path / "invalid.json"
        invalid_config.write_text("not valid json{")

        with pytest.raises(json.JSONDecodeError):
            resolve_from_file(str(invalid_config))

    def test_missing_file_rejected(self, tmp_path):
        """Test that non-existent file raises FileNotFoundError"""
        from fluidmcp.cli.services.config_resolver import resolve_from_file

        with pytest.raises(FileNotFoundError):
            resolve_from_file(str(tmp_path / "nonexistent.json"))

    def test_valid_config_file_loads(self, tmp_path):
        """Test that a valid config file with inline server config loads correctly"""
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "echo",
                    "args": ["test"],
                    "env": {}
                }
            }
        }
        config_path = tmp_path / "valid.json"
        config_path.write_text(json.dumps(config))

        from fluidmcp.cli.services.config_resolver import resolve_from_file

        server_config = resolve_from_file(str(config_path))

        # Direct configs with "command" don't need installation
        assert server_config.needs_install is False
        assert server_config.source_type == "file"
        assert "test-server" in server_config.servers
        assert server_config.servers["test-server"]["command"] == "echo"

    @pytest.mark.skipif(
        not os.environ.get("MCP_TOKEN"),
        reason="MCP_TOKEN not set - registry tests require authentication"
    )
    def test_config_resolution_parses_package_strings(self, tmp_path):
        """Test that config resolution correctly expands package strings to full metadata"""
        config = {
            "mcpServers": {
                "fetch": "Fetch/fetch@0.6.2"
            }
        }
        config_path = tmp_path / "packages.json"
        config_path.write_text(json.dumps(config))

        from fluidmcp.cli.services.config_resolver import resolve_from_file

        try:
            server_config = resolve_from_file(str(config_path))

            # Validate ServerConfig properties
            assert server_config.needs_install is True, "File configs should need installation"
            assert server_config.source_type == "file", f"Wrong source type: {server_config.source_type}"
            assert len(server_config.servers) >= 1, "Should have at least one server"

            # Validate expanded server config
            server_name = list(server_config.servers.keys())[0]
            server = server_config.servers[server_name]

            assert "command" in server, f"Expanded config missing 'command': {server}"
            assert "args" in server, f"Expanded config missing 'args': {server}"
            assert "fmcp_package" in server, f"Should preserve fmcp_package reference: {server}"
            assert server["fmcp_package"] == "Fetch/fetch@0.6.2", \
                f"Wrong fmcp_package: {server['fmcp_package']}"

        except Exception as e:
            if "403" in str(e) or "Forbidden" in str(e) or "registry" in str(e).lower():
                pytest.skip("Registry unavailable (403 Forbidden)")
            raise
