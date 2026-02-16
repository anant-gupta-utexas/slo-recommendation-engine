"""Latency SLO recommendation calculation service.

This module provides the LatencyCalculator service for computing latency-based
SLO recommendations using percentile analysis with configurable noise margins.

Author: SLO Recommendation Engine Team
"""

from dataclasses import dataclass
from typing import List

from src.domain.entities.sli_data import LatencySliData
from src.domain.entities.slo_recommendation import (
    RecommendationTier,
    TierLevel,
)


@dataclass
class LatencyCalculator:
    """Calculates latency SLO recommendations from historical latency data.

    Strategy:
    - Conservative tier: p999 + noise margin (default 5%, 10% if shared infra)
    - Balanced tier: p99 + noise margin
    - Aggressive tier: p95 (no noise margin - achievable under normal conditions)

    Noise margins account for:
    - Load spikes
    - Infrastructure variability
    - GC pauses / cold starts
    - Shared infrastructure contention (higher margin)

    Attributes:
        noise_margin_default: Default noise margin for dedicated infrastructure (5%)
        noise_margin_shared_infra: Noise margin for shared infrastructure (10%)
        bootstrap_resample_count: Number of bootstrap resamples for confidence intervals
    """

    noise_margin_default: float = 0.05
    noise_margin_shared_infra: float = 0.10
    bootstrap_resample_count: int = 1000

    def __post_init__(self) -> None:
        """Validate configuration parameters."""
        if not 0 <= self.noise_margin_default <= 1:
            raise ValueError(f"noise_margin_default must be in [0, 1], got {self.noise_margin_default}")
        if not 0 <= self.noise_margin_shared_infra <= 1:
            raise ValueError(f"noise_margin_shared_infra must be in [0, 1], got {self.noise_margin_shared_infra}")
        if self.bootstrap_resample_count < 100:
            raise ValueError(f"bootstrap_resample_count must be >= 100, got {self.bootstrap_resample_count}")

    def compute_tiers(
        self,
        sli_data: List[LatencySliData],
        shared_infrastructure: bool = False,
    ) -> List[RecommendationTier]:
        """Compute latency SLO recommendation tiers from historical data.

        Args:
            sli_data: List of latency SLI data points (must have p50/p95/p99/p999)
            shared_infrastructure: If True, use higher noise margin

        Returns:
            List of 3 RecommendationTier objects (Conservative, Balanced, Aggressive)

        Raises:
            ValueError: If sli_data is empty or has invalid data
        """
        if not sli_data:
            raise ValueError("sli_data cannot be empty")

        # Extract percentile values across all data points
        p50_values = [d.p50_ms for d in sli_data]
        p95_values = [d.p95_ms for d in sli_data]
        p99_values = [d.p99_ms for d in sli_data]
        p999_values = [d.p999_ms for d in sli_data]

        # Validate data quality
        if not all(p50_values) or not all(p95_values) or not all(p99_values) or not all(p999_values):
            raise ValueError("All latency data points must have non-zero p50/p95/p99/p999 values")

        # Determine noise margin
        noise_margin = (
            self.noise_margin_shared_infra if shared_infrastructure
            else self.noise_margin_default
        )

        # Conservative: p999 + noise margin
        conservative_p999 = max(p999_values)
        conservative_target_ms = conservative_p999 * (1 + noise_margin)
        conservative_breach_prob = self.estimate_breach_probability(p999_values, conservative_target_ms)
        conservative_ci = self._bootstrap_confidence_interval(p999_values, 0.999)

        # Balanced: p99 + noise margin
        balanced_p99 = max(p99_values)
        balanced_target_ms = balanced_p99 * (1 + noise_margin)
        balanced_breach_prob = self.estimate_breach_probability(p99_values, balanced_target_ms)
        balanced_ci = self._bootstrap_confidence_interval(p99_values, 0.99)

        # Aggressive: p95 (no noise margin)
        aggressive_p95 = max(p95_values)
        aggressive_target_ms = aggressive_p95
        aggressive_breach_prob = self.estimate_breach_probability(p95_values, aggressive_target_ms)
        aggressive_ci = self._bootstrap_confidence_interval(p95_values, 0.95)

        return [
            RecommendationTier(
                level=TierLevel.CONSERVATIVE,
                target=conservative_target_ms,
                target_ms=int(conservative_target_ms),
                estimated_breach_probability=conservative_breach_prob,
                confidence_interval=conservative_ci,
                percentile="p999",
            ),
            RecommendationTier(
                level=TierLevel.BALANCED,
                target=balanced_target_ms,
                target_ms=int(balanced_target_ms),
                estimated_breach_probability=balanced_breach_prob,
                confidence_interval=balanced_ci,
                percentile="p99",
            ),
            RecommendationTier(
                level=TierLevel.AGGRESSIVE,
                target=aggressive_target_ms,
                target_ms=int(aggressive_target_ms),
                estimated_breach_probability=aggressive_breach_prob,
                confidence_interval=aggressive_ci,
                percentile="p95",
            ),
        ]

    def estimate_breach_probability(
        self,
        percentile_values: List[float],
        threshold: float,
    ) -> float:
        """Estimate breach probability based on historical percentile data.

        Args:
            percentile_values: Historical percentile values (e.g., p99 over time)
            threshold: Target threshold value

        Returns:
            Estimated breach probability [0.0, 1.0]
        """
        if not percentile_values:
            return 0.5  # Maximum uncertainty

        breaches = sum(1 for val in percentile_values if val > threshold)
        return breaches / len(percentile_values)

    def _bootstrap_confidence_interval(
        self,
        percentile_values: List[float],
        percentile: float,
    ) -> tuple[float, float]:
        """Bootstrap 95% confidence interval for a percentile estimate.

        Args:
            percentile_values: Historical percentile values
            percentile: Target percentile (e.g., 0.99 for p99)

        Returns:
            Tuple of (lower_bound, upper_bound) at 95% confidence
        """
        import random
        import statistics

        if len(percentile_values) == 1:
            # No variability, return point estimate
            val = percentile_values[0]
            return (val, val)

        # Bootstrap resampling
        resampled_maxes = []
        for _ in range(self.bootstrap_resample_count):
            resample = random.choices(percentile_values, k=len(percentile_values))
            resampled_maxes.append(max(resample))

        # 95% confidence interval
        lower = statistics.quantiles(resampled_maxes, n=40)[1]  # 2.5th percentile (1/40)
        upper = statistics.quantiles(resampled_maxes, n=40)[38]  # 97.5th percentile (39/40)

        return (lower, upper)
