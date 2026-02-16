"""Availability SLO recommendation calculator.

This service computes availability SLO recommendation tiers using percentile-based
analysis of historical data, capped by composite availability bounds from dependencies.
"""

import random
from statistics import quantiles

from src.domain.entities.slo_recommendation import RecommendationTier, TierLevel


class AvailabilityCalculator:
    """Computes availability SLO recommendation tiers.

    Algorithm:
    1. Compute base availability from historical rolling windows
    2. Compute tier targets from percentile analysis (p99.9, p99, p95)
    3. Apply composite availability bound cap for Conservative and Balanced tiers
    4. Estimate breach probability from historical breaches
    5. Compute error budget in monthly minutes
    6. Bootstrap confidence intervals for uncertainty quantification
    """

    MONTHLY_MINUTES = 43200  # 30 days * 24 hours * 60 minutes

    def compute_tiers(
        self,
        historical_availability: float,
        rolling_availabilities: list[float],
        composite_bound: float,
    ) -> dict[TierLevel, RecommendationTier]:
        """Compute three-tier availability recommendation.

        Conservative: p99.9 floor (most pessimistic 0.1% of history), capped by composite bound
        Balanced: p99 (most pessimistic 1% of history), capped by composite bound
        Aggressive: p95 (most pessimistic 5% of history), NOT capped (shows achievable potential)

        Args:
            historical_availability: Mean availability over the full window (0.0-1.0)
            rolling_availabilities: List of availability values per bucket (e.g., daily)
            composite_bound: Upper bound from dependency composite (0.0-1.0)

        Returns:
            Dictionary mapping TierLevel to RecommendationTier

        Raises:
            ValueError: If rolling_availabilities is empty or contains invalid values
        """
        if not rolling_availabilities:
            raise ValueError("rolling_availabilities cannot be empty")

        if not all(0.0 <= a <= 1.0 for a in rolling_availabilities):
            raise ValueError("All rolling availabilities must be between 0.0 and 1.0")

        if not (0.0 <= composite_bound <= 1.0):
            raise ValueError("composite_bound must be between 0.0 and 1.0")

        # Sort for percentile calculation
        sorted_avail = sorted(rolling_availabilities)

        # Compute percentile targets using quantiles
        # quantiles(data, n=100) returns 99 values splitting data into 100 buckets
        # We need p0.1 (Conservative), p1 (Balanced), p5 (Aggressive)
        if len(sorted_avail) == 1:
            # Edge case: single data point, use it for all tiers
            conservative_raw = balanced_raw = aggressive_raw = sorted_avail[0]
        else:
            # p0.1 ≈ index 0.001 * len, p1 ≈ index 0.01 * len, p5 ≈ index 0.05 * len
            conservative_raw = self._percentile(sorted_avail, 0.1)
            balanced_raw = self._percentile(sorted_avail, 1.0)
            aggressive_raw = self._percentile(sorted_avail, 5.0)

        # Apply dependency adjustment (hard cap for Conservative and Balanced)
        conservative_target = min(conservative_raw, composite_bound)
        balanced_target = min(balanced_raw, composite_bound)
        aggressive_target = aggressive_raw  # NOT capped

        # Estimate breach probabilities
        conservative_breach = self.estimate_breach_probability(
            conservative_target, rolling_availabilities
        )
        balanced_breach = self.estimate_breach_probability(
            balanced_target, rolling_availabilities
        )
        aggressive_breach = self.estimate_breach_probability(
            aggressive_target, rolling_availabilities
        )

        # Compute confidence intervals via bootstrap
        conservative_ci = self._bootstrap_confidence_interval(
            rolling_availabilities, 0.1
        )
        balanced_ci = self._bootstrap_confidence_interval(rolling_availabilities, 1.0)
        aggressive_ci = self._bootstrap_confidence_interval(rolling_availabilities, 5.0)

        return {
            TierLevel.CONSERVATIVE: RecommendationTier(
                level=TierLevel.CONSERVATIVE,
                target=conservative_target * 100,  # Convert to percentage
                error_budget_monthly_minutes=self.compute_error_budget_minutes(
                    conservative_target * 100
                ),
                estimated_breach_probability=conservative_breach,
                confidence_interval=(
                    conservative_ci[0] * 100,
                    conservative_ci[1] * 100,
                ),
            ),
            TierLevel.BALANCED: RecommendationTier(
                level=TierLevel.BALANCED,
                target=balanced_target * 100,
                error_budget_monthly_minutes=self.compute_error_budget_minutes(
                    balanced_target * 100
                ),
                estimated_breach_probability=balanced_breach,
                confidence_interval=(balanced_ci[0] * 100, balanced_ci[1] * 100),
            ),
            TierLevel.AGGRESSIVE: RecommendationTier(
                level=TierLevel.AGGRESSIVE,
                target=aggressive_target * 100,
                error_budget_monthly_minutes=self.compute_error_budget_minutes(
                    aggressive_target * 100
                ),
                estimated_breach_probability=aggressive_breach,
                confidence_interval=(aggressive_ci[0] * 100, aggressive_ci[1] * 100),
            ),
        }

    def estimate_breach_probability(
        self,
        target: float,
        rolling_availabilities: list[float],
    ) -> float:
        """Count fraction of windows where target would have been breached.

        Args:
            target: Target availability threshold (0.0-1.0)
            rolling_availabilities: List of historical availability values

        Returns:
            Fraction of windows below target (0.0-1.0)
        """
        if not rolling_availabilities:
            return 0.0

        breaches = sum(1 for avail in rolling_availabilities if avail < target)
        return breaches / len(rolling_availabilities)

    @staticmethod
    def compute_error_budget_minutes(target_percentage: float) -> float:
        """Compute monthly error budget in minutes.

        Monthly minutes = 43200 (30 days)
        Budget = (100 - target_percentage) / 100 * 43200

        Args:
            target_percentage: Availability target as percentage (e.g., 99.9)

        Returns:
            Error budget in monthly minutes

        Example:
            99.9% availability → 0.1% error budget → 43.2 minutes/month
        """
        if not (0.0 <= target_percentage <= 100.0):
            raise ValueError(
                f"target_percentage must be between 0.0 and 100.0, got {target_percentage}"
            )

        error_fraction = (100.0 - target_percentage) / 100.0
        return error_fraction * AvailabilityCalculator.MONTHLY_MINUTES

    def _percentile(self, sorted_values: list[float], percentile: float) -> float:
        """Compute percentile from sorted values.

        Args:
            sorted_values: List of values in ascending order
            percentile: Percentile to compute (0.0-100.0)

        Returns:
            Value at the given percentile
        """
        if not sorted_values:
            raise ValueError("sorted_values cannot be empty")

        n = len(sorted_values)
        if n == 1:
            return sorted_values[0]

        # Linear interpolation for percentile
        # percentile=0.1 means we want the value at position 0.1% of the data
        index = (percentile / 100.0) * (n - 1)
        lower_idx = int(index)
        upper_idx = min(lower_idx + 1, n - 1)
        fraction = index - lower_idx

        return sorted_values[lower_idx] * (1 - fraction) + sorted_values[
            upper_idx
        ] * fraction

    def _bootstrap_confidence_interval(
        self, data: list[float], percentile: float, n_resamples: int = 1000
    ) -> tuple[float, float]:
        """Compute 95% confidence interval for a percentile via bootstrap.

        Args:
            data: Original data points
            percentile: Percentile to compute CI for (0.0-100.0)
            n_resamples: Number of bootstrap resamples

        Returns:
            Tuple of (lower_bound, upper_bound) for 95% CI
        """
        if not data:
            return (0.0, 0.0)

        if len(data) == 1:
            # Single data point, no uncertainty
            return (data[0], data[0])

        # Bootstrap resampling
        bootstrap_estimates = []
        n = len(data)

        for _ in range(n_resamples):
            # Resample with replacement
            resample = [random.choice(data) for _ in range(n)]
            resample_sorted = sorted(resample)
            estimate = self._percentile(resample_sorted, percentile)
            bootstrap_estimates.append(estimate)

        # Compute 2.5th and 97.5th percentiles of bootstrap distribution
        bootstrap_sorted = sorted(bootstrap_estimates)
        lower = self._percentile(bootstrap_sorted, 2.5)
        upper = self._percentile(bootstrap_sorted, 97.5)

        return (lower, upper)
