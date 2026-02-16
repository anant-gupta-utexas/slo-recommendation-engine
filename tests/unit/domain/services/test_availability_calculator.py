"""Unit tests for AvailabilityCalculator service."""

import pytest
import random

from src.domain.entities.slo_recommendation import TierLevel
from src.domain.services.availability_calculator import AvailabilityCalculator


class TestAvailabilityCalculator:
    """Tests for AvailabilityCalculator service."""

    @pytest.fixture
    def calculator(self):
        """Create calculator instance for testing."""
        return AvailabilityCalculator()

    @pytest.fixture
    def sample_rolling_availabilities(self):
        """Sample rolling availability data (30 days, mostly high with some dips)."""
        # Set seed for reproducibility in tests
        random.seed(42)
        base = [0.999] * 20  # 20 days of 99.9%
        dips = [0.995, 0.990, 0.985]  # 3 days of lower availability
        normal = [0.998] * 7  # 7 days of 99.8%
        return base + dips + normal

    def test_compute_tiers_with_typical_data(self, calculator, sample_rolling_availabilities):
        """Test tier computation with typical availability data."""
        historical_mean = sum(sample_rolling_availabilities) / len(
            sample_rolling_availabilities
        )
        composite_bound = 0.997  # 99.7% composite from dependencies

        tiers = calculator.compute_tiers(
            historical_availability=historical_mean,
            rolling_availabilities=sample_rolling_availabilities,
            composite_bound=composite_bound,
        )

        assert len(tiers) == 3
        assert TierLevel.CONSERVATIVE in tiers
        assert TierLevel.BALANCED in tiers
        assert TierLevel.AGGRESSIVE in tiers

        # Conservative should be the most pessimistic (lowest)
        # Balanced should be in the middle
        # Aggressive should be the most optimistic (highest)
        conservative_target = tiers[TierLevel.CONSERVATIVE].target
        balanced_target = tiers[TierLevel.BALANCED].target
        aggressive_target = tiers[TierLevel.AGGRESSIVE].target

        assert conservative_target <= balanced_target <= aggressive_target

        # Conservative and Balanced should be capped by composite bound
        assert conservative_target <= composite_bound * 100
        assert balanced_target <= composite_bound * 100
        # Aggressive is NOT capped
        # (may or may not be higher than composite_bound depending on data)

    def test_tiers_capped_by_composite_bound(self, calculator):
        """Test that Conservative and Balanced tiers are capped by composite bound."""
        # Create data with very high availability
        rolling_avail = [0.9999] * 30  # 99.99% consistently

        # But composite bound is lower due to dependencies
        composite_bound = 0.997  # 99.7%

        tiers = calculator.compute_tiers(
            historical_availability=0.9999,
            rolling_availabilities=rolling_avail,
            composite_bound=composite_bound,
        )

        # Conservative and Balanced should be capped at 99.7%
        assert tiers[TierLevel.CONSERVATIVE].target <= composite_bound * 100
        assert tiers[TierLevel.BALANCED].target <= composite_bound * 100

        # Aggressive should NOT be capped and could be higher
        # In this case, aggressive should reflect the actual high availability
        assert tiers[TierLevel.AGGRESSIVE].target >= composite_bound * 100

    def test_aggressive_tier_not_capped(self, calculator):
        """Test that Aggressive tier is NOT capped by composite bound."""
        rolling_avail = [0.998] * 30
        composite_bound = 0.990  # Lower composite bound

        tiers = calculator.compute_tiers(
            historical_availability=0.998,
            rolling_availabilities=rolling_avail,
            composite_bound=composite_bound,
        )

        # Aggressive tier should reflect the actual high performance
        # It should be higher than the composite bound
        assert tiers[TierLevel.AGGRESSIVE].target > composite_bound * 100

    def test_error_budget_computed_correctly(self, calculator, sample_rolling_availabilities):
        """Test that error budget in monthly minutes is computed correctly."""
        tiers = calculator.compute_tiers(
            historical_availability=0.998,
            rolling_availabilities=sample_rolling_availabilities,
            composite_bound=0.997,
        )

        for tier in tiers.values():
            # Error budget should be non-negative
            assert tier.error_budget_monthly_minutes >= 0

            # Verify computation: budget = (100 - target) / 100 * 43200
            expected_budget = (
                100.0 - tier.target
            ) / 100.0 * AvailabilityCalculator.MONTHLY_MINUTES
            assert tier.error_budget_monthly_minutes == pytest.approx(
                expected_budget, rel=1e-6
            )

    def test_breach_probability_estimated(self, calculator, sample_rolling_availabilities):
        """Test that breach probabilities are estimated from historical data."""
        tiers = calculator.compute_tiers(
            historical_availability=0.998,
            rolling_availabilities=sample_rolling_availabilities,
            composite_bound=0.997,
        )

        # All tiers should have breach probability between 0 and 1
        for tier in tiers.values():
            assert 0.0 <= tier.estimated_breach_probability <= 1.0

        # Conservative tier (lower target) should have lower breach probability
        # Aggressive tier (higher target) should have higher breach probability
        assert (
            tiers[TierLevel.CONSERVATIVE].estimated_breach_probability
            <= tiers[TierLevel.BALANCED].estimated_breach_probability
            <= tiers[TierLevel.AGGRESSIVE].estimated_breach_probability
        )

    def test_confidence_intervals_computed(self, calculator, sample_rolling_availabilities):
        """Test that confidence intervals are computed via bootstrap."""
        tiers = calculator.compute_tiers(
            historical_availability=0.998,
            rolling_availabilities=sample_rolling_availabilities,
            composite_bound=0.997,
        )

        for tier in tiers.values():
            assert tier.confidence_interval is not None
            lower, upper = tier.confidence_interval

            # CI should be valid
            assert lower <= upper
            # CI should contain the target (usually)
            # Due to bootstrap variance, we allow some slack
            assert lower <= tier.target * 1.01  # Allow 1% slack

    def test_empty_rolling_availabilities_raises_error(self, calculator):
        """Test that empty rolling availabilities raises ValueError."""
        with pytest.raises(ValueError, match="rolling_availabilities cannot be empty"):
            calculator.compute_tiers(
                historical_availability=0.999,
                rolling_availabilities=[],
                composite_bound=0.99,
            )

    def test_invalid_rolling_availability_value_raises_error(self, calculator):
        """Test that invalid rolling availability values raise ValueError."""
        with pytest.raises(
            ValueError, match="All rolling availabilities must be between 0.0 and 1.0"
        ):
            calculator.compute_tiers(
                historical_availability=0.999,
                rolling_availabilities=[0.999, 1.5, 0.998],  # 1.5 is invalid
                composite_bound=0.99,
            )

    def test_invalid_composite_bound_raises_error(self, calculator):
        """Test that invalid composite bound raises ValueError."""
        with pytest.raises(ValueError, match="composite_bound must be between 0.0 and 1.0"):
            calculator.compute_tiers(
                historical_availability=0.999,
                rolling_availabilities=[0.999] * 30,
                composite_bound=1.5,  # Invalid
            )

    def test_single_data_point(self, calculator):
        """Test tier computation with single data point."""
        single_avail = [0.995]

        tiers = calculator.compute_tiers(
            historical_availability=0.995,
            rolling_availabilities=single_avail,
            composite_bound=0.99,
        )

        # With single data point, all uncapped tiers should be the same
        # Conservative and Balanced may be capped
        # Aggressive should equal the single data point
        assert tiers[TierLevel.AGGRESSIVE].target == pytest.approx(99.5)

    def test_perfect_availability(self, calculator):
        """Test tier computation with 100% availability."""
        perfect_avail = [1.0] * 30

        tiers = calculator.compute_tiers(
            historical_availability=1.0,
            rolling_availabilities=perfect_avail,
            composite_bound=0.999,
        )

        # Conservative and Balanced capped at composite bound (99.9%)
        assert tiers[TierLevel.CONSERVATIVE].target <= 99.9
        assert tiers[TierLevel.BALANCED].target <= 99.9

        # Aggressive reflects perfect availability
        assert tiers[TierLevel.AGGRESSIVE].target == pytest.approx(100.0)

        # Error budgets should be sensible
        assert tiers[TierLevel.AGGRESSIVE].error_budget_monthly_minutes == pytest.approx(
            0.0
        )

    def test_zero_availability(self, calculator):
        """Test tier computation with 0% availability."""
        zero_avail = [0.0] * 30

        tiers = calculator.compute_tiers(
            historical_availability=0.0,
            rolling_availabilities=zero_avail,
            composite_bound=0.1,
        )

        # All tiers should be at 0%
        assert tiers[TierLevel.CONSERVATIVE].target == pytest.approx(0.0)
        assert tiers[TierLevel.BALANCED].target == pytest.approx(0.0)
        assert tiers[TierLevel.AGGRESSIVE].target == pytest.approx(0.0)


class TestEstimateBreachProbability:
    """Tests for estimate_breach_probability method."""

    @pytest.fixture
    def calculator(self):
        """Create calculator instance for testing."""
        return AvailabilityCalculator()

    def test_no_breaches(self, calculator):
        """Test breach probability when no historical breaches."""
        rolling_avail = [0.999] * 30
        target = 0.995  # Target below all historical values

        breach_prob = calculator.estimate_breach_probability(target, rolling_avail)

        assert breach_prob == 0.0

    def test_all_breaches(self, calculator):
        """Test breach probability when all historical values breach."""
        rolling_avail = [0.99] * 30
        target = 0.995  # Target above all historical values

        breach_prob = calculator.estimate_breach_probability(target, rolling_avail)

        assert breach_prob == 1.0

    def test_partial_breaches(self, calculator):
        """Test breach probability with partial breaches."""
        rolling_avail = [0.999] * 27 + [0.99] * 3  # 3 out of 30 breach
        target = 0.995  # 0.99 < 0.995 < 0.999

        breach_prob = calculator.estimate_breach_probability(target, rolling_avail)

        assert breach_prob == pytest.approx(0.1)  # 3/30 = 0.1

    def test_empty_list(self, calculator):
        """Test breach probability with empty list."""
        breach_prob = calculator.estimate_breach_probability(0.99, [])

        assert breach_prob == 0.0


class TestComputeErrorBudgetMinutes:
    """Tests for compute_error_budget_minutes static method."""

    def test_compute_error_budget_99_9(self):
        """Test error budget for 99.9% availability."""
        budget = AvailabilityCalculator.compute_error_budget_minutes(99.9)

        # 99.9% → 0.1% error → 0.001 * 43200 = 43.2 minutes
        assert budget == pytest.approx(43.2)

    def test_compute_error_budget_99_5(self):
        """Test error budget for 99.5% availability."""
        budget = AvailabilityCalculator.compute_error_budget_minutes(99.5)

        # 99.5% → 0.5% error → 0.005 * 43200 = 216 minutes
        assert budget == pytest.approx(216.0)

    def test_compute_error_budget_100(self):
        """Test error budget for 100% availability."""
        budget = AvailabilityCalculator.compute_error_budget_minutes(100.0)

        assert budget == pytest.approx(0.0)

    def test_compute_error_budget_0(self):
        """Test error budget for 0% availability."""
        budget = AvailabilityCalculator.compute_error_budget_minutes(0.0)

        # 0% → 100% error → 1.0 * 43200 = 43200 minutes
        assert budget == pytest.approx(43200.0)

    def test_invalid_target_percentage_raises_error(self):
        """Test that invalid target percentage raises ValueError."""
        with pytest.raises(ValueError, match="target_percentage must be between 0.0 and 100.0"):
            AvailabilityCalculator.compute_error_budget_minutes(150.0)

        with pytest.raises(ValueError, match="target_percentage must be between 0.0 and 100.0"):
            AvailabilityCalculator.compute_error_budget_minutes(-10.0)


class TestPercentileCalculation:
    """Tests for _percentile internal method."""

    @pytest.fixture
    def calculator(self):
        """Create calculator instance for testing."""
        return AvailabilityCalculator()

    def test_percentile_single_value(self, calculator):
        """Test percentile with single value."""
        result = calculator._percentile([0.99], 50.0)
        assert result == pytest.approx(0.99)

    def test_percentile_50th(self, calculator):
        """Test 50th percentile (median)."""
        data = sorted([0.990, 0.992, 0.994, 0.996, 0.998])
        result = calculator._percentile(data, 50.0)

        # Median should be the middle value
        assert result == pytest.approx(0.994, abs=0.001)

    def test_percentile_0th(self, calculator):
        """Test 0th percentile (minimum)."""
        data = sorted([0.990, 0.992, 0.994, 0.996, 0.998])
        result = calculator._percentile(data, 0.0)

        assert result == pytest.approx(0.990)

    def test_percentile_100th(self, calculator):
        """Test 100th percentile (maximum)."""
        data = sorted([0.990, 0.992, 0.994, 0.996, 0.998])
        result = calculator._percentile(data, 100.0)

        assert result == pytest.approx(0.998)

    def test_percentile_interpolation(self, calculator):
        """Test that percentile uses linear interpolation."""
        data = sorted([0.0, 1.0])
        result = calculator._percentile(data, 25.0)

        # 25th percentile of [0, 1] should be 0.25
        assert result == pytest.approx(0.25)

    def test_percentile_empty_raises_error(self, calculator):
        """Test that empty data raises ValueError."""
        with pytest.raises(ValueError, match="sorted_values cannot be empty"):
            calculator._percentile([], 50.0)


class TestBootstrapConfidenceInterval:
    """Tests for _bootstrap_confidence_interval internal method."""

    @pytest.fixture
    def calculator(self):
        """Create calculator instance for testing."""
        return AvailabilityCalculator()

    def test_bootstrap_empty_data(self, calculator):
        """Test bootstrap with empty data."""
        lower, upper = calculator._bootstrap_confidence_interval([], 50.0)

        assert lower == 0.0
        assert upper == 0.0

    def test_bootstrap_single_value(self, calculator):
        """Test bootstrap with single value (no uncertainty)."""
        lower, upper = calculator._bootstrap_confidence_interval([0.99], 50.0)

        assert lower == pytest.approx(0.99)
        assert upper == pytest.approx(0.99)

    def test_bootstrap_confidence_interval_width(self, calculator):
        """Test that bootstrap CI has reasonable width."""
        random.seed(42)  # For reproducibility
        data = [0.990 + random.gauss(0, 0.002) for _ in range(100)]

        lower, upper = calculator._bootstrap_confidence_interval(data, 50.0, n_resamples=1000)

        # CI should be non-empty
        assert lower < upper

        # CI should be reasonably wide (more than 0, less than full range)
        assert (upper - lower) > 0.0
        assert (upper - lower) < (max(data) - min(data))

    def test_bootstrap_deterministic_with_seed(self, calculator):
        """Test that bootstrap with same seed gives same results."""
        data = [0.99, 0.992, 0.994, 0.996, 0.998]

        random.seed(123)
        lower1, upper1 = calculator._bootstrap_confidence_interval(data, 50.0, n_resamples=100)

        random.seed(123)
        lower2, upper2 = calculator._bootstrap_confidence_interval(data, 50.0, n_resamples=100)

        assert lower1 == pytest.approx(lower2)
        assert upper1 == pytest.approx(upper2)
