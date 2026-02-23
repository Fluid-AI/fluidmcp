"""
OpenTelemetry initialization for FluidMCP.

Phase-2: OTLP HTTP exporter with optional console debugging.
Supports multiple exporters with graceful fallback.
Works reliably in restricted networks (GitHub Codespaces, containers).
"""
import os
from loguru import logger

# Global flag to track initialization state
_otel_initialized = False


def init_otel() -> bool:
    """
    Initialize OpenTelemetry with Jaeger and/or Console exporters.

    Environment variables:
        OTEL_ENABLED: Set to 'false' to disable (default: enabled)
        OTEL_SERVICE_NAME: Service name for traces (default: 'fluidmcp')
        OTEL_SERVICE_VERSION: Service version (default: '2.0.0')
        OTEL_EXPORTER: Exporter type - 'jaeger', 'console', 'both' (default: 'jaeger')
        OTEL_EXPORTER_OTLP_ENDPOINT: OTLP endpoint URL (default: 'http://localhost:4318/v1/traces')

    Returns:
        True if initialized successfully, False if disabled or failed

    Safety:
        - Idempotent: Safe to call multiple times
        - Defensive: Catches all exceptions and logs warnings
        - No crashes: Returns False on failure, never raises
        - Graceful fallback: If Jaeger fails, continues without tracing
    """
    global _otel_initialized

    # Check if already initialized
    if _otel_initialized:
        logger.debug("OpenTelemetry already initialized, skipping")
        return True

    # Check if explicitly disabled
    if os.getenv("OTEL_ENABLED", "true").lower() == "false":
        logger.info("OpenTelemetry disabled via OTEL_ENABLED=false")
        return False

    try:
        # Import here to avoid import errors if packages not installed
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
        from opentelemetry.sdk.resources import Resource

        # Create resource with service metadata
        service_name = os.getenv("OTEL_SERVICE_NAME", "fluidmcp")
        service_version = os.getenv("OTEL_SERVICE_VERSION", "2.0.0")

        resource = Resource.create({
            "service.name": service_name,
            "service.version": service_version,
        })

        # Create tracer provider with resource
        provider = TracerProvider(resource=resource)

        # Determine which exporters to use
        exporter_type = os.getenv("OTEL_EXPORTER", "jaeger").lower()
        exporters_added = []

        # Add OTLP exporter (HTTP - compatible with Jaeger OTLP collector)
        if exporter_type in ["jaeger", "both"]:
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

                # OTLP endpoint (HTTP) - compatible with Jaeger collector
                otlp_endpoint = os.getenv(
                    "OTEL_EXPORTER_OTLP_ENDPOINT",
                    "http://localhost:4318/v1/traces"  # Jaeger OTLP HTTP endpoint
                )

                otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
                otlp_processor = BatchSpanProcessor(otlp_exporter)
                provider.add_span_processor(otlp_processor)
                exporters_added.append(f"otlp({otlp_endpoint})")
                logger.info(f"✓ OTLP exporter configured: {otlp_endpoint}")

            except ImportError:
                logger.error("❌ OTLP exporter not installed: pip install opentelemetry-exporter-otlp-proto-http")
            except Exception as e:
                logger.error(f"❌ Failed to initialize OTLP exporter: {e}")

        # Add Console exporter
        if exporter_type in ["console", "both"]:
            try:
                console_exporter = ConsoleSpanExporter()
                console_processor = BatchSpanProcessor(console_exporter)
                provider.add_span_processor(console_processor)
                exporters_added.append("console")
                logger.debug("Console exporter added")

            except Exception as e:
                logger.warning(f"⚠️  Failed to initialize Console exporter: {e}")

        # Check if at least one exporter was added
        if not exporters_added:
            logger.error("❌ No OpenTelemetry exporters configured successfully")
            logger.error("❌ Traces will NOT be collected. Check OTEL_EXPORTER configuration and dependencies.")
            return False

        # Set global tracer provider
        trace.set_tracer_provider(provider)

        # Mark as initialized
        _otel_initialized = True

        exporters_str = ", ".join(exporters_added)
        logger.info(f"✓ OpenTelemetry initialized: service={service_name}, version={service_version}, exporters=[{exporters_str}]")
        return True

    except ImportError as e:
        logger.error(f"❌ OpenTelemetry packages not installed: {e}")
        logger.error("❌ Install with: pip install -r requirements.txt")
        return False

    except Exception as e:
        logger.error(f"❌ Failed to initialize OpenTelemetry: {e}")
        logger.warning("⚠️  Continuing without tracing")
        return False


def verify_otlp_endpoint(endpoint: str, timeout: float = 2.0) -> bool:
    """
    Test connectivity to OTLP endpoint.

    Args:
        endpoint: OTLP HTTP endpoint URL
        timeout: Connection timeout in seconds

    Returns:
        True if reachable, False otherwise

    Safety:
        - Quick connectivity check (doesn't send actual traces)
        - Uses httpx with timeout
        - Catches all exceptions
    """
    try:
        import httpx

        # Extract base URL (remove /v1/traces path)
        base_url = endpoint.rsplit("/v1/traces", 1)[0]

        # Quick connectivity check to the base endpoint
        # Note: We don't send actual trace data, just verify HTTP connectivity
        with httpx.Client(timeout=timeout) as client:
            response = client.get(base_url, follow_redirects=False)
            # Any HTTP response (even 404) means the endpoint is reachable
            logger.debug(f"OTLP endpoint {base_url} is reachable (status: {response.status_code})")
            return True

    except httpx.ConnectError as e:
        logger.warning(f"⚠️  OTLP endpoint {endpoint} not reachable: {e}")
        return False
    except httpx.TimeoutException:
        logger.warning(f"⚠️  OTLP endpoint {endpoint} timed out after {timeout}s")
        return False
    except Exception as e:
        logger.warning(f"⚠️  Failed to verify OTLP endpoint {endpoint}: {e}")
        return False


def instrument_fastapi_app(app):
    """
    Instrument FastAPI application with OpenTelemetry.

    Args:
        app: FastAPI application instance

    Returns:
        True if instrumented successfully, False otherwise

    Safety:
        - Only instruments if OTEL was initialized
        - Catches all exceptions
        - Safe to call even if instrumentation packages missing
    """
    if not _otel_initialized:
        logger.debug("OpenTelemetry not initialized, skipping FastAPI instrumentation")
        return False

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        # Instrument the FastAPI app
        # This automatically creates spans for all HTTP requests
        FastAPIInstrumentor.instrument_app(app)

        logger.info("✓ FastAPI instrumented with OpenTelemetry")
        return True

    except ImportError as e:
        logger.warning(f"⚠️  FastAPI instrumentation package not installed: {e}")
        logger.warning("⚠️  Install with: pip install opentelemetry-instrumentation-fastapi")
        return False

    except Exception as e:
        logger.warning(f"⚠️  Failed to instrument FastAPI: {e}")
        logger.warning("⚠️  Continuing without request tracing")
        return False
