"""Mock Prometheus client for testing and development.

This module provides a mock implementation of TelemetryQueryServiceInterface
that returns realistic telemetry data from seed data instead of querying a real
Prometheus instance. Useful for development, testing, and demos.
"""

from datetime import datetime, timedelta, timezone

from src.domain.entities.sli_data import AvailabilitySliData, LatencySliData
from src.domain.repositories.telemetry_query_service import (
    TelemetryQueryServiceInterface,
)
from src.infrastructure.telemetry.seed_data import (
    SEED_DATA,
    generate_rolling_availability,
    get_service_config,
)


class MockPrometheusClient(TelemetryQueryServiceInterface):
    """Mock Prometheus client that returns realistic telemetry from seed data.

    This client simulates Prometheus/Mimir queries by returning pre-configured
    data from the seed_data module. It's designed for:
    - Local development without Prometheus
    - Integration tests with predictable data
    - Demos and documentation
    """

    def __init__(self, seed_data: dict | None = None):
        """Initialize mock client with optional custom seed data.

        Args:
            seed_data: Optional custom seed data dict (defaults to SEED_DATA from seed_data.py)
                      Format: {service_id: {availability, latency, completeness, days_available}}
        """
        self._seed_data = seed_data if seed_data is not None else SEED_DATA

    async def get_availability_sli(
        self, service_id: str, window_days: int
    ) -> AvailabilitySliData | None:
        """Get availability SLI data from seed data.

        Args:
            service_id: Business identifier of the service
            window_days: Number of days to look back

        Returns:
            AvailabilitySliData if service has data, None otherwise
        """
        config = self._seed_data.get(service_id)
        if not config or config.get("availability") is None:
            return None

        avail_config = config["availability"]
        days_available = config["days_available"]

        # If requesting more days than available, return None
        if window_days > days_available:
            return None

        # Calculate window
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=window_days)

        # Scale events proportionally to requested window
        scale_factor = window_days / days_available
        good_events = int(avail_config["good_events"] * scale_factor)
        total_events = int(avail_config["total_events"] * scale_factor)
        sample_count = int(avail_config["sample_count"] * scale_factor)

        # Recalculate ratio from scaled events for consistency
        availability_ratio = good_events / total_events if total_events > 0 else 0.0

        return AvailabilitySliData(
            service_id=service_id,
            good_events=good_events,
            total_events=total_events,
            availability_ratio=availability_ratio,
            window_start=window_start,
            window_end=now,
            sample_count=sample_count,
        )

    async def get_latency_percentiles(
        self, service_id: str, window_days: int
    ) -> LatencySliData | None:
        """Get latency percentile data from seed data.

        Args:
            service_id: Business identifier of the service
            window_days: Number of days to look back

        Returns:
            LatencySliData if service has data, None otherwise
        """
        config = self._seed_data.get(service_id)
        if not config or config.get("latency") is None:
            return None

        latency_config = config["latency"]
        days_available = config["days_available"]

        # If requesting more days than available, return None
        if window_days > days_available:
            return None

        # Calculate window
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=window_days)

        # Scale sample count proportionally
        scale_factor = window_days / days_available
        sample_count = int(latency_config["sample_count"] * scale_factor)

        return LatencySliData(
            service_id=service_id,
            p50_ms=latency_config["p50_ms"],
            p95_ms=latency_config["p95_ms"],
            p99_ms=latency_config["p99_ms"],
            p999_ms=latency_config["p999_ms"],
            window_start=window_start,
            window_end=now,
            sample_count=sample_count,
        )

    async def get_rolling_availability(
        self, service_id: str, window_days: int, bucket_hours: int = 24
    ) -> list[float]:
        """Get rolling availability buckets from generated data.

        Args:
            service_id: Business identifier of the service
            window_days: Number of days to look back
            bucket_hours: Hours per bucket (default 24 = daily)

        Returns:
            List of availability ratios (one per bucket), empty if no data
        """
        config = self._seed_data.get(service_id)
        if not config or config.get("availability") is None:
            return []

        avail_config = config["availability"]
        days_available = config["days_available"]

        # If requesting more days than available, return empty
        if window_days > days_available:
            return []

        # Calculate number of buckets
        num_buckets = int(window_days * 24 / bucket_hours)

        # Generate rolling availability with realistic variance
        base_availability = avail_config["base"]
        variance = avail_config["variance"]

        # Use service_id hash as seed for reproducible randomness
        seed = hash(service_id) % (2**31)

        rolling_values = generate_rolling_availability(
            base_availability=base_availability,
            variance=variance,
            num_days=num_buckets,
            random_seed=seed,
        )

        return rolling_values

    async def get_data_completeness(self, service_id: str, window_days: int) -> float:
        """Get data completeness score from seed data.

        Args:
            service_id: Business identifier of the service
            window_days: Number of days to look back

        Returns:
            Completeness score (0.0-1.0)
        """
        config = self._seed_data.get(service_id)
        if not config:
            return 0.0

        completeness_config = config.get("completeness", {})

        # Return pre-configured completeness for common windows
        if window_days == 30:
            return completeness_config.get("30_days", 0.0)
        elif window_days == 90:
            return completeness_config.get("90_days", 0.0)
        else:
            # Calculate completeness based on days_available
            days_available = config.get("days_available", 0)
            if days_available == 0:
                return 0.0
            return min(1.0, days_available / window_days)


def create_mock_prometheus_client(
    seed_data: dict | None = None,
) -> MockPrometheusClient:
    """Factory function to create a mock Prometheus client.

    Args:
        seed_data: Optional custom seed data dict

    Returns:
        MockPrometheusClient instance
    """
    return MockPrometheusClient(seed_data=seed_data)
