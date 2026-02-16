"""Metrics middleware for recording HTTP request metrics.

Records Prometheus metrics for all HTTP requests including duration,
status codes, and endpoints.
"""

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.infrastructure.observability.metrics import record_http_request


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to record HTTP request metrics.

    Records:
    - Total request count per endpoint
    - Request duration histogram
    - Status code distribution

    Labels: method, endpoint, status_code
    Note: Does NOT include service_id to avoid high cardinality
    """

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Process request and record metrics.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain

        Returns:
            HTTP response
        """
        # Record start time
        start_time = time.perf_counter()

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration = time.perf_counter() - start_time

        # Extract endpoint (remove query params for better grouping)
        endpoint = self._normalize_endpoint(request)

        # Record metrics
        record_http_request(
            method=request.method,
            endpoint=endpoint,
            status_code=response.status_code,
            duration=duration,
        )

        return response

    def _normalize_endpoint(self, request: Request) -> str:
        """Normalize endpoint path for metrics.

        Removes UUIDs and other variable path components to avoid
        high cardinality in metrics.

        Args:
            request: HTTP request

        Returns:
            Normalized endpoint path

        Examples:
            /services/123e4567-e89b-12d3-a456-426614174000 -> /services/{id}
            /services/123e4567-e89b-12d3-a456-426614174000/dependencies -> /services/{id}/dependencies
        """
        path = request.url.path

        # If we have route match from FastAPI, use that
        if hasattr(request, "scope") and "route" in request.scope:
            route = request.scope["route"]
            if hasattr(route, "path"):
                return route.path

        # Fallback: basic normalization
        # Replace UUID-like patterns with {id}
        import re

        uuid_pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
        normalized = re.sub(uuid_pattern, "{id}", path, flags=re.IGNORECASE)

        return normalized
