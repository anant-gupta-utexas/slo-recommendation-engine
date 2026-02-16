"""Prometheus metrics instrumentation.

Defines and exports Prometheus metrics for monitoring the application.
Avoids high cardinality by omitting service_id from labels.
"""

from prometheus_client import Counter, Gauge, Histogram
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

# HTTP Request Metrics
http_requests_total = Counter(
    name="slo_engine_http_requests_total",
    documentation="Total number of HTTP requests",
    labelnames=["method", "endpoint", "status_code"],
)

http_request_duration_seconds = Histogram(
    name="slo_engine_http_request_duration_seconds",
    documentation="HTTP request duration in seconds",
    labelnames=["method", "endpoint", "status_code"],
    buckets=(
        0.005,  # 5ms
        0.01,  # 10ms
        0.025,  # 25ms
        0.05,  # 50ms
        0.1,  # 100ms
        0.25,  # 250ms
        0.5,  # 500ms
        1.0,  # 1s
        2.5,  # 2.5s
        5.0,  # 5s
        10.0,  # 10s
    ),
)

# Graph Traversal Metrics
graph_traversal_duration_seconds = Histogram(
    name="slo_engine_graph_traversal_duration_seconds",
    documentation="Graph traversal operation duration in seconds",
    labelnames=["direction", "depth"],
    buckets=(
        0.001,  # 1ms
        0.005,  # 5ms
        0.01,  # 10ms
        0.025,  # 25ms
        0.05,  # 50ms
        0.1,  # 100ms
        0.25,  # 250ms
        0.5,  # 500ms
        1.0,  # 1s
        2.5,  # 2.5s
    ),
)

# Database Metrics
db_connections_active = Gauge(
    name="slo_engine_db_connections_active",
    documentation="Current number of active database connections",
)

db_connections_idle = Gauge(
    name="slo_engine_db_connections_idle",
    documentation="Current number of idle database connections in pool",
)

db_pool_size = Gauge(
    name="slo_engine_db_pool_size",
    documentation="Configured database connection pool size",
)

# Cache Metrics
cache_hits_total = Counter(
    name="slo_engine_cache_hits_total",
    documentation="Total number of cache hits",
    labelnames=["cache_type"],
)

cache_misses_total = Counter(
    name="slo_engine_cache_misses_total",
    documentation="Total number of cache misses",
    labelnames=["cache_type"],
)

# Graph Ingestion Metrics
graph_nodes_upserted_total = Counter(
    name="slo_engine_graph_nodes_upserted_total",
    documentation="Total number of service nodes upserted",
    labelnames=["discovery_source"],
)

graph_edges_upserted_total = Counter(
    name="slo_engine_graph_edges_upserted_total",
    documentation="Total number of dependency edges upserted",
    labelnames=["discovery_source"],
)

circular_dependencies_detected_total = Counter(
    name="slo_engine_circular_dependencies_detected_total",
    documentation="Total number of circular dependencies detected",
)

# Rate Limiting Metrics
rate_limit_exceeded_total = Counter(
    name="slo_engine_rate_limit_exceeded_total",
    documentation="Total number of requests rejected due to rate limiting",
    labelnames=["client_id", "endpoint"],
)

# SLO Recommendation Batch Metrics
slo_batch_recommendations_total = Counter(
    name="slo_engine_slo_batch_recommendations_total",
    documentation="Total number of SLO batch recommendation runs",
    labelnames=["status"],  # success, failure
)

slo_batch_recommendations_duration_seconds = Histogram(
    name="slo_engine_slo_batch_recommendations_duration_seconds",
    documentation="SLO batch recommendation computation duration in seconds",
    buckets=(
        1.0,    # 1s
        5.0,    # 5s
        10.0,   # 10s
        30.0,   # 30s
        60.0,   # 1m
        120.0,  # 2m
        300.0,  # 5m
        600.0,  # 10m
        1800.0, # 30m
        3600.0, # 1h
    ),
)


def get_metrics_content() -> tuple[bytes, str]:
    """Generate Prometheus metrics in exposition format.

    Returns:
        Tuple of (metrics_bytes, content_type)
    """
    return generate_latest(), CONTENT_TYPE_LATEST


def record_http_request(
    method: str,
    endpoint: str,
    status_code: int,
    duration: float,
) -> None:
    """Record HTTP request metrics.

    Args:
        method: HTTP method (GET, POST, etc.)
        endpoint: API endpoint path
        status_code: HTTP status code
        duration: Request duration in seconds
    """
    http_requests_total.labels(
        method=method,
        endpoint=endpoint,
        status_code=str(status_code),
    ).inc()

    http_request_duration_seconds.labels(
        method=method,
        endpoint=endpoint,
        status_code=str(status_code),
    ).observe(duration)


def record_graph_traversal(
    direction: str,
    depth: int,
    duration: float,
) -> None:
    """Record graph traversal metrics.

    Args:
        direction: Traversal direction (upstream, downstream, bidirectional)
        depth: Maximum traversal depth
        duration: Traversal duration in seconds
    """
    graph_traversal_duration_seconds.labels(
        direction=direction,
        depth=str(depth),
    ).observe(duration)


def update_db_pool_metrics(
    active: int,
    idle: int,
    pool_size: int,
) -> None:
    """Update database connection pool metrics.

    Args:
        active: Number of active connections
        idle: Number of idle connections
        pool_size: Total pool size
    """
    db_connections_active.set(active)
    db_connections_idle.set(idle)
    db_pool_size.set(pool_size)


def record_cache_hit(cache_type: str) -> None:
    """Record cache hit.

    Args:
        cache_type: Type of cache (e.g., 'subgraph', 'service')
    """
    cache_hits_total.labels(cache_type=cache_type).inc()


def record_cache_miss(cache_type: str) -> None:
    """Record cache miss.

    Args:
        cache_type: Type of cache (e.g., 'subgraph', 'service')
    """
    cache_misses_total.labels(cache_type=cache_type).inc()


def record_graph_ingestion(
    nodes_upserted: int,
    edges_upserted: int,
    discovery_source: str,
) -> None:
    """Record graph ingestion metrics.

    Args:
        nodes_upserted: Number of service nodes upserted
        edges_upserted: Number of dependency edges upserted
        discovery_source: Source of discovery (manual, otel_service_graph, etc.)
    """
    graph_nodes_upserted_total.labels(
        discovery_source=discovery_source
    ).inc(nodes_upserted)
    graph_edges_upserted_total.labels(
        discovery_source=discovery_source
    ).inc(edges_upserted)


def record_circular_dependency_detected() -> None:
    """Record detection of a circular dependency."""
    circular_dependencies_detected_total.inc()


def record_rate_limit_exceeded(
    client_id: str,
    endpoint: str,
) -> None:
    """Record rate limit exceeded event.

    Args:
        client_id: Client identifier (API key ID or IP)
        endpoint: Endpoint that was rate limited
    """
    rate_limit_exceeded_total.labels(
        client_id=client_id,
        endpoint=endpoint,
    ).inc()


def record_batch_recommendation_run(
    status: str,
    duration: float,
) -> None:
    """Record SLO batch recommendation run metrics.

    Args:
        status: Run status (success or failure)
        duration: Run duration in seconds
    """
    slo_batch_recommendations_total.labels(status=status).inc()
    slo_batch_recommendations_duration_seconds.observe(duration)
