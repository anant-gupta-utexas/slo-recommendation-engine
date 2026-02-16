"""Seed data for mock Prometheus telemetry client.

This module provides realistic telemetry data for testing and development,
covering various scenarios: high confidence, cold-start, no data, high variance, etc.
"""

import random
from datetime import datetime, timedelta, timezone


def generate_rolling_availability(
    base_availability: float,
    variance: float,
    num_days: int,
    random_seed: int | None = None,
) -> list[float]:
    """Generate realistic rolling availability data with variance.

    Args:
        base_availability: Base availability ratio (0.0-1.0)
        variance: Amount of variance to apply (e.g., 0.005 = 0.5%)
        num_days: Number of daily buckets to generate
        random_seed: Optional seed for reproducible randomness

    Returns:
        List of availability ratios, one per day
    """
    if random_seed is not None:
        random.seed(random_seed)

    values = []
    for _ in range(num_days):
        # Add gaussian noise
        noise = random.gauss(0, variance)
        value = max(0.0, min(1.0, base_availability + noise))
        values.append(value)

    return values


# Seed data dictionary: service_id -> scenario config
SEED_DATA = {
    # Scenario 1: High confidence service (30 days, 98% completeness, stable)
    "payment-service": {
        "availability": {
            "base": 0.9950,  # 99.5% availability
            "variance": 0.003,  # Low variance (stable)
            "good_events": 9_950_000,
            "total_events": 10_000_000,
            "sample_count": 720,  # 30 days * 24 hours
        },
        "latency": {
            "p50_ms": 45.0,
            "p95_ms": 120.0,
            "p99_ms": 250.0,
            "p999_ms": 500.0,
            "sample_count": 720,
        },
        "completeness": {
            "30_days": 0.98,
            "90_days": 0.96,
        },
        "days_available": 30,
    },
    # Scenario 2: Stable high-availability service (30 days)
    "auth-service": {
        "availability": {
            "base": 0.9990,  # 99.9% availability
            "variance": 0.001,  # Very low variance
            "good_events": 19_980_000,
            "total_events": 20_000_000,
            "sample_count": 720,
        },
        "latency": {
            "p50_ms": 25.0,
            "p95_ms": 80.0,
            "p99_ms": 150.0,
            "p999_ms": 300.0,
            "sample_count": 720,
        },
        "completeness": {
            "30_days": 0.99,
            "90_days": 0.98,
        },
        "days_available": 30,
    },
    # Scenario 3: Service with higher variance (30 days)
    "notification-service": {
        "availability": {
            "base": 0.9900,  # 99.0% availability
            "variance": 0.010,  # Higher variance
            "good_events": 4_950_000,
            "total_events": 5_000_000,
            "sample_count": 720,
        },
        "latency": {
            "p50_ms": 100.0,
            "p95_ms": 350.0,
            "p99_ms": 800.0,
            "p999_ms": 1500.0,
            "sample_count": 720,
        },
        "completeness": {
            "30_days": 0.95,
            "90_days": 0.93,
        },
        "days_available": 30,
    },
    # Scenario 4: Moderate availability service (30 days)
    "analytics-service": {
        "availability": {
            "base": 0.9800,  # 98.0% availability
            "variance": 0.008,
            "good_events": 2_940_000,
            "total_events": 3_000_000,
            "sample_count": 720,
        },
        "latency": {
            "p50_ms": 200.0,
            "p95_ms": 600.0,
            "p99_ms": 1200.0,
            "p999_ms": 2500.0,
            "sample_count": 720,
        },
        "completeness": {
            "30_days": 0.97,
            "90_days": 0.95,
        },
        "days_available": 30,
    },
    # Scenario 5: Lower availability, higher latency (30 days)
    "legacy-report-service": {
        "availability": {
            "base": 0.9500,  # 95.0% availability
            "variance": 0.015,  # High variance
            "good_events": 1_900_000,
            "total_events": 2_000_000,
            "sample_count": 720,
        },
        "latency": {
            "p50_ms": 500.0,
            "p95_ms": 1500.0,
            "p99_ms": 3000.0,
            "p999_ms": 5000.0,
            "sample_count": 720,
        },
        "completeness": {
            "30_days": 0.92,
            "90_days": 0.90,
        },
        "days_available": 30,
    },
    # Scenario 6: Cold-start service (only 10 days of data, triggers extended lookback)
    "new-checkout-service": {
        "availability": {
            "base": 0.9920,
            "variance": 0.005,
            "good_events": 992_000,
            "total_events": 1_000_000,
            "sample_count": 240,  # 10 days * 24 hours
        },
        "latency": {
            "p50_ms": 60.0,
            "p95_ms": 180.0,
            "p99_ms": 400.0,
            "p999_ms": 800.0,
            "sample_count": 240,
        },
        "completeness": {
            "30_days": 0.33,  # Only 10/30 days = 33% (triggers cold-start)
            "90_days": 0.11,  # Only 10/90 days = 11%
        },
        "days_available": 10,
    },
    # Scenario 7: Cold-start service (only 7 days of data)
    "experimental-ml-service": {
        "availability": {
            "base": 0.9850,
            "variance": 0.012,
            "good_events": 689_500,
            "total_events": 700_000,
            "sample_count": 168,  # 7 days * 24 hours
        },
        "latency": {
            "p50_ms": 300.0,
            "p95_ms": 900.0,
            "p99_ms": 1800.0,
            "p999_ms": 3500.0,
            "sample_count": 168,
        },
        "completeness": {
            "30_days": 0.23,  # 7/30 = 23% (cold-start)
            "90_days": 0.08,  # 7/90 = 8%
        },
        "days_available": 7,
    },
    # Scenario 8: Service with NO data (not yet instrumented or down)
    "uninstrumented-service": {
        "availability": None,
        "latency": None,
        "completeness": {
            "30_days": 0.0,
            "90_days": 0.0,
        },
        "days_available": 0,
    },
}


def get_service_config(service_id: str) -> dict | None:
    """Get seed configuration for a service.

    Args:
        service_id: Business identifier of the service

    Returns:
        Configuration dict if service exists in seed data, None otherwise
    """
    return SEED_DATA.get(service_id)


def get_all_service_ids() -> list[str]:
    """Get list of all service IDs in seed data.

    Returns:
        List of service identifiers
    """
    return list(SEED_DATA.keys())
