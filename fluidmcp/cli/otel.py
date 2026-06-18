"""
OpenTelemetry initialization for FluidMCP.

Supports OTLP HTTP export (Grafana Tempo), console debug, or both.
Gracefully no-ops if packages are missing or the collector is unreachable.

Environment variables:
    OTEL_ENABLED                  true | false  (default: true)
    OTEL_SERVICE_NAME             (default: fluidmcp)
    OTEL_SERVICE_VERSION          (default: 2.0.0)
    OTEL_EXPORTER                 otlp | console | both  (default: otlp)
    OTEL_EXPORTER_OTLP_ENDPOINT   (default: http://tempo:4318/v1/traces)
    OTEL_SHUTDOWN_TIMEOUT         seconds (default: 5.0)
"""
import asyncio
import os
import threading
import time
from loguru import logger

_otel_initialized = False
_otel_shutdown_lock = threading.Lock()
_otel_shutdown_done = False
_otel_provider = None


def init_otel() -> bool:
    global _otel_initialized

    if _otel_initialized:
        return True

    if os.getenv("OTEL_ENABLED", "true").lower() == "false":
        logger.info("OpenTelemetry disabled via OTEL_ENABLED=false")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
        from opentelemetry.sdk.resources import Resource

        service_name = os.getenv("OTEL_SERVICE_NAME", "fluidmcp")
        service_version = os.getenv("OTEL_SERVICE_VERSION", "2.0.0")

        resource = Resource.create({
            "service.name": service_name,
            "service.version": service_version,
        })

        global _otel_provider
        provider = TracerProvider(resource=resource)
        _otel_provider = provider

        # "otlp" is the correct name — previously called "jaeger" because the
        # OTLP exporter originated from the Jaeger project. Renamed for clarity.
        exporter_type = os.getenv("OTEL_EXPORTER", "otlp").lower()
        exporters_added = []

        if exporter_type in ("otlp", "both"):
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

                otlp_endpoint = os.getenv(
                    "OTEL_EXPORTER_OTLP_ENDPOINT",
                    "http://tempo:4318/v1/traces",
                )
                otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
                provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
                exporters_added.append(f"otlp({otlp_endpoint})")
                logger.info(f"OpenTelemetry OTLP exporter → {otlp_endpoint}")

                # Verify reachability non-blocking — fire-and-forget in a thread
                # so we don't stall the async event loop during startup.
                threading.Thread(
                    target=_verify_endpoint_sync,
                    args=(otlp_endpoint,),
                    daemon=True,
                ).start()

            except ImportError:
                logger.error("opentelemetry-exporter-otlp-proto-http not installed")
            except Exception as exc:
                logger.error(f"Failed to configure OTLP exporter: {exc}")

        if exporter_type in ("console", "both"):
            try:
                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
                exporters_added.append("console")
            except Exception as exc:
                logger.warning(f"Console exporter failed: {exc}")

        if not exporters_added:
            logger.error("No OTEL exporters configured — tracing disabled")
            return False

        # Wire httpx instrumentation so outbound HTTP calls from backends
        # (Prometheus, Loki, Tempo clients) appear as child spans automatically.
        _instrument_httpx()

        trace.set_tracer_provider(provider)
        _otel_initialized = True
        logger.info(f"OpenTelemetry ready: service={service_name} exporters={exporters_added}")
        return True

    except ImportError as exc:
        logger.error(f"OpenTelemetry packages missing: {exc}")
        return False
    except Exception as exc:
        logger.error(f"OpenTelemetry init failed: {exc}")
        return False


def _verify_endpoint_sync(endpoint: str, timeout: float = 2.0) -> None:
    """
    Log a warning if the OTLP collector is unreachable at startup.
    Runs in a daemon thread — never blocks the event loop.
    """
    try:
        import httpx
        base = endpoint.rsplit("/v1/traces", 1)[0]
        with httpx.Client(timeout=timeout) as client:
            client.get(base, follow_redirects=False)
        logger.debug(f"OTLP endpoint reachable: {base}")
    except Exception:
        logger.warning(
            f"OTLP endpoint unreachable at startup: {endpoint} — "
            "spans will queue in memory until the collector is ready"
        )


def _instrument_httpx() -> None:
    """Instrument httpx so outbound HTTP calls appear as child OTEL spans."""
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
        logger.debug("httpx instrumented with OpenTelemetry")
    except ImportError:
        logger.debug("opentelemetry-instrumentation-httpx not installed — skipping")
    except Exception as exc:
        logger.debug(f"httpx instrumentation skipped: {exc}")


def instrument_fastapi_app(app) -> bool:
    if not _otel_initialized:
        return False
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI instrumented with OpenTelemetry")
        return True
    except ImportError as exc:
        logger.warning(f"FastAPI OTEL instrumentation missing: {exc}")
        return False
    except Exception as exc:
        logger.warning(f"FastAPI OTEL instrumentation failed: {exc}")
        return False


def shutdown_otel(timeout_seconds: float = 5.0) -> bool:
    """
    Flush and shut down the OTEL tracer provider.

    Thread-safe: all state checks are inside the lock to eliminate the TOCTOU
    race between the idempotency check and the initialized/provider checks.
    """
    global _otel_shutdown_done, _otel_provider

    with _otel_shutdown_lock:
        # All early-exit conditions checked inside the lock — no TOCTOU window.
        if _otel_shutdown_done:
            return True
        if not _otel_initialized or _otel_provider is None:
            _otel_shutdown_done = True
            return True

        # Mark done immediately inside the lock so concurrent callers skip.
        _otel_shutdown_done = True

    try:
        env_timeout = os.getenv("OTEL_SHUTDOWN_TIMEOUT")
        if env_timeout:
            try:
                timeout_seconds = max(float(env_timeout), 0.1)
            except ValueError:
                pass

        timeout_millis = int(timeout_seconds * 1000)
        flushed = _otel_provider.force_flush(timeout_millis=timeout_millis)
        if not flushed:
            logger.warning(
                f"OTEL force_flush timed out after {timeout_seconds}s — some spans may be lost"
            )
        _otel_provider.shutdown()
        logger.info("OpenTelemetry shutdown complete")
        return flushed

    except Exception as exc:
        logger.error(f"OpenTelemetry shutdown error: {exc}")
        return False
