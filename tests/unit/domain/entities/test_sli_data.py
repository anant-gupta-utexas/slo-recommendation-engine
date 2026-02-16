"""Unit tests for SLI data value objects."""

import pytest
from datetime import datetime, timedelta, timezone

from src.domain.entities.sli_data import AvailabilitySliData, LatencySliData


class TestAvailabilitySliData:
    """Tests for AvailabilitySliData value object."""

    @pytest.fixture
    def sample_window(self):
        """Sample time window for testing."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=30)
        return start, now

    def test_create_availability_sli_data(self, sample_window):
        """Test creating valid availability SLI data."""
        start, end = sample_window
        data = AvailabilitySliData(
            service_id="checkout-service",
            good_events=99920,
            total_events=100000,
            availability_ratio=0.9992,
            window_start=start,
            window_end=end,
            sample_count=30,
        )

        assert data.service_id == "checkout-service"
        assert data.good_events == 99920
        assert data.total_events == 100000
        assert data.availability_ratio == 0.9992
        assert data.window_start == start
        assert data.window_end == end
        assert data.sample_count == 30

    def test_error_rate_property(self, sample_window):
        """Test that error_rate is computed correctly from availability_ratio."""
        start, end = sample_window
        data = AvailabilitySliData(
            service_id="test-service",
            good_events=995,
            total_events=1000,
            availability_ratio=0.995,
            window_start=start,
            window_end=end,
        )

        assert data.error_rate == pytest.approx(0.005)

    def test_perfect_availability_zero_error_rate(self, sample_window):
        """Test that 100% availability gives 0% error rate."""
        start, end = sample_window
        data = AvailabilitySliData(
            service_id="test-service",
            good_events=1000,
            total_events=1000,
            availability_ratio=1.0,
            window_start=start,
            window_end=end,
        )

        assert data.error_rate == 0.0

    def test_negative_good_events_raises_error(self, sample_window):
        """Test that negative good_events raises ValueError."""
        start, end = sample_window
        with pytest.raises(ValueError, match="good_events must be non-negative"):
            AvailabilitySliData(
                service_id="test-service",
                good_events=-1,
                total_events=1000,
                availability_ratio=0.999,
                window_start=start,
                window_end=end,
            )

    def test_negative_total_events_raises_error(self, sample_window):
        """Test that negative total_events raises ValueError."""
        start, end = sample_window
        with pytest.raises(ValueError, match="total_events must be non-negative"):
            AvailabilitySliData(
                service_id="test-service",
                good_events=999,
                total_events=-1,
                availability_ratio=0.999,
                window_start=start,
                window_end=end,
            )

    def test_good_events_exceeds_total_raises_error(self, sample_window):
        """Test that good_events > total_events raises ValueError."""
        start, end = sample_window
        with pytest.raises(ValueError, match="good_events .* cannot exceed total_events"):
            AvailabilitySliData(
                service_id="test-service",
                good_events=1001,
                total_events=1000,
                availability_ratio=1.0,
                window_start=start,
                window_end=end,
            )

    def test_availability_ratio_too_high_raises_error(self, sample_window):
        """Test that availability_ratio > 1.0 raises ValueError."""
        start, end = sample_window
        with pytest.raises(ValueError, match="availability_ratio must be between 0.0 and 1.0"):
            AvailabilitySliData(
                service_id="test-service",
                good_events=1000,
                total_events=1000,
                availability_ratio=1.5,
                window_start=start,
                window_end=end,
            )

    def test_availability_ratio_negative_raises_error(self, sample_window):
        """Test that negative availability_ratio raises ValueError."""
        start, end = sample_window
        with pytest.raises(ValueError, match="availability_ratio must be between 0.0 and 1.0"):
            AvailabilitySliData(
                service_id="test-service",
                good_events=0,
                total_events=1000,
                availability_ratio=-0.1,
                window_start=start,
                window_end=end,
            )

    def test_negative_sample_count_raises_error(self, sample_window):
        """Test that negative sample_count raises ValueError."""
        start, end = sample_window
        with pytest.raises(ValueError, match="sample_count must be non-negative"):
            AvailabilitySliData(
                service_id="test-service",
                good_events=999,
                total_events=1000,
                availability_ratio=0.999,
                window_start=start,
                window_end=end,
                sample_count=-1,
            )

    def test_invalid_window_raises_error(self, sample_window):
        """Test that window_end <= window_start raises ValueError."""
        start, end = sample_window
        with pytest.raises(ValueError, match="window_end must be after window_start"):
            AvailabilitySliData(
                service_id="test-service",
                good_events=999,
                total_events=1000,
                availability_ratio=0.999,
                window_start=end,
                window_end=start,
            )

    def test_default_sample_count(self, sample_window):
        """Test that sample_count defaults to 0."""
        start, end = sample_window
        data = AvailabilitySliData(
            service_id="test-service",
            good_events=999,
            total_events=1000,
            availability_ratio=0.999,
            window_start=start,
            window_end=end,
        )

        assert data.sample_count == 0


class TestLatencySliData:
    """Tests for LatencySliData value object."""

    @pytest.fixture
    def sample_window(self):
        """Sample time window for testing."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=30)
        return start, now

    def test_create_latency_sli_data(self, sample_window):
        """Test creating valid latency SLI data."""
        start, end = sample_window
        data = LatencySliData(
            service_id="checkout-service",
            p50_ms=120.5,
            p95_ms=450.0,
            p99_ms=780.0,
            p999_ms=1150.0,
            window_start=start,
            window_end=end,
            sample_count=100000,
        )

        assert data.service_id == "checkout-service"
        assert data.p50_ms == 120.5
        assert data.p95_ms == 450.0
        assert data.p99_ms == 780.0
        assert data.p999_ms == 1150.0
        assert data.window_start == start
        assert data.window_end == end
        assert data.sample_count == 100000

    def test_all_percentiles_equal_valid(self, sample_window):
        """Test that all percentiles being equal is valid (constant latency)."""
        start, end = sample_window
        data = LatencySliData(
            service_id="test-service",
            p50_ms=100.0,
            p95_ms=100.0,
            p99_ms=100.0,
            p999_ms=100.0,
            window_start=start,
            window_end=end,
        )

        assert data.p50_ms == 100.0
        assert data.p95_ms == 100.0
        assert data.p99_ms == 100.0
        assert data.p999_ms == 100.0

    def test_zero_latency_valid(self, sample_window):
        """Test that zero latency is valid."""
        start, end = sample_window
        data = LatencySliData(
            service_id="test-service",
            p50_ms=0.0,
            p95_ms=0.0,
            p99_ms=0.0,
            p999_ms=0.0,
            window_start=start,
            window_end=end,
        )

        assert data.p50_ms == 0.0

    def test_negative_p50_raises_error(self, sample_window):
        """Test that negative p50 raises ValueError."""
        start, end = sample_window
        with pytest.raises(ValueError, match="p50_ms must be non-negative"):
            LatencySliData(
                service_id="test-service",
                p50_ms=-1.0,
                p95_ms=450.0,
                p99_ms=780.0,
                p999_ms=1150.0,
                window_start=start,
                window_end=end,
            )

    def test_negative_p95_raises_error(self, sample_window):
        """Test that negative p95 raises ValueError."""
        start, end = sample_window
        with pytest.raises(ValueError, match="p95_ms must be non-negative"):
            LatencySliData(
                service_id="test-service",
                p50_ms=120.0,
                p95_ms=-1.0,
                p99_ms=780.0,
                p999_ms=1150.0,
                window_start=start,
                window_end=end,
            )

    def test_negative_p99_raises_error(self, sample_window):
        """Test that negative p99 raises ValueError."""
        start, end = sample_window
        with pytest.raises(ValueError, match="p99_ms must be non-negative"):
            LatencySliData(
                service_id="test-service",
                p50_ms=120.0,
                p95_ms=450.0,
                p99_ms=-1.0,
                p999_ms=1150.0,
                window_start=start,
                window_end=end,
            )

    def test_negative_p999_raises_error(self, sample_window):
        """Test that negative p999 raises ValueError."""
        start, end = sample_window
        with pytest.raises(ValueError, match="p999_ms must be non-negative"):
            LatencySliData(
                service_id="test-service",
                p50_ms=120.0,
                p95_ms=450.0,
                p99_ms=780.0,
                p999_ms=-1.0,
                window_start=start,
                window_end=end,
            )

    def test_percentile_ordering_p50_greater_than_p95_raises_error(self, sample_window):
        """Test that p50 > p95 raises ValueError."""
        start, end = sample_window
        with pytest.raises(ValueError, match="Percentiles must be in ascending order"):
            LatencySliData(
                service_id="test-service",
                p50_ms=500.0,
                p95_ms=450.0,
                p99_ms=780.0,
                p999_ms=1150.0,
                window_start=start,
                window_end=end,
            )

    def test_percentile_ordering_p95_greater_than_p99_raises_error(self, sample_window):
        """Test that p95 > p99 raises ValueError."""
        start, end = sample_window
        with pytest.raises(ValueError, match="Percentiles must be in ascending order"):
            LatencySliData(
                service_id="test-service",
                p50_ms=120.0,
                p95_ms=800.0,
                p99_ms=780.0,
                p999_ms=1150.0,
                window_start=start,
                window_end=end,
            )

    def test_percentile_ordering_p99_greater_than_p999_raises_error(self, sample_window):
        """Test that p99 > p999 raises ValueError."""
        start, end = sample_window
        with pytest.raises(ValueError, match="Percentiles must be in ascending order"):
            LatencySliData(
                service_id="test-service",
                p50_ms=120.0,
                p95_ms=450.0,
                p99_ms=1200.0,
                p999_ms=1150.0,
                window_start=start,
                window_end=end,
            )

    def test_negative_sample_count_raises_error(self, sample_window):
        """Test that negative sample_count raises ValueError."""
        start, end = sample_window
        with pytest.raises(ValueError, match="sample_count must be non-negative"):
            LatencySliData(
                service_id="test-service",
                p50_ms=120.0,
                p95_ms=450.0,
                p99_ms=780.0,
                p999_ms=1150.0,
                window_start=start,
                window_end=end,
                sample_count=-1,
            )

    def test_invalid_window_raises_error(self, sample_window):
        """Test that window_end <= window_start raises ValueError."""
        start, end = sample_window
        with pytest.raises(ValueError, match="window_end must be after window_start"):
            LatencySliData(
                service_id="test-service",
                p50_ms=120.0,
                p95_ms=450.0,
                p99_ms=780.0,
                p999_ms=1150.0,
                window_start=end,
                window_end=start,
            )

    def test_default_sample_count(self, sample_window):
        """Test that sample_count defaults to 0."""
        start, end = sample_window
        data = LatencySliData(
            service_id="test-service",
            p50_ms=120.0,
            p95_ms=450.0,
            p99_ms=780.0,
            p999_ms=1150.0,
            window_start=start,
            window_end=end,
        )

        assert data.sample_count == 0
