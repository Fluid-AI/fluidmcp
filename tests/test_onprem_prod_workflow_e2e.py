"""End-to-end test of the on-prem production workflow, with no mocks:

    fmcp run prod-config.json --file --start-server

using the on-prem layout (python servers, per-server env_file, TRANSPORT_TYPE=http):

    <root>/prod-config.json
    <root>/servers/<name>/server.py
    <root>/servers/<name>/.env

Relative "args"/"env_file" paths resolve against the config file's directory,
so the config sits next to servers/ (as it must inside the container).

Requires the `mcp` SDK (FastMCP) to run the test servers; skipped otherwise.
All credentials are fake.
"""
import asyncio
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import textwrap
import time

import httpx
import psutil
import pytest

pytest.importorskip("mcp.server.fastmcp")

SERVER_PY = textwrap.dedent('''
    import asyncio
    import os

    from mcp.server.fastmcp import Context, FastMCP

    LABEL = os.environ.get("SERVER_LABEL", "unset")
    mcp = FastMCP(LABEL, host="127.0.0.1", port=int(os.environ.get("MCP_PORT", "8000")))


    @mcp.tool()
    def echo(text: str) -> str:
        return f"{LABEL}:{text}"


    @mcp.tool()
    async def slow_echo(text: str, seconds: float = 0.5) -> str:
        await asyncio.sleep(seconds)
        return f"{LABEL}:{text}"


    @mcp.tool()
    def fail() -> str:
        raise ValueError("simulated failure")


    @mcp.tool()
    def get_env(name: str) -> str:
        return os.environ.get(name, "<unset>")


    @mcp.tool()
    async def log_then_echo(text: str, ctx: Context) -> str:
        await ctx.info(f"working on {text}")
        await ctx.report_progress(50, 100)
        return f"{LABEL}:{text}"


    if __name__ == "__main__":
        transport = os.environ.get("TRANSPORT_TYPE", "stdio")
        mcp.run(transport="streamable-http" if transport == "http" else "stdio")
''')

SERVERS = {
    "srv-a": ("server_a", "label-a", "postgresql://fake:FAKE_A@db-a.invalid/x"),
    "srv-b": ("server_b", "label-b", "postgresql://fake:FAKE_B@db-b.invalid/x"),
}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _call(req_id, tool, args):
    return {"jsonrpc": "2.0", "id": req_id, "method": "tools/call",
            "params": {"name": tool, "arguments": args}}


def _text(body):
    return body["result"]["content"][0]["text"]


@pytest.fixture(scope="module")
def gateway(tmp_path_factory):
    root = tmp_path_factory.mktemp("onprem")
    config = {"mcpServers": {}}
    for name, (folder, label, conn) in SERVERS.items():
        d = root / "servers" / folder
        d.mkdir(parents=True)
        (d / "server.py").write_text(SERVER_PY)
        (d / ".env").write_text(f"TRANSPORT_TYPE=http\nSERVER_LABEL={label}\nONGC_HR_CONN={conn}\n")
        config["mcpServers"][name] = {
            "command": sys.executable,
            "args": [f"servers/{folder}/server.py"],
            "env_file": f"servers/{folder}/.env",
        }
    (root / "prod-config.json").write_text(json.dumps(config))

    port = _free_port()
    env = {**os.environ, "MCP_CLIENT_SERVER_ALL_PORT": str(port), "FMCP_HEALTH_CHECK_INTERVAL": "2"}
    log = open(root / "fmcp.log", "w")
    # Prefer the installed `fmcp` console script; fall back to its entry point
    # (setup.py: fmcp=fluidmcp:main) when the package is not installed.
    fmcp = shutil.which("fmcp")
    launcher = [fmcp] if fmcp else [sys.executable, "-c", "import sys; from fluidmcp import main; sys.exit(main())"]
    proc = subprocess.Popen(
        launcher + ["run", "prod-config.json", "--file", "--start-server"],
        cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            if httpx.get(f"{base}/health", timeout=2).json().get("running_servers") == len(SERVERS):
                break
        except (httpx.HTTPError, ValueError):
            pass
        assert proc.poll() is None, (root / "fmcp.log").read_text()[-3000:]
        time.sleep(0.5)
    else:
        proc.kill()
        pytest.fail("gateway did not become healthy:\n" + (root / "fmcp.log").read_text()[-3000:])

    yield {"base": base, "proc": proc, "root": root}

    if proc.poll() is None:
        proc.kill()
    # Orphaned servers are reparented away from us, so match on cwd instead of ancestry
    for p in psutil.process_iter(["cwd"]):
        if p.info["cwd"] and p.info["cwd"].startswith(str(root)):
            try:
                p.kill()
            except psutil.Error:
                pass
    log.close()


def _rpc(gw, server, payload, timeout=60):
    return httpx.post(f"{gw['base']}/{server}/mcp", json=payload, timeout=timeout)


def test_protocol_flow_over_http_transport(gateway):
    init = _rpc(gateway, "srv-a", {"jsonrpc": "2.0", "id": "i1", "method": "initialize",
                                   "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                                              "clientInfo": {"name": "t", "version": "0"}}})
    assert init.status_code == 200 and init.json()["id"] == "i1"
    assert _rpc(gateway, "srv-a", {"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code in (202, 204)

    tools = _rpc(gateway, "srv-a", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).json()
    assert tools["id"] == 2
    assert {"echo", "get_env", "log_then_echo"} <= {t["name"] for t in tools["result"]["tools"]}

    echo = _rpc(gateway, "srv-a", _call(3, "echo", {"text": "hi"})).json()
    assert echo["id"] == 3 and _text(echo) == "label-a:hi"

    unknown = _rpc(gateway, "srv-a", _call(4, "nope", {})).json()
    assert unknown["id"] == 4 and unknown["result"]["isError"] is True

    failing = _rpc(gateway, "srv-a", _call(5, "fail", {})).json()
    assert failing["id"] == 5 and failing["result"]["isError"] is True


def test_tool_logging_does_not_replace_result(gateway):
    body = _rpc(gateway, "srv-a", _call("log-1", "log_then_echo", {"text": "x"})).json()
    assert body.get("id") == "log-1", body
    assert _text(body) == "label-a:x"


def test_null_params_is_not_a_gateway_crash(gateway):
    for payload in (
        {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": None},
        {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "echo", "arguments": None}},
    ):
        resp = _rpc(gateway, "srv-a", payload)
        assert resp.status_code != 500, (payload, resp.text)


def test_env_file_isolated_per_server(gateway):
    for name, (_, label, conn) in SERVERS.items():
        assert _text(_rpc(gateway, name, _call(1, "get_env", {"name": "SERVER_LABEL"})).json()) == label
        assert _text(_rpc(gateway, name, _call(2, "get_env", {"name": "ONGC_HR_CONN"})).json()) == conn


def test_concurrent_requests_get_their_own_response(gateway):
    async def run():
        async with httpx.AsyncClient(timeout=60) as client:
            jobs = []
            for i in range(40):
                server = "srv-a" if i % 2 else "srv-b"
                tool, args = (("slow_echo", {"text": f"m{i}", "seconds": (i % 5) * 0.2})
                              if i % 3 else ("log_then_echo", {"text": f"m{i}"}))
                jobs.append((i, server, client.post(f"{gateway['base']}/{server}/mcp",
                                                    json=_call(f"r{i}", tool, args))))
            results = await asyncio.gather(*(j[2] for j in jobs))
            for (i, server, _), resp in zip(jobs, results):
                body = resp.json()
                label = SERVERS[server][1]
                assert body["id"] == f"r{i}", body
                assert _text(body) == f"{label}:m{i}", body

    asyncio.run(run())


def test_manual_restart_keeps_env_file(gateway):
    resp = httpx.post(f"{gateway['base']}/api/servers/srv-b/restart", timeout=90)
    assert resp.status_code == 200, resp.text
    body = _rpc(gateway, "srv-b", _call(1, "get_env", {"name": "ONGC_HR_CONN"})).json()
    assert _text(body) == SERVERS["srv-b"][2]
    health = httpx.get(f"{gateway['base']}/health").json()
    assert health["running_servers"] == len(SERVERS)


def test_sigterm_terminates_mcp_children(gateway):
    """Runs last (module order): docker stop sends SIGTERM to the gateway."""
    proc = gateway["proc"]
    children = [c for c in psutil.Process(proc.pid).children(recursive=True)]
    assert len(children) == len(SERVERS)

    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=30)
    gone, alive = psutil.wait_procs(children, timeout=10)
    assert not alive, f"MCP children outlived the gateway: {[p.pid for p in alive]}"
