"""Unit tests for LatencyCalculator service.

Tests cover:
- Tier computation with percentile analysis
- Noise margin application (default vs shared infrastructure)
- Breach probability estimation
- Bootstrap confidence intervals
- Edge cases (single data point, uniform data, high variability)
"""

from datetime import datetime, timedelta

import pytest

from src.domain.entities.sli_data import LatencySliData
from src.domain.entities.slo_recommendation import TierLevel
from src.domain.services.latency_calculator import LatencyCalculator


# Test fixture helpers
def create_latency_sli(
    p50_ms: float,
    p95_ms: float,
    p99_ms: float,
    p999_ms: float,
    service_id: str = "test-service",
    days_ago: int = 0,
) -> LatencySliData:
    """Helper to create LatencySliData for tests."""
    window_end = datetime.utcnow() - timedelta(days=days_ago)
    window_start = window_end - timedelta(hours=1)
    return LatencySliData(
        service_id=service_id,
        p50_ms=p50_ms,
        p95_ms=p95_ms,
        p99_ms=p99_ms,
        p999_ms=p999_ms,
        window_start=window_start,
        window_end=window_end,
        sample_count=1000,
    )


class TestLatencyCalculatorInit:
    """Tests for LatencyCalculator initialization and validation."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default parameters."""
        calc = LatencyCalculator()
        assert calc.noise_margin_default == 0.05
        assert calc.noise_margin_shared_infra == 0.10
        assert calc.bootstrap_resample_count == 1000

    def test_init_with_custom_params(self) -> None:
        """Test initialization with custom parameters."""
        calc = LatencyCalculator(
            noise_margin_default=0.08,
            noise_margin_shared_infra=0.15,
            bootstrap_resample_count=500,
        )
        assert calc.noise_margin_default == 0.08
        assert calc.noise_margin_shared_infra == 0.15
        assert calc.bootstrap_resample_count == 500

    def test_init_invalid_noise_margin_default(self) -> None:
        """Test initialization fails with invalid noise_margin_default."""
        with pytest.raises(ValueError, match="noise_margin_default must be in"):
            LatencyCalculator(noise_margin_default=-0.1)

        with pytest.raises(ValueError, match="noise_margin_default must be in"):
            LatencyCalculator(noise_margin_default=1.5)

    def test_init_invalid_noise_margin_shared_infra(self) -> None:
        """Test initialization fails with invalid noise_margin_shared_infra."""
        with pytest.raises(ValueError, match="noise_margin_shared_infra must be in"):
            LatencyCalculator(noise_margin_shared_infra=-0.1)

        with pytest.raises(ValueError, match="noise_margin_shared_infra must be in"):
            LatencyCalculator(noise_margin_shared_infra=1.5)

    def test_init_invalid_bootstrap_resample_count(self) -> None:
        """Test initialization fails with too few bootstrap resamples."""
        with pytest.raises(ValueError, match="bootstrap_resample_count must be >= 100"):
            LatencyCalculator(bootstrap_resample_count=50)


class TestComputeTiers:
    """Tests for compute_tiers method."""

    def test_compute_tiers_basic(self) -> None:
        """Test basic tier computation with stable latency data."""
        calc = LatencyCalculator(noise_margin_default=0.05, bootstrap_resample_count=100)

        # Stable latency: p50=100ms, p95=200ms, p99=250ms, p999=300ms
        sli_data = [
            create_latency_sli(100.0, 200.0, 250.0, 300.0, days_ago=i)
            for i in range(30)
        ]

        tiers = calc.compute_tiers(sli_data, shared_infrastructure=False)

        assert len(tiers) == 3

        # Conservative: p999 + 5% = 300 * 1.05 = 315ms
        conservative = next(t for t in tiers if t.level == TierLevel.CONSERVATIVE)
        assert conservative.target == 315.0
        assert 0.0 <= conservative.estimated_breach_probability <= 1.0
        assert conservative.confidence_interval[0] <= conservative.confidence_interval[1]

        # Balanced: p99 + 5% = 250 * 1.05 = 262.5ms
        balanced = next(t for t in tiers if t.level == TierLevel.BALANCED)
        assert balanced.target == 262.5
        assert 0.0 <= balanced.estimated_breach_probability <= 1.0

        # Aggressive: p95 (no noise) = 200ms
        aggressive = next(t for t in tiers if t.level == TierLevel.AGGRESSIVE)
        assert aggressive.target == 200.0
        assert 0.0 <= aggressive.estimated_breach_probability <= 1.0

    def test_compute_tiers_shared_infrastructure(self) -> None:
        """Test tier computation with shared infrastructure (higher noise margin)."""
        calc = LatencyCalculator(
            noise_margin_default=0.05,
            noise_margin_shared_infra=0.10,
            bootstrap_resample_count=100,
        )

        sli_data = [
            create_latency_sli(100.0, 200.0, 250.0, 300.0, days_ago=i)
            for i in range(10)
        ]

        tiers = calc.compute_tiers(sli_data, shared_infrastructure=True)

        # Conservative: p999 + 10% = 300 * 1.10 = 330ms
        conservative = next(t for t in tiers if t.level == TierLevel.CONSERVATIVE)
        assert conservative.target == 330.0

        # Balanced: p99 + 10% = 250 * 1.10 = 275ms
        balanced = next(t for t in tiers if t.level == TierLevel.BALANCED)
        assert balanced.target == 275.0

        # Aggressive: p95 (no noise) = 200ms
        aggressive = next(t for t in tiers if t.level == TierLevel.AGGRESSIVE)
        assert aggressive.target == 200.0

    def test_compute_tiers_variable_latency(self) -> None:
        """Test tier computation with variable latency (uses max percentile values)."""
        calc = LatencyCalculator(noise_margin_default=0.05, bootstrap_resample_count=100)

        sli_data = [
            create_latency_sli(100.0, 200.0, 250.0, 300.0, days_ago=0),
            create_latency_sli(110.0, 220.0, 270.0, 350.0, days_ago=1),  # Higher
            create_latency_sli(95.0, 190.0, 240.0, 290.0, days_ago=2),
        ]

        tiers = calc.compute_tiers(sli_data, shared_infrastructure=False)

        # Conservative: max(p999) + 5% = 350 * 1.05 = 367.5ms
        conservative = next(t for t in tiers if t.level == TierLevel.CONSERVATIVE)
        assert conservative.target == 367.5

        # Balanced: max(p99) + 5% = 270 * 1.05 = 283.5ms
        balanced = next(t for t in tiers if t.level == TierLevel.BALANCED)
        assert balanced.target == 283.5

        # Aggressive: max(p95) = 220ms
        aggressive = next(t for t in tiers if t.level == TierLevel.AGGRESSIVE)
        assert aggressive.target == 220.0

    def test_compute_tiers_single_data_point(self) -> None:
        """Test tier computation with single data point."""
        calc = LatencyCalculator(noise_margin_default=0.05, bootstrap_resample_count=100)

        sli_data = [
            create_latency_sli(100.0, 200.0, 250.0, 300.0, days_ago=0),
        ]

        tiers = calc.compute_tiers(sli_data, shared_infrastructure=False)

        assert len(tiers) == 3

        # Conservative: 300 * 1.05 = 315ms
        conservative = next(t for t in tiers if t.level == TierLevel.CONSERVATIVE)
        assert conservative.target == 315.0
        # CI should be point estimate
        assert conservative.confidence_interval[0] == 300.0
        assert conservative.confidence_interval[1] == 300.0

    def test_compute_tiers_high_latency_spike(self) -> None:
        """Test tier computation with occasional high latency spikes."""
        calc = LatencyCalculator(noise_margin_default=0.05, bootstrap_resample_count=100)

        sli_data = [
            create_latency_sli(100.0, 200.0, 250.0, 300.0, days_ago=0),
            create_latency_sli(100.0, 200.0, 250.0, 300.0, days_ago=1),
            create_latency_sli(100.0, 200.0, 250.0, 300.0, days_ago=2),
            create_latency_sli(120.0, 500.0, 800.0, 1200.0, days_ago=3),  # Spike
        ]

        tiers = calc.compute_tiers(sli_data, shared_infrastructure=False)

        # Conservative: max(p999) + 5% = 1200 * 1.05 = 1260ms
        conservative = next(t for t in tiers if t.level == TierLevel.CONSERVATIVE)
        assert conservative.target == 1260.0

        # Breach probability should be 0 since target (1260ms) includes noise margin above the spike (1200ms)
        assert conservative.estimated_breach_probability == 0.0

    def test_compute_tiers_empty_sli_data(self) -> None:
        """Test compute_tiers raises error with empty sli_data."""
        calc = LatencyCalculator()

        with pytest.raises(ValueError, match="sli_data cannot be empty"):
            calc.compute_tiers([])

    def test_compute_tiers_zero_latency_values(self) -> None:
        """Test compute_tiers raises error with zero latency values."""
        calc = LatencyCalculator()

        # All zeros (invalid ordering will be caught by LatencySliData validation)
        # So we test with valid ordering but one zero value
        with pytest.raises(ValueError):
            # This will fail LatencySliData validation (p50 <= p95 check)
            # because 100 <= 200 <= 250 <= 0 is False
            create_latency_sli(100.0, 200.0, 250.0, 0.0)


class TestEstimateBreachProbability:
    """Tests for estimate_breach_probability method."""

    def test_estimate_breach_probability_no_breaches(self) -> None:
        """Test breach probability when all values below threshold."""
        calc = LatencyCalculator()
        percentile_values = [100.0, 110.0, 105.0, 95.0, 100.0]
        threshold = 120.0

        prob = calc.estimate_breach_probability(percentile_values, threshold)

        assert prob == 0.0

    def test_estimate_breach_probability_all_breaches(self) -> None:
        """Test breach probability when all values above threshold."""
        calc = LatencyCalculator()
        percentile_values = [150.0, 160.0, 155.0, 145.0, 170.0]
        threshold = 120.0

        prob = calc.estimate_breach_probability(percentile_values, threshold)

        assert prob == 1.0

    def test_estimate_breach_probability_partial_breaches(self) -> None:
        """Test breach probability with partial breaches."""
        calc = LatencyCalculator()
        percentile_values = [100.0, 150.0, 110.0, 160.0, 105.0]  # 2 out of 5 breach
        threshold = 120.0

        prob = calc.estimate_breach_probability(percentile_values, threshold)

        assert prob == 0.4  # 2/5

    def test_estimate_breach_probability_edge_case_threshold(self) -> None:
        """Test breach probability with threshold exactly at max value."""
        calc = LatencyCalculator()
        percentile_values = [100.0, 110.0, 105.0, 115.0, 120.0]
        threshold = 120.0

        prob = calc.estimate_breach_probability(percentile_values, threshold)

        # No breach since 120 <= 120 is False
        assert prob == 0.0

    def test_estimate_breach_probability_empty_data(self) -> None:
        """Test breach probability returns 0.5 for empty data (maximum uncertainty)."""
        calc = LatencyCalculator()
        prob = calc.estimate_breach_probability([], 100.0)
        assert prob == 0.5


class TestBootstrapConfidenceInterval:
    """Tests for bootstrap confidence interval computation."""

    def test_bootstrap_confidence_interval_single_value(self) -> None:
        """Test bootstrap CI with single value (no variability)."""
        calc = LatencyCalculator(bootstrap_resample_count=100)
        percentile_values = [250.0]

        lower, upper = calc._bootstrap_confidence_interval(percentile_values, 0.99)

        # No variability, CI should be point estimate
        assert lower == 250.0
        assert upper == 250.0

    def test_bootstrap_confidence_interval_uniform_data(self) -> None:
        """Test bootstrap CI with uniform data (low variability)."""
        calc = LatencyCalculator(bootstrap_resample_count=100)
        percentile_values = [250.0] * 30

        lower, upper = calc._bootstrap_confidence_interval(percentile_values, 0.99)

        # All values identical, CI should be tight
        assert lower == 250.0
        assert upper == 250.0

    def test_bootstrap_confidence_interval_variable_data(self) -> None:
        """Test bootstrap CI with variable data."""
        calc = LatencyCalculator(bootstrap_resample_count=500)
        percentile_values = [200.0, 220.0, 240.0, 260.0, 280.0, 300.0]

        lower, upper = calc._bootstrap_confidence_interval(percentile_values, 0.99)

        # CI should span some range
        assert lower < upper
        assert lower >= min(percentile_values)
        assert upper <= max(percentile_values) or abs(upper - max(percentile_values)) < 1.0

    def test_bootstrap_confidence_interval_high_variability(self) -> None:
        """Test bootstrap CI with high variability data."""
        calc = LatencyCalculator(bootstrap_resample_count=500)
        percentile_values = [100.0, 150.0, 500.0, 200.0, 800.0, 250.0]

        lower, upper = calc._bootstrap_confidence_interval(percentile_values, 0.99)

        # CI should be wide
        assert upper - lower > 100.0
        assert lower >= min(percentile_values)

    def test_bootstrap_confidence_interval_bounds(self) -> None:
        """Test bootstrap CI respects bounds of input data."""
        calc = LatencyCalculator(bootstrap_resample_count=1000)
        percentile_values = [100.0, 120.0, 130.0, 140.0, 150.0]

        lower, upper = calc._bootstrap_confidence_interval(percentile_values, 0.95)

        # CI should be within data range (bootstrap resampling can't exceed max)
        assert lower >= min(percentile_values) - 1.0  # Small tolerance for floating point
        assert upper <= max(percentile_values) + 1.0


class TestIntegrationScenarios:
    """Integration tests with realistic scenarios."""

    def test_stable_low_latency_service(self) -> None:
        """Test recommendation for stable low-latency service."""
        calc = LatencyCalculator(noise_margin_default=0.05, bootstrap_resample_count=200)

        # Stable low latency: p50=50ms, p95=100ms, p99=120ms, p999=150ms
        sli_data = [
            create_latency_sli(50.0, 100.0, 120.0, 150.0, days_ago=i)
            for i in range(30)
        ]

        tiers = calc.compute_tiers(sli_data, shared_infrastructure=False)

        conservative = next(t for t in tiers if t.level == TierLevel.CONSERVATIVE)
        balanced = next(t for t in tiers if t.level == TierLevel.BALANCED)
        aggressive = next(t for t in tiers if t.level == TierLevel.AGGRESSIVE)

        # Conservative: 150 * 1.05 = 157.5ms
        assert conservative.target == 157.5
        # Balanced: 120 * 1.05 = 126ms
        assert balanced.target == 126.0
        # Aggressive: 100ms
        assert aggressive.target == 100.0

        # Breach probabilities should be low for stable service
        assert conservative.estimated_breach_probability == 0.0
        assert balanced.estimated_breach_probability == 0.0
        assert aggressive.estimated_breach_probability == 0.0

    def test_high_latency_shared_infrastructure_service(self) -> None:
        """Test recommendation for high-latency service on shared infrastructure."""
        calc = LatencyCalculator(
            noise_margin_default=0.05,
            noise_margin_shared_infra=0.10,
            bootstrap_resample_count=200,
        )

        # High latency: p50=500ms, p95=1000ms, p99=1500ms, p999=2000ms
        sli_data = [
            create_latency_sli(500.0, 1000.0, 1500.0, 2000.0, days_ago=i)
            for i in range(20)
        ]

        tiers = calc.compute_tiers(sli_data, shared_infrastructure=True)

        conservative = next(t for t in tiers if t.level == TierLevel.CONSERVATIVE)
        balanced = next(t for t in tiers if t.level == TierLevel.BALANCED)
        aggressive = next(t for t in tiers if t.level == TierLevel.AGGRESSIVE)

        # Conservative: 2000 * 1.10 = 2200ms
        assert abs(conservative.target - 2200.0) < 0.01
        # Balanced: 1500 * 1.10 = 1650ms
        assert abs(balanced.target - 1650.0) < 0.01
        # Aggressive: 1000ms
        assert abs(aggressive.target - 1000.0) < 0.01

    def test_service_with_occasional_spikes(self) -> None:
        """Test recommendation for service with occasional latency spikes."""
        calc = LatencyCalculator(noise_margin_default=0.05, bootstrap_resample_count=200)

        sli_data = [
            create_latency_sli(100.0, 200.0, 250.0, 300.0, days_ago=0),
            create_latency_sli(100.0, 200.0, 250.0, 300.0, days_ago=1),
            create_latency_sli(100.0, 200.0, 250.0, 300.0, days_ago=2),
            create_latency_sli(100.0, 200.0, 250.0, 300.0, days_ago=3),
            create_latency_sli(150.0, 400.0, 600.0, 800.0, days_ago=4),  # Spike 1
            create_latency_sli(100.0, 200.0, 250.0, 300.0, days_ago=5),
            create_latency_sli(100.0, 200.0, 250.0, 300.0, days_ago=6),
            create_latency_sli(140.0, 350.0, 550.0, 750.0, days_ago=7),  # Spike 2
        ]

        tiers = calc.compute_tiers(sli_data, shared_infrastructure=False)

        conservative = next(t for t in tiers if t.level == TierLevel.CONSERVATIVE)
        balanced = next(t for t in tiers if t.level == TierLevel.BALANCED)
        aggressive = next(t for t in tiers if t.level == TierLevel.AGGRESSIVE)

        # Conservative: max(p999) + 5% = 800 * 1.05 = 840ms
        assert conservative.target == 840.0
        # Balanced: max(p99) + 5% = 600 * 1.05 = 630ms
        assert balanced.target == 630.0
        # Aggressive: max(p95) = 400ms
        assert aggressive.target == 400.0

        # Breach probabilities should be 0 since targets include noise margins above the spikes
        # (targets: 840ms, 630ms, 400ms are all above historical max values with margin)
        assert conservative.estimated_breach_probability == 0.0
        assert balanced.estimated_breach_probability == 0.0
        assert aggressive.estimated_breach_probability == 0.0

    def test_known_answer_test_vector(self) -> None:
        """Test with known answer test vector for correctness."""
        calc = LatencyCalculator(noise_margin_default=0.10, bootstrap_resample_count=100)

        # Known data: p50=100, p95=200, p99=250, p999=300
        sli_data = [
            create_latency_sli(100.0, 200.0, 250.0, 300.0, days_ago=0),
            create_latency_sli(100.0, 200.0, 250.0, 300.0, days_ago=1),
        ]

        tiers = calc.compute_tiers(sli_data, shared_infrastructure=False)

        conservative = next(t for t in tiers if t.level == TierLevel.CONSERVATIVE)
        balanced = next(t for t in tiers if t.level == TierLevel.BALANCED)
        aggressive = next(t for t in tiers if t.level == TierLevel.AGGRESSIVE)

        # Conservative: 300 * 1.10 = 330ms
        assert conservative.target == 330.0
        assert conservative.estimated_breach_probability == 0.0
        # Balanced: 250 * 1.10 = 275ms
        assert balanced.target == 275.0
        assert balanced.estimated_breach_probability == 0.0
        # Aggressive: 200ms
        assert aggressive.target == 200.0
        assert aggressive.estimated_breach_probability == 0.0
