"""
Health check endpoints.

Provides liveness and readiness probes for Kubernetes.
Also provides Prometheus metrics endpoint.
"""

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.cache.health import check_redis_health
from src.infrastructure.database.health import check_database_health_with_session
from src.infrastructure.database.session import get_async_session
from src.infrastructure.observability.metrics import get_metrics_content

router = APIRouter()


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Liveness probe",
    description="Check if the service is alive",
    tags=["Health"],
)
async def liveness() -> dict:
    """
    Liveness probe - check if the process is running.

    This endpoint always returns 200 if the process is alive.
    Used by Kubernetes to determine if the pod should be restarted.
    """
    return {
        "status": "healthy",
        "service": "slo-recommendation-engine",
    }


@router.get(
    "/health/ready",
    status_code=status.HTTP_200_OK,
    summary="Readiness probe",
    description="Check if the service is ready to accept traffic",
    tags=["Health"],
    responses={
        200: {"description": "Service is ready"},
        503: {"description": "Service is not ready (dependencies unavailable)"},
    },
)
async def readiness(
    session: AsyncSession = Depends(get_async_session),
) -> JSONResponse:
    """
    Readiness probe - check if the service can handle requests.

    Checks:
    - Database connectivity

    Returns 200 if all dependencies are healthy, 503 otherwise.
    Used by Kubernetes to determine if the pod should receive traffic.
    """
    checks = {}

    # Check database
    db_healthy = await check_database_health_with_session(session)
    checks["database"] = "healthy" if db_healthy else "unhealthy"

    # Check Redis
    redis_healthy = await check_redis_health()
    checks["redis"] = "healthy" if redis_healthy else "unhealthy"

    # Determine overall health
    all_healthy = all(v == "healthy" for v in checks.values())

    if all_healthy:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ready", "checks": checks},
        )
    else:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "checks": checks},
        )


@router.get(
    "/metrics",
    status_code=status.HTTP_200_OK,
    summary="Prometheus metrics",
    description="Export Prometheus metrics in exposition format",
    tags=["Observability"],
    response_class=Response,
)
async def metrics() -> Response:
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus exposition format for scraping.

    Metrics include:
    - HTTP request counts and durations
    - Graph traversal performance
    - Database connection pool stats
    - Cache hit/miss rates
    - Rate limiting counters
    """
    metrics_bytes, content_type = get_metrics_content()

    return Response(
        content=metrics_bytes,
        media_type=content_type,
    )
