"""Active dependency probing for MCP servers.

The passive :mod:`tool_error_tracker` only sees failures when someone actually
calls a tool. On an **idle** server a broken database connection is completely
invisible until the next real request — which is exactly the 3am case, where the
first person to notice is a user in the morning.

An active probe closes that gap: call one cheap, side-effect-free tool on an
interval (e.g. a ``SELECT 1`` query tool) and watch it fail.

Opt-in per server::

    "health_probe": {
      "tool": "execute_query",
      "args": {"query": "SELECT 1"},
      "interval_seconds": 120,
      "timeout_seconds": 15,
      "failure_threshold": 2
    }

Probes run inside the existing health-monitor cycle — no second scheduler.
"""

import asyncio
import json
import os
import time
from typing import Any, Dict, Optional, Tuple

import httpx
from loguru import logger


class DependencyProbe:
    """Periodically calls a configured tool to verify a server's dependencies."""

    DEFAULT_INTERVAL = 120
    DEFAULT_TIMEOUT = 15
    DEFAULT_FAILURE_THRESHOLD = 2

    def __init__(self):
        # server_id -> monotonic timestamp of last probe attempt
        self._last_probe: Dict[str, float] = {}
        # server_id -> consecutive failure count
        self._failures: Dict[str, int] = {}
        # server_id -> True while the dependency is considered failed
        self._failed: Dict[str, bool] = {}

    @staticmethod
    def probe_config(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract and normalise a server's probe config, or None if not set."""
        probe = config.get("health_probe")
        if not probe or not isinstance(probe, dict):
            return None
        tool = probe.get("tool")
        if not tool:
            return None
        return {
            "tool": tool,
            "args": probe.get("args") or {},
            "interval_seconds": int(probe.get("interval_seconds",
                                              DependencyProbe.DEFAULT_INTERVAL)),
            "timeout_seconds": float(probe.get("timeout_seconds",
                                               DependencyProbe.DEFAULT_TIMEOUT)),
            "failure_threshold": int(probe.get("failure_threshold",
                                               DependencyProbe.DEFAULT_FAILURE_THRESHOLD)),
        }

    def due(self, server_id: str, probe: Dict[str, Any]) -> bool:
        """Whether this server's probe interval has elapsed."""
        last = self._last_probe.get(server_id)
        if last is None:
            return True
        return (time.monotonic() - last) >= probe["interval_seconds"]

    async def run(
        self,
        server_id: str,
        process: Any,
        probe: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Execute one probe.

        Returns a transition dict when the dependency state *changes*
        (``failed`` / ``recovered``), otherwise None.
        """
        self._last_probe[server_id] = time.monotonic()

        ok, message = await self._call_tool(server_id, process, probe)

        threshold = probe["failure_threshold"]
        was_failed = self._failed.get(server_id, False)

        if ok:
            self._failures[server_id] = 0
            if was_failed:
                self._failed[server_id] = False
                logger.info(f"[probe] '{server_id}' dependency recovered")
                return {"transition": "recovered", "tool": probe["tool"]}
            return None

        count = self._failures.get(server_id, 0) + 1
        self._failures[server_id] = count
        logger.warning(
            f"[probe] '{server_id}' probe failed ({count}/{threshold}): {message}"
        )

        if count >= threshold and not was_failed:
            self._failed[server_id] = True

            from .failure_classifier import diagnose

            verdict = diagnose(tool_errors=[message] if message else None)
            return {
                "transition": "failed",
                "tool": probe["tool"],
                "consecutive_failures": count,
                "message": (message or "")[:500],
                **{
                    k: verdict[k]
                    for k in ("failure_category", "failure_owner", "summary",
                              "remediation", "confidence")
                    if k in verdict
                },
            }

        return None

    async def _call_tool(
        self,
        server_id: str,
        process: Any,
        probe: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """Invoke the probe tool over the server's HTTP port.

        Returns (ok, error_message). Only HTTP-transport servers can be probed
        without contending with the stdio pipe the gateway uses for real traffic.
        """
        base_url = getattr(process, "base_url", None)
        if not base_url:
            return True, None  # stdio server — cannot probe safely, treat as OK.

        payload = {
            "jsonrpc": "2.0",
            "id": f"probe_{int(time.time())}",
            "method": "tools/call",
            "params": {"name": probe["tool"], "arguments": probe["args"]},
        }
        url = f"{base_url.rstrip('/')}/mcp"

        try:
            async with httpx.AsyncClient(timeout=probe["timeout_seconds"]) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Accept": "application/json, text/event-stream"},
                )
        except httpx.TimeoutException:
            return False, f"probe timed out after {probe['timeout_seconds']}s"
        except httpx.ConnectError as e:
            return False, f"probe could not connect: {e}"
        except Exception as e:
            logger.debug(f"[probe] '{server_id}' unexpected probe error: {e}")
            return True, None  # Ambiguous — do not accuse the dependency.

        if response.status_code != 200:
            return False, f"probe returned HTTP {response.status_code}"

        try:
            data = _parse_response(response)
        except Exception as e:
            return False, f"probe returned unparseable response: {e}"

        # JSON-RPC transport-level error
        if isinstance(data, dict) and "error" in data:
            error = data["error"]
            message = error.get("message", str(error)) if isinstance(error, dict) else str(error)
            return False, f"probe tool error: {message}"

        # MCP tool-level error: a 200 OK result carrying isError=true. This is
        # how MCP servers report "the query failed", so missing it would make
        # every probe look successful.
        result = data.get("result") if isinstance(data, dict) else None
        if isinstance(result, dict) and result.get("isError"):
            return False, f"probe tool returned isError: {_result_text(result)}"

        return True, None

    def is_failed(self, server_id: str) -> bool:
        return self._failed.get(server_id, False)

    def reset(self, server_id: str) -> None:
        self._last_probe.pop(server_id, None)
        self._failures.pop(server_id, None)
        self._failed.pop(server_id, None)

    def status(self, server_id: str) -> Dict[str, Any]:
        return {
            "dependency_failed": self._failed.get(server_id, False),
            "consecutive_failures": self._failures.get(server_id, 0),
            "last_probe_age_seconds": (
                round(time.monotonic() - self._last_probe[server_id], 1)
                if server_id in self._last_probe else None
            ),
        }


def _parse_response(response: httpx.Response) -> Dict[str, Any]:
    """Parse a JSON or SSE-framed MCP response."""
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        for line in response.text.splitlines():
            if line.startswith("data: "):
                return json.loads(line[6:])
        raise ValueError("no data line in SSE response")
    return response.json()


def _result_text(result: Dict[str, Any]) -> str:
    """Extract readable text from an MCP tool result's content blocks."""
    content = result.get("content")
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        joined = " ".join(p for p in parts if p).strip()
        if joined:
            return joined[:500]
    return str(result)[:500]
