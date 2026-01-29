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

import math
import pytest
import time
import threading
from fluidmcp.cli.services.metrics import (
    Counter,
    Gauge,
    Histogram,
    MetricsCollector,
    MetricsRegistry,
    RequestTimer,
    ToolTimer,
)


class TestMetricsRegistry:
    """Unit tests for MetricsRegistry class."""

    def test_register_metric(self):
        """Test registering a metric."""
        registry = MetricsRegistry()
        counter = Counter("test_counter", "Test counter")

        registry.register(counter)

        # Verify metric was registered
        retrieved = registry.get_metric("test_counter")
        assert retrieved is counter

    def test_register_duplicate_metric_logs_warning(self):
        """Test registering duplicate metric logs warning."""
        registry = MetricsRegistry()
        counter1 = Counter("duplicate_metric", "First counter")
        counter2 = Counter("duplicate_metric", "Second counter")

        registry.register(counter1)
        registry.register(counter2)  # Should log warning

        # Second metric should replace first
        retrieved = registry.get_metric("duplicate_metric")
        assert retrieved is counter2

    def test_get_nonexistent_metric(self):
        """Test getting non-existent metric returns None."""
        registry = MetricsRegistry()

        result = registry.get_metric("nonexistent")

        assert result is None

    def test_render_all_metrics(self):
        """Test rendering all metrics in Prometheus format."""
        registry = MetricsRegistry()

        counter = Counter("test_counter", "Test counter")
        counter.inc()
        registry.register(counter)

        gauge = Gauge("test_gauge", "Test gauge")
        gauge.set(42.0)
        registry.register(gauge)

        output = registry.render_all()

        # Should contain both metrics
        assert "test_counter" in output
        assert "test_gauge" in output
        assert "# HELP test_counter Test counter" in output
        assert "# HELP test_gauge Test gauge" in output

    def test_render_all_empty_registry(self):
        """Test rendering empty registry."""
        registry = MetricsRegistry()

        output = registry.render_all()

        # Should return empty string or minimal output
        assert isinstance(output, str)


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

    def test_histogram_rejects_nan_value(self):
        """Test histogram rejects NaN values."""
        histogram = Histogram("test_histogram", "Test description", buckets=[1.0, 5.0])

        # Observe NaN - should be rejected (silently ignored)
        histogram.observe(math.nan)

        # Histogram should be empty (no observations recorded)
        assert len(histogram.histograms) == 0

    def test_histogram_rejects_inf_value(self):
        """Test histogram rejects infinite values."""
        histogram = Histogram("test_histogram", "Test description", buckets=[1.0, 5.0])

        # Observe +Inf and -Inf - both should be rejected
        histogram.observe(math.inf)
        histogram.observe(-math.inf)

        # Histogram should be empty (no observations recorded)
        assert len(histogram.histograms) == 0

    def test_histogram_rejects_negative_value(self):
        """Test histogram rejects negative values."""
        histogram = Histogram("test_histogram", "Test description", buckets=[1.0, 5.0])

        # Observe negative value - should be rejected
        histogram.observe(-1.5)

        # Histogram should be empty (no observations recorded)
        assert len(histogram.histograms) == 0

    def test_histogram_rejects_invalid_type(self):
        """Test histogram rejects invalid data types."""
        histogram = Histogram("test_histogram", "Test description", buckets=[1.0, 5.0])

        # Observe string value - should be rejected
        histogram.observe("invalid")

        # Histogram should be empty (no observations recorded)
        assert len(histogram.histograms) == 0

    def test_histogram_accepts_integer_values(self):
        """Test histogram accepts integer values and converts them to float."""
        histogram = Histogram("test_histogram", "Test description", buckets=[1.0, 5.0, 10.0])

        # Observe integer values - should be accepted and converted to float
        histogram.observe(3)
        histogram.observe(7)

        # Histogram should have recorded the observations
        assert len(histogram.histograms) == 1
        hist_data = histogram.histograms[()]
        assert hist_data["count"] == 2
        assert hist_data["sum"] == 10.0  # 3 + 7 = 10

    def test_histogram_value_exceeds_all_buckets(self):
        """Test histogram handles values exceeding all buckets."""
        histogram = Histogram("test_histogram", "Test description", buckets=[1.0, 5.0, 10.0])

        # Observe value exceeding all buckets
        histogram.observe(100.0)

        # Should increment count and sum, but no specific bucket
        key = ()
        assert histogram.histograms[key]["count"] == 1
        assert histogram.histograms[key]["sum"] == 100.0

        # Render should show value in +Inf bucket
        output = histogram.render()
        assert 'le="+Inf"} 1' in output

    def test_histogram_invalid_buckets_raises_error(self):
        """Test histogram raises error for invalid bucket values."""
        # Test negative bucket
        with pytest.raises(ValueError, match="positive finite numbers"):
            Histogram("test", "desc", buckets=[1.0, -5.0, 10.0])

        # Test NaN bucket
        with pytest.raises(ValueError, match="positive finite numbers"):
            Histogram("test", "desc", buckets=[1.0, math.nan, 10.0])

        # Test Inf bucket
        with pytest.raises(ValueError, match="positive finite numbers"):
            Histogram("test", "desc", buckets=[1.0, math.inf, 10.0])

        # Test non-numeric bucket
        with pytest.raises(ValueError, match="positive finite numbers"):
            Histogram("test", "desc", buckets=[1.0, "invalid", 10.0])


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

    def test_set_server_uptime(self):
        """Test setting server uptime."""
        collector = MetricsCollector(server_id="test_server_uptime")
        collector.set_uptime(uptime_seconds=3600.5)

        uptime = collector.registry.get_metric("fluidmcp_server_uptime_seconds")
        output = uptime.render()
        assert 'server_id="test_server_uptime"' in output
        assert "3600.5" in output

    def test_set_gpu_memory(self):
        """Test setting GPU memory usage."""
        collector = MetricsCollector(server_id="test_server_gpu")
        collector.set_gpu_memory(gpu_index=0, memory_bytes=4294967296.0)  # 4GB

        gpu_mem = collector.registry.get_metric("fluidmcp_gpu_memory_bytes")
        output = gpu_mem.render()
        assert 'server_id="test_server_gpu"' in output
        assert 'gpu_index="0"' in output
        assert "4294967296.0" in output

    def test_set_gpu_utilization(self):
        """Test setting GPU utilization."""
        collector = MetricsCollector(server_id="test_server_gpu_util")
        collector.set_gpu_utilization(utilization=0.75)

        gpu_util = collector.registry.get_metric("fluidmcp_gpu_memory_utilization_ratio")
        output = gpu_util.render()
        assert 'server_id="test_server_gpu_util"' in output
        assert "0.75" in output

    def test_record_tool_call(self):
        """Test recording tool calls."""
        collector = MetricsCollector(server_id="test_server_tool")
        collector.record_tool_call(tool_name="read_file", status="success", duration=0.123)

        # Check tool call counter
        tool_calls = collector.registry.get_metric("fluidmcp_tool_calls_total")
        output = tool_calls.render()
        assert 'server_id="test_server_tool"' in output
        assert 'tool_name="read_file"' in output
        assert 'status="success"' in output

        # Check tool duration histogram
        tool_duration = collector.registry.get_metric("fluidmcp_tool_execution_seconds")
        output = tool_duration.render()
        assert 'server_id="test_server_tool"' in output
        assert 'tool_name="read_file"' in output

    def test_record_streaming_request(self):
        """Test recording streaming requests."""
        collector = MetricsCollector(server_id="test_server_stream")
        collector.record_streaming_request(completion_status="completed")

        streaming = collector.registry.get_metric("fluidmcp_streaming_requests_total")
        output = streaming.render()
        assert 'server_id="test_server_stream"' in output
        assert 'completion_status="completed"' in output

    def test_increment_active_streams(self):
        """Test incrementing active streams."""
        collector = MetricsCollector(server_id="test_server_active_stream")
        collector.increment_active_streams()

        streams = collector.registry.get_metric("fluidmcp_active_streams")
        output = streams.render()
        assert 'server_id="test_server_active_stream"' in output

    def test_decrement_active_streams(self):
        """Test decrementing active streams."""
        collector = MetricsCollector(server_id="test_server_dec_stream")
        collector.increment_active_streams()
        collector.increment_active_streams()
        collector.decrement_active_streams()

        streams = collector.registry.get_metric("fluidmcp_active_streams")
        assert streams.samples[("test_server_dec_stream",)] == 1.0


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
        """Test counter with labels handles concurrent increments from multiple threads."""
        counter = Counter("test", "desc", labels=["thread_id"])
        num_threads = 10
        increments = 100

        def worker(thread_id):
            for _ in range(increments):
                counter.inc({"thread_id": str(thread_id)})

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Each thread should have its own labeled counter with the correct count
        assert len(counter.samples) == num_threads
        for value in counter.samples.values():
            assert value == increments
        # And the total across all labels should equal num_threads * increments
        assert sum(counter.samples.values()) == num_threads * increments

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
