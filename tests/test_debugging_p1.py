"""
Tests for P1 debugging features:
- classify_exit_code()
- Crash event enrichment (server_name, exit_category/label/description, resource snapshot)
- MCPHealthMonitor resource snapshot caching and memory trend
"""
import pytest
import asyncio
import subprocess
from collections import deque
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from fluidmcp.cli.services.server_manager import (
    ServerManager,
    MCPHealthMonitor,
    classify_exit_code,
)
from fluidmcp.cli.repositories import InMemoryBackend


# ---------------------------------------------------------------------------
# classify_exit_code
# ---------------------------------------------------------------------------

class TestClassifyExitCode:

    def test_known_codes(self):
        cases = [
            (0,    "clean",    "clean_exit"),
            (1,    "error",    "generic_error"),
            (126,  "config",   "permission_denied"),
            (127,  "config",   "command_not_found"),
            (137,  "resource", "oom_killed"),
            (139,  "crash",    "segfault"),
            (143,  "shutdown", "sigterm_container"),
            (255,  "error",    "unknown_fatal"),
            (-1,   "resource", "killed_by_fluidmcp"),
            (-9,   "resource", "sigkill"),
            (-15,  "shutdown", "sigterm"),
        ]
        for code, expected_category, expected_label in cases:
            result = classify_exit_code(code)
            assert result["category"] == expected_category, f"code={code}"
            assert result["label"] == expected_label, f"code={code}"
            assert isinstance(result["description"], str)
            assert len(result["description"]) > 0

    def test_unknown_code_returns_error_category(self):
        result = classify_exit_code(42)
        assert result["category"] == "error"
        assert result["label"] == "unknown"
        assert "42" in result["description"]

    def test_returns_dict_with_required_keys(self):
        result = classify_exit_code(0)
        assert set(result.keys()) == {"category", "label", "description"}


# ---------------------------------------------------------------------------
# Crash event enrichment in _cleanup_server
# ---------------------------------------------------------------------------

@pytest.fixture
def backend():
    return InMemoryBackend()

@pytest.fixture
def server_manager(backend):
    return ServerManager(backend)


class TestCrashEventEnrichment:

    @pytest.mark.asyncio
    async def test_crash_event_includes_exit_classification(self, server_manager):
        """Crash event must include exit_category, exit_label, exit_description."""
        saved_events = []

        async def capture_crash_event(event):
            saved_events.append(event)
            return True

        server_manager.db.save_crash_event = capture_crash_event
        server_manager.db.save_instance_state = AsyncMock()

        await server_manager._cleanup_server("my-server", exit_code=127, intentional=False)

        assert len(saved_events) == 1
        event = saved_events[0]
        assert event["exit_category"] == "config"
        assert event["exit_label"] == "command_not_found"
        assert isinstance(event["exit_description"], str)

    @pytest.mark.asyncio
    async def test_crash_event_includes_server_name(self, server_manager):
        """Crash event must include server_name from config."""
        saved_events = []

        async def capture_crash_event(event):
            saved_events.append(event)
            return True

        server_manager.db.save_crash_event = capture_crash_event
        server_manager.db.save_instance_state = AsyncMock()
        server_manager.configs["my-server"] = {"name": "My Filesystem Server"}

        await server_manager._cleanup_server("my-server", exit_code=1, intentional=False)

        assert saved_events[0]["server_name"] == "My Filesystem Server"

    @pytest.mark.asyncio
    async def test_crash_event_falls_back_to_id_when_no_name(self, server_manager):
        """server_name falls back to server_id when config has no name field."""
        saved_events = []

        async def capture_crash_event(event):
            saved_events.append(event)
            return True

        server_manager.db.save_crash_event = capture_crash_event
        server_manager.db.save_instance_state = AsyncMock()

        await server_manager._cleanup_server("no-name-server", exit_code=1, intentional=False)

        assert saved_events[0]["server_name"] == "no-name-server"

    @pytest.mark.asyncio
    async def test_crash_event_includes_resource_snapshot(self, server_manager):
        """Crash event includes memory/cpu/active_requests when health monitor snapshot exists."""
        saved_events = []

        async def capture_crash_event(event):
            saved_events.append(event)
            return True

        server_manager.db.save_crash_event = capture_crash_event
        server_manager.db.save_instance_state = AsyncMock()

        # Simulate health monitor with a cached snapshot
        mock_monitor = Mock()
        mock_monitor._last_resource_snapshot = {
            "my-server": {
                "memory_rss_bytes": 104857600,
                "cpu_percent": 45.2,
                "active_requests": 3,
            }
        }
        server_manager._health_monitor = mock_monitor

        await server_manager._cleanup_server("my-server", exit_code=137, intentional=False)

        event = saved_events[0]
        assert event["memory_bytes_at_crash"] == 104857600
        assert event["cpu_percent_at_crash"] == 45.2
        assert event["active_requests_at_crash"] == 3

    @pytest.mark.asyncio
    async def test_intentional_stop_does_not_save_crash_event(self, server_manager):
        """Intentional stops must not create crash events."""
        saved_events = []

        async def capture_crash_event(event):
            saved_events.append(event)

        server_manager.db.save_crash_event = capture_crash_event
        server_manager.db.save_instance_state = AsyncMock()

        await server_manager._cleanup_server("my-server", exit_code=0, intentional=True)

        assert len(saved_events) == 0

    @pytest.mark.asyncio
    async def test_clean_exit_does_not_save_crash_event(self, server_manager):
        """exit_code=0 non-intentional stop also must not create crash event."""
        saved_events = []

        async def capture_crash_event(event):
            saved_events.append(event)

        server_manager.db.save_crash_event = capture_crash_event
        server_manager.db.save_instance_state = AsyncMock()

        await server_manager._cleanup_server("my-server", exit_code=0, intentional=False)

        assert len(saved_events) == 0


# ---------------------------------------------------------------------------
# MCPHealthMonitor resource snapshot caching
# ---------------------------------------------------------------------------

class TestResourceSnapshotCache:

    def _make_monitor(self, server_manager):
        return MCPHealthMonitor(server_manager, check_interval=30)

    def test_initial_snapshot_cache_is_empty(self, server_manager):
        monitor = self._make_monitor(server_manager)
        assert monitor._last_resource_snapshot == {}

    def test_update_resource_snapshot_skips_without_psutil(self, server_manager):
        monitor = self._make_monitor(server_manager)
        mock_process = Mock()
        mock_process.pid = 9999

        with patch("fluidmcp.cli.services.server_manager._psutil_available", False):
            monitor._update_resource_snapshot("srv", mock_process)

        assert "srv" not in monitor._last_resource_snapshot

    def test_update_resource_snapshot_warms_up_cpu_on_first_call(self, server_manager):
        """First call should warm up cpu_percent and NOT store a snapshot."""
        monitor = self._make_monitor(server_manager)
        mock_process = Mock()
        mock_process.pid = 1234

        mock_proc = Mock()
        mock_proc.cpu_percent = Mock(return_value=0.0)
        mock_proc.memory_info = Mock(return_value=Mock(rss=1024))

        with patch("fluidmcp.cli.services.server_manager._psutil_available", True), \
             patch("psutil.Process", return_value=mock_proc):
            monitor._update_resource_snapshot("srv", mock_process)

        # Warm-up: no snapshot stored yet
        assert "srv" not in monitor._last_resource_snapshot
        assert 1234 in monitor._cpu_warmed_pids

    def test_update_resource_snapshot_stores_on_second_call(self, server_manager):
        """After warm-up, second call should store a real snapshot."""
        monitor = self._make_monitor(server_manager)
        mock_process = Mock()
        mock_process.pid = 1234
        monitor._cpu_warmed_pids.add(1234)  # simulate already warmed

        mock_proc = Mock()
        mock_proc.cpu_percent = Mock(return_value=23.4)
        mock_proc.memory_info = Mock(return_value=Mock(rss=52428800))

        with patch("fluidmcp.cli.services.server_manager._psutil_available", True), \
             patch("psutil.Process", return_value=mock_proc):
            monitor._update_resource_snapshot("srv", mock_process)

        snapshot = monitor._last_resource_snapshot["srv"]
        assert snapshot["memory_rss_bytes"] == 52428800
        assert snapshot["cpu_percent"] == 23.4

    def test_update_resource_snapshot_handles_no_such_process(self, server_manager):
        """NoSuchProcess must not raise — process may die mid-check."""
        import psutil
        monitor = self._make_monitor(server_manager)
        mock_process = Mock()
        mock_process.pid = 1234
        monitor._cpu_warmed_pids.add(1234)

        with patch("fluidmcp.cli.services.server_manager._psutil_available", True), \
             patch("psutil.Process", side_effect=psutil.NoSuchProcess(pid=1234)):
            monitor._update_resource_snapshot("srv", mock_process)  # must not raise


# ---------------------------------------------------------------------------
# Memory trend
# ---------------------------------------------------------------------------

class TestMemoryTrend:

    def _make_monitor(self, server_manager):
        return MCPHealthMonitor(server_manager, check_interval=30)

    def test_unknown_when_no_history(self, server_manager):
        monitor = self._make_monitor(server_manager)
        assert monitor.get_memory_trend("srv") == "unknown"

    def test_unknown_when_only_one_sample(self, server_manager):
        monitor = self._make_monitor(server_manager)
        monitor._memory_history["srv"] = deque([100], maxlen=3)
        assert monitor.get_memory_trend("srv") == "unknown"

    def test_increasing(self, server_manager):
        monitor = self._make_monitor(server_manager)
        monitor._memory_history["srv"] = deque([100, 200, 300], maxlen=3)
        assert monitor.get_memory_trend("srv") == "increasing"

    def test_decreasing(self, server_manager):
        monitor = self._make_monitor(server_manager)
        monitor._memory_history["srv"] = deque([300, 200, 100], maxlen=3)
        assert monitor.get_memory_trend("srv") == "decreasing"

    def test_stable(self, server_manager):
        monitor = self._make_monitor(server_manager)
        monitor._memory_history["srv"] = deque([200, 200, 200], maxlen=3)
        assert monitor.get_memory_trend("srv") == "stable"

    def test_fluctuating(self, server_manager):
        monitor = self._make_monitor(server_manager)
        monitor._memory_history["srv"] = deque([100, 300, 200], maxlen=3)
        assert monitor.get_memory_trend("srv") == "fluctuating"

    def test_two_samples_increasing(self, server_manager):
        monitor = self._make_monitor(server_manager)
        monitor._memory_history["srv"] = deque([100, 200], maxlen=3)
        assert monitor.get_memory_trend("srv") == "increasing"
