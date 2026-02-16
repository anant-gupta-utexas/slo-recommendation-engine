"""Structured logging configuration with OpenTelemetry integration.

Configures structlog for JSON logging with correlation IDs from trace context.
Excludes sensitive data (API keys, tokens) from logs.
"""

import logging
import sys
from typing import Any

import structlog
from opentelemetry import trace

from src.infrastructure.config import get_settings


def configure_logging() -> None:
    """Configure structured logging with structlog.

    Sets up:
    - JSON logging format (when enabled)
    - Correlation IDs from OpenTelemetry trace context
    - Log level from configuration
    - Standard library logging integration
    """
    settings = get_settings()
    otel_config = settings.observability

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, otel_config.log_level.upper()),
    )

    # Build processor chain
    processors: list = [
        # Add log level
        structlog.stdlib.add_log_level,
        # Add timestamp
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        # Add trace context (correlation IDs)
        _add_trace_context,
        # Filter sensitive data
        _filter_sensitive_data,
        # Stack info for exceptions
        structlog.processors.StackInfoRenderer(),
        # Format exceptions
        structlog.dev.set_exc_info,
    ]

    # Add JSON or console renderer
    if otel_config.log_json_format:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _add_trace_context(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Add OpenTelemetry trace context to log events.

    Adds trace_id and span_id for correlation with distributed traces.

    Args:
        logger: Logger instance
        method_name: Log method name (info, error, etc.)
        event_dict: Log event dictionary

    Returns:
        Updated event dictionary with trace context
    """
    span = trace.get_current_span()
    if span:
        span_context = span.get_span_context()
        if span_context.is_valid:
            event_dict["trace_id"] = format(span_context.trace_id, "032x")
            event_dict["span_id"] = format(span_context.span_id, "016x")

    return event_dict


def _filter_sensitive_data(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Filter sensitive data from log events.

    Removes or masks:
    - API keys
    - Tokens
    - Passwords
    - Authorization headers

    Args:
        logger: Logger instance
        method_name: Log method name (info, error, etc.)
        event_dict: Log event dictionary

    Returns:
        Updated event dictionary with sensitive data filtered
    """
    # List of sensitive keys to filter
    sensitive_keys = {
        "api_key",
        "apikey",
        "token",
        "password",
        "secret",
        "authorization",
        "auth",
        "x-api-key",
    }

    def mask_value(key: str, value: Any) -> Any:
        """Mask sensitive values."""
        if isinstance(key, str) and key.lower() in sensitive_keys:
            if isinstance(value, str) and len(value) > 4:
                # Show first 4 chars, mask rest
                return f"{value[:4]}{'*' * (len(value) - 4)}"
            return "***REDACTED***"
        return value

    # Recursively filter sensitive data
    def filter_dict(d: dict[str, Any]) -> dict[str, Any]:
        return {k: mask_value(k, filter_dict(v) if isinstance(v, dict) else v) for k, v in d.items()}

    return filter_dict(event_dict)


def get_logger(name: str) -> structlog.BoundLogger:
    """Get structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Structured logger with bound context

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("User created", user_id="123", email="user@example.com")
    """
    return structlog.get_logger(name)
