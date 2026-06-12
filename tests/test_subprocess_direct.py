#!/usr/bin/env python3
"""
Step 1: Direct subprocess concurrency test.
Starts the addition MCP server directly and sends 100 concurrent requests.
No FluidMCP gateway involved — tests the subprocess in isolation.

Usage:
    python tests/test_subprocess_direct.py [--port PORT] [--concurrency N]

Can also be pointed at a running server:
    python tests/test_subprocess_direct.py --port 8500 --no-spawn
"""

import asyncio
import httpx
import subprocess
import sys
import os
import time
import json
import argparse

SERVER_PATH = os.path.join(os.path.dirname(__file__), "..", "examples", "addition-mcp", "server.py")


def make_tool_call(request_id: int) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {
            "name": "add_numbers",
            "arguments": {"a": request_id, "b": 1}
        }
    }


def validate_response(request_id: int, response: dict) -> tuple:
    """Check the JSON-RPC response is correct. Returns (ok, detail)."""
    if "error" in response:
        return False, f"JSON-RPC error: {response['error']}"
    result = response.get("result", {})
    content = result.get("content", [])
    if not content:
        return False, f"No content in result: {result}"
    text = content[0].get("text", "")
    expected = str(float(request_id) + 1.0)
    if text == expected:
        return True, text
    return False, f"Expected '{expected}', got '{text}'"


def parse_sse_response(text: str) -> dict:
    """Extract JSON from SSE text/event-stream response."""
    for line in text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    raise ValueError(f"No data line in SSE response: {text[:200]}")


async def initialize_session(client: httpx.AsyncClient, port: int) -> str:
    """Do MCP initialize handshake, return session ID."""
    url = f"http://127.0.0.1:{port}/mcp"
    payload = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "capabilities": {},
            "clientInfo": {"name": "concurrency-test", "version": "1.0"},
            "protocolVersion": "2025-03-26"
        }
    }
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}

    resp = await client.post(url, json=payload, headers=headers, timeout=10.0)
    session_id = resp.headers.get("mcp-session-id")
    if not session_id:
        raise RuntimeError(f"No mcp-session-id in response headers: {dict(resp.headers)}")
    return session_id


async def send_request(client: httpx.AsyncClient, port: int, session_id: str, request_id: int, timeout: float) -> dict:
    url = f"http://127.0.0.1:{port}/mcp"
    payload = make_tool_call(request_id)
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "mcp-session-id": session_id,
    }

    start = time.monotonic()
    try:
        resp = await client.post(url, json=payload, headers=headers, timeout=timeout)
        elapsed = time.monotonic() - start

        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            data = parse_sse_response(resp.text)
        else:
            data = resp.json()

        ok, detail = validate_response(request_id, data)
        return {"id": request_id, "ok": ok, "elapsed_ms": round(elapsed * 1000), "detail": detail}
    except Exception as e:
        elapsed = time.monotonic() - start
        return {"id": request_id, "ok": False, "elapsed_ms": round(elapsed * 1000),
                "detail": f"{type(e).__name__}: {e}"}


async def run_test(port: int, concurrency: int, timeout: float, spawn: bool):
    proc = None

    if spawn:
        print(f"Starting addition-mcp server on port {port}...")
        env = os.environ.copy()
        env["MCP_PORT"] = str(port)
        env["TRANSPORT_TYPE"] = "http"

        proc = subprocess.Popen(
            [sys.executable, SERVER_PATH],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        # Wait for server to be ready
        ready = False
        for _ in range(20):
            await asyncio.sleep(0.5)
            if proc.poll() is not None:
                stderr = proc.stderr.read().decode()[:500]
                print(f"ERROR: Server process died. stderr: {stderr}")
                return
            try:
                async with httpx.AsyncClient() as c:
                    sid = await initialize_session(c, port)
                    if sid:
                        ready = True
                        break
            except Exception:
                pass

        if not ready:
            print("ERROR: Server failed to start within 10 seconds")
            proc.kill()
            return

        print(f"Server ready (PID={proc.pid}).")
    else:
        print(f"Connecting to existing server on port {port}...")

    # Initialize a session
    async with httpx.AsyncClient() as client:
        session_id = await initialize_session(client, port)
        print(f"Session: {session_id}")
        print(f"Sending {concurrency} concurrent requests...\n")

        start = time.monotonic()
        tasks = [send_request(client, port, session_id, i + 1, timeout) for i in range(concurrency)]
        results = await asyncio.gather(*tasks)
        wall_clock = time.monotonic() - start

    # Report
    ok_count = sum(1 for r in results if r["ok"])
    fail_count = sum(1 for r in results if not r["ok"])
    latencies = [r["elapsed_ms"] for r in results if r["ok"]]

    print("=" * 60)
    print(f"  DIRECT SUBPROCESS TEST — {concurrency} concurrent requests")
    print("=" * 60)
    print(f"  OK:     {ok_count}/{concurrency}")
    print(f"  FAILED: {fail_count}/{concurrency}")
    print(f"  Wall clock: {round(wall_clock * 1000)}ms")
    if latencies:
        latencies.sort()
        print(f"  Latency P50:  {latencies[len(latencies)//2]}ms")
        print(f"  Latency P95:  {latencies[int(len(latencies)*0.95)]}ms")
        print(f"  Latency P99:  {latencies[int(len(latencies)*0.99)]}ms")
        print(f"  Latency Max:  {latencies[-1]}ms")
    print("=" * 60)

    if fail_count > 0:
        print(f"\nFailed requests:")
        for r in results:
            if not r["ok"]:
                print(f"  req #{r['id']:3d} | {r['elapsed_ms']:5d}ms | {r['detail']}")

    # Cleanup
    if proc:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Direct MCP subprocess concurrency test")
    parser.add_argument("--port", type=int, default=9111, help="Port for the MCP server")
    parser.add_argument("--concurrency", type=int, default=100, help="Number of concurrent requests")
    parser.add_argument("--timeout", type=float, default=30.0, help="Per-request timeout in seconds")
    parser.add_argument("--no-spawn", action="store_true", help="Don't start a server, connect to existing one")
    args = parser.parse_args()

    asyncio.run(run_test(args.port, args.concurrency, args.timeout, spawn=not args.no_spawn))
