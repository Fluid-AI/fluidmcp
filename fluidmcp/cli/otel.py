"""
OpenTelemetry initialization for FluidMCP.

Phase-2: Jaeger exporter with optional console debugging.
Supports multiple exporters with graceful fallback.
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
        JAEGER_AGENT_HOST: Jaeger agent hostname (default: 'localhost')
        JAEGER_AGENT_PORT: Jaeger agent UDP port (default: 6831)

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

        # Add Jaeger exporter
        if exporter_type in ["jaeger", "both"]:
            try:
                from opentelemetry.exporter.jaeger.thrift import JaegerExporter

                jaeger_host = os.getenv("JAEGER_AGENT_HOST", "localhost")
                jaeger_port = int(os.getenv("JAEGER_AGENT_PORT", "6831"))

                jaeger_exporter = JaegerExporter(
                    agent_host_name=jaeger_host,
                    agent_port=jaeger_port,
                )
                jaeger_processor = BatchSpanProcessor(jaeger_exporter)
                provider.add_span_processor(jaeger_processor)
                exporters_added.append(f"jaeger({jaeger_host}:{jaeger_port})")
                logger.debug(f"Jaeger exporter added: {jaeger_host}:{jaeger_port}")

            except ImportError:
                logger.warning("⚠️  Jaeger exporter not installed: pip install opentelemetry-exporter-jaeger")
            except Exception as e:
                logger.warning(f"⚠️  Failed to initialize Jaeger exporter: {e}")

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
            logger.error("❌ No exporters configured successfully")
            return False

        # Set global tracer provider
        trace.set_tracer_provider(provider)

        # Mark as initialized
        _otel_initialized = True

        exporters_str = ", ".join(exporters_added)
        logger.info(f"✓ OpenTelemetry initialized: service={service_name}, version={service_version}, exporters=[{exporters_str}]")
        return True

    except ImportError as e:
        logger.warning(f"⚠️  OpenTelemetry packages not installed: {e}")
        logger.warning("⚠️  Install with: pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-jaeger")
        return False

    except Exception as e:
        logger.warning(f"⚠️  Failed to initialize OpenTelemetry: {e}")
        logger.warning("⚠️  Continuing without tracing")
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
