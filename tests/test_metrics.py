"""
Automated unit tests for metrics collection system.

This replaces the manual tests in tests/manual/test_metrics.py with
automated unit tests suitable for CI/CD pipelines.

Tests cover:
- Counter, Gauge, Histogram metric classes
- MetricsCollector methods
- RequestTimer and ToolTimer context managers
- Thread safety under concurrent access
"""

import pytest
import time
import threading
from fluidmcp.cli.services.metrics import (
    Counter,
    Gauge,
    Histogram,
    MetricsCollector,
    RequestTimer,
    ToolTimer,
)


class TestCounter:
    """Unit tests for Counter metric class."""

    def test_counter_init(self):
        """Test counter initialization."""
        counter = Counter("test_counter", "Test description")
        assert counter.name == "test_counter"
        assert counter.description == "Test description"
        assert counter.labels == []
        assert counter.samples == {}

    def test_counter_init_with_labels(self):
        """Test counter initialization with labels."""
        counter = Counter("test_counter", "Test description", labels=["method", "status"])
        assert counter.labels == ["method", "status"]

    def test_counter_increment_no_labels(self):
        """Test counter increment without labels."""
        counter = Counter("test_counter", "Test description")
        counter.inc()
        assert counter.samples[()] == 1.0

    def test_counter_increment_with_amount(self):
        """Test counter increment with custom amount."""
        counter = Counter("test_counter", "Test description")
        counter.inc(amount=5.0)
        assert counter.samples[()] == 5.0

    def test_counter_increment_with_labels(self):
        """Test counter increment with labels."""
        counter = Counter("test_counter", "Test description", labels=["method", "status"])
        counter.inc(label_values={"method": "GET", "status": "200"})
        assert counter.samples[("GET", "200")] == 1.0

    def test_counter_multiple_increments(self):
        """Test counter handles multiple increments correctly."""
        counter = Counter("test_counter", "Test description")
        counter.inc()
        counter.inc()
        counter.inc()
        assert counter.samples[()] == 3.0

    def test_counter_negative_increment_raises_error(self):
        """Test counter raises error on negative increment."""
        counter = Counter("test_counter", "Test description")
        with pytest.raises(ValueError, match="Counter can only increase"):
            counter.inc(amount=-1.0)

    def test_counter_render_without_labels(self):
        """Test counter rendering in Prometheus format without labels."""
        counter = Counter("test_counter", "Test description")
        counter.inc()
        counter.inc()

        output = counter.render()
        assert "# HELP test_counter Test description" in output
        assert "# TYPE test_counter counter" in output
        assert "test_counter 2.0" in output

    def test_counter_render_with_labels(self):
        """Test counter rendering with labels."""
        counter = Counter("test_counter", "Test description", labels=["method"])
        counter.inc(label_values={"method": "GET"})
        counter.inc(label_values={"method": "POST"})

        output = counter.render()
        assert "# HELP test_counter Test description" in output
        assert "# TYPE test_counter counter" in output
        assert 'test_counter{method="GET"} 1.0' in output
        assert 'test_counter{method="POST"} 1.0' in output

    def test_counter_thread_safety(self):
        """Test counter is thread-safe under concurrent access."""
        counter = Counter("test_counter", "Test description")
        num_threads = 10
        increments_per_thread = 100

        def increment():
            for _ in range(increments_per_thread):
                counter.inc()

        threads = [threading.Thread(target=increment) for _ in range(num_threads)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        expected_total = num_threads * increments_per_thread
        assert counter.samples[()] == expected_total


class TestGauge:
    """Unit tests for Gauge metric class."""

    def test_gauge_init(self):
        """Test gauge initialization."""
        gauge = Gauge("test_gauge", "Test description")
        assert gauge.name == "test_gauge"
        assert gauge.description == "Test description"
        assert gauge.samples == {}

    def test_gauge_set_value(self):
        """Test gauge set method."""
        gauge = Gauge("test_gauge", "Test description")
        gauge.set(42.5)
        assert gauge.samples[()] == 42.5

    def test_gauge_set_overwrites_previous_value(self):
        """Test gauge set overwrites previous value."""
        gauge = Gauge("test_gauge", "Test description")
        gauge.set(10.0)
        gauge.set(20.0)
        assert gauge.samples[()] == 20.0

    def test_gauge_increment(self):
        """Test gauge increment method."""
        gauge = Gauge("test_gauge", "Test description")
        gauge.set(10.0)
        gauge.inc(amount=5.0)
        assert gauge.samples[()] == 15.0

    def test_gauge_decrement(self):
        """Test gauge decrement method."""
        gauge = Gauge("test_gauge", "Test description")
        gauge.set(10.0)
        gauge.dec(amount=3.0)
        assert gauge.samples[()] == 7.0

    def test_gauge_can_go_negative(self):
        """Test gauge can have negative values."""
        gauge = Gauge("test_gauge", "Test description")
        gauge.set(5.0)
        gauge.dec(amount=10.0)
        assert gauge.samples[()] == -5.0

    def test_gauge_with_labels(self):
        """Test gauge with labels."""
        gauge = Gauge("test_gauge", "Test description", labels=["host"])
        gauge.set(100.0, label_values={"host": "server1"})
        gauge.set(200.0, label_values={"host": "server2"})

        assert gauge.samples[("server1",)] == 100.0
        assert gauge.samples[("server2",)] == 200.0

    def test_gauge_render_format(self):
        """Test gauge rendering in Prometheus format."""
        gauge = Gauge("test_gauge", "Test description")
        gauge.set(42.0)

        output = gauge.render()
        assert "# HELP test_gauge Test description" in output
        assert "# TYPE test_gauge gauge" in output
        assert "test_gauge 42.0" in output

    def test_gauge_thread_safety_set(self):
        """Test gauge is thread-safe for set operations."""
        gauge = Gauge("test_gauge", "Test description")
        num_threads = 10

        def set_value(value):
            gauge.set(value)

        threads = [threading.Thread(target=set_value, args=(i,)) for i in range(num_threads)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Final value should be one of the set values (0-9)
        assert 0 <= gauge.samples[()] < num_threads


class TestHistogram:
    """Unit tests for Histogram metric class."""

    def test_histogram_init(self):
        """Test histogram initialization."""
        histogram = Histogram("test_histogram", "Test description")
        assert histogram.name == "test_histogram"
        assert histogram.description == "Test description"
        assert len(histogram.buckets) > 0

    def test_histogram_init_with_custom_buckets(self):
        """Test histogram with custom buckets."""
        buckets = [0.1, 0.5, 1.0, 5.0]
        histogram = Histogram("test_histogram", "Test description", buckets=buckets)
        assert histogram.buckets == buckets

    def test_histogram_observe_single_value(self):
        """Test histogram observe method."""
        histogram = Histogram("test_histogram", "Test description", buckets=[0.1, 1.0, 10.0])
        histogram.observe(0.5)

        # Value 0.5 should fall into bucket 1.0 (first bucket >= 0.5)
        key = ()
        assert histogram.histograms[key]["buckets"][1.0] == 1
        assert histogram.histograms[key]["sum"] == 0.5
        assert histogram.histograms[key]["count"] == 1

    def test_histogram_observe_multiple_values(self):
        """Test histogram with multiple observations."""
        histogram = Histogram("test_histogram", "Test description", buckets=[1.0, 5.0, 10.0])
        histogram.observe(0.5)
        histogram.observe(3.0)
        histogram.observe(7.0)

        key = ()
        assert histogram.histograms[key]["count"] == 3
        assert histogram.histograms[key]["sum"] == 10.5

    def test_histogram_observe_with_labels(self):
        """Test histogram with labels."""
        histogram = Histogram("test_histogram", "Test description",
                            buckets=[1.0, 5.0], labels=["endpoint"])
        histogram.observe(2.0, label_values={"endpoint": "/api"})
        histogram.observe(3.0, label_values={"endpoint": "/health"})

        assert histogram.histograms[("/api",)]["count"] == 1
        assert histogram.histograms[("/health",)]["count"] == 1

    def test_histogram_render_includes_buckets(self):
        """Test histogram rendering includes bucket boundaries."""
        histogram = Histogram("test_histogram", "Test description", buckets=[1.0, 5.0])
        histogram.observe(2.0)

        output = histogram.render()
        assert "# HELP test_histogram Test description" in output
        assert "# TYPE test_histogram histogram" in output
        assert '_bucket{le="1.0"}' in output
        assert '_bucket{le="5.0"}' in output
        assert '_bucket{le="+Inf"}' in output
        assert "_sum" in output
        assert "_count" in output

    def test_histogram_thread_safety(self):
        """Test histogram is thread-safe under concurrent observations."""
        histogram = Histogram("test_histogram", "Test description", buckets=[1.0, 5.0, 10.0])
        num_threads = 10
        observations_per_thread = 100

        def observe():
            for _ in range(observations_per_thread):
                histogram.observe(2.5)

        threads = [threading.Thread(target=observe) for _ in range(num_threads)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        expected_count = num_threads * observations_per_thread
        assert histogram.histograms[()]["count"] == expected_count
        assert histogram.histograms[()]["sum"] == 2.5 * expected_count


class TestMetricsCollector:
    """Unit tests for MetricsCollector class."""

    def test_collector_init(self):
        """Test metrics collector initialization."""
        collector = MetricsCollector(server_id="test_server")
        assert collector.server_id == "test_server"
        assert collector.registry is not None

    def test_record_request(self):
        """Test recording a request."""
        collector = MetricsCollector(server_id="test_server")
        collector.record_request(method="GET", status="200", duration=0.5)

        # Verify counter was incremented
        requests = collector.registry.get_metric("fluidmcp_requests_total")
        output = requests.render()
        assert 'server_id="test_server"' in output
        assert 'method="GET"' in output
        assert 'status="200"' in output

    def test_record_error(self):
        """Test recording an error."""
        collector = MetricsCollector(server_id="test_server")
        collector.record_error(error_type="ValueError")

        errors = collector.registry.get_metric("fluidmcp_errors_total")
        output = errors.render()
        assert 'error_type="ValueError"' in output
        assert 'server_id="test_server"' in output

    def test_increment_active_requests(self):
        """Test incrementing active requests."""
        collector = MetricsCollector(server_id="test_server")
        collector.increment_active_requests()

        active = collector.registry.get_metric("fluidmcp_active_requests")
        output = active.render()
        assert 'server_id="test_server"' in output
        assert "1.0" in output

    def test_decrement_active_requests(self):
        """Test decrementing active requests."""
        collector = MetricsCollector(server_id="test_server_decrement")  # Use unique server_id
        collector.increment_active_requests()
        collector.increment_active_requests()
        collector.decrement_active_requests()

        active = collector.registry.get_metric("fluidmcp_active_requests")
        assert active.samples[("test_server_decrement",)] == 1.0

    def test_set_server_status(self):
        """Test setting server status."""
        collector = MetricsCollector(server_id="test_server")
        collector.set_server_status(status_code=2)  # running

        status = collector.registry.get_metric("fluidmcp_server_status")
        assert status.samples[("test_server",)] == 2.0

    def test_record_restart(self):
        """Test recording server restart."""
        collector = MetricsCollector(server_id="test_server")
        collector.record_restart(reason="crash")

        restarts = collector.registry.get_metric("fluidmcp_server_restarts_total")
        output = restarts.render()
        assert 'server_id="test_server"' in output
        assert 'reason="crash"' in output


class TestRequestTimer:
    """Unit tests for RequestTimer context manager."""

    def test_request_timer_records_duration(self):
        """Test RequestTimer records request duration."""
        collector = MetricsCollector(server_id="test_server")

        with RequestTimer(collector, method="GET"):
            time.sleep(0.05)

        # Verify duration was recorded
        duration_hist = collector.registry.get_metric("fluidmcp_request_duration_seconds")
        output = duration_hist.render()
        assert 'server_id="test_server"' in output
        assert 'method="GET"' in output

    def test_request_timer_increments_active_requests(self):
        """Test RequestTimer increments/decrements active requests."""
        collector = MetricsCollector(server_id="test_server_timer1")  # Use unique server_id
        active = collector.registry.get_metric("fluidmcp_active_requests")

        # Check initial state
        initial_count = active.samples.get(("test_server_timer1",), 0)

        with RequestTimer(collector, method="GET"):
            # Active requests should be incremented during execution
            assert active.samples[("test_server_timer1",)] == initial_count + 1

        # Active requests should be decremented after completion
        assert active.samples.get(("test_server_timer1",), 0) == initial_count

    def test_request_timer_handles_exception(self):
        """Test RequestTimer properly cleans up on exception."""
        collector = MetricsCollector(server_id="test_server_timer2")  # Use unique server_id
        active = collector.registry.get_metric("fluidmcp_active_requests")

        # Get initial count for this specific server_id
        initial_count = active.samples.get(("test_server_timer2",), 0)

        try:
            with RequestTimer(collector, method="GET"):
                raise ValueError("Test error")
        except ValueError:
            pass

        # Active requests should be back to initial count (decremented properly)
        assert active.samples.get(("test_server_timer2",), 0) == initial_count

        # Error should be recorded
        errors = collector.registry.get_metric("fluidmcp_errors_total")
        output = errors.render()
        assert 'error_type="client_error"' in output  # ValueError categorized as client_error

    def test_request_timer_categorizes_broken_pipe_error(self):
        """Test RequestTimer categorizes BrokenPipeError as io_error."""
        collector = MetricsCollector(server_id="test_server_pipe")

        try:
            with RequestTimer(collector, method="POST"):
                raise BrokenPipeError("Connection broken")
        except BrokenPipeError:
            pass

        # Error should be categorized as io_error
        errors = collector.registry.get_metric("fluidmcp_errors_total")
        output = errors.render()
        assert 'error_type="io_error"' in output

    def test_request_timer_categorizes_timeout_error(self):
        """Test RequestTimer categorizes TimeoutError as network_error."""
        collector = MetricsCollector(server_id="test_server_timeout")

        try:
            with RequestTimer(collector, method="GET"):
                raise TimeoutError("Request timeout")
        except TimeoutError:
            pass

        # Error should be categorized as network_error
        errors = collector.registry.get_metric("fluidmcp_errors_total")
        output = errors.render()
        assert 'error_type="network_error"' in output

    def test_request_timer_categorizes_connection_error(self):
        """Test RequestTimer categorizes ConnectionError as network_error."""
        collector = MetricsCollector(server_id="test_server_conn")

        try:
            with RequestTimer(collector, method="GET"):
                raise ConnectionError("Connection failed")
        except ConnectionError:
            pass

        # Error should be categorized as network_error
        errors = collector.registry.get_metric("fluidmcp_errors_total")
        output = errors.render()
        assert 'error_type="network_error"' in output

    def test_request_timer_categorizes_permission_error(self):
        """Test RequestTimer categorizes PermissionError as auth_error."""
        collector = MetricsCollector(server_id="test_server_perm")

        try:
            with RequestTimer(collector, method="GET"):
                raise PermissionError("Permission denied")
        except PermissionError:
            pass

        # Error should be categorized as auth_error
        errors = collector.registry.get_metric("fluidmcp_errors_total")
        output = errors.render()
        assert 'error_type="auth_error"' in output

    def test_request_timer_categorizes_type_error(self):
        """Test RequestTimer categorizes TypeError as client_error."""
        collector = MetricsCollector(server_id="test_server_type")

        try:
            with RequestTimer(collector, method="GET"):
                raise TypeError("Type mismatch")
        except TypeError:
            pass

        # Error should be categorized as client_error
        errors = collector.registry.get_metric("fluidmcp_errors_total")
        output = errors.render()
        assert 'error_type="client_error"' in output


class TestToolTimer:
    """Unit tests for ToolTimer context manager."""

    def test_tool_timer_records_execution(self):
        """Test ToolTimer records tool execution."""
        collector = MetricsCollector(server_id="test_server")

        with ToolTimer(collector, tool_name="test_tool"):
            time.sleep(0.05)

        # Verify tool call was recorded
        tool_calls = collector.registry.get_metric("fluidmcp_tool_calls_total")
        output = tool_calls.render()
        assert 'tool_name="test_tool"' in output
        assert 'server_id="test_server"' in output
        assert 'status="success"' in output

    def test_tool_timer_handles_exception(self):
        """Test ToolTimer records even on exception."""
        collector = MetricsCollector(server_id="test_server")

        try:
            with ToolTimer(collector, tool_name="test_tool"):
                raise ValueError("Test error")
        except ValueError:
            pass

        # Verify tool call was recorded with error status
        tool_calls = collector.registry.get_metric("fluidmcp_tool_calls_total")
        output = tool_calls.render()
        assert 'tool_name="test_tool"' in output
        assert 'server_id="test_server"' in output
        assert 'status="error"' in output


class TestThreadSafety:
    """Thread safety tests for metrics under concurrent access."""

    def test_concurrent_counter_increments(self):
        """Test counter handles concurrent increments from multiple threads."""
        counter = Counter("test", "desc")
        num_threads = 10
        increments = 100

        def worker():
            for _ in range(increments):
                counter.inc()

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert counter.samples[()] == num_threads * increments

    def test_concurrent_histogram_observations(self):
        """Test histogram handles concurrent observations."""
        histogram = Histogram("test", "desc", buckets=[1.0, 5.0, 10.0])
        num_threads = 10
        observations = 100

        def worker():
            for i in range(observations):
                histogram.observe(i % 10)

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert histogram.histograms[()]["count"] == num_threads * observations

    def test_concurrent_collector_operations(self):
        """Test MetricsCollector handles concurrent operations."""
        collector = MetricsCollector(server_id="test_server")
        num_threads = 10

        def worker():
            for i in range(50):
                collector.record_request(method="GET", status="200", duration=0.1)
                collector.record_error(error_type="TestError")

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify metrics were recorded
        requests = collector.registry.get_metric("fluidmcp_requests_total")
        errors = collector.registry.get_metric("fluidmcp_errors_total")

        requests_output = requests.render()
        errors_output = errors.render()

        assert "fluidmcp_requests_total" in requests_output
        assert "fluidmcp_errors_total" in errors_output
        assert 'server_id="test_server"' in requests_output
