"""
Tests for LLM metrics collection and export.

Tests metric tracking, Prometheus export, JSON export, and thread safety.
"""

import pytest
import time
from fluidmcp.cli.services.llm_metrics import (
    LLMMetricsCollector,
    ModelMetrics,
    get_metrics_collector,
    reset_metrics_collector
)


@pytest.fixture(autouse=True)
def reset_global_collector():
    """Reset global collector before each test."""
    reset_metrics_collector()
    yield
    reset_metrics_collector()


class TestModelMetrics:
    """Test ModelMetrics dataclass calculations."""

    def test_avg_latency_with_requests(self):
        """Test average latency calculation with requests."""
        metrics = ModelMetrics()
        metrics.total_requests = 3
        metrics.total_latency = 6.0

        assert metrics.avg_latency() == 2.0

    def test_avg_latency_no_requests(self):
        """Test average latency returns 0 when no requests."""
        metrics = ModelMetrics()
        assert metrics.avg_latency() == 0.0

    def test_success_rate(self):
        """Test success rate calculation."""
        metrics = ModelMetrics()
        metrics.total_requests = 10
        metrics.successful_requests = 8

        assert metrics.success_rate() == 80.0

    def test_success_rate_no_requests(self):
        """Test success rate returns 0 when no requests."""
        metrics = ModelMetrics()
        assert metrics.success_rate() == 0.0

    def test_error_rate(self):
        """Test error rate calculation."""
        metrics = ModelMetrics()
        metrics.total_requests = 10
        metrics.failed_requests = 2

        assert metrics.error_rate() == 20.0


class TestLLMMetricsCollector:
    """Test LLMMetricsCollector functionality."""

    def test_collector_initialization(self):
        """Test collector initializes correctly."""
        collector = LLMMetricsCollector()

        assert len(collector.get_all_metrics()) == 0
        assert collector._start_time <= time.time()

    def test_record_request_start_creates_metrics(self):
        """Test that recording request start creates model metrics."""
        collector = LLMMetricsCollector()

        start_time = collector.record_request_start("test-model", "replicate")

        metrics = collector.get_model_metrics("test-model")
        assert metrics is not None
        assert metrics.provider_type == "replicate"
        assert metrics.total_requests == 1
        assert start_time <= time.time()

    def test_record_request_success(self):
        """Test recording successful request."""
        collector = LLMMetricsCollector()

        start_time = collector.record_request_start("test-model", "vllm")
        time.sleep(0.01)  # Ensure some latency
        collector.record_request_success(
            "test-model",
            start_time,
            prompt_tokens=10,
            completion_tokens=50
        )

        metrics = collector.get_model_metrics("test-model")
        assert metrics.successful_requests == 1
        assert metrics.failed_requests == 0
        assert metrics.total_latency > 0
        assert metrics.min_latency > 0
        assert metrics.max_latency > 0
        assert metrics.total_prompt_tokens == 10
        assert metrics.total_completion_tokens == 50
        assert metrics.total_tokens == 60

    def test_record_request_failure(self):
        """Test recording failed request."""
        collector = LLMMetricsCollector()

        start_time = collector.record_request_start("test-model", "replicate")
        time.sleep(0.01)
        collector.record_request_failure("test-model", start_time, status_code=500)

        metrics = collector.get_model_metrics("test-model")
        assert metrics.successful_requests == 0
        assert metrics.failed_requests == 1
        assert metrics.errors_by_status[500] == 1
        assert metrics.total_latency > 0

    def test_multiple_requests_aggregate_correctly(self):
        """Test that multiple requests aggregate metrics correctly."""
        collector = LLMMetricsCollector()

        # 3 successful requests
        for i in range(3):
            start = collector.record_request_start("model-a", "vllm")
            time.sleep(0.01)
            collector.record_request_success("model-a", start, prompt_tokens=10, completion_tokens=20)

        # 2 failed requests
        for i in range(2):
            start = collector.record_request_start("model-a", "vllm")
            time.sleep(0.01)
            collector.record_request_failure("model-a", start, status_code=429)

        metrics = collector.get_model_metrics("model-a")
        assert metrics.total_requests == 5
        assert metrics.successful_requests == 3
        assert metrics.failed_requests == 2
        assert metrics.total_prompt_tokens == 30
        assert metrics.total_completion_tokens == 60
        assert metrics.errors_by_status[429] == 2

    def test_multiple_models_tracked_separately(self):
        """Test that multiple models are tracked independently."""
        collector = LLMMetricsCollector()

        # Model A
        start_a = collector.record_request_start("model-a", "replicate")
        collector.record_request_success("model-a", start_a, prompt_tokens=10)

        # Model B
        start_b = collector.record_request_start("model-b", "vllm")
        collector.record_request_failure("model-b", start_b, status_code=500)

        metrics_a = collector.get_model_metrics("model-a")
        metrics_b = collector.get_model_metrics("model-b")

        assert metrics_a.successful_requests == 1
        assert metrics_a.failed_requests == 0
        assert metrics_a.provider_type == "replicate"

        assert metrics_b.successful_requests == 0
        assert metrics_b.failed_requests == 1
        assert metrics_b.provider_type == "vllm"

    def test_get_all_metrics(self):
        """Test getting all metrics at once."""
        collector = LLMMetricsCollector()

        collector.record_request_start("model-1", "replicate")
        collector.record_request_start("model-2", "vllm")
        collector.record_request_start("model-3", "replicate")

        all_metrics = collector.get_all_metrics()
        assert len(all_metrics) == 3
        assert "model-1" in all_metrics
        assert "model-2" in all_metrics
        assert "model-3" in all_metrics

    def test_reset_specific_model(self):
        """Test resetting metrics for a specific model."""
        collector = LLMMetricsCollector()

        start = collector.record_request_start("model-a", "vllm")
        collector.record_request_success("model-a", start, prompt_tokens=10)

        start = collector.record_request_start("model-b", "replicate")
        collector.record_request_success("model-b", start, prompt_tokens=20)

        # Reset model-a
        collector.reset_metrics("model-a")

        metrics_a = collector.get_model_metrics("model-a")
        metrics_b = collector.get_model_metrics("model-b")

        assert metrics_a.total_requests == 0
        assert metrics_a.provider_type == "vllm"  # Provider type preserved
        assert metrics_b.total_requests == 1  # Model B unaffected

    def test_reset_all_metrics(self):
        """Test resetting all metrics."""
        collector = LLMMetricsCollector()

        collector.record_request_start("model-a", "vllm")
        collector.record_request_start("model-b", "replicate")

        collector.reset_metrics()  # Reset all

        assert len(collector.get_all_metrics()) == 0

    def test_export_prometheus_format(self):
        """Test Prometheus export format."""
        collector = LLMMetricsCollector()

        start = collector.record_request_start("test-model", "replicate")
        time.sleep(0.01)
        collector.record_request_success("test-model", start, prompt_tokens=10, completion_tokens=20)

        prometheus_output = collector.export_prometheus()

        # Check for required Prometheus elements
        assert "# HELP" in prometheus_output
        assert "# TYPE" in prometheus_output
        assert "fluidmcp_llm_requests_total" in prometheus_output
        assert "fluidmcp_llm_latency_seconds" in prometheus_output
        assert "fluidmcp_llm_tokens_total" in prometheus_output
        assert 'model_id="test-model"' in prometheus_output
        assert 'provider="replicate"' in prometheus_output
        assert "fluidmcp_uptime_seconds" in prometheus_output

    def test_export_prometheus_with_errors(self):
        """Test Prometheus export includes error counts."""
        collector = LLMMetricsCollector()

        start = collector.record_request_start("test-model", "vllm")
        collector.record_request_failure("test-model", start, status_code=500)

        start = collector.record_request_start("test-model", "vllm")
        collector.record_request_failure("test-model", start, status_code=429)

        prometheus_output = collector.export_prometheus()

        assert "fluidmcp_llm_errors_by_status" in prometheus_output
        assert 'status_code="500"' in prometheus_output
        assert 'status_code="429"' in prometheus_output

    def test_export_json_format(self):
        """Test JSON export format."""
        collector = LLMMetricsCollector()

        start = collector.record_request_start("test-model", "replicate")
        time.sleep(0.01)
        collector.record_request_success("test-model", start, prompt_tokens=15, completion_tokens=35)

        json_output = collector.export_json()

        assert "uptime_seconds" in json_output
        assert "models" in json_output
        assert "test-model" in json_output["models"]

        model_data = json_output["models"]["test-model"]
        assert model_data["provider_type"] == "replicate"
        assert model_data["requests"]["total"] == 1
        assert model_data["requests"]["successful"] == 1
        assert model_data["requests"]["success_rate_percent"] == 100.0
        assert model_data["tokens"]["prompt"] == 15
        assert model_data["tokens"]["completion"] == 35
        assert model_data["tokens"]["total"] == 50
        assert "latency" in model_data

    def test_export_json_multiple_models(self):
        """Test JSON export with multiple models."""
        collector = LLMMetricsCollector()

        start_a = collector.record_request_start("model-a", "vllm")
        collector.record_request_success("model-a", start_a)

        start_b = collector.record_request_start("model-b", "replicate")
        collector.record_request_failure("model-b", start_b, status_code=500)

        json_output = collector.export_json()

        assert len(json_output["models"]) == 2
        assert json_output["models"]["model-a"]["provider_type"] == "vllm"
        assert json_output["models"]["model-b"]["provider_type"] == "replicate"
        assert json_output["models"]["model-a"]["requests"]["successful"] == 1
        assert json_output["models"]["model-b"]["requests"]["failed"] == 1


class TestGlobalCollector:
    """Test global collector singleton pattern."""

    def test_get_metrics_collector_returns_singleton(self):
        """Test that get_metrics_collector returns same instance."""
        collector1 = get_metrics_collector()
        collector2 = get_metrics_collector()

        assert collector1 is collector2

    def test_reset_metrics_collector_creates_new_instance(self):
        """Test that reset creates new collector instance."""
        collector1 = get_metrics_collector()
        collector1.record_request_start("test", "vllm")

        reset_metrics_collector()

        collector2 = get_metrics_collector()
        assert collector1 is not collector2
        assert len(collector2.get_all_metrics()) == 0

    def test_concurrent_singleton_initialization(self):
        """Test that singleton initialization is thread-safe."""
        import threading

        # Reset to ensure we test initialization
        reset_metrics_collector()

        collectors = []
        barrier = threading.Barrier(10)  # Synchronize 10 threads

        def get_collector():
            # Wait for all threads to be ready
            barrier.wait()
            # All threads try to get collector simultaneously
            collector = get_metrics_collector()
            collectors.append(collector)

        # Create 10 threads that all try to initialize collector
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=get_collector)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify all threads got the same instance (singleton)
        assert len(collectors) == 10
        first_collector = collectors[0]
        for collector in collectors:
            assert collector is first_collector  # All same instance


class TestThreadSafety:
    """Test thread safety of metrics collector."""

    def test_concurrent_requests_thread_safe(self):
        """Test that concurrent requests are tracked safely."""
        import threading

        collector = LLMMetricsCollector()

        def record_requests(model_id, count):
            for _ in range(count):
                start = collector.record_request_start(model_id, "vllm")
                collector.record_request_success(model_id, start)

        threads = []
        for i in range(5):
            thread = threading.Thread(target=record_requests, args=(f"model-{i}", 10))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Verify all requests were tracked
        all_metrics = collector.get_all_metrics()
        assert len(all_metrics) == 5
        for i in range(5):
            metrics = all_metrics[f"model-{i}"]
            assert metrics.total_requests == 10
            assert metrics.successful_requests == 10

    def test_get_model_metrics_returns_isolated_copy(self):
        """Test that modifying returned metrics doesn't affect internal state."""
        collector = LLMMetricsCollector()

        # Record a request
        start = collector.record_request_start("test-model", "vllm")
        collector.record_request_failure("test-model", start, status_code=500)

        # Get metrics copy
        metrics_copy = collector.get_model_metrics("test-model")
        assert metrics_copy is not None
        assert metrics_copy.total_requests == 1
        assert metrics_copy.errors_by_status[500] == 1

        # Modify the copy's mutable field
        metrics_copy.errors_by_status[500] = 999
        metrics_copy.errors_by_status[404] = 123

        # Verify internal state is unchanged
        metrics_internal = collector.get_model_metrics("test-model")
        assert metrics_internal.errors_by_status[500] == 1  # Not 999
        assert 404 not in metrics_internal.errors_by_status  # Not added

    def test_get_all_metrics_returns_isolated_copies(self):
        """Test that modifying returned metrics dict doesn't affect internal state."""
        collector = LLMMetricsCollector()

        # Record requests for multiple models
        for i in range(3):
            start = collector.record_request_start(f"model-{i}", "vllm")
            collector.record_request_failure(f"model-{i}", start, status_code=500)

        # Get all metrics
        all_metrics = collector.get_all_metrics()
        assert len(all_metrics) == 3

        # Modify copies
        all_metrics["model-0"].errors_by_status[500] = 999
        all_metrics["model-1"].errors_by_status[404] = 123

        # Verify internal state unchanged
        internal = collector.get_all_metrics()
        assert internal["model-0"].errors_by_status[500] == 1  # Not 999
        assert 404 not in internal["model-1"].errors_by_status  # Not added
