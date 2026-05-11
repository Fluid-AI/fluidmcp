"""Tests for OpenTelemetry tracing helpers."""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import List

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, ReadableSpan
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

from fluidmcp.cli.services.tracing import (
    get_tracer,
    trace_mcp_operation,
    set_span_attribute,
    record_mcp_error,
    enrich_current_span,
    enrich_span_with_error,
    _sanitize_attribute,
    _REDACTED,
)


class _CollectingExporter(SpanExporter):
    """Simple in-memory span exporter for tests."""

    def __init__(self):
        self.spans: List[ReadableSpan] = []

    def export(self, spans):
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass

    def get_finished_spans(self) -> List[ReadableSpan]:
        return list(self.spans)


@pytest.fixture(autouse=True)
def setup_otel():
    """Set up an in-memory OTEL provider for each test.

    Uses the internal _TRACER_PROVIDER_SET_ONCE reset to allow
    setting a new provider per test.
    """
    import fluidmcp.cli.services.tracing as tracing_module
    from opentelemetry.trace import _TRACER_PROVIDER_SET_ONCE

    # Reset the global "set once" guard so we can install a fresh provider
    _TRACER_PROVIDER_SET_ONCE._done = False

    exporter = _CollectingExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Reset cached tracer so it picks up new provider
    tracing_module._tracer = None

    yield exporter

    provider.shutdown()
    tracing_module._tracer = None


# --- _sanitize_attribute tests ---


class TestSanitizeAttribute:
    def test_safe_key_passes_through(self):
        assert _sanitize_attribute("mcp.server_id", "filesystem") == "filesystem"

    def test_key_with_token_is_redacted(self):
        assert _sanitize_attribute("api_token", "sk-secret") == _REDACTED

    def test_key_with_key_is_redacted(self):
        assert _sanitize_attribute("api_key", "abc123") == _REDACTED

    def test_key_with_secret_is_redacted(self):
        assert _sanitize_attribute("client_secret", "xyz") == _REDACTED

    def test_key_with_password_is_redacted(self):
        assert _sanitize_attribute("db_password", "hunter2") == _REDACTED

    def test_key_with_auth_is_redacted(self):
        assert _sanitize_attribute("auth_header", "Bearer xyz") == _REDACTED

    def test_key_with_credential_is_redacted(self):
        assert _sanitize_attribute("credential_data", "cred") == _REDACTED

    def test_key_with_bearer_is_redacted(self):
        assert _sanitize_attribute("bearer_value", "tok") == _REDACTED

    def test_key_with_cookie_is_redacted(self):
        assert _sanitize_attribute("session_cookie", "abc") == _REDACTED

    def test_case_insensitive(self):
        assert _sanitize_attribute("API_TOKEN", "val") == _REDACTED
        assert _sanitize_attribute("ApiKey", "val") == _REDACTED


# --- trace_mcp_operation tests ---


class TestTraceMcpOperation:
    def test_creates_span_with_correct_name(self, setup_otel):
        exporter = setup_otel
        with trace_mcp_operation("tools/list", "filesystem"):
            pass

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "mcp.tools/list"

    def test_sets_server_id_and_operation_attributes(self, setup_otel):
        exporter = setup_otel
        with trace_mcp_operation("tools/call", "memory"):
            pass

        spans = exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert attrs["mcp.server_id"] == "memory"
        assert attrs["mcp.operation"] == "tools/call"

    def test_custom_attributes_added(self, setup_otel):
        exporter = setup_otel
        with trace_mcp_operation("tools/list", "fs", {"request_id": 42}):
            pass

        spans = exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert attrs["request_id"] == 42

    def test_sensitive_custom_attributes_redacted(self, setup_otel):
        exporter = setup_otel
        with trace_mcp_operation("tools/list", "fs", {"api_key": "sk-secret"}):
            pass

        spans = exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert attrs["api_key"] == _REDACTED

    def test_yields_span_object(self, setup_otel):
        with trace_mcp_operation("tools/list", "fs") as span:
            assert span is not None
            assert span.is_recording()

    def test_records_exception_on_error(self, setup_otel):
        exporter = setup_otel
        with pytest.raises(ValueError, match="test error"):
            with trace_mcp_operation("tools/call", "fs"):
                raise ValueError("test error")

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].status.status_code.name == "ERROR"
        # Exception should be recorded as an event
        events = spans[0].events
        assert any("ValueError" in str(e.attributes) for e in events)

    def test_reraises_exceptions(self, setup_otel):
        with pytest.raises(RuntimeError, match="boom"):
            with trace_mcp_operation("tools/call", "fs"):
                raise RuntimeError("boom")


# --- set_span_attribute tests ---


class TestSetSpanAttribute:
    def test_sets_attribute_on_active_span(self, setup_otel):
        exporter = setup_otel
        with trace_mcp_operation("tools/call", "fs") as span:
            set_span_attribute("tool.name", "read_file")

        spans = exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert attrs["tool.name"] == "read_file"

    def test_redacts_sensitive_attribute(self, setup_otel):
        exporter = setup_otel
        with trace_mcp_operation("tools/call", "fs"):
            set_span_attribute("api_key", "sk-1234567890")

        spans = exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert attrs["api_key"] == _REDACTED

    def test_no_crash_without_active_span(self):
        # Should not raise even with no active recording span
        set_span_attribute("key", "value")


# --- record_mcp_error tests ---


class TestRecordMcpError:
    def test_records_exception_on_span(self, setup_otel):
        exporter = setup_otel
        err = ValueError("bad input")
        with trace_mcp_operation("tools/call", "fs"):
            record_mcp_error(err)

        spans = exporter.get_finished_spans()
        events = spans[0].events
        assert any("ValueError" in str(e.attributes) for e in events)

    def test_records_custom_message_event(self, setup_otel):
        exporter = setup_otel
        err = ValueError("bad")
        with trace_mcp_operation("tools/call", "fs"):
            record_mcp_error(err, "Custom error context")

        spans = exporter.get_finished_spans()
        events = spans[0].events
        assert any(e.name == "Custom error context" for e in events)

    def test_no_crash_without_active_span(self):
        record_mcp_error(ValueError("no span"))


# --- enrich_current_span tests ---


class TestEnrichCurrentSpan:
    def test_sets_user_id(self, setup_otel):
        exporter = setup_otel
        with trace_mcp_operation("tools/list", "fs"):
            enrich_current_span(user_id="user_123")

        spans = exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert attrs["user.id"] == "user_123"

    def test_sets_server_id(self, setup_otel):
        exporter = setup_otel
        with trace_mcp_operation("tools/list", "fs"):
            enrich_current_span(server_id="memory")

        spans = exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert attrs["mcp.server_id"] == "memory"

    def test_sets_request_id(self, setup_otel):
        exporter = setup_otel
        with trace_mcp_operation("tools/list", "fs"):
            enrich_current_span(request_id=42)

        spans = exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert attrs["request.id"] == "42"

    def test_custom_kwargs_added(self, setup_otel):
        exporter = setup_otel
        with trace_mcp_operation("tools/list", "fs"):
            enrich_current_span(custom_field="hello")

        spans = exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert attrs["custom_field"] == "hello"

    def test_sensitive_kwargs_redacted(self, setup_otel):
        exporter = setup_otel
        with trace_mcp_operation("tools/list", "fs"):
            enrich_current_span(api_token="sk-secret123")

        spans = exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert attrs["api_token"] == _REDACTED

    def test_none_kwargs_skipped(self, setup_otel):
        exporter = setup_otel
        with trace_mcp_operation("tools/list", "fs"):
            enrich_current_span(user_id=None, custom_field=None)

        spans = exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert "user.id" not in attrs
        assert "custom_field" not in attrs

    def test_no_crash_without_active_span(self):
        enrich_current_span(user_id="user_123")


# --- enrich_span_with_error tests ---


class TestEnrichSpanWithError:
    def test_sets_error_status(self, setup_otel):
        exporter = setup_otel
        err = ValueError("something broke")
        with trace_mcp_operation("tools/call", "fs"):
            enrich_span_with_error(err)

        spans = exporter.get_finished_spans()
        assert spans[0].status.status_code.name == "ERROR"
        attrs = dict(spans[0].attributes)
        assert attrs["error"] is True

    def test_sets_user_and_server_context(self, setup_otel):
        exporter = setup_otel
        err = ValueError("fail")
        with trace_mcp_operation("tools/call", "fs"):
            enrich_span_with_error(err, user_id="u1", server_id="mem")

        spans = exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert attrs["user.id"] == "u1"
        assert attrs["mcp.server_id"] == "mem"

    def test_records_exception_event(self, setup_otel):
        exporter = setup_otel
        err = RuntimeError("crash")
        with trace_mcp_operation("tools/call", "fs"):
            enrich_span_with_error(err)

        spans = exporter.get_finished_spans()
        events = spans[0].events
        assert any("RuntimeError" in str(e.attributes) for e in events)

    def test_records_custom_message_event(self, setup_otel):
        exporter = setup_otel
        err = ValueError("bad")
        with trace_mcp_operation("tools/call", "fs"):
            enrich_span_with_error(err, message="Custom context")

        spans = exporter.get_finished_spans()
        events = spans[0].events
        error_events = [e for e in events if e.name == "error"]
        assert len(error_events) == 1
        assert error_events[0].attributes["message"] == "Custom context"
        assert error_events[0].attributes["error.type"] == "ValueError"

    def test_no_crash_without_active_span(self):
        enrich_span_with_error(ValueError("no span"))


# --- get_tracer tests ---


class TestGetTracer:
    def test_returns_tracer(self):
        tracer = get_tracer()
        assert tracer is not None

    def test_returns_same_tracer_on_repeated_calls(self):
        t1 = get_tracer()
        t2 = get_tracer()
        assert t1 is t2
