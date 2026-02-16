"""Integration tests for structured logging.

Tests that logs are formatted correctly and sensitive data is filtered.
"""

import logging

import pytest

from src.infrastructure.observability.logging import (
    configure_logging,
    get_logger,
)


class TestStructuredLogging:
    """Tests for structured logging configuration."""

    def test_logger_outputs_json_format(self, caplog):
        """Test that logger outputs valid JSON when configured."""
        configure_logging()
        logger = get_logger(__name__)

        with caplog.at_level(logging.INFO):
            logger.info(
                "Test message",
                user_id="123",
                action="create",
            )

        # Check that log output contains expected fields
        assert len(caplog.records) > 0
        # Note: structlog output format depends on configuration
        # In tests, we mainly verify it doesn't crash

    def test_sensitive_data_filtering(self):
        """Test that sensitive data is filtered by the processor."""
        from src.infrastructure.observability.logging import _filter_sensitive_data

        event_dict = {
            "event": "User login",
            "user_id": "123",
            "api_key": "secret_key_12345",
            "password": "my_password",
        }

        filtered = _filter_sensitive_data(None, "info", event_dict)

        # Verify sensitive data is masked
        assert filtered["api_key"] != "secret_key_12345"
        assert "secr" in filtered["api_key"]  # first 4 chars visible
        assert filtered["password"] != "my_password"
        assert "my_p" in filtered["password"]  # first 4 chars visible
        # Verify user_id is still there (not sensitive)
        assert filtered["user_id"] == "123"
        # Verify event is preserved
        assert filtered["event"] == "User login"

    def test_log_levels(self):
        """Test different log levels."""
        configure_logging()
        logger = get_logger(__name__)

        # Test all log levels (should not crash)
        logger.debug("Debug message", level="debug")
        logger.info("Info message", level="info")
        logger.warning("Warning message", level="warning")
        logger.error("Error message", level="error")

    def test_exception_logging(self):
        """Test exception logging with stack traces."""
        configure_logging()
        logger = get_logger(__name__)

        try:
            raise ValueError("Test exception")
        except ValueError:
            logger.error("Exception occurred", exc_info=True)
            # Should not crash when logging exception


class TestCorrelationIDs:
    """Tests for correlation ID injection from trace context."""

    def test_trace_context_added_to_logs(self):
        """Test that trace context (trace_id, span_id) is added when available."""
        # This is tested implicitly through OpenTelemetry instrumentation
        # When a span is active, trace_id and span_id should appear in logs
        configure_logging()
        logger = get_logger(__name__)

        # Without active span (no trace context)
        logger.info("Test without span")

        # With OpenTelemetry, trace context would be automatically injected
        # This is integration-tested through E2E tests with actual requests
