"""
End-to-end JSON-RPC response-correlation test against a real FluidMCP gateway.

Sends concurrent MCP requests, each with a unique JSON-RPC ID, from independent
HTTP clients to one gateway server endpoint (so they share one MCP subprocess)
and verifies that every response carries the ID of the request that owns it:

    response["id"] == request["id"]

Arrival order does not matter; responses are matched only by the JSON-RPC ID
returned by the gateway. Image content is never compared.

The network tests hit a real deployment and trigger real image generations, so
they are skipped unless explicitly enabled:

    export FLUIDMCP_E2E=true
    export FLUIDMCP_E2E_TOKEN=...            # bearer token, if the gateway requires one
    pytest tests/test_e2e_jsonrpc_correlation.py -s -v

Optional:
    FLUIDMCP_E2E_ENDPOINT   override the endpoint (default: production gemini-image-mcp)
    FLUIDMCP_E2E_LARGE=true also run the 10-concurrent-request case

The result only describes the gateway code deployed at the endpoint. To validate
a gateway change, point FLUIDMCP_E2E_ENDPOINT at a deployment that includes it.

The offline tests at the bottom exercise the correlation checker itself and
always run.
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
import pytest


DEFAULT_ENDPOINT = "https://gateway.fluidmcp.com/gemini-image-mcp/mcp"
ENDPOINT = os.getenv("FLUIDMCP_E2E_ENDPOINT", DEFAULT_ENDPOINT)
TOKEN = os.getenv("FLUIDMCP_E2E_TOKEN", "")
REQUEST_TIMEOUT = 90.0  # per request; the gateway's own stdio read timeout defaults to 45s
CONNECT_TIMEOUT = 45.0  # TLS handshakes to the deployed gateway have been observed at 12-16s

PROMPTS = [
    "Generate a simple orange circle on a white background.",
    "Generate a simple purple square on a white background.",
    "Generate a simple blue triangle on a white background.",
    "Generate a simple green star on a white background.",
    "Generate a simple yellow hexagon on a white background.",
]

requires_e2e = pytest.mark.skipif(
    os.getenv("FLUIDMCP_E2E") != "true",
    reason="Real-endpoint E2E test. Set FLUIDMCP_E2E=true to enable.",
)


# ── Records and correlation checking ────────────────────────────────────────

@dataclass
class CallRecord:
    request_id: Any
    prompt: str = ""
    http_status: Optional[int] = None
    response_json: Any = None
    response_id: Any = None
    sent_at: float = 0.0
    received_at: float = 0.0
    error: str = ""
    session_header: Optional[str] = None

    @property
    def elapsed(self) -> float:
        return max(self.received_at - self.sent_at, 0.0)

    @property
    def has_response_id(self) -> bool:
        return isinstance(self.response_json, dict) and "id" in self.response_json


@dataclass
class CorrelationReport:
    records: List[CallRecord]
    expected_ids: List[Any]
    mismatches: List[CallRecord] = field(default_factory=list)
    missing: List[CallRecord] = field(default_factory=list)
    unexpected: List[CallRecord] = field(default_factory=list)
    duplicates: List[Any] = field(default_factory=list)
    http_failures: List[CallRecord] = field(default_factory=list)
    rpc_errors: List[CallRecord] = field(default_factory=list)
    arrival_order: List[Any] = field(default_factory=list)

    @property
    def correlation_ok(self) -> bool:
        return not (self.mismatches or self.missing or self.unexpected or self.duplicates)

    @property
    def ok(self) -> bool:
        return self.correlation_ok and not (self.http_failures or self.rpc_errors)

    @property
    def out_of_order(self) -> bool:
        return self.arrival_order != [r.request_id for r in self.records if r.received_at]

    def failure_lines(self) -> List[str]:
        lines = []
        for r in self.mismatches:
            lines.append(
                "JSON-RPC response correlation failure: "
                f"request_id={r.request_id} response_id={r.response_id}"
            )
        for r in self.unexpected:
            lines.append(f"Unexpected response ID: request_id={r.request_id} response_id={r.response_id}")
        for rid in self.duplicates:
            lines.append(f"Duplicate response ID received by more than one request: response_id={rid}")
        for r in self.missing:
            lines.append(f"Missing response: request_id={r.request_id} reason={r.error or 'no JSON-RPC id'}")
        for r in self.http_failures:
            hint = " (concurrency limit)" if r.http_status == 429 else ""
            hint = " (authentication)" if r.http_status in (401, 403) else hint
            lines.append(f"HTTP failure: request_id={r.request_id} status={r.http_status}{hint} {r.error}")
        for r in self.rpc_errors:
            lines.append(f"JSON-RPC error: request_id={r.request_id} {r.error}")
        return lines

    def render(self, title: str = "FluidMCP E2E JSON-RPC correlation test") -> str:
        out = [title, "", "Endpoint:", ENDPOINT, "", f"Concurrent requests: {len(self.records)}", ""]
        out.append(f"{'Request ID':<24}{'Response ID':<24}{'HTTP':<6}{'Elapsed':>9}  Status")
        for r in self.records:
            if r in self.mismatches or r in self.unexpected:
                status = "MISMATCH"
            elif r in self.missing:
                status = "MISSING"
            elif r in self.http_failures or r in self.rpc_errors:
                status = "ERROR"
            else:
                status = "PASS"
            resp = r.response_id if r.has_response_id else "-"
            out.append(f"{str(r.request_id):<24}{str(resp):<24}{str(r.http_status or '-'):<6}{r.elapsed:>8.2f}s  {status}")
        out += [
            "",
            f"Arrival order: {', '.join(str(i) for i in self.arrival_order)}",
            f"Out of order: {'yes' if self.out_of_order else 'no'}",
            "",
            f"Requests: {len(self.records)}",
            f"Responses: {sum(1 for r in self.records if r.has_response_id)}",
            f"Mismatches: {len(self.mismatches)}",
            f"Missing: {len(self.missing)}",
            f"Duplicates: {len(self.duplicates)}",
            f"HTTP failures: {len(self.http_failures)}",
            f"JSON-RPC errors: {len(self.rpc_errors)}",
            "",
        ]
        out += self.failure_lines()
        out += ["", f"RESULT: {'PASS' if self.ok else 'FAIL'}"]
        return "\n".join(out)


def check_correlation(records: List[CallRecord], expected_ids: List[Any]) -> CorrelationReport:
    """Match responses to requests strictly by the JSON-RPC ID each response carries."""
    report = CorrelationReport(records=records, expected_ids=expected_ids)
    expected = set(expected_ids)
    seen: Dict[Any, int] = {}
    for r in records:
        if r.http_status is not None and r.http_status != 200:
            report.http_failures.append(r)
        if not r.has_response_id:
            report.missing.append(r)
            continue
        rid = r.response_id
        seen[rid] = seen.get(rid, 0) + 1
        if rid not in expected:
            report.unexpected.append(r)
        elif rid != r.request_id:
            report.mismatches.append(r)
        body = r.response_json
        if "error" in body:
            r.error = r.error or f"error={str(body['error'])[:200]}"
            report.rpc_errors.append(r)
        elif isinstance(body.get("result"), dict) and body["result"].get("isError"):
            r.error = r.error or "result.isError=true"
            report.rpc_errors.append(r)
    report.duplicates = sorted((rid for rid, n in seen.items() if n > 1), key=str)
    report.arrival_order = [r.request_id for r in sorted((r for r in records if r.received_at), key=lambda r: r.received_at)]
    return report


# ── Real MCP client ─────────────────────────────────────────────────────────

class McpClient:
    """One independent HTTP client (own connection pool and MCP session)."""

    def __init__(self, name: str):
        self.name = name
        self.session_id: Optional[str] = None
        self.init_response: Any = None
        self.initialized_status: Optional[int] = None
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=CONNECT_TIMEOUT))

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if TOKEN:
            headers["Authorization"] = f"Bearer {TOKEN}"
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    async def post(self, message: Dict[str, Any], prompt: str = "") -> CallRecord:
        record = CallRecord(request_id=message.get("id"), prompt=prompt)
        record.sent_at = time.monotonic()
        try:
            resp = await self._http.post(ENDPOINT, json=message, headers=self._headers())
            record.received_at = time.monotonic()
            record.http_status = resp.status_code
            record.session_header = resp.headers.get("mcp-session-id")
            if resp.status_code in (202, 204) or not resp.content:
                return record
            try:
                record.response_json = _parse_body(resp)
            except ValueError:
                record.error = f"non-JSON body: {resp.text[:200]!r}"
                return record
            if isinstance(record.response_json, dict) and "id" in record.response_json:
                record.response_id = record.response_json["id"]
            if resp.status_code != 200:
                record.error = f"body={resp.text[:200]!r}"
        except httpx.TimeoutException as e:
            record.received_at = time.monotonic()
            record.error = f"{type(e).__name__} after {record.elapsed:.1f}s"
        except httpx.HTTPError as e:
            record.received_at = time.monotonic()
            record.error = f"{type(e).__name__}: {e}"
        return record

    async def initialize(self) -> None:
        init = await self.post({
            "jsonrpc": "2.0",
            "id": f"e2e-init-{self.name}",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "fluidmcp-e2e-correlation", "version": "1.0.0"},
            },
        })
        _require_ok(init, "initialize")
        self.init_response = init.response_json
        assert init.response_id == f"e2e-init-{self.name}", f"initialize returned id={init.response_id!r}"
        self.session_id = init.session_header
        notif = await self.post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.initialized_status = notif.http_status
        assert notif.http_status in (200, 202, 204), f"notifications/initialized -> HTTP {notif.http_status} {notif.error}"

    async def aclose(self) -> None:
        await self._http.aclose()


def _parse_body(resp: httpx.Response) -> Any:
    """Parse a JSON body, or the last JSON `data:` event of an SSE body."""
    ctype = resp.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        payloads = [line[5:].strip() for line in resp.text.splitlines() if line.startswith("data:")]
        if not payloads:
            raise ValueError("empty SSE body")
        return json.loads(payloads[-1])
    return resp.json()


def _require_ok(record: CallRecord, step: str) -> None:
    if record.http_status in (401, 403):
        pytest.fail(f"{step}: HTTP {record.http_status} (authentication). Set FLUIDMCP_E2E_TOKEN.")
    if record.http_status != 200 or not isinstance(record.response_json, dict):
        pytest.fail(f"{step}: HTTP {record.http_status} error={record.error or '-'}")
    if "error" in record.response_json:
        pytest.fail(f"{step}: JSON-RPC error {str(record.response_json['error'])[:300]}")


async def _new_client(name: str) -> McpClient:
    client = McpClient(name)
    await client.initialize()
    return client


def _select_image_tool(tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    names = [t.get("name", "") for t in tools]
    for tool in tools:
        if tool.get("name") == "generate_image":
            return tool
    candidates = [t for t in tools if "image" in t.get("name", "").lower() and "generat" in t.get("name", "").lower()]
    if len(candidates) != 1:
        pytest.fail(f"Could not identify a unique image generation tool. Available tools: {names}")
    return candidates[0]


def _build_arguments(tool: Dict[str, Any], prompt: str) -> Dict[str, Any]:
    """Fill only the prompt argument, taken from the tool's real input schema."""
    schema = tool.get("inputSchema") or {}
    props = schema.get("properties") or {}
    required = list(schema.get("required") or [])
    if "prompt" in props:
        prompt_key = "prompt"
    else:
        strings = [k for k in required if (props.get(k) or {}).get("type") == "string"]
        if len(strings) != 1:
            pytest.skip(f"Cannot determine the prompt argument from schema: {json.dumps(schema)[:300]}")
        prompt_key = strings[0]
    other_required = [k for k in required if k != prompt_key]
    if other_required:
        pytest.skip(f"Tool requires arguments with no safe value: {other_required}")
    return {prompt_key: prompt}


async def _discover_tool() -> Dict[str, Any]:
    client = await _new_client("discovery")
    try:
        listing = await client.post({"jsonrpc": "2.0", "id": "e2e-tools-list", "method": "tools/list"})
        _require_ok(listing, "tools/list")
        tools = (listing.response_json.get("result") or {}).get("tools") or []
        tool = _select_image_tool(tools)
        print("\nMCP initialization flow: initialize -> notifications/initialized -> tools/list -> tools/call")
        print(f"Token: {'set' if TOKEN else 'not set'}")
        print(f"initialize response: {json.dumps(client.init_response)[:600]}")
        print(f"Mcp-Session-Id returned: {'yes' if client.session_id else 'no'}; "
              f"notifications/initialized -> HTTP {client.initialized_status}")
        print(f"Tool used: {tool.get('name')} inputSchema: {json.dumps(tool.get('inputSchema'))[:600]}")
        return tool
    finally:
        await client.aclose()


async def _run_concurrent(request_ids: List[str]) -> CorrelationReport:
    tool = await _discover_tool()
    clients = await asyncio.gather(*(_new_client(f"c{i}") for i in range(len(request_ids))))
    try:
        calls = []
        for i, (client, rid) in enumerate(zip(clients, request_ids)):
            prompt = PROMPTS[i % len(PROMPTS)]
            message = {
                "jsonrpc": "2.0",
                "id": rid,
                "method": "tools/call",
                "params": {"name": tool["name"], "arguments": _build_arguments(tool, prompt)},
            }
            calls.append(client.post(message, prompt=prompt))
        # All requests in flight at once: no lock, no sleeps between sends.
        records = await asyncio.gather(*calls)
    finally:
        await asyncio.gather(*(c.aclose() for c in clients))
    report = check_correlation(list(records), request_ids)
    print("\n" + report.render())
    return report


# ── Real-endpoint tests ─────────────────────────────────────────────────────

@requires_e2e
class TestRealGatewayCorrelation:

    async def test_five_concurrent_unique_ids(self):
        ids = [f"e2e-test-{i:03d}" for i in range(1, 6)]
        report = await _run_concurrent(ids)
        assert report.ok, report.render()

    @pytest.mark.skipif(os.getenv("FLUIDMCP_E2E_LARGE") != "true",
                        reason="Set FLUIDMCP_E2E_LARGE=true to run the 10-request case.")
    async def test_ten_concurrent_unique_ids(self):
        ids = [f"e2e-test-{i:03d}" for i in range(11, 21)]
        report = await _run_concurrent(ids)
        assert report.ok, report.render()

    async def test_duplicate_client_ids_independent_clients(self):
        """Two clients both use id=1; responses are told apart by result shape, not content."""
        tool = await _discover_tool()
        lister, caller = await asyncio.gather(_new_client("dup-list"), _new_client("dup-call"))
        try:
            list_rec, call_rec = await asyncio.gather(
                lister.post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
                caller.post({
                    "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": tool["name"], "arguments": _build_arguments(tool, PROMPTS[0])},
                }, prompt=PROMPTS[0]),
            )
        finally:
            await asyncio.gather(lister.aclose(), caller.aclose())

        def shape(rec: CallRecord) -> str:
            result = (rec.response_json or {}).get("result") if isinstance(rec.response_json, dict) else None
            if isinstance(result, dict) and "tools" in result:
                return "tools/list"
            if isinstance(result, dict) and "content" in result:
                return "tools/call"
            return "error" if isinstance(rec.response_json, dict) and "error" in rec.response_json else "none"

        lines = [
            "FluidMCP E2E duplicate client ID test", "", "Endpoint:", ENDPOINT, "",
            f"client=dup-list method=tools/list request_id=1 response_id={list_rec.response_id} "
            f"http={list_rec.http_status} shape={shape(list_rec)} elapsed={list_rec.elapsed:.2f}s {list_rec.error}",
            f"client=dup-call method=tools/call request_id=1 response_id={call_rec.response_id} "
            f"http={call_rec.http_status} shape={shape(call_rec)} elapsed={call_rec.elapsed:.2f}s {call_rec.error}",
        ]
        ok = (list_rec.response_id == 1 and call_rec.response_id == 1
              and shape(list_rec) == "tools/list" and shape(call_rec) == "tools/call")
        if shape(list_rec) == "tools/call" or shape(call_rec) == "tools/list":
            lines.append("Responses were cross-delivered between clients sharing id=1")
        lines += ["", f"RESULT: {'PASS' if ok else 'FAIL'}"]
        print("\n" + "\n".join(lines))
        assert ok, "\n".join(lines)


# ── Offline tests of the correlation checker (always run) ───────────────────

def _rec(request_id, response_id, received_at, result=None, status=200):
    body = {"jsonrpc": "2.0", "id": response_id, "result": result or {"content": []}}
    return CallRecord(request_id=request_id, http_status=status, response_json=body,
                      response_id=response_id, sent_at=0.0, received_at=received_at)


class TestCorrelationChecker:

    def test_out_of_order_arrival_passes(self):
        ids = [f"e2e-test-{i:03d}" for i in range(1, 6)]
        arrival = {"e2e-test-003": 1, "e2e-test-001": 2, "e2e-test-005": 3, "e2e-test-002": 4, "e2e-test-004": 5}
        records = [_rec(i, i, arrival[i]) for i in ids]
        report = check_correlation(records, ids)
        assert report.ok
        assert report.out_of_order
        assert report.arrival_order == ["e2e-test-003", "e2e-test-001", "e2e-test-005", "e2e-test-002", "e2e-test-004"]

    def test_shifted_responses_fail_with_exact_message(self):
        """Historic failure: each request received the previous request's response."""
        ids = ["e2e-test-001", "e2e-test-002", "e2e-test-003"]
        records = [_rec("e2e-test-001", "stale-x", 1), _rec("e2e-test-002", "e2e-test-001", 2),
                   _rec("e2e-test-003", "e2e-test-002", 3)]
        report = check_correlation(records, ids)
        assert not report.ok
        text = report.render()
        assert "JSON-RPC response correlation failure: request_id=e2e-test-003 response_id=e2e-test-002" in text
        assert "Unexpected response ID: request_id=e2e-test-001 response_id=stale-x" in text
        assert "RESULT: FAIL" in text

    def test_duplicate_and_missing_detected(self):
        ids = ["a", "b", "c"]
        records = [_rec("a", "a", 1), _rec("b", "a", 2), CallRecord(request_id="c", error="timeout after 90.0s")]
        report = check_correlation(records, ids)
        assert report.duplicates == ["a"]
        assert [r.request_id for r in report.missing] == ["c"]
        assert [r.request_id for r in report.mismatches] == ["b"]

    def test_http_and_rpc_errors_fail_without_mismatch(self):
        ids = ["a", "b"]
        err = CallRecord(request_id="a", http_status=200, response_json={"jsonrpc": "2.0", "id": "a", "error": {"code": -32603}},
                         response_id="a", received_at=1)
        limited = CallRecord(request_id="b", http_status=429, received_at=2, error="body='too many'")
        report = check_correlation([err, limited], ids)
        assert report.correlation_ok is False  # b has no JSON-RPC id → missing
        assert not report.mismatches
        assert "(concurrency limit)" in report.render()
        assert [r.request_id for r in report.rpc_errors] == ["a"]
