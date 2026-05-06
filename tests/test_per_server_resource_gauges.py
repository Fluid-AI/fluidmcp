"""
Tests for P7 - per-server Prometheus resource gauges.

Covers:
- fluidmcp_server_memory_rss_bytes updated after snapshot cycle
- fluidmcp_server_cpu_percent updated after snapshot cycle
- fluidmcp_server_open_fds updated after snapshot cycle
- Gauges not set on warm-up cycle (first call)
- Gauges not set when psutil unavailable
- MetricsCollector helpers write to correct label keys
- Multiple servers tracked independently
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

from fluidmcp.cli.services.server_manager import ServerManager, MCPHealthMonitor
from fluidmcp.cli.services.metrics import get_registry, MetricsCollector
from fluidmcp.cli.repositories import InMemoryBackend


@pytest.fixture
def backend():
    return InMemoryBackend()


@pytest.fixture
def server_manager(backend):
    return ServerManager(backend)


@pytest.fixture
def monitor(server_manager):
    return MCPHealthMonitor(server_manager, check_interval=30)


def _make_process(pid=1234):
    p = Mock()
    p.pid = pid
    p.poll = Mock(return_value=None)
    return p


def _make_psutil_proc(rss=50 * 1024 * 1024, cpu=12.5, fds=20):
    proc = Mock()
    proc.memory_info = Mock(return_value=Mock(rss=rss))
    proc.cpu_percent = Mock(return_value=cpu)
    proc.num_fds = Mock(return_value=fds)
    proc.num_threads = Mock(return_value=4)
    return proc


def _get_gauge(name, server_id):
    registry = get_registry()
    gauge = registry.get_metric(name)
    if gauge is None:
        return None
    key = gauge._get_label_key({"server_id": server_id})
    return gauge.samples.get(key)


# ---------------------------------------------------------------------------
# MetricsCollector helpers
# ---------------------------------------------------------------------------

class TestMetricsCollectorHelpers:

    def test_set_server_memory_rss(self):
        collector = MetricsCollector("test_srv_rss")
        collector.set_server_memory_rss(104857600)
        assert _get_gauge("fluidmcp_server_memory_rss_bytes", "test_srv_rss") == 104857600

    def test_set_server_cpu_percent(self):
        collector = MetricsCollector("test_srv_cpu")
        collector.set_server_cpu_percent(23.4)
        assert _get_gauge("fluidmcp_server_cpu_percent", "test_srv_cpu") == 23.4

    def test_set_server_open_fds(self):
        collector = MetricsCollector("test_srv_fds")
        collector.set_server_open_fds(42)
        assert _get_gauge("fluidmcp_server_open_fds", "test_srv_fds") == 42

    def test_multiple_servers_tracked_independently(self):
        MetricsCollector("alpha").set_server_memory_rss(10 * 1024 * 1024)
        MetricsCollector("beta").set_server_memory_rss(20 * 1024 * 1024)
        assert _get_gauge("fluidmcp_server_memory_rss_bytes", "alpha") == 10 * 1024 * 1024
        assert _get_gauge("fluidmcp_server_memory_rss_bytes", "beta") == 20 * 1024 * 1024


# ---------------------------------------------------------------------------
# _update_resource_snapshot emits gauges
# ---------------------------------------------------------------------------

class TestSnapshotEmitsGauges:

    def test_gauges_set_after_warm_up(self, monitor):
        process = _make_process(pid=9901)
        psutil_proc = _make_psutil_proc(rss=67108864, cpu=5.0, fds=15)

        with patch("psutil.Process", return_value=psutil_proc):
            # First call: warm-up, no gauges yet
            monitor._update_resource_snapshot("srv_gauge", process)
            assert _get_gauge("fluidmcp_server_memory_rss_bytes", "srv_gauge") is None

            # Second call: real reading, gauges emitted
            monitor._update_resource_snapshot("srv_gauge", process)

        assert _get_gauge("fluidmcp_server_memory_rss_bytes", "srv_gauge") == 67108864
        assert _get_gauge("fluidmcp_server_cpu_percent", "srv_gauge") == 5.0
        assert _get_gauge("fluidmcp_server_open_fds", "srv_gauge") == 15

    def test_snapshot_also_cached(self, monitor):
        process = _make_process(pid=9902)
        psutil_proc = _make_psutil_proc(rss=33554432, cpu=1.5, fds=8)

        with patch("psutil.Process", return_value=psutil_proc):
            monitor._update_resource_snapshot("srv_cache", process)
            monitor._update_resource_snapshot("srv_cache", process)

        snapshot = monitor._last_resource_snapshot.get("srv_cache")
        assert snapshot is not None
        assert snapshot["memory_rss_bytes"] == 33554432
        assert snapshot["cpu_percent"] == 1.5
        assert snapshot["open_fds"] == 8

    def test_no_gauge_on_no_such_process(self, monitor):
        process = _make_process(pid=9903)
        import psutil
        with patch("psutil.Process", side_effect=psutil.NoSuchProcess(pid=9903)):
            monitor._update_resource_snapshot("srv_dead", process)

        assert _get_gauge("fluidmcp_server_memory_rss_bytes", "srv_dead") is None

    def test_gauges_registered_in_registry(self):
        registry = get_registry()
        assert registry.get_metric("fluidmcp_server_memory_rss_bytes") is not None
        assert registry.get_metric("fluidmcp_server_cpu_percent") is not None
        assert registry.get_metric("fluidmcp_server_open_fds") is not None
