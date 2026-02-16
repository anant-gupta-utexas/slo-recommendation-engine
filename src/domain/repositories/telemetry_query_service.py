"""Interface for querying telemetry data.

This interface abstracts the telemetry source (Prometheus, Mimir, etc.)
allowing the domain layer to remain independent of specific telemetry implementations.
"""

from abc import ABC, abstractmethod

from src.domain.entities.sli_data import AvailabilitySliData, LatencySliData


class TelemetryQueryServiceInterface(ABC):
    """Interface for querying telemetry data (abstracted from Prometheus/Mimir)."""

    @abstractmethod
    async def get_availability_sli(
        self, service_id: str, window_days: int
    ) -> AvailabilitySliData | None:
        """Returns availability SLI data over the given window.

        Args:
            service_id: Business identifier of the service (e.g., "checkout-service")
            window_days: Number of days to look back from now

        Returns:
            AvailabilitySliData if data is available, None if no data found
        """
        pass

    @abstractmethod
    async def get_latency_percentiles(
        self, service_id: str, window_days: int
    ) -> LatencySliData | None:
        """Returns latency percentile data over the given window.

        Args:
            service_id: Business identifier of the service (e.g., "checkout-service")
            window_days: Number of days to look back from now

        Returns:
            LatencySliData if data is available, None if no data found
        """
        pass

    @abstractmethod
    async def get_rolling_availability(
        self, service_id: str, window_days: int, bucket_hours: int = 24
    ) -> list[float]:
        """Returns rolling availability values (one per bucket) for breach estimation.

        Each bucket represents the availability ratio during that time period.
        Used for computing breach probability by counting historical breaches.

        Args:
            service_id: Business identifier of the service
            window_days: Number of days to look back from now
            bucket_hours: Hours per bucket (default 24 = daily buckets)

        Returns:
            List of availability ratios (0.0-1.0), one per bucket, ordered chronologically
            Empty list if no data available
        """
        pass

    @abstractmethod
    async def get_data_completeness(
        self, service_id: str, window_days: int
    ) -> float:
        """Returns data completeness score (0.0-1.0) for the window.

        Data completeness measures what fraction of expected data points are present.
        Used to trigger cold-start extended lookback when completeness is low.

        Args:
            service_id: Business identifier of the service
            window_days: Number of days to look back from now

        Returns:
            Completeness score from 0.0 (no data) to 1.0 (all expected data present)
        """
        pass
