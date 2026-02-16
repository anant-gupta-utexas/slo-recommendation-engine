"""Domain value objects for SLI data.

This module defines value objects that represent raw SLI (Service Level Indicator)
data fetched from telemetry sources like Prometheus.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class AvailabilitySliData:
    """Raw availability SLI data from telemetry source.

    Attributes:
        service_id: Identifier of the service
        good_events: Number of successful requests/events
        total_events: Total number of requests/events
        availability_ratio: Ratio of good events to total (good/total)
        window_start: Start of the measurement window
        window_end: End of the measurement window
        sample_count: Number of data points aggregated
    """

    service_id: str
    good_events: int
    total_events: int
    availability_ratio: float
    window_start: datetime
    window_end: datetime
    sample_count: int = 0

    def __post_init__(self):
        """Validate availability data constraints."""
        if self.good_events < 0:
            raise ValueError(f"good_events must be non-negative, got {self.good_events}")
        if self.total_events < 0:
            raise ValueError(f"total_events must be non-negative, got {self.total_events}")
        if self.good_events > self.total_events:
            raise ValueError(
                f"good_events ({self.good_events}) cannot exceed total_events ({self.total_events})"
            )
        if not (0.0 <= self.availability_ratio <= 1.0):
            raise ValueError(
                f"availability_ratio must be between 0.0 and 1.0, got {self.availability_ratio}"
            )
        if self.sample_count < 0:
            raise ValueError(f"sample_count must be non-negative, got {self.sample_count}")
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")

    @property
    def error_rate(self) -> float:
        """Calculate error rate from availability ratio.

        Returns:
            Error rate as a fraction (1.0 - availability_ratio)
        """
        return 1.0 - self.availability_ratio


@dataclass
class LatencySliData:
    """Raw latency SLI data from telemetry source.

    Attributes:
        service_id: Identifier of the service
        p50_ms: 50th percentile latency in milliseconds
        p95_ms: 95th percentile latency in milliseconds
        p99_ms: 99th percentile latency in milliseconds
        p999_ms: 99.9th percentile latency in milliseconds
        window_start: Start of the measurement window
        window_end: End of the measurement window
        sample_count: Number of data points aggregated
    """

    service_id: str
    p50_ms: float
    p95_ms: float
    p99_ms: float
    p999_ms: float
    window_start: datetime
    window_end: datetime
    sample_count: int = 0

    def __post_init__(self):
        """Validate latency data constraints."""
        # Validate all percentiles are non-negative
        if self.p50_ms < 0:
            raise ValueError(f"p50_ms must be non-negative, got {self.p50_ms}")
        if self.p95_ms < 0:
            raise ValueError(f"p95_ms must be non-negative, got {self.p95_ms}")
        if self.p99_ms < 0:
            raise ValueError(f"p99_ms must be non-negative, got {self.p99_ms}")
        if self.p999_ms < 0:
            raise ValueError(f"p999_ms must be non-negative, got {self.p999_ms}")

        # Validate percentile ordering (p50 <= p95 <= p99 <= p999)
        if not (self.p50_ms <= self.p95_ms <= self.p99_ms <= self.p999_ms):
            raise ValueError(
                f"Percentiles must be in ascending order: p50 ({self.p50_ms}) <= "
                f"p95 ({self.p95_ms}) <= p99 ({self.p99_ms}) <= p999 ({self.p999_ms})"
            )

        if self.sample_count < 0:
            raise ValueError(f"sample_count must be non-negative, got {self.sample_count}")
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
