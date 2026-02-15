"""Global error handling middleware.

Converts all exceptions to RFC 7807 Problem Details format for consistent error responses.
Includes correlation IDs for request tracing.
"""

import logging
import uuid
from typing import Any
from fastapi import Request, status
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.exc import IntegrityError, OperationalError

from src.infrastructure.api.schemas.error_schema import ProblemDetails

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Middleware to handle all exceptions and return RFC 7807 Problem Details."""

    async def dispatch(self, request: Request, call_next):
        """Catch all exceptions and convert to Problem Details format.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain

        Returns:
            Response with Problem Details format on error
        """
        # Generate correlation ID for request tracing
        correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        try:
            response = await call_next(request)
            # Add correlation ID to successful responses
            response.headers["X-Correlation-ID"] = correlation_id
            return response

        except Exception as exc:
            # Log exception with correlation ID
            logger.error(
                f"Request failed with correlation_id={correlation_id}",
                exc_info=exc,
                extra={
                    "correlation_id": correlation_id,
                    "path": request.url.path,
                    "method": request.method,
                },
            )

            # Convert to Problem Details
            problem = self._exception_to_problem(exc, request, correlation_id)
            return self._create_response(problem)

    def _exception_to_problem(
        self, exc: Exception, request: Request, correlation_id: str
    ) -> ProblemDetails:
        """Convert exception to RFC 7807 Problem Details.

        Args:
            exc: Exception that was raised
            request: Request that caused the exception
            correlation_id: Correlation ID for tracing

        Returns:
            ProblemDetails object
        """
        # Map exception types to HTTP status codes and Problem Details
        if isinstance(exc, HTTPException):
            # FastAPI HTTPException (from verify_api_key, etc.)
            return ProblemDetails(
                type="about:blank",  # Standard for simple errors
                title=self._get_status_text(exc.status_code),
                status=exc.status_code,
                detail=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                instance=request.url.path,
                correlation_id=correlation_id,
            )

        if isinstance(exc, ValueError):
            return ProblemDetails(
                type="https://httpstatuses.com/400",
                title="Bad Request",
                status=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
                instance=request.url.path,
                correlation_id=correlation_id,
            )

        if isinstance(exc, IntegrityError):
            # Database constraint violation
            return ProblemDetails(
                type="https://httpstatuses.com/409",
                title="Conflict",
                status=status.HTTP_409_CONFLICT,
                detail="Resource conflict or constraint violation",
                instance=request.url.path,
                correlation_id=correlation_id,
            )

        if isinstance(exc, OperationalError):
            # Database connection/operational error
            return ProblemDetails(
                type="https://httpstatuses.com/503",
                title="Service Unavailable",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database is temporarily unavailable",
                instance=request.url.path,
                correlation_id=correlation_id,
            )

        # Default to 500 Internal Server Error
        return ProblemDetails(
            type="https://httpstatuses.com/500",
            title="Internal Server Error",
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
            instance=request.url.path,
            correlation_id=correlation_id,
        )

    def _get_status_text(self, status_code: int) -> str:
        """Get human-readable status text for HTTP status code.

        Args:
            status_code: HTTP status code

        Returns:
            Status text (e.g., "Unauthorized" for 401)
        """
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
        return status_texts.get(status_code, "Error")

    def _create_response(self, problem: ProblemDetails) -> JSONResponse:
        """Create JSONResponse from ProblemDetails.

        Args:
            problem: Problem Details object

        Returns:
            JSONResponse with appropriate status code and headers
        """
        return JSONResponse(
            status_code=problem.status,
            content=problem.model_dump(exclude_none=True),
            headers={
                "Content-Type": "application/problem+json",
                "X-Correlation-ID": problem.correlation_id or "",
            },
        )
