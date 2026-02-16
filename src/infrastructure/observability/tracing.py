"""OpenTelemetry distributed tracing setup.

Configures OpenTelemetry SDK with OTLP exporter for distributed tracing.
Includes auto-instrumentation for FastAPI, SQLAlchemy, and HTTPX.
"""

import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

from src.infrastructure.config import get_settings

logger = logging.getLogger(__name__)


def setup_tracing() -> TracerProvider:
    """Setup OpenTelemetry tracing with OTLP exporter.

    Configures:
    - TracerProvider with service name and version
    - OTLP exporter for sending traces to collector
    - Trace sampling based on configured sample rate
    - Auto-instrumentation for HTTPX and SQLAlchemy

    Returns:
        TracerProvider instance

    Note:
        FastAPI must be instrumented separately after app creation
        using instrument_fastapi_app()
    """
    settings = get_settings()
    otel_config = settings.observability

    # Create resource with service information
    resource = Resource.create(
        {
            "service.name": otel_config.service_name,
            "service.version": "0.1.0",  # TODO: Get from package metadata
            "deployment.environment": settings.environment,
        }
    )

    # Create tracer provider with sampling
    sampler = TraceIdRatioBased(otel_config.trace_sample_rate)
    provider = TracerProvider(resource=resource, sampler=sampler)

    # Create OTLP exporter
    try:
        otlp_exporter = OTLPSpanExporter(
            endpoint=otel_config.exporter_otlp_endpoint,
            insecure=True,  # Use False in production with TLS
        )

        # Add batch span processor for better performance
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

        logger.info(
            "OpenTelemetry tracing configured",
            extra={
                "service_name": otel_config.service_name,
                "otlp_endpoint": otel_config.exporter_otlp_endpoint,
                "sample_rate": otel_config.trace_sample_rate,
            },
        )
    except Exception as e:
        logger.warning(
            "Failed to configure OTLP exporter, tracing will be disabled",
            extra={"error": str(e)},
        )

    # Set as global tracer provider
    trace.set_tracer_provider(provider)

    # Auto-instrument libraries
    try:
        HTTPXClientInstrumentor().instrument()
        SQLAlchemyInstrumentor().instrument()
        logger.info("Auto-instrumentation enabled for HTTPX and SQLAlchemy")
    except Exception as e:
        logger.warning(
            "Failed to enable auto-instrumentation",
            extra={"error": str(e)},
        )

    return provider


def instrument_fastapi_app(app) -> None:
    """Instrument FastAPI application with OpenTelemetry.

    Must be called after FastAPI app is created.

    Args:
        app: FastAPI application instance
    """
    try:
        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI auto-instrumentation enabled")
    except Exception as e:
        logger.warning(
            "Failed to instrument FastAPI app",
            extra={"error": str(e)},
        )


def get_tracer(name: str):
    """Get OpenTelemetry tracer for manual instrumentation.

    Args:
        name: Tracer name (typically __name__)

    Returns:
        Tracer instance for creating spans

    Example:
        >>> tracer = get_tracer(__name__)
        >>> with tracer.start_as_current_span("operation_name") as span:
        ...     span.set_attribute("key", "value")
        ...     # Do work
    """
    return trace.get_tracer(name)
