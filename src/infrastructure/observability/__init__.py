"""Observability infrastructure module.

Provides OpenTelemetry tracing, structured logging, and Prometheus metrics.
"""

from src.infrastructure.observability.logging import configure_logging, get_logger
from src.infrastructure.observability.metrics import (
    get_metrics_content,
    record_cache_hit,
    record_cache_miss,
    record_circular_dependency_detected,
    record_graph_ingestion,
    record_graph_traversal,
    record_http_request,
    record_rate_limit_exceeded,
    update_db_pool_metrics,
)
from src.infrastructure.observability.tracing import (
    get_tracer,
    instrument_fastapi_app,
    setup_tracing,
)

__all__ = [
    # Logging
    "configure_logging",
    "get_logger",
    # Tracing
    "setup_tracing",
    "instrument_fastapi_app",
    "get_tracer",
    # Metrics
    "get_metrics_content",
    "record_http_request",
    "record_graph_traversal",
    "update_db_pool_metrics",
    "record_cache_hit",
    "record_cache_miss",
    "record_graph_ingestion",
    "record_circular_dependency_detected",
    "record_rate_limit_exceeded",
]
