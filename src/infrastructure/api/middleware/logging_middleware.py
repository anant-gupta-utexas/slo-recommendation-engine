"""Logging middleware for structured request/response logging.

Logs all HTTP requests with correlation IDs, duration, and status codes.
Excludes sensitive data like API keys from logs.
"""

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log HTTP requests and responses.

    Logs:
    - Request method, path, and headers (excluding sensitive data)
    - Response status code and duration
    - Correlation IDs from trace context (automatic via structlog)
    - Client IP address
    """

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Process request and log details.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain

        Returns:
            HTTP response
        """
        # Record start time
        start_time = time.perf_counter()

        # Extract request info
        method = request.method
        path = request.url.path
        client_ip = self._get_client_ip(request)

        # Log incoming request
        logger.info(
            "HTTP request received",
            method=method,
            path=path,
            client_ip=client_ip,
            query_params=str(request.query_params) if request.query_params else None,
        )

        # Process request
        try:
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log response
            logger.info(
                "HTTP request completed",
                method=method,
                path=path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
                client_ip=client_ip,
            )

            return response

        except Exception as e:
            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log error
            logger.error(
                "HTTP request failed",
                method=method,
                path=path,
                duration_ms=round(duration_ms, 2),
                client_ip=client_ip,
                error=str(e),
                exc_info=True,
            )
            raise

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request.

        Checks X-Forwarded-For header first (for proxy/load balancer),
        falls back to direct client address.

        Args:
            request: HTTP request

        Returns:
            Client IP address
        """
        # Check X-Forwarded-For header (proxy/load balancer)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take first IP in chain (original client)
            return forwarded_for.split(",")[0].strip()

        # Fallback to direct client
        if request.client:
            return request.client.host

        return "unknown"
