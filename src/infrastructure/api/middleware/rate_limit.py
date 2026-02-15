"""Rate limiting middleware using token bucket algorithm.

Implements per-client rate limiting with different limits for different endpoints.
Uses in-memory storage for MVP (can be migrated to Redis for distributed deployment).
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


@dataclass
class TokenBucket:
    """Token bucket for rate limiting.

    Implements a simple token bucket algorithm with refill rate.
    """

    capacity: int
    refill_rate: float  # tokens per second
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self) -> None:
        """Initialize bucket with full capacity."""
        self.tokens = float(self.capacity)
        self.last_refill = time.time()

    def consume(self, tokens: int = 1) -> bool:
        """Attempt to consume tokens from bucket.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens were consumed, False if insufficient tokens
        """
        self._refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def _refill(self) -> None:
        """Refill bucket based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        refill_amount = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + refill_amount)
        self.last_refill = now

    def time_until_available(self, tokens: int = 1) -> float:
        """Calculate seconds until requested tokens are available.

        Args:
            tokens: Number of tokens needed

        Returns:
            Seconds until tokens available (0 if already available)
        """
        self._refill()
        if self.tokens >= tokens:
            return 0.0
        shortage = tokens - self.tokens
        return shortage / self.refill_rate


# Rate limit configuration per endpoint pattern
# Format: (requests per window, window in seconds)
RATE_LIMITS = {
    "POST /api/v1/services/dependencies": (10, 60),  # 10 requests per minute
    "GET /api/v1/services/": (60, 60),  # 60 requests per minute for queries
    "default": (30, 60),  # 30 requests per minute for other endpoints
}

# Exclude health checks from rate limiting
EXCLUDED_PATHS = {
    "/api/v1/health",
    "/api/v1/health/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for rate limiting API requests.

    Uses token bucket algorithm with per-client tracking.
    """

    def __init__(self, app):
        """Initialize rate limiter with in-memory storage."""
        super().__init__(app)
        # client_id -> endpoint_pattern -> TokenBucket
        self.buckets: dict[str, dict[str, TokenBucket]] = defaultdict(dict)

    async def dispatch(self, request: Request, call_next):
        """Apply rate limiting to request.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain

        Returns:
            Response or 429 if rate limit exceeded
        """
        # Skip rate limiting for excluded paths
        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)

        # Get client identifier from request state (set by auth middleware)
        client_id = getattr(request.state, "client_id", "anonymous")

        # Determine rate limit for this endpoint
        endpoint_pattern = self._get_endpoint_pattern(request)
        limit_config = RATE_LIMITS.get(endpoint_pattern, RATE_LIMITS["default"])
        requests_per_window, window_seconds = limit_config

        # Get or create token bucket for this client + endpoint
        if endpoint_pattern not in self.buckets[client_id]:
            refill_rate = requests_per_window / window_seconds
            self.buckets[client_id][endpoint_pattern] = TokenBucket(
                capacity=requests_per_window, refill_rate=refill_rate
            )

        bucket = self.buckets[client_id][endpoint_pattern]

        # Try to consume token
        if not bucket.consume():
            # Rate limit exceeded
            retry_after = int(bucket.time_until_available()) + 1
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "type": "https://httpstatuses.com/429",
                    "title": "Too Many Requests",
                    "status": 429,
                    "detail": f"Rate limit exceeded. Try again in {retry_after} seconds.",
                    "instance": request.url.path,
                },
                headers={
                    "X-RateLimit-Limit": str(requests_per_window),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                    "Retry-After": str(retry_after),
                },
            )

        # Token consumed - proceed with request
        response = await call_next(request)

        # Add rate limit headers to response
        remaining_tokens = int(bucket.tokens)
        response.headers["X-RateLimit-Limit"] = str(requests_per_window)
        response.headers["X-RateLimit-Remaining"] = str(remaining_tokens)
        response.headers["X-RateLimit-Reset"] = str(
            int(time.time() + window_seconds)
        )

        return response

    def _get_endpoint_pattern(self, request: Request) -> str:
        """Determine endpoint pattern for rate limiting.

        Args:
            request: HTTP request

        Returns:
            Endpoint pattern matching RATE_LIMITS keys
        """
        method = request.method
        path = request.url.path

        # Match specific patterns
        if path == "/api/v1/services/dependencies":
            return f"{method} /api/v1/services/dependencies"

        # Match parameterized paths (e.g., /api/v1/services/{service-id}/dependencies)
        if path.startswith("/api/v1/services/") and path.endswith("/dependencies"):
            return "GET /api/v1/services/"

        # Default pattern
        return "default"
