"""
RFC 7807 Problem Details error response schemas.

Implements standard error response format for the API.
"""

from typing import Any

from pydantic import BaseModel, Field


class ProblemDetails(BaseModel):
    """
    RFC 7807 Problem Details for HTTP APIs.

    Standard error response format that provides machine-readable details
    about errors in a consistent structure.
    """

    type: str = Field(
        ...,
        description="URI reference that identifies the problem type",
        example="https://slo-engine.internal/errors/invalid-schema",
    )
    title: str = Field(..., description="Short, human-readable summary of the problem")
    status: int = Field(..., description="HTTP status code", ge=100, le=599)
    detail: str = Field(
        ..., description="Human-readable explanation specific to this occurrence"
    )
    instance: str = Field(
        ..., description="URI reference that identifies the specific occurrence"
    )
    correlation_id: str | None = Field(
        None, description="Correlation ID for request tracing"
    )
    retry_after_seconds: int | None = Field(
        None,
        description="Seconds to wait before retrying (for 429 responses)",
        ge=0,
    )
    field: str | None = Field(
        None, description="Field name that caused the error (for validation errors)"
    )
    value: Any | None = Field(
        None, description="Invalid value that caused the error (for validation errors)"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "examples": [
                {
                    "type": "https://slo-engine.internal/errors/invalid-schema",
                    "title": "Invalid Request Schema",
                    "status": 400,
                    "detail": "Field 'nodes[0].service_id' is required but missing",
                    "instance": "/api/v1/services/dependencies",
                },
                {
                    "type": "https://slo-engine.internal/errors/service-not-found",
                    "title": "Service Not Found",
                    "status": 404,
                    "detail": "Service with ID 'nonexistent-service' is not registered",
                    "instance": "/api/v1/services/nonexistent-service/dependencies",
                },
                {
                    "type": "https://slo-engine.internal/errors/rate-limit-exceeded",
                    "title": "Rate Limit Exceeded",
                    "status": 429,
                    "detail": "API rate limit of 10 req/min exceeded. Retry after 45 seconds.",
                    "instance": "/api/v1/services/dependencies",
                    "retry_after_seconds": 45,
                },
            ]
        }
