"""Rolling per-tool error-rate tracking for MCP servers.

This is what catches the failure class the process watchdog cannot see: a server
whose PID is alive and whose HTTP port answers, but whose tool calls all fail
because a database connection, credential, or upstream dependency is broken.

Tracked **per (server, tool)**, not only per server. A single broken tool inside
an otherwise-busy server dilutes to nothing in a server-wide average and would
never cross a threshold — which is exactly the "one endpoint suddenly started
failing" case. Both views are exposed: per-tool rates drive alerts, the
server-wide rate gives context.
"""

import os
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

from loguru import logger

from ..utils.error_utils import redact_secrets


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (ValueError, TypeError):
        logger.warning(f"Invalid {name}, using default {default}")
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (ValueError, TypeError):
        logger.warning(f"Invalid {name}, using default {default}")
        return default


class ToolErrorTracker:
    """Sliding-window outcome tracking per (server_id, tool_name)."""

    #: Outcome values considered failures. "timeout" counts — a tool that never
    #: returns is as broken as one that errors, and pool exhaustion presents as
    #: timeouts before it presents as errors.
    FAILURE_OUTCOMES = frozenset({"error", "timeout", "tool_error", "parse_error"})

    def __init__(self):
        # (server_id, tool_name) -> deque[(timestamp, outcome, message)]
        self._samples: Dict[Tuple[str, str], Deque[Tuple[float, str, str]]] = {}
        # server_id -> currently-degraded flag, so transitions fire once
        self._degraded: Dict[str, bool] = {}
        # server_id -> last classified failure seen
        self._last_error: Dict[str, Dict[str, Any]] = {}

    # ── configuration ─────────────────────────────────────────────────────

    @property
    def window_seconds(self) -> float:
        return _env_float("FMCP_ERROR_WINDOW_SECONDS", 300.0)

    @property
    def error_rate_threshold(self) -> float:
        return _env_float("FMCP_DEGRADED_ERROR_RATE", 0.5)

    @property
    def min_samples(self) -> int:
        return _env_int("FMCP_DEGRADED_MIN_SAMPLES", 5)

    @property
    def recovery_rate(self) -> float:
        """Error rate below which a degraded server is considered recovered."""
        return _env_float("FMCP_RECOVERY_ERROR_RATE", 0.1)

    @property
    def recovery_streak(self) -> int:
        """Consecutive successful calls required to clear a degraded flag.

        Recovery is judged on a trailing success streak rather than on the
        whole-window error rate. Rate-based recovery is pathologically sticky:
        the historical failures stay inside the window, so a server that is
        demonstrably working again keeps reporting degraded until those samples
        age out — minutes after an operator can see it is fixed. A streak
        matches what "it is working again" actually means, while still requiring
        sustained evidence rather than one lucky call.
        """
        return _env_int("FMCP_RECOVERY_STREAK", 5)

    # ── recording ─────────────────────────────────────────────────────────

    def record(
        self,
        server_id: str,
        tool_name: str,
        outcome: str,
        message: Optional[str] = None,
    ) -> None:
        """Record one tool-call outcome.

        Args:
            server_id: Server the call was routed to.
            tool_name: Tool invoked (use the JSON-RPC method for non-tool calls).
            outcome: "success" or one of FAILURE_OUTCOMES.
            message: Error text, used for classification. Truncated on store.
        """
        try:
            key = (server_id, tool_name or "unknown")
            samples = self._samples.get(key)
            if samples is None:
                samples = deque(maxlen=200)
                self._samples[key] = samples

            # Classify against the RAW message, store the REDACTED one. Stored
            # text reaches the event feed, webhooks and the customer's own
            # monitoring store, and MCP servers routinely echo their connection
            # strings in errors. Redacting before classification would strip the
            # tokens the patterns match on.
            safe_message = redact_secrets(message or "")[:500]
            samples.append((time.monotonic(), outcome, safe_message))

            if outcome in self.FAILURE_OUTCOMES and message:
                # Lazy import: failure_classifier imports server_manager, which
                # imports this module.
                from .failure_classifier import classify_text

                hit = classify_text(message)
                entry = {"tool": tool_name, "message": safe_message}
                if hit:
                    # `matched` comes from the raw text, so redact it too.
                    entry.update(hit)
                    entry["matched"] = redact_secrets(hit.get("matched", ""))
                self._last_error[server_id] = entry
        except Exception as e:
            # Metrics must never break request handling.
            logger.debug(f"ToolErrorTracker.record failed for '{server_id}': {e}")

    # ── querying ──────────────────────────────────────────────────────────

    def _live_samples(self, key: Tuple[str, str]) -> List[Tuple[float, str, str]]:
        """Samples inside the current window, pruning expired ones."""
        samples = self._samples.get(key)
        if not samples:
            return []
        cutoff = time.monotonic() - self.window_seconds
        while samples and samples[0][0] < cutoff:
            samples.popleft()
        return list(samples)

    def tool_stats(self, server_id: str) -> List[Dict[str, Any]]:
        """Per-tool stats for a server, worst error rate first."""
        results: List[Dict[str, Any]] = []
        for (sid, tool), _ in list(self._samples.items()):
            if sid != server_id:
                continue
            samples = self._live_samples((sid, tool))
            if not samples:
                continue
            failures = [s for s in samples if s[1] in self.FAILURE_OUTCOMES]
            last_error = next(
                (s[2] for s in reversed(samples)
                 if s[1] in self.FAILURE_OUTCOMES and s[2]),
                None,
            )
            results.append({
                "tool": tool,
                "calls": len(samples),
                "errors": len(failures),
                "error_rate_5m": round(len(failures) / len(samples), 3),
                "last_error": last_error,
            })

        results.sort(key=lambda r: (-r["error_rate_5m"], -r["errors"]))
        return results

    def server_error_rate(self, server_id: str) -> Tuple[float, int]:
        """Server-wide (error_rate, sample_count) across all tools."""
        total = 0
        failures = 0
        for (sid, tool) in list(self._samples.keys()):
            if sid != server_id:
                continue
            samples = self._live_samples((sid, tool))
            total += len(samples)
            failures += sum(1 for s in samples if s[1] in self.FAILURE_OUTCOMES)
        if total == 0:
            return 0.0, 0
        return round(failures / total, 3), total

    def _trailing_success_streak(self, server_id: str) -> int:
        """Length of the current all-success tail across every tool on a server.

        Counts backwards through the merged, time-ordered sample stream and stops
        at the first failure. Merging matters: a streak on one tool while another
        keeps failing is not a recovery.
        """
        merged: List[Tuple[float, str, str]] = []
        for (sid, tool) in list(self._samples.keys()):
            if sid != server_id:
                continue
            merged.extend(self._live_samples((sid, tool)))
        merged.sort(key=lambda sample: sample[0])

        streak = 0
        for _, outcome, _message in reversed(merged):
            if outcome in self.FAILURE_OUTCOMES:
                break
            streak += 1
        return streak

    def failing_tools(self, server_id: str) -> List[Dict[str, Any]]:
        """Tools currently above the error-rate threshold with enough samples."""
        threshold = self.error_rate_threshold
        minimum = self.min_samples
        return [
            stat for stat in self.tool_stats(server_id)
            if stat["error_rate_5m"] >= threshold and stat["calls"] >= minimum
        ]

    def last_error(self, server_id: str) -> Optional[Dict[str, Any]]:
        """Most recent classified error for a server."""
        return self._last_error.get(server_id)

    # ── state transitions ─────────────────────────────────────────────────

    def evaluate(self, server_id: str) -> Optional[Dict[str, Any]]:
        """Decide whether a server just became degraded or recovered.

        Returns a transition dict, or None if nothing changed. Callers emit the
        corresponding event; this method only owns the decision and the flag.
        """
        failing = self.failing_tools(server_id)
        rate, samples = self.server_error_rate(server_id)
        was_degraded = self._degraded.get(server_id, False)

        # Degraded when any individual tool is failing, OR the server-wide rate
        # is over threshold. The per-tool arm is what catches one broken endpoint
        # inside an otherwise-healthy server.
        should_degrade = bool(failing) or (
            samples >= self.min_samples and rate >= self.error_rate_threshold
        )

        if should_degrade and not was_degraded:
            self._degraded[server_id] = True
            return {
                "transition": "degraded",
                "error_rate_5m": rate,
                "samples": samples,
                "failing_tools": failing,
                "last_error": self._last_error.get(server_id),
            }

        if was_degraded and not should_degrade:
            # Recovered once no tool is failing AND a sustained run of successes
            # has followed. The streak is what makes this responsive; the
            # not-failing check is what keeps it symmetric with degradation.
            streak = self._trailing_success_streak(server_id)
            if streak >= self.recovery_streak:
                self._degraded[server_id] = False
                return {
                    "transition": "recovered",
                    "error_rate_5m": rate,
                    "samples": samples,
                    "success_streak": streak,
                }

        return None

    def is_degraded(self, server_id: str) -> bool:
        return self._degraded.get(server_id, False)

    def reset(self, server_id: str) -> None:
        """Clear all state for a server (called on restart)."""
        for key in [k for k in self._samples if k[0] == server_id]:
            del self._samples[key]
        self._degraded.pop(server_id, None)
        self._last_error.pop(server_id, None)

    def snapshot(self, server_id: str) -> Dict[str, Any]:
        """Compact view for the fleet rollup."""
        rate, samples = self.server_error_rate(server_id)
        return {
            "error_rate_5m": rate,
            "calls_5m": samples,
            "failing_tools": self.failing_tools(server_id),
            "degraded": self.is_degraded(server_id),
            "success_streak": self._trailing_success_streak(server_id),
        }


#: Process-wide singleton — the gateway proxy and management API both feed it.
_tracker: Optional[ToolErrorTracker] = None


def get_tool_error_tracker() -> ToolErrorTracker:
    global _tracker
    if _tracker is None:
        _tracker = ToolErrorTracker()
    return _tracker


def record_tool_outcome(
    server_id: str,
    tool_name: str,
    outcome: str,
    message: Optional[str] = None,
) -> None:
    """Module-level convenience recorder. Never raises."""
    try:
        get_tool_error_tracker().record(server_id, tool_name, outcome, message)
    except Exception:
        pass
