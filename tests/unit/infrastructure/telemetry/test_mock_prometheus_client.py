"""Unit tests for MockPrometheusClient.

This module tests the mock Prometheus client implementation,
verifying that it correctly returns seed data and handles edge cases.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.infrastructure.telemetry.mock_prometheus_client import MockPrometheusClient
from src.infrastructure.telemetry.seed_data import SEED_DATA


class TestMockPrometheusClient:
    """Unit tests for MockPrometheusClient."""

    @pytest.fixture
    def client(self) -> MockPrometheusClient:
        """Create MockPrometheusClient with default seed data.

        Returns:
            MockPrometheusClient instance
        """
        return MockPrometheusClient()

    @pytest.fixture
    def custom_seed_data(self) -> dict:
        """Create custom seed data for testing.

        Returns:
            Custom seed data dict
        """
        return {
            "test-service": {
                "availability": {
                    "base": 0.999,
                    "variance": 0.002,
                    "good_events": 9_990_000,
                    "total_events": 10_000_000,
                    "sample_count": 720,
                },
                "latency": {
                    "p50_ms": 50.0,
                    "p95_ms": 150.0,
                    "p99_ms": 300.0,
                    "p999_ms": 600.0,
                    "sample_count": 720,
                },
                "completeness": {
                    "30_days": 1.0,
                    "90_days": 1.0,
                },
                "days_available": 30,
            }
        }

    async def test_get_availability_sli_returns_data(
        self, client: MockPrometheusClient
    ):
        """Test getting availability SLI for service with data.

        Args:
            client: MockPrometheusClient fixture
        """
        # Act
        result = await client.get_availability_sli("payment-service", 30)

        # Assert
        assert result is not None
        assert result.service_id == "payment-service"
        assert 0.0 <= result.availability_ratio <= 1.0
        assert result.good_events <= result.total_events
        assert result.total_events > 0
        assert result.sample_count > 0
        assert result.window_end > result.window_start
        assert (result.window_end - result.window_start).days == 30

    async def test_get_availability_sli_scales_by_window(
        self, client: MockPrometheusClient
    ):
        """Test that availability data scales proportionally with window size.

        Args:
            client: MockPrometheusClient fixture
        """
        # Act: Get 30-day and 15-day windows
        result_30d = await client.get_availability_sli("payment-service", 30)
        result_15d = await client.get_availability_sli("payment-service", 15)

        # Assert: 15-day should have roughly half the events
        assert result_30d is not None
        assert result_15d is not None
        assert result_15d.total_events < result_30d.total_events
        # Should be approximately half (within 10% tolerance due to integer rounding)
        ratio = result_15d.total_events / result_30d.total_events
        assert 0.45 <= ratio <= 0.55

    async def test_get_availability_sli_no_data_service(
        self, client: MockPrometheusClient
    ):
        """Test getting availability for service with no data.

        Args:
            client: MockPrometheusClient fixture
        """
        # Act
        result = await client.get_availability_sli("uninstrumented-service", 30)

        # Assert
        assert result is None

    async def test_get_availability_sli_nonexistent_service(
        self, client: MockPrometheusClient
    ):
        """Test getting availability for service not in seed data.

        Args:
            client: MockPrometheusClient fixture
        """
        # Act
        result = await client.get_availability_sli("nonexistent-service", 30)

        # Assert
        assert result is None

    async def test_get_availability_sli_window_exceeds_available_days(
        self, client: MockPrometheusClient
    ):
        """Test requesting more days than available returns None.

        Args:
            client: MockPrometheusClient fixture
        """
        # Act: Cold-start service has only 10 days of data
        result = await client.get_availability_sli("new-checkout-service", 30)

        # Assert
        assert result is None

    async def test_get_latency_percentiles_returns_data(
        self, client: MockPrometheusClient
    ):
        """Test getting latency percentiles for service with data.

        Args:
            client: MockPrometheusClient fixture
        """
        # Act
        result = await client.get_latency_percentiles("payment-service", 30)

        # Assert
        assert result is not None
        assert result.service_id == "payment-service"
        assert result.p50_ms > 0
        assert result.p95_ms > 0
        assert result.p99_ms > 0
        assert result.p999_ms > 0
        # Verify percentile ordering
        assert result.p50_ms <= result.p95_ms <= result.p99_ms <= result.p999_ms
        assert result.sample_count > 0
        assert result.window_end > result.window_start

    async def test_get_latency_percentiles_scales_sample_count(
        self, client: MockPrometheusClient
    ):
        """Test that latency sample count scales with window size.

        Args:
            client: MockPrometheusClient fixture
        """
        # Act
        result_30d = await client.get_latency_percentiles("payment-service", 30)
        result_15d = await client.get_latency_percentiles("payment-service", 15)

        # Assert
        assert result_30d is not None
        assert result_15d is not None
        assert result_15d.sample_count < result_30d.sample_count
        # Percentile values should remain the same (they're aggregates, not sums)
        assert result_15d.p99_ms == result_30d.p99_ms

    async def test_get_latency_percentiles_no_data_service(
        self, client: MockPrometheusClient
    ):
        """Test getting latency for service with no data.

        Args:
            client: MockPrometheusClient fixture
        """
        # Act
        result = await client.get_latency_percentiles("uninstrumented-service", 30)

        # Assert
        assert result is None

    async def test_get_latency_percentiles_window_exceeds_available(
        self, client: MockPrometheusClient
    ):
        """Test requesting latency for more days than available.

        Args:
            client: MockPrometheusClient fixture
        """
        # Act
        result = await client.get_latency_percentiles("new-checkout-service", 30)

        # Assert
        assert result is None

    async def test_get_rolling_availability_returns_buckets(
        self, client: MockPrometheusClient
    ):
        """Test getting rolling availability returns correct number of buckets.

        Args:
            client: MockPrometheusClient fixture
        """
        # Act: 30 days with daily buckets = 30 buckets
        result = await client.get_rolling_availability("payment-service", 30)

        # Assert
        assert len(result) == 30
        # All values should be valid availability ratios
        for value in result:
            assert 0.0 <= value <= 1.0

    async def test_get_rolling_availability_has_variance(
        self, client: MockPrometheusClient
    ):
        """Test that rolling availability shows realistic variance.

        Args:
            client: MockPrometheusClient fixture
        """
        # Act
        result = await client.get_rolling_availability("payment-service", 30)

        # Assert: Should have some variance (not all identical)
        unique_values = set(result)
        assert len(unique_values) > 1, "Should have variance, not all identical values"

        # Values should cluster around base availability
        mean = sum(result) / len(result)
        base_avail = SEED_DATA["payment-service"]["availability"]["base"]
        # Mean should be within 2% of base (allowing for random variance)
        assert abs(mean - base_avail) < 0.02

    async def test_get_rolling_availability_reproducible(
        self, client: MockPrometheusClient
    ):
        """Test that rolling availability is reproducible (same seed).

        Args:
            client: MockPrometheusClient fixture
        """
        # Act: Get same data twice
        result1 = await client.get_rolling_availability("payment-service", 30)
        result2 = await client.get_rolling_availability("payment-service", 30)

        # Assert: Should be identical
        assert result1 == result2

    async def test_get_rolling_availability_custom_bucket_hours(
        self, client: MockPrometheusClient
    ):
        """Test rolling availability with custom bucket size.

        Args:
            client: MockPrometheusClient fixture
        """
        # Act: 30 days with 12-hour buckets = 60 buckets
        result = await client.get_rolling_availability(
            "payment-service", 30, bucket_hours=12
        )

        # Assert
        assert len(result) == 60

    async def test_get_rolling_availability_no_data_service(
        self, client: MockPrometheusClient
    ):
        """Test getting rolling availability for service with no data.

        Args:
            client: MockPrometheusClient fixture
        """
        # Act
        result = await client.get_rolling_availability("uninstrumented-service", 30)

        # Assert
        assert result == []

    async def test_get_rolling_availability_window_exceeds_available(
        self, client: MockPrometheusClient
    ):
        """Test requesting rolling availability for more days than available.

        Args:
            client: MockPrometheusClient fixture
        """
        # Act
        result = await client.get_rolling_availability("new-checkout-service", 30)

        # Assert
        assert result == []

    async def test_get_data_completeness_30_days(self, client: MockPrometheusClient):
        """Test getting 30-day data completeness.

        Args:
            client: MockPrometheusClient fixture
        """
        # Act
        result = await client.get_data_completeness("payment-service", 30)

        # Assert
        assert 0.0 <= result <= 1.0
        assert result == SEED_DATA["payment-service"]["completeness"]["30_days"]

    async def test_get_data_completeness_90_days(self, client: MockPrometheusClient):
        """Test getting 90-day data completeness.

        Args:
            client: MockPrometheusClient fixture
        """
        # Act
        result = await client.get_data_completeness("payment-service", 90)

        # Assert
        assert result == SEED_DATA["payment-service"]["completeness"]["90_days"]

    async def test_get_data_completeness_cold_start_service(
        self, client: MockPrometheusClient
    ):
        """Test data completeness for cold-start service (< 90% at 30 days).

        Args:
            client: MockPrometheusClient fixture
        """
        # Act
        result = await client.get_data_completeness("new-checkout-service", 30)

        # Assert: Should be < 0.90 to trigger cold-start
        assert result < 0.90
        assert result == 0.33  # 10 days / 30 days

    async def test_get_data_completeness_no_data_service(
        self, client: MockPrometheusClient
    ):
        """Test data completeness for service with no data.

        Args:
            client: MockPrometheusClient fixture
        """
        # Act
        result = await client.get_data_completeness("uninstrumented-service", 30)

        # Assert
        assert result == 0.0

    async def test_get_data_completeness_custom_window(
        self, client: MockPrometheusClient
    ):
        """Test data completeness for non-standard window (e.g., 15 days).

        Args:
            client: MockPrometheusClient fixture
        """
        # Act: 15-day window for service with 30 days available
        result = await client.get_data_completeness("payment-service", 15)

        # Assert: Should calculate as days_available / window_days
        assert result == 1.0  # 30 days available >= 15 days requested

    async def test_custom_seed_data(self, custom_seed_data: dict):
        """Test creating client with custom seed data.

        Args:
            custom_seed_data: Custom seed data fixture
        """
        # Arrange
        client = MockPrometheusClient(seed_data=custom_seed_data)

        # Act
        avail = await client.get_availability_sli("test-service", 30)
        latency = await client.get_latency_percentiles("test-service", 30)
        rolling = await client.get_rolling_availability("test-service", 30)
        completeness = await client.get_data_completeness("test-service", 30)

        # Assert
        assert avail is not None
        assert avail.service_id == "test-service"
        assert latency is not None
        assert latency.service_id == "test-service"
        assert len(rolling) == 30
        assert completeness == 1.0

    async def test_all_seed_data_services_have_required_fields(
        self, client: MockPrometheusClient
    ):
        """Test that all services in seed data have required fields.

        Args:
            client: MockPrometheusClient fixture
        """
        # Act & Assert
        for service_id, config in SEED_DATA.items():
            assert "days_available" in config
            assert "completeness" in config

            if config["days_available"] > 0:
                # Services with data should have availability or latency
                has_avail = config.get("availability") is not None
                has_latency = config.get("latency") is not None
                assert has_avail or has_latency, f"{service_id} has no metrics"

    async def test_high_variance_service_shows_variance(
        self, client: MockPrometheusClient
    ):
        """Test that high-variance service shows more spread in rolling availability.

        Args:
            client: MockPrometheusClient fixture
        """
        # Act: Compare low-variance vs high-variance services
        low_variance = await client.get_rolling_availability("auth-service", 30)
        high_variance = await client.get_rolling_availability(
            "legacy-report-service", 30
        )

        # Assert: High variance service should have wider spread
        def calculate_std_dev(values: list[float]) -> float:
            mean = sum(values) / len(values)
            variance = sum((x - mean) ** 2 for x in values) / len(values)
            return variance**0.5

        low_std = calculate_std_dev(low_variance)
        high_std = calculate_std_dev(high_variance)
        assert high_std > low_std

    async def test_multiple_services_have_different_data(
        self, client: MockPrometheusClient
    ):
        """Test that different services return different data.

        Args:
            client: MockPrometheusClient fixture
        """
        # Act
        payment_avail = await client.get_availability_sli("payment-service", 30)
        auth_avail = await client.get_availability_sli("auth-service", 30)

        # Assert: Different services should have different availability
        assert payment_avail is not None
        assert auth_avail is not None
        assert (
            payment_avail.availability_ratio != auth_avail.availability_ratio
        ), "Services should have different availability ratios"
