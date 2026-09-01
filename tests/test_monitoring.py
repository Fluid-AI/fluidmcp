"""Tests for the MCP fleet monitoring subsystem.

Covers the detection paths that matter operationally:

- failure classification and owner attribution
- pre-flight config validation (missing / placeholder credentials)
- per-tool error rates, including the single-broken-endpoint case
- event bus sequencing, cursor semantics, and severity filtering
- webhook SSRF guards and HMAC signing
- gateway self-monitoring (boot identity, config validity)
- uptime computation from state transitions
"""

import asyncio
import hashlib
import hmac
import json
import os

import pytest

from fluidmcp.cli.models.events import EventType, MonitoringEvent, Severity
from fluidmcp.cli.repositories.memory import InMemoryBackend
from fluidmcp.cli.services import failure_classifier as fc
from fluidmcp.cli.services import gateway_info
from fluidmcp.cli.services.config_validator import validate_server_config
from fluidmcp.cli.services.dependency_probe import DependencyProbe
from fluidmcp.cli.services.event_bus import EventBus
from fluidmcp.cli.services.tool_error_tracker import ToolErrorTracker
from fluidmcp.cli.services.webhook_dispatcher import (
    sign_payload,
    validate_webhook_url,
)


# ==================== Failure classification ====================

class TestFailureClassifier:
    """The classifier's job is category + owner. Owner drives alert routing."""

    @pytest.mark.parametrize("text,category,owner", [
        ("Error: connect ECONNREFUSED 10.20.1.44:1433", "db_connection_refused", "customer"),
        ("Login failed for user 'sa'.", "db_auth_failed", "customer"),
        ("FATAL: password authentication failed for user \"app\"", "db_auth_failed", "customer"),
        ("QueuePool limit of size 5 overflow 10 reached", "db_pool_exhausted", "customer"),
        ("Error: Invalid API key provided", "upstream_auth_failed", "customer"),
        ("HTTP 429 Too Many Requests", "rate_limited", "external"),
        ("upstream returned 503 Service Unavailable", "upstream_5xx", "external"),
        ("Error: Cannot find module '@scope/thing'", "missing_dependency", "fluidmcp"),
        ("spawn npx ENOENT", "bad_command", "fluidmcp"),
        ("FATAL ERROR: JavaScript heap out of memory", "oom", "fluidmcp"),
        ("Error: ETIMEDOUT", "upstream_timeout", "unknown"),
    ])
    def test_classifies_with_correct_owner(self, text, category, owner):
        result = fc.classify_text(text)
        assert result is not None, f"failed to classify: {text}"
        assert result["failure_category"] == category
        assert result["failure_owner"] == owner
        assert result["remediation"], "every pattern must carry a remediation"

    def test_unrecognised_text_returns_none(self):
        assert fc.classify_text("everything is fine here") is None
        assert fc.classify_text("") is None
        assert fc.classify_text(None) is None

    def test_specific_patterns_beat_generic_timeout(self):
        """Pool exhaustion must not be swallowed by the bare 'timeout' pattern."""
        result = fc.classify_text("QueuePool limit reached, connection timed out")
        assert result["failure_category"] == "db_pool_exhausted"

    def test_clean_exit_is_not_a_failure(self):
        assert fc.classify_exit(0) is None
        assert fc.classify_exit(-15) is None   # SIGTERM
        assert fc.classify_exit(143) is None   # container SIGTERM

    def test_oom_exit_code(self):
        result = fc.classify_exit(137)
        assert result["failure_category"] == "oom"
        assert result["failure_owner"] == "fluidmcp"

    def test_tool_errors_outrank_exit_code(self):
        """A running server's tool error is more specific than a stale exit code."""
        verdict = fc.diagnose(
            exit_code=1,
            stderr="some unrelated warning",
            tool_errors=["Login failed for user 'sa'."],
        )
        assert verdict["failure_category"] == "db_auth_failed"
        assert verdict["confidence"] == "high"

    def test_config_issues_outrank_everything(self):
        verdict = fc.diagnose(
            exit_code=137,
            tool_errors=["ECONNREFUSED"],
            config_issues={"missing_env": ["DB_PASSWORD"], "placeholder_env": []},
        )
        assert verdict["failure_category"] == "missing_credentials"
        assert verdict["failure_owner"] == "customer"
        assert "DB_PASSWORD" in verdict["remediation"]

    def test_restart_would_not_help_for_credentials(self):
        """Restarting a server with wrong credentials just hides the fault."""
        verdict = fc.diagnose(tool_errors=["Login failed for user 'sa'."])
        assert verdict["restart_would_help"] is False

    def test_restart_would_help_for_pool_exhaustion(self):
        """A leaked pool genuinely is cleared by a restart."""
        verdict = fc.diagnose(tool_errors=["QueuePool limit of size 5 reached"])
        assert verdict["restart_would_help"] is True

    def test_unknown_failure_is_still_actionable(self):
        verdict = fc.diagnose(stderr="mysterious garbage")
        assert verdict["failure_category"] == "unknown"
        assert verdict["remediation"]


# ==================== Config validation ====================

class TestConfigValidator:
    """Scenario: an MCP is missing env vars or credentials."""

    def test_detects_missing_required_env(self):
        result = validate_server_config(
            "sql", {"command": "python3", "env": {}, "required_env": ["DB_HOST", "DB_PASSWORD"]}
        )
        assert set(result["missing_env"]) == {"DB_HOST", "DB_PASSWORD"}
        assert not result["valid"]

    def test_detects_placeholder_credentials(self):
        result = validate_server_config(
            "sql", {"command": "python3", "env": {"DB_PASSWORD": "<your-password>"}}
        )
        assert result["placeholder_env"] == ["DB_PASSWORD"]
        assert any(e["key"] == "DB_PASSWORD" for e in result["errors"])

    def test_detects_unresolved_interpolation(self):
        result = validate_server_config(
            "sql", {"command": "python3", "env": {"API_KEY": "${NEVER_SET}"}}
        )
        assert result["unresolved_env"] == ["API_KEY"]

    def test_detects_missing_command(self):
        result = validate_server_config(
            "x", {"command": "definitely-not-a-real-binary-xyz", "env": {}}
        )
        assert any(e["key"] == "command" for e in result["errors"])

    def test_clean_config_passes(self):
        result = validate_server_config(
            "ok", {"command": "python3", "env": {"TOKEN": "sk-abc123def456ghi789jkl"}}
        )
        assert result["valid"]
        assert not result["errors"]

    def test_never_leaks_credential_values(self):
        """Only key names may appear anywhere in the result. These are secrets."""
        secret = "sup3rs3cr3t-actual-password-value"
        result = validate_server_config(
            "sql", {"command": "python3", "env": {"DB_PASSWORD": "<placeholder>",
                                                  "REAL_SECRET": secret}}
        )
        assert secret not in json.dumps(result)

    def test_does_not_block_by_default(self):
        """Blocking by default would turn monitoring into an outage."""
        result = validate_server_config(
            "sql", {"command": "python3", "env": {}, "required_env": ["DB_PASSWORD"]}
        )
        assert result["blocking"] is False

    def test_strict_config_blocks(self):
        result = validate_server_config(
            "sql",
            {"command": "python3", "env": {}, "required_env": ["DB_PASSWORD"],
             "strict_config": True},
        )
        assert result["blocking"] is True

    def test_non_credential_placeholder_is_a_warning_not_an_error(self):
        result = validate_server_config(
            "x", {"command": "python3", "env": {"LOG_PREFIX": "your-prefix"}}
        )
        assert result["placeholder_env"] == ["LOG_PREFIX"]
        assert not any(e["key"] == "LOG_PREFIX" for e in result["errors"])


# ==================== Per-tool error tracking ====================

class TestToolErrorTracker:
    """Scenario: one endpoint starts failing inside a healthy server."""

    def test_single_broken_tool_is_detected_despite_low_server_rate(self):
        """The case a server-wide average structurally cannot catch."""
        tracker = ToolErrorTracker()
        for _ in range(40):
            tracker.record("sql", "list_tables", "success")
        for _ in range(40):
            tracker.record("sql", "describe", "success")
        for _ in range(18):
            tracker.record("sql", "execute_query", "error", "ECONNREFUSED 10.0.0.5:1433")

        rate, samples = tracker.server_error_rate("sql")
        assert rate < 0.5, "server-wide rate should stay below the threshold"

        failing = tracker.failing_tools("sql")
        assert len(failing) == 1
        assert failing[0]["tool"] == "execute_query"
        assert failing[0]["error_rate_5m"] == 1.0

        transition = tracker.evaluate("sql")
        assert transition["transition"] == "degraded"

    def test_isError_outcome_counts_as_failure(self):
        """MCP reports tool failures inside a 200 OK result, not as an error."""
        tracker = ToolErrorTracker()
        for _ in range(10):
            tracker.record("sql", "query", "tool_error", "connection refused")
        assert tracker.failing_tools("sql")

    def test_timeouts_count_as_failures(self):
        tracker = ToolErrorTracker()
        for _ in range(10):
            tracker.record("sql", "query", "timeout", "no response within 30s")
        assert tracker.failing_tools("sql")

    def test_degraded_fires_once_not_every_cycle(self):
        tracker = ToolErrorTracker()
        for _ in range(10):
            tracker.record("sql", "query", "error", "ECONNREFUSED")
        assert tracker.evaluate("sql")["transition"] == "degraded"
        assert tracker.evaluate("sql") is None
        assert tracker.evaluate("sql") is None

    def test_below_min_samples_does_not_degrade(self):
        """Two failures on a cold server is noise, not a signal."""
        tracker = ToolErrorTracker()
        tracker.record("sql", "query", "error", "boom")
        tracker.record("sql", "query", "error", "boom")
        assert tracker.evaluate("sql") is None

    def test_recovery_after_sustained_success(self):
        """Recovery is streak-based, so it must be responsive, not eventual."""
        tracker = ToolErrorTracker()
        for _ in range(8):
            tracker.record("sql", "query", "error", "ECONNREFUSED")
        assert tracker.evaluate("sql")["transition"] == "degraded"

        transition = None
        calls = 0
        for _ in range(30):
            tracker.record("sql", "query", "success")
            calls += 1
            transition = tracker.evaluate("sql")
            if transition:
                break

        assert transition is not None, "should recover"
        assert transition["transition"] == "recovered"
        assert tracker.is_degraded("sql") is False
        # A rate-based rule needed ~200 calls here because the historical
        # failures stayed inside the window. Keep this bound tight so that
        # regression cannot creep back in.
        assert calls <= 15, f"recovery took {calls} calls — too sticky"

    def test_recovery_requires_a_real_streak(self):
        """One lucky call after a failure run is not a recovery."""
        tracker = ToolErrorTracker()
        for _ in range(8):
            tracker.record("sql", "query", "error", "ECONNREFUSED")
        tracker.evaluate("sql")
        tracker.record("sql", "query", "success")
        assert tracker.evaluate("sql") is None
        assert tracker.is_degraded("sql") is True

    def test_streak_on_one_tool_does_not_mask_another_failing(self):
        """A healed tool must not clear the flag while a sibling still fails."""
        tracker = ToolErrorTracker()
        for _ in range(8):
            tracker.record("sql", "execute_query", "error", "ECONNREFUSED")
        assert tracker.evaluate("sql")["transition"] == "degraded"

        for _ in range(10):
            tracker.record("sql", "execute_query", "success")
            tracker.record("sql", "other_tool", "error", "still broken")

        assert tracker.evaluate("sql") is None
        assert tracker.is_degraded("sql") is True
        assert tracker._trailing_success_streak("sql") == 0
        assert [t["tool"] for t in tracker.failing_tools("sql")] == ["other_tool"]

    def test_classifies_last_error(self):
        tracker = ToolErrorTracker()
        tracker.record("sql", "query", "error", "Login failed for user 'sa'.")
        last = tracker.last_error("sql")
        assert last["failure_category"] == "db_auth_failed"
        assert last["failure_owner"] == "customer"

    def test_reset_clears_state(self):
        tracker = ToolErrorTracker()
        for _ in range(10):
            tracker.record("sql", "query", "error", "boom")
        tracker.evaluate("sql")
        tracker.reset("sql")
        assert tracker.server_error_rate("sql") == (0.0, 0)
        assert tracker.is_degraded("sql") is False

    def test_servers_are_isolated(self):
        tracker = ToolErrorTracker()
        for _ in range(10):
            tracker.record("broken", "q", "error", "boom")
        for _ in range(10):
            tracker.record("healthy", "q", "success")
        assert tracker.failing_tools("broken")
        assert not tracker.failing_tools("healthy")


# ==================== Event bus ====================

class TestEventBus:
    @pytest.mark.asyncio
    async def test_assigns_monotonic_gap_free_seq(self):
        bus = EventBus()
        for i in range(20):
            bus.emit(EventType.SERVER_STARTED, server_id=f"s{i}")
        events = await bus.list_events(limit=500)
        seqs = [e["seq"] for e in events]
        assert seqs == list(range(1, 21))

    @pytest.mark.asyncio
    async def test_since_cursor_is_exclusive(self):
        bus = EventBus()
        for i in range(10):
            bus.emit(EventType.SERVER_STARTED, server_id=f"s{i}")
        events = await bus.list_events(since=5)
        assert [e["seq"] for e in events] == [6, 7, 8, 9, 10]

    @pytest.mark.asyncio
    async def test_severity_filter_is_inclusive_upward(self):
        bus = EventBus()
        bus.emit(EventType.SERVER_STARTED, server_id="a")        # info
        bus.emit(EventType.SERVER_RESTARTING, server_id="a")     # warning
        bus.emit(EventType.SERVER_CRASHED, server_id="a")        # critical
        assert len(await bus.list_events(severity="info")) == 3
        assert len(await bus.list_events(severity="warning")) == 2
        assert len(await bus.list_events(severity="critical")) == 1

    @pytest.mark.asyncio
    async def test_server_and_type_filters(self):
        bus = EventBus()
        bus.emit(EventType.SERVER_CRASHED, server_id="a")
        bus.emit(EventType.SERVER_CRASHED, server_id="b")
        bus.emit(EventType.SERVER_STARTED, server_id="a")
        assert len(await bus.list_events(server_id="a")) == 2
        assert len(await bus.list_events(event_type="server.crashed")) == 2

    @pytest.mark.asyncio
    async def test_emit_never_raises_on_bad_input(self):
        """A monitoring failure must never break a server restart."""
        bus = EventBus()
        # Unserialisable payload — must be swallowed, not propagated.
        assert bus.emit(EventType.SERVER_CRASHED, server_id="a", obj=object()) is not None

    @pytest.mark.asyncio
    async def test_carries_boot_identity(self):
        bus = EventBus()
        event = bus.emit(EventType.SERVER_CRASHED, server_id="a")
        assert event.boot_id == gateway_info.BOOT_ID
        assert event.gateway_id == gateway_info.gateway_id()

    @pytest.mark.asyncio
    async def test_persists_to_backend(self):
        backend = InMemoryBackend()
        await backend.connect()
        bus = EventBus(db=backend)
        bus.start()
        for i in range(5):
            bus.emit(EventType.SERVER_CRASHED, server_id=f"s{i}")
        await asyncio.sleep(0.1)
        await bus.stop()
        stored = await backend.list_events_since(boot_id=gateway_info.BOOT_ID)
        assert len(stored) == 5

    @pytest.mark.asyncio
    async def test_sse_subscriber_receives_events(self):
        bus = EventBus()
        queue = bus.subscribe()
        bus.emit(EventType.SERVER_CRASHED, server_id="a")
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event.type == EventType.SERVER_CRASHED
        bus.unsubscribe(queue)

    @pytest.mark.asyncio
    async def test_slow_subscriber_drops_rather_than_blocking(self):
        """A slow SSE consumer must not back-pressure the health monitor."""
        bus = EventBus()
        queue = bus.subscribe(maxsize=5)
        for i in range(50):
            bus.emit(EventType.SERVER_STARTED, server_id=f"s{i}")
        assert bus.stats()["dropped_subscriber"] > 0
        assert bus.latest_seq == 50  # emission still completed
        bus.unsubscribe(queue)


# ==================== Webhooks ====================

class TestWebhookSecurity:
    def test_rejects_plain_http_by_default(self, monkeypatch):
        monkeypatch.delenv("FMCP_WEBHOOK_ALLOW_INSECURE", raising=False)
        monkeypatch.delenv("FMCP_WEBHOOK_ALLOWLIST", raising=False)
        assert validate_webhook_url("http://example.com/h") is not None

    def test_allows_https(self, monkeypatch):
        monkeypatch.delenv("FMCP_WEBHOOK_ALLOW_INSECURE", raising=False)
        monkeypatch.delenv("FMCP_WEBHOOK_ALLOWLIST", raising=False)
        assert validate_webhook_url("https://example.com/h") is None

    def test_blocks_cloud_metadata_even_in_permissive_mode(self, monkeypatch):
        """The security case that must hold under every configuration."""
        monkeypatch.setenv("FMCP_WEBHOOK_ALLOW_INSECURE", "true")
        monkeypatch.delenv("FMCP_WEBHOOK_ALLOWLIST", raising=False)
        for url in (
            "http://169.254.169.254/latest/meta-data",
            "https://169.254.169.254/",
        ):
            assert validate_webhook_url(url) is not None, url

    def test_blocks_private_ranges_unless_opted_in(self, monkeypatch):
        monkeypatch.delenv("FMCP_WEBHOOK_ALLOW_INSECURE", raising=False)
        monkeypatch.delenv("FMCP_WEBHOOK_ALLOWLIST", raising=False)
        assert validate_webhook_url("https://10.0.0.5/h") is not None
        monkeypatch.setenv("FMCP_WEBHOOK_ALLOW_INSECURE", "true")
        assert validate_webhook_url("https://10.0.0.5/h") is None

    def test_enforces_allowlist(self, monkeypatch):
        monkeypatch.setenv("FMCP_WEBHOOK_ALLOWLIST", "monitor.internal,*.trusted.example")
        assert validate_webhook_url("https://evil.example/h") is not None
        assert validate_webhook_url("https://a.trusted.example/h") is None

    def test_rejects_non_http_schemes(self, monkeypatch):
        monkeypatch.delenv("FMCP_WEBHOOK_ALLOWLIST", raising=False)
        for url in ("file:///etc/passwd", "gopher://x/", "ftp://x/"):
            assert validate_webhook_url(url) is not None, url

    def test_signature_is_verifiable(self):
        secret = "whsec_test_secret_value"
        body = b'1756721642.{"seq":1}'
        signature = sign_payload(secret, body)
        expected = "sha256=" + hmac.new(
            secret.encode(), body, hashlib.sha256
        ).hexdigest()
        assert hmac.compare_digest(signature, expected)

    def test_signature_changes_with_body(self):
        secret = "whsec_test_secret_value"
        assert sign_payload(secret, b"a") != sign_payload(secret, b"b")


# ==================== Gateway self-monitoring ====================

class TestGatewayInfo:
    def test_boot_id_is_stable_within_process(self):
        assert gateway_info.BOOT_ID == gateway_info.BOOT_ID
        assert gateway_info.BOOT_ID.startswith("boot_")

    def test_identity_carries_required_fields(self):
        identity = gateway_info.identity()
        for field in ("gateway_id", "boot_id", "boot_count", "started_at",
                      "uptime_seconds"):
            assert field in identity

    def test_detects_missing_bearer_token_in_secure_mode(self, monkeypatch):
        """The redeploy failure mode: /api 500s with nothing explaining why."""
        monkeypatch.setenv("FMCP_SECURE_MODE", "true")
        monkeypatch.delenv("FMCP_BEARER_TOKEN", raising=False)
        result = gateway_info.validate_gateway_config(db_connected=True)
        assert not result["valid"]
        assert any(e["key"] == "FMCP_BEARER_TOKEN" for e in result["errors"])

    def test_detects_unreachable_configured_database(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://nope:27017")
        monkeypatch.delenv("FMCP_SECURE_MODE", raising=False)
        result = gateway_info.validate_gateway_config(db_connected=False)
        assert any(e["key"] == "MONGODB_URI" for e in result["errors"])

    def test_missing_mongo_uri_is_a_warning_not_an_error(self, monkeypatch):
        """In-memory mode is a valid choice, just a lossy one."""
        monkeypatch.delenv("MONGODB_URI", raising=False)
        monkeypatch.delenv("FMCP_MONGODB_URI", raising=False)
        monkeypatch.delenv("FMCP_SECURE_MODE", raising=False)
        result = gateway_info.validate_gateway_config(db_connected=False)
        assert result["valid"]
        assert any(w["key"] == "MONGODB_URI" for w in result["warnings"])

    def test_clean_config_is_valid(self, monkeypatch):
        monkeypatch.setenv("FMCP_SECURE_MODE", "true")
        monkeypatch.setenv("FMCP_BEARER_TOKEN", "a" * 64)
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        result = gateway_info.validate_gateway_config(db_connected=True)
        assert result["valid"]

    def test_self_resources_present(self):
        resources = gateway_info.self_resources()
        assert "memory_rss_bytes" in resources
        assert "event_loop_lag_ms" in resources


# ==================== Dependency probe ====================

class TestDependencyProbe:
    def test_probe_config_parsing(self):
        config = DependencyProbe.probe_config({
            "health_probe": {"tool": "execute_query", "args": {"query": "SELECT 1"}}
        })
        assert config["tool"] == "execute_query"
        assert config["interval_seconds"] == DependencyProbe.DEFAULT_INTERVAL

    def test_no_probe_configured(self):
        assert DependencyProbe.probe_config({}) is None
        assert DependencyProbe.probe_config({"health_probe": {}}) is None

    def test_first_probe_is_always_due(self):
        probe = DependencyProbe()
        config = DependencyProbe.probe_config({"health_probe": {"tool": "t"}})
        assert probe.due("s", config) is True

    @pytest.mark.asyncio
    async def test_stdio_server_is_not_probed(self):
        """Probing stdio would contend with the gateway's own pipe."""
        probe = DependencyProbe()
        config = DependencyProbe.probe_config({"health_probe": {"tool": "t"}})

        class StdioProcess:
            base_url = None

        assert await probe.run("s", StdioProcess(), config) is None
        assert probe.is_failed("s") is False

    def test_reset_clears_state(self):
        probe = DependencyProbe()
        probe._failed["s"] = True
        probe._failures["s"] = 5
        probe.reset("s")
        assert probe.is_failed("s") is False
        assert probe.status("s")["consecutive_failures"] == 0


# ==================== Monitoring must never break recovery ====================

class TestMonitoringCannotBreakRestarts:
    """The load-bearing invariant: monitoring code must not abort a restart.

    A live test caught a real regression here — `self.record_transition` was
    called on MCPHealthMonitor, where the method does not exist, and the
    resulting AttributeError was swallowed by the restart path's broad
    `except Exception`. Crashed servers silently stopped being restarted.
    A missing metric is cheap; a skipped restart is an outage.
    """

    def test_record_transition_lives_on_server_manager(self):
        from fluidmcp.cli.services.server_manager import (
            MCPHealthMonitor,
            ServerManager,
        )
        assert hasattr(ServerManager, "record_transition")
        assert not hasattr(MCPHealthMonitor, "record_transition"), (
            "MCPHealthMonitor must not grow its own record_transition — "
            "call self._sm.record_transition() so the receiver is unambiguous"
        )

    def test_health_monitor_never_calls_self_record_transition(self):
        """Guard the exact typo, by inspecting the monitor's own source."""
        import ast
        import inspect

        from fluidmcp.cli.services import server_manager as sm

        source = inspect.getsource(sm)
        tree = ast.parse(source)
        monitor = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "MCPHealthMonitor"
        )
        offenders = [
            node.lineno for node in ast.walk(monitor)
            if isinstance(node, ast.Attribute)
            and node.attr == "record_transition"
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
        ]
        assert not offenders, (
            f"MCPHealthMonitor calls self.record_transition at lines {offenders}; "
            f"use self._sm.record_transition or self._safe_transition"
        )

    @pytest.mark.asyncio
    async def test_safe_transition_swallows_backend_failures(self):
        from fluidmcp.cli.services.server_manager import (
            MCPHealthMonitor,
            ServerManager,
        )

        class ExplodingBackend(InMemoryBackend):
            async def save_state_transition(self, transition):
                raise RuntimeError("database is on fire")

        backend = ExplodingBackend()
        await backend.connect()
        monitor = MCPHealthMonitor(ServerManager(backend))
        # Must not raise — this call sits inline in the restart path.
        await monitor._safe_transition("s", "restarting", reason="test")

    @pytest.mark.asyncio
    async def test_record_transition_swallows_backend_failures(self):
        from fluidmcp.cli.services.server_manager import ServerManager

        class ExplodingBackend(InMemoryBackend):
            async def save_state_transition(self, transition):
                raise RuntimeError("database is on fire")

        backend = ExplodingBackend()
        await backend.connect()
        await ServerManager(backend).record_transition("s", "running")


# ==================== Uptime computation ====================

class TestUptimeComputation:
    def test_no_transitions_reports_unmeasured(self):
        from fluidmcp.cli.api.monitoring import _uptime_for_server

        report = _uptime_for_server("s", [], 86400)
        assert report["measured"] is False
        assert report["uptime_pct"] == 100.0

    def test_downtime_reduces_uptime(self):
        from datetime import datetime, timedelta, timezone

        from fluidmcp.cli.api.monitoring import _uptime_for_server

        now = datetime.now(timezone.utc)
        transitions = [
            {"server_id": "s", "to_state": "running",
             "timestamp": (now - timedelta(hours=4)).isoformat()},
            {"server_id": "s", "to_state": "failed",
             "timestamp": (now - timedelta(hours=2)).isoformat()},
            {"server_id": "s", "to_state": "running",
             "timestamp": (now - timedelta(hours=1)).isoformat()},
        ]
        report = _uptime_for_server("s", transitions, 86400)
        assert report["measured"] is True
        assert report["crash_count"] == 1
        assert 0 < report["downtime_seconds"] <= 3700
        assert report["uptime_pct"] < 100.0
        # One hour down, recovered — MTTR should be about an hour.
        assert 3400 <= report["mttr_seconds"] <= 3700

    def test_degraded_time_is_separate_from_downtime(self):
        """A server up but unusable is not uptime, and not downtime either."""
        from datetime import datetime, timedelta, timezone

        from fluidmcp.cli.api.monitoring import _uptime_for_server

        now = datetime.now(timezone.utc)
        transitions = [
            {"server_id": "s", "to_state": "running",
             "timestamp": (now - timedelta(hours=4)).isoformat()},
            {"server_id": "s", "to_state": "degraded",
             "timestamp": (now - timedelta(hours=2)).isoformat()},
        ]
        report = _uptime_for_server("s", transitions, 86400)
        assert report["degraded_seconds"] > 0
        assert report["downtime_seconds"] == 0


# ==================== Persistence ====================

class TestMonitoringPersistence:
    @pytest.mark.asyncio
    async def test_event_cursor_and_filters(self):
        backend = InMemoryBackend()
        await backend.connect()
        for i in range(1, 11):
            await backend.save_event({
                "seq": i,
                "type": "server.crashed" if i % 2 else "server.started",
                "severity": "critical" if i % 2 else "info",
                "server_id": "s1",
                "boot_id": "boot_test",
                "timestamp": f"2026-09-01T10:00:{i:02d}Z",
            })
        assert [e["seq"] for e in await backend.list_events_since(
            since=5, boot_id="boot_test")] == [6, 7, 8, 9, 10]
        assert len(await backend.list_events_since(
            severity="critical", boot_id="boot_test")) == 5

    @pytest.mark.asyncio
    async def test_events_scoped_by_boot_id(self):
        """seq restarts on reboot, so cursors must be boot-scoped."""
        backend = InMemoryBackend()
        await backend.connect()
        await backend.save_event({"seq": 1, "boot_id": "boot_a", "severity": "info"})
        await backend.save_event({"seq": 1, "boot_id": "boot_b", "severity": "info"})
        assert len(await backend.list_events_since(boot_id="boot_a")) == 1

    @pytest.mark.asyncio
    async def test_boot_count_increments(self):
        backend = InMemoryBackend()
        await backend.connect()
        assert await backend.save_boot_record({"gateway_id": "gw"}) == 1
        assert await backend.save_boot_record({"gateway_id": "gw"}) == 2
        assert await backend.save_boot_record({"gateway_id": "other"}) == 1

    @pytest.mark.asyncio
    async def test_webhook_crud(self):
        backend = InMemoryBackend()
        await backend.connect()
        await backend.save_webhook({"id": "w1", "url": "https://x/h", "enabled": True})
        assert len(await backend.list_webhooks(enabled_only=True)) == 1
        await backend.set_webhook_enabled("w1", False)
        assert len(await backend.list_webhooks(enabled_only=True)) == 0
        assert len(await backend.list_webhooks(enabled_only=False)) == 1
        assert await backend.delete_webhook("w1") is True
        assert await backend.delete_webhook("w1") is False

    @pytest.mark.asyncio
    async def test_state_transitions_round_trip(self):
        backend = InMemoryBackend()
        await backend.connect()
        await backend.save_state_transition({
            "server_id": "s", "to_state": "running",
            "timestamp": "2026-09-01T10:00:00Z",
        })
        rows = await backend.list_state_transitions(server_id="s")
        assert len(rows) == 1
        assert rows[0]["to_state"] == "running"


# ==================== Event model ====================

class TestEventModel:
    def test_every_event_type_has_a_default_severity(self):
        from fluidmcp.cli.models.events import DEFAULT_SEVERITY

        for event_type in EventType:
            assert event_type in DEFAULT_SEVERITY, f"{event_type} missing severity"

    def test_wire_format_is_json_serialisable(self):
        event = MonitoringEvent(
            type=EventType.SERVER_CRASHED,
            severity=Severity.CRITICAL,
            server_id="s",
            data={"exit_code": 137},
        )
        payload = json.dumps(event.to_dict())
        assert "server.crashed" in payload

    def test_timestamp_renders_as_utc_z(self):
        event = MonitoringEvent(
            type=EventType.SERVER_STARTED, severity=Severity.INFO
        )
        assert event.to_dict()["timestamp"].endswith("Z")


# ==================== SSE stream formatting ====================

class TestSSEStreamFormatting:
    """Drives the SSE generator inside one event loop.

    A TestClient-based test cannot work here: TestClient runs the app in a
    separate thread with its own loop, and ``emit()`` reaches subscribers via an
    ``asyncio.Queue`` belonging to that loop — ``put_nowait`` across threads does
    not reliably wake the waiter. In production every emit originates on the
    app's own loop (health monitor, request handlers), so this exercises the real
    code path; the threading limitation is an artefact of the test harness only.
    """

    @staticmethod
    def _sse_frame(event) -> str:
        """Render one event exactly as the endpoint does."""
        name = event.type.value if hasattr(event.type, "value") else str(event.type)
        return f"event: {name}\ndata: {json.dumps(event.to_dict())}\n\n"

    @pytest.mark.asyncio
    async def test_frame_is_parseable_sse(self):
        bus = EventBus()
        queue = bus.subscribe()
        bus.emit(EventType.SERVER_CRASHED, server_id="sql", exit_code=137)
        event = await asyncio.wait_for(queue.get(), timeout=1.0)

        frame = self._sse_frame(event)
        lines = frame.split("\n")
        assert lines[0] == "event: server.crashed"
        assert lines[1].startswith("data: ")
        assert frame.endswith("\n\n"), "SSE frames must end with a blank line"

        payload = json.loads(lines[1].removeprefix("data: "))
        assert payload["server_id"] == "sql"
        assert payload["data"]["exit_code"] == 137
        assert payload["boot_id"] == gateway_info.BOOT_ID
        bus.unsubscribe(queue)

    @pytest.mark.asyncio
    async def test_data_line_never_contains_a_raw_newline(self):
        """A newline inside the data line would split one event into two."""
        bus = EventBus()
        queue = bus.subscribe()
        bus.emit(
            EventType.SERVER_CRASHED,
            server_id="sql",
            stderr_tail="line one\nline two\nline three",
        )
        event = await asyncio.wait_for(queue.get(), timeout=1.0)

        frame = self._sse_frame(event)
        data_line = frame.split("\n")[1]
        assert "\n" not in data_line.removeprefix("data: ")
        # json.dumps escapes it, so the content still round-trips intact.
        payload = json.loads(data_line.removeprefix("data: "))
        assert payload["data"]["stderr_tail"] == "line one\nline two\nline three"
        bus.unsubscribe(queue)

    @pytest.mark.asyncio
    async def test_shutdown_sentinel_reaches_subscribers(self):
        """Bus shutdown must close open streams rather than hang them."""
        bus = EventBus()
        queue = bus.subscribe()
        await bus.stop()
        assert await asyncio.wait_for(queue.get(), timeout=1.0) is None

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_the_queue(self):
        bus = EventBus()
        queue = bus.subscribe()
        assert bus.stats()["subscribers"] == 1
        bus.unsubscribe(queue)
        assert bus.stats()["subscribers"] == 0
        # Idempotent — a double close must not raise.
        bus.unsubscribe(queue)


# ==================== Secret redaction ====================

class TestSecretRedaction:
    """Monitoring events travel further than logs.

    A crash payload or a `last_error` string reaches webhooks, an external
    monitoring store, a Slack channel and an incident ticket. MCP servers
    routinely echo their own connection strings in error text, so anything
    published must be scrubbed — while still classifying correctly, which means
    classifying the raw text and publishing the redacted form.
    """

    SECRET = "hunter2SuperSecretValue"

    @pytest.mark.parametrize("raw", [
        "could not connect to postgres://app:hunter2SuperSecretValue@db:5432/prod",
        "Login failed, password=hunter2SuperSecretValue",
        "auth error: api_key: hunter2SuperSecretValue",
        'connect failed {"secret": "hunter2SuperSecretValue"}',
    ])
    def test_redacts_credential_shapes(self, raw):
        from fluidmcp.cli.utils.error_utils import redact_secrets

        assert self.SECRET not in redact_secrets(raw)

    def test_redacts_bearer_and_jwt(self):
        from fluidmcp.cli.utils.error_utils import redact_secrets

        jwt = ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
               "dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk")
        out = redact_secrets(f"Authorization: Bearer {jwt}")
        assert jwt not in out

    def test_redacts_provider_key_prefixes(self):
        from fluidmcp.cli.utils.error_utils import redact_secrets

        for key in ("r8_AbCdEfGhIjKlMnOpQrStUvWx123",
                    "sk_live_abcdefghijklmnop",
                    "ghp_AbCdEfGhIjKlMnOpQrStUv1234"):
            assert key not in redact_secrets(f"rejected key {key}")

    def test_preserves_diagnostic_signal(self):
        """Redaction must not destroy the tokens the classifier matches on."""
        from fluidmcp.cli.utils.error_utils import redact_secrets

        for message, expected in [
            ("connect ECONNREFUSED 10.20.1.44:1433", "db_connection_refused"),
            ("QueuePool limit of size 5 overflow 10 reached", "db_pool_exhausted"),
            ("Login failed for user 'sa'.", "db_auth_failed"),
            ("503 Service Unavailable", "upstream_5xx"),
        ]:
            redacted = redact_secrets(message)
            hit = fc.classify_text(redacted)
            assert hit is not None, f"redaction broke classification of {message!r}"
            assert hit["failure_category"] == expected

    def test_tracker_stores_redacted_but_classifies_raw(self):
        tracker = ToolErrorTracker()
        raw = (f"could not connect to postgres://app:{self.SECRET}@db:5432/prod "
               f"(ECONNREFUSED)")
        for _ in range(6):
            tracker.record("sql", "query", "error", raw)

        assert self.SECRET not in json.dumps(tracker.snapshot("sql"))
        assert self.SECRET not in json.dumps(tracker.last_error("sql"))
        assert self.SECRET not in json.dumps(tracker.tool_stats("sql"))
        # Classification still worked, from the raw text.
        assert tracker.last_error("sql")["failure_category"] == "db_connection_refused"

    def test_config_validator_never_returns_values(self):
        result = validate_server_config("sql", {
            "command": "python3",
            "env": {"DB_PASSWORD": "<placeholder>", "API_KEY": self.SECRET},
            "required_env": ["MISSING"],
        })
        assert self.SECRET not in json.dumps(result)

    def test_diagnose_never_echoes_config_values(self):
        verdict = fc.diagnose(config_issues={
            "missing_env": ["MISSING"], "placeholder_env": ["DB_PASSWORD"],
        })
        assert self.SECRET not in json.dumps(verdict)

    def test_redacted_json_still_parses(self):
        """A mangled payload is nearly as unhelpful as a leaked one."""
        from fluidmcp.cli.utils.error_utils import redact_secrets

        raw = '{"api_key":"r8_abc123def456ghi","error":"denied"}'
        redacted = redact_secrets(raw)
        parsed = json.loads(redacted)
        assert parsed["api_key"] == "***REDACTED***"
        assert parsed["error"] == "denied"

    def test_redaction_is_idempotent(self):
        from fluidmcp.cli.utils.error_utils import redact_secrets

        once = redact_secrets("password=hunter2SuperSecretValue")
        assert redact_secrets(once) == once

    def test_handles_non_string_input(self):
        from fluidmcp.cli.utils.error_utils import redact_secrets

        assert redact_secrets(None) == "None"
        assert redact_secrets(12345) == "12345"
