"""Launch the source checkout's real CLI and a real Streamable HTTP MCP subprocess."""

import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import psutil
import pytest


TRANSPORTS = ("http",)
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module", params=[
    (count, endpoint, id_mode)
    for count in (50, 100)
    for endpoint, id_mode in (("jsonrpc", "unique"), ("jsonrpc", "reused"),
                             ("tools-call", "gateway-assigned"))
], ids=lambda value: f"{value[1]}-{value[0]}-users-{value[2]}-rpc-ids")
def gateway(tmp_path_factory, request):
    artifacts = tmp_path_factory.mktemp("fluidmcp-e2e")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    names = {transport: f"e2e-{transport}-{uuid.uuid4().hex[:8]}" for transport in TRANSPORTS}
    config = {"mcpServers": {
        name: {
            "command": sys.executable,
            "args": [str(Path(__file__).with_name("fake_mcp_server.py")),
                     "--transport", transport, "--artifacts", str(artifacts)],
            "transport": transport,
            "max_concurrent_requests": 100,
        }
        for transport, name in names.items()
    }}
    config_path = artifacts / "config.json"
    config_path.write_text(json.dumps(config, indent=2))
    # Avoid inheriting application credentials/configuration or external proxies.
    env = {key: os.environ[key] for key in ("PATH", "LANG", "SYSTEMROOT") if key in os.environ}
    env.update({
        "PYTHONPATH": str(ROOT), "PYTHONUNBUFFERED": "1",
        "MCP_CLIENT_SERVER_ALL_PORT": str(port),
        "MCP_INSTALLATION_DIR": str(artifacts / "packages"),
        "FMCP_SECURE_MODE": "false",
        "FMCP_HTTP_PROXY_TIMEOUT": "30", "FMCP_HTTP_POOL_MAX_CONNECTIONS": "200",
    })
    # Source-layout __main__.py uses an invalid absolute import; invoke the
    # actual CLI entry function directly, without requiring an installed wheel.
    command = [sys.executable, "-c", "from fluidmcp.cli.cli import main; main()",
               "run", str(config_path), "--file", "--start-server"]
    log_path = artifacts / "gateway.log"
    print(f"\nE2E artifacts: {artifacts}")
    with log_path.open("w") as log:
        process = subprocess.Popen(command, cwd=artifacts, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            base_url = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 90
            with httpx.Client(timeout=2, trust_env=False) as client:
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        pytest.fail(f"Gateway exited ({process.returncode}):\n{log_path.read_text()[-8000:]}")
                    try:
                        health = client.get(f"{base_url}/health")
                        if health.status_code == 200 and health.json().get("running_servers") == len(TRANSPORTS):
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.2)
                else:
                    pytest.fail(f"Streamable HTTP server not ready after 90s; see {log_path}\n"
                                + log_path.read_text()[-8000:])
            yield {"url": base_url, "names": names, "artifacts": artifacts,
                   "scenario": request.param}
        finally:
            # Capture children before stopping the parent; reap even after test failures.
            try:
                children = psutil.Process(process.pid).children(recursive=True)
            except psutil.NoSuchProcess:
                children = []
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            _, alive = psutil.wait_procs(children, timeout=5)
            for child in alive:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            psutil.wait_procs(alive, timeout=5)
