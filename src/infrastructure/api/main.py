"""
FastAPI application entry point.

Implements the API layer of the Infrastructure following Clean Architecture.
This module sets up the FastAPI app, registers routes, middleware, and exception handlers.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.infrastructure.database.config import dispose_db, init_db
from src.infrastructure.observability import (
    configure_logging,
    instrument_fastapi_app,
    setup_tracing,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.

    Startup:
    - Configure observability (logging, tracing)
    - Initialize database connection pool
    - Instrument FastAPI with OpenTelemetry
    - Start background task scheduler

    Shutdown:
    - Shutdown background task scheduler
    - Dispose database connection pool
    """
    # Startup: Configure observability
    configure_logging()
    setup_tracing()

    # Initialize database
    await init_db()

    # Instrument FastAPI after app is created
    instrument_fastapi_app(app)

    # Start background task scheduler
    from src.infrastructure.tasks.scheduler import start_scheduler
    await start_scheduler()

    yield

    # Shutdown: Stop scheduler first, then dispose DB
    from src.infrastructure.tasks.scheduler import shutdown_scheduler
    await shutdown_scheduler()
    await dispose_db()


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        FastAPI: Configured FastAPI application instance
    """
    app = FastAPI(
        title="SLO Recommendation Engine API",
        description=(
            "Dependency-aware SLO recommendation system that ingests service "
            "dependency graphs and provides intelligent SLO recommendations."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # CORS middleware (should be first)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: Configure from settings for production
        allow_credentials=False,  # Cannot use credentials with wildcard origins
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Custom middleware (order matters: last added = first executed)
    from .middleware.error_handler import ErrorHandlerMiddleware
    from .middleware.logging_middleware import LoggingMiddleware
    from .middleware.metrics_middleware import MetricsMiddleware
    from .middleware.rate_limit import RateLimitMiddleware

    app.add_middleware(ErrorHandlerMiddleware)  # Outermost: catches all errors
    app.add_middleware(MetricsMiddleware)  # Record metrics for all requests
    app.add_middleware(LoggingMiddleware)  # Log all requests
    app.add_middleware(RateLimitMiddleware)  # Rate limiting

    # Register routes
    from .routes import (
        constraint_analysis,
        dependencies,
        health,
        impact_analysis,
        recommendations,
        slo_lifecycle,
    )

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(
        dependencies.router, prefix="/api/v1/services", tags=["Dependencies"]
    )
    app.include_router(
        recommendations.router,
        prefix="/api/v1/services",
        tags=["SLO Recommendations"],
    )
    app.include_router(
        constraint_analysis.router,
        prefix="/api/v1/services",
        tags=["Constraint Analysis"],
    )
    app.include_router(
        slo_lifecycle.router,
        prefix="/api/v1/services",
        tags=["SLO Lifecycle"],
    )
    app.include_router(
        impact_analysis.router,
        prefix="/api/v1/slos",
        tags=["Impact Analysis"],
    )

    # Register exception handlers for proper RFC 7807 format
    from fastapi.exceptions import HTTPException, RequestValidationError
    from .schemas.error_schema import ProblemDetails

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc: HTTPException):
        """Convert HTTPException to RFC 7807 Problem Details."""
        import uuid
        correlation_id = getattr(request.state, "correlation_id", None) or str(uuid.uuid4())

        # Map status code to title
        status_texts = {
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            409: "Conflict",
            422: "Unprocessable Entity",
            429: "Too Many Requests",
            500: "Internal Server Error",
            503: "Service Unavailable",
        }

        problem = ProblemDetails(
            type="about:blank",
            title=status_texts.get(exc.status_code, "Error"),
            status=exc.status_code,
            detail=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            instance=request.url.path,
            correlation_id=correlation_id,
        )

        return JSONResponse(
            status_code=exc.status_code,
            content=problem.model_dump(exclude_none=True),
            headers={
                "Content-Type": "application/problem+json",
                "X-Correlation-ID": correlation_id,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc: RequestValidationError):
        """Convert Pydantic validation errors to RFC 7807 Problem Details."""
        import uuid
        correlation_id = getattr(request.state, "correlation_id", None) or str(uuid.uuid4())

        problem = ProblemDetails(
            type="about:blank",
            title="Unprocessable Entity",
            status=422,
            detail=f"Validation failed: {exc.errors()}",
            instance=request.url.path,
            correlation_id=correlation_id,
        )

        return JSONResponse(
            status_code=422,
            content=problem.model_dump(exclude_none=True),
            headers={
                "Content-Type": "application/problem+json",
                "X-Correlation-ID": correlation_id,
            },
        )

    # Root endpoint
    @app.get("/", status_code=status.HTTP_200_OK)
    async def root():
        """Root endpoint - API information."""
        return {
            "name": "SLO Recommendation Engine API",
            "version": "1.0.0",
            "status": "operational",
            "docs": "/docs",
        }

    return app


# Create app instance
app = create_app()
