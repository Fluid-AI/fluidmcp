"""
OpenTelemetry Instrumentation for FluidMCP.

This module provides comprehensive observability instrumentation using OpenTelemetry,
including traces, metrics, and structured logging with trace correlation.
"""

import os
import logging
from typing import Optional, Dict, Any
from contextlib import contextmanager

# OpenTelemetry imports
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
from opentelemetry.trace import Status, StatusCode
from opentelemetry.metrics import Counter, Histogram, UpDownCounter

# Standard library
import json
import time
from loguru import logger


class OpenTelemetryManager:
    """Manages OpenTelemetry instrumentation for FluidMCP."""

    def __init__(self):
        self.tracer = None
        self.meter = None
        self._initialized = False

        # Custom metrics
        self.mcp_request_counter = None
        self.mcp_request_duration = None
        self.mcp_tool_execution_counter = None
        self.mcp_tool_execution_duration = None
        self.mcp_error_counter = None
        self.active_requests = None

    def init_telemetry(
        self,
        service_name: str = "fluidmcp",
        service_version: str = "2.0.0",
        otlp_endpoint: Optional[str] = None,
        enable_tracing: bool = True,
        enable_metrics: bool = True,
        enable_logs: bool = True,
    ) -> None:
        """
        Initialize OpenTelemetry instrumentation.

        Args:
            service_name: Name of the service
            service_version: Version of the service
            otlp_endpoint: OTLP endpoint URL (defaults to env var)
            enable_tracing: Whether to enable distributed tracing
            enable_metrics: Whether to enable metrics collection
            enable_logs: Whether to enable structured logging
        """
        if self._initialized:
            logger.warning("OpenTelemetry already initialized")
            return

        # Get configuration from environment
        otlp_endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        service_name = os.getenv("OTEL_SERVICE_NAME", service_name)

        # Create resource
        resource = Resource.create({
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
            "service.instance.id": os.getenv("HOSTNAME", "fluidmcp-instance"),
            "environment": os.getenv("ENVIRONMENT", "development"),
        })

        # Initialize tracing
        if enable_tracing:
            self._init_tracing(resource, otlp_endpoint)

        # Initialize metrics
        if enable_metrics:
            self._init_metrics(resource, otlp_endpoint)

        # Initialize auto-instrumentation
        self._init_auto_instrumentation()

        # Configure structured logging
        if enable_logs:
            self._configure_structured_logging()

        self._initialized = True
        logger.info(f"✅ OpenTelemetry initialized for {service_name}")

    def _init_tracing(self, resource: Resource, otlp_endpoint: str) -> None:
        """Initialize distributed tracing."""
        # Create tracer provider
        tracer_provider = TracerProvider(resource=resource)

        # Configure OTLP exporter
        otlp_exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            insecure=otlp_endpoint.startswith("http://"),
        )

        # Add batch processor
        span_processor = BatchSpanProcessor(otlp_exporter)
        tracer_provider.add_span_processor(span_processor)

        # Set global tracer provider
        trace.set_tracer_provider(tracer_provider)
        self.tracer = trace.get_tracer(__name__)

        logger.info(f"📊 Tracing enabled → {otlp_endpoint}")

    def _init_metrics(self, resource: Resource, otlp_endpoint: str) -> None:
        """Initialize metrics collection."""
        # Create metric reader
        metric_exporter = OTLPMetricExporter(
            endpoint=otlp_endpoint,
            insecure=otlp_endpoint.startswith("http://"),
        )
        metric_reader = PeriodicExportingMetricReader(
            exporter=metric_exporter,
            export_interval_millis=30000,  # Export every 30 seconds
        )

        # Create meter provider
        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[metric_reader],
        )

        # Set global meter provider
        metrics.set_meter_provider(meter_provider)
        self.meter = metrics.get_meter(__name__)

        # Create custom metrics
        self._create_custom_metrics()

        logger.info(f"📈 Metrics enabled → {otlp_endpoint}")

    def _create_custom_metrics(self) -> None:
        """Create custom metrics for MCP operations."""
        if not self.meter:
            return

        # MCP request metrics
        self.mcp_request_counter = self.meter.create_counter(
            name="mcp_requests_total",
            description="Total number of MCP requests",
            unit="1"
        )

        self.mcp_request_duration = self.meter.create_histogram(
            name="mcp_request_duration_seconds",
            description="Duration of MCP requests",
            unit="s"
        )

        # Tool execution metrics
        self.mcp_tool_execution_counter = self.meter.create_counter(
            name="mcp_tool_executions_total",
            description="Total number of MCP tool executions",
            unit="1"
        )

        self.mcp_tool_execution_duration = self.meter.create_histogram(
            name="mcp_tool_execution_duration_seconds",
            description="Duration of MCP tool executions",
            unit="s"
        )

        # Error metrics
        self.mcp_error_counter = self.meter.create_counter(
            name="mcp_errors_total",
            description="Total number of MCP errors",
            unit="1"
        )

        # Active requests gauge
        self.active_requests = self.meter.create_up_down_counter(
            name="mcp_active_requests",
            description="Number of currently active MCP requests",
            unit="1"
        )

    def _init_auto_instrumentation(self) -> None:
        """Initialize automatic instrumentation for common libraries."""
        try:
            # Instrument FastAPI
            FastAPIInstrumentor().instrument()
            logger.info("🔧 FastAPI instrumentation enabled")

            # Instrument HTTPX (for external API calls)
            HTTPXClientInstrumentor().instrument()
            logger.info("🔧 HTTPX instrumentation enabled")

            # Instrument PyMongo (for database operations)
            PymongoInstrumentor().instrument()
            logger.info("🔧 PyMongo instrumentation enabled")

        except Exception as e:
            logger.error(f"Failed to initialize auto-instrumentation: {e}")

    def _configure_structured_logging(self) -> None:
        """Configure structured logging with trace correlation."""
        # Add trace context to loguru logs
        class TraceContextFilter(logging.Filter):
            def filter(self, record):
                # Get current span context
                current_span = trace.get_current_span()
                if current_span.is_recording():
                    span_context = current_span.get_span_context()
                    record.trace_id = f"{span_context.trace_id:032x}"
                    record.span_id = f"{span_context.span_id:016x}"
                else:
                    record.trace_id = None
                    record.span_id = None
                return True

        # Add filter to root logger
        trace_filter = TraceContextFilter()
        logging.getLogger().addFilter(trace_filter)

        logger.info("📝 Structured logging with trace correlation enabled")

    @contextmanager
    def trace_request(self, method: str, endpoint: str, **attributes):
        """Context manager for tracing HTTP requests."""
        if not self.tracer:
            yield
            return

        with self.tracer.start_as_span(
            f"{method} {endpoint}",
            kind=trace.SpanKind.SERVER,
        ) as span:
            # Add attributes
            span.set_attributes({
                "http.method": method,
                "http.url": endpoint,
                **attributes
            })

            try:
                yield span
            except Exception as e:
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                raise

    @contextmanager
    def trace_tool_execution(self, tool_name: str, **attributes):
        """Context manager for tracing MCP tool executions."""
        if not self.tracer:
            yield
            return

        with self.tracer.start_as_span(
            f"tool.{tool_name}",
            kind=trace.SpanKind.INTERNAL,
        ) as span:
            span.set_attributes({
                "mcp.tool.name": tool_name,
                **attributes
            })

            try:
                yield span
            except Exception as e:
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                raise

    def record_request_metrics(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration: float,
        **labels
    ) -> None:
        """Record metrics for an HTTP request."""
        if not self.meter:
            return

        # Request counter
        self.mcp_request_counter.add(
            1,
            {
                "method": method,
                "endpoint": endpoint,
                "status_code": str(status_code),
                **labels
            }
        )

        # Request duration
        self.mcp_request_duration.record(
            duration,
            {
                "method": method,
                "endpoint": endpoint,
                "status_code": str(status_code),
                **labels
            }
        )

        # Error counter for non-2xx responses
        if status_code >= 400:
            self.mcp_error_counter.add(
                1,
                {
                    "method": method,
                    "endpoint": endpoint,
                    "status_code": str(status_code),
                    **labels
                }
            )

    def record_tool_execution_metrics(
        self,
        tool_name: str,
        duration: float,
        success: bool = True,
        **labels
    ) -> None:
        """Record metrics for tool execution."""
        if not self.meter:
            return

        # Tool execution counter
        self.mcp_tool_execution_counter.add(
            1,
            {
                "tool_name": tool_name,
                "success": str(success).lower(),
                **labels
            }
        )

        # Tool execution duration
        self.mcp_tool_execution_duration.record(
            duration,
            {
                "tool_name": tool_name,
                "success": str(success).lower(),
                **labels
            }
        )

    @contextmanager
    def active_request_context(self):
        """Context manager to track active requests."""
        if self.active_requests:
            self.active_requests.add(1)
        try:
            yield
        finally:
            if self.active_requests:
                self.active_requests.add(-1)

    def get_trace_context(self) -> Dict[str, str]:
        """Get current trace context for log correlation."""
        current_span = trace.get_current_span()
        if current_span.is_recording():
            span_context = current_span.get_span_context()
            return {
                "trace_id": f"{span_context.trace_id:032x}",
                "span_id": f"{span_context.span_id:016x}",
            }
        return {}

    def shutdown(self) -> None:
        """Shutdown OpenTelemetry instrumentation."""
        if not self._initialized:
            return

        try:
            # Shutdown tracing
            if trace.get_tracer_provider():
                trace.get_tracer_provider().shutdown()

            # Shutdown metrics
            if metrics.get_meter_provider():
                metrics.get_meter_provider().shutdown()

            logger.info("🛑 OpenTelemetry shutdown complete")
        except Exception as e:
            logger.error(f"Error during OpenTelemetry shutdown: {e}")


# Global instance
otel_manager = OpenTelemetryManager()


def init_opentelemetry(
    service_name: str = "fluidmcp",
    service_version: str = "2.0.0",
    enable_tracing: bool = True,
    enable_metrics: bool = True,
    enable_logs: bool = True,
) -> OpenTelemetryManager:
    """
    Initialize OpenTelemetry for the application.

    This should be called early in the application startup process.
    """
    otel_manager.init_telemetry(
        service_name=service_name,
        service_version=service_version,
        enable_tracing=enable_tracing,
        enable_metrics=enable_metrics,
        enable_logs=enable_logs,
    )
    return otel_manager


def get_otel_manager() -> OpenTelemetryManager:
    """Get the global OpenTelemetry manager instance."""
    return otel_manager


def shutdown_opentelemetry() -> None:
    """Shutdown OpenTelemetry instrumentation."""
    otel_manager.shutdown()