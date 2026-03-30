"""
Tests for Prometheus label escaping in metrics export.

Tests that special characters in model IDs and provider types are properly
escaped to produce valid Prometheus format output.
"""

import pytest
from fluidmcp.cli.services.llm_metrics import LLMMetricsCollector, reset_metrics_collector


@pytest.fixture(autouse=True)
def reset_collector():
    """Reset global collector before each test."""
    reset_metrics_collector()
    yield
    reset_metrics_collector()


class TestPrometheusLabelEscaping:
    """Test Prometheus label value escaping for special characters."""

    def test_escape_label_value_backslash(self):
        """Test that backslashes are properly escaped."""
        collector = LLMMetricsCollector()

        # Test escaping method directly
        result = collector._escape_label_value("model\\with\\backslash")
        assert result == "model\\\\with\\\\backslash"

    def test_escape_label_value_double_quote(self):
        """Test that double quotes are properly escaped."""
        collector = LLMMetricsCollector()

        result = collector._escape_label_value('model"with"quotes')
        assert result == 'model\\"with\\"quotes'

    def test_escape_label_value_newline(self):
        """Test that newlines are properly escaped."""
        collector = LLMMetricsCollector()

        result = collector._escape_label_value("model\nwith\nnewlines")
        assert result == "model\\nwith\\nnewlines"

    def test_escape_label_value_combined(self):
        """Test multiple special characters together."""
        collector = LLMMetricsCollector()

        result = collector._escape_label_value('test\\model"name\nline2')
        assert result == 'test\\\\model\\"name\\nline2'

    def test_prometheus_export_with_special_chars_in_model_id(self):
        """Test Prometheus export with special characters in model ID."""
        collector = LLMMetricsCollector()

        # Model ID with double quote
        model_id = 'test"model'
        start = collector.record_request_start(model_id, "vllm")
        collector.record_request_success(model_id, start, prompt_tokens=5, completion_tokens=2)

        prometheus_output = collector.export_prometheus()

        # Verify the escaped model ID appears in output
        assert 'model_id="test\\"model"' in prometheus_output

        # Verify the escaping worked correctly - the literal should be:
        # model_id="test\"model" (where \" is the escaped quote)
        # This is correct Prometheus format

    def test_prometheus_export_with_backslash_in_model_id(self):
        """Test Prometheus export with backslash in model ID."""
        collector = LLMMetricsCollector()

        model_id = 'test\\model'
        start = collector.record_request_start(model_id, "vllm")
        collector.record_request_success(model_id, start)

        prometheus_output = collector.export_prometheus()

        # Verify the escaped backslash appears
        assert 'model_id="test\\\\model"' in prometheus_output

    def test_prometheus_export_with_newline_in_provider_type(self):
        """Test Prometheus export with newline in provider type."""
        collector = LLMMetricsCollector()

        model_id = "test-model"
        provider_type = "vllm\nprovider"
        start = collector.record_request_start(model_id, provider_type)
        collector.record_request_success(model_id, start)

        prometheus_output = collector.export_prometheus()

        # Verify the escaped newline appears
        assert 'provider="vllm\\nprovider"' in prometheus_output
        # Verify no actual newlines in metric lines (would break format)
        lines = prometheus_output.split('\n')
        metric_lines = [l for l in lines if l and not l.startswith('#')]
        for line in metric_lines:
            # After first split by \n, there shouldn't be actual newlines in label values
            assert '\n' not in line.split('{')[1].split('}')[0] if '{' in line else True

    def test_prometheus_export_special_chars_in_multiple_models(self):
        """Test Prometheus export with special characters in multiple models."""
        collector = LLMMetricsCollector()

        models = [
            ('model"one', "vllm"),
            ('model\\two', "replicate"),
            ('model\nthree', "ollama")
        ]

        for model_id, provider in models:
            start = collector.record_request_start(model_id, provider)
            collector.record_request_success(model_id, start)

        prometheus_output = collector.export_prometheus()

        # Verify all models are properly escaped
        assert 'model_id="model\\"one"' in prometheus_output
        assert 'model_id="model\\\\two"' in prometheus_output
        assert 'model_id="model\\nthree"' in prometheus_output

    def test_json_export_preserves_original_values(self):
        """Test that JSON export preserves original unescaped values."""
        collector = LLMMetricsCollector()

        model_id = 'test"model\\with\nspecial'
        start = collector.record_request_start(model_id, "vllm")
        collector.record_request_success(model_id, start)

        json_output = collector.export_json()

        # JSON export should preserve original values (JSON handles escaping)
        assert model_id in json_output["models"]
        assert json_output["models"][model_id]["requests"]["total"] == 1

    def test_normal_model_ids_unchanged(self):
        """Test that normal model IDs without special characters work as before."""
        collector = LLMMetricsCollector()

        model_id = "normal-model-123"
        start = collector.record_request_start(model_id, "vllm")
        collector.record_request_success(model_id, start)

        prometheus_output = collector.export_prometheus()

        # Normal model ID should appear as-is
        assert 'model_id="normal-model-123"' in prometheus_output
        assert 'fluidmcp_llm_requests_total{model_id="normal-model-123",provider="vllm"} 1' in prometheus_output
