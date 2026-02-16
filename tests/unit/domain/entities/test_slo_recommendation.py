"""Unit tests for SLO recommendation domain entities."""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from src.domain.entities.slo_recommendation import (
    DataQuality,
    DependencyImpact,
    Explanation,
    FeatureAttribution,
    RecommendationStatus,
    RecommendationTier,
    SliType,
    SloRecommendation,
    TierLevel,
)


class TestRecommendationTier:
    """Tests for RecommendationTier entity."""

    def test_create_availability_tier(self):
        """Test creating a valid availability tier."""
        tier = RecommendationTier(
            level=TierLevel.BALANCED,
            target=99.9,
            error_budget_monthly_minutes=43.8,
            estimated_breach_probability=0.08,
            confidence_interval=(99.8, 99.95),
        )

        assert tier.level == TierLevel.BALANCED
        assert tier.target == 99.9
        assert tier.error_budget_monthly_minutes == 43.8
        assert tier.estimated_breach_probability == 0.08
        assert tier.confidence_interval == (99.8, 99.95)

    def test_create_latency_tier(self):
        """Test creating a valid latency tier."""
        tier = RecommendationTier(
            level=TierLevel.AGGRESSIVE,
            target=500.0,
            percentile="p95",
            target_ms=500,
            estimated_breach_probability=0.12,
        )

        assert tier.level == TierLevel.AGGRESSIVE
        assert tier.target == 500.0
        assert tier.percentile == "p95"
        assert tier.target_ms == 500
        assert tier.error_budget_monthly_minutes is None

    def test_breach_probability_validation_too_high(self):
        """Test that breach probability > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="estimated_breach_probability must be between 0.0 and 1.0"):
            RecommendationTier(
                level=TierLevel.BALANCED,
                target=99.9,
                estimated_breach_probability=1.5,
            )

    def test_breach_probability_validation_negative(self):
        """Test that negative breach probability raises ValueError."""
        with pytest.raises(ValueError, match="estimated_breach_probability must be between 0.0 and 1.0"):
            RecommendationTier(
                level=TierLevel.BALANCED,
                target=99.9,
                estimated_breach_probability=-0.1,
            )

    def test_breach_probability_edge_cases(self):
        """Test that 0.0 and 1.0 are valid breach probabilities."""
        tier_zero = RecommendationTier(
            level=TierLevel.CONSERVATIVE,
            target=99.5,
            estimated_breach_probability=0.0,
        )
        assert tier_zero.estimated_breach_probability == 0.0

        tier_one = RecommendationTier(
            level=TierLevel.AGGRESSIVE,
            target=99.99,
            estimated_breach_probability=1.0,
        )
        assert tier_one.estimated_breach_probability == 1.0


class TestFeatureAttribution:
    """Tests for FeatureAttribution entity."""

    def test_create_feature_attribution(self):
        """Test creating a valid feature attribution."""
        attr = FeatureAttribution(
            feature="historical_availability_mean",
            contribution=0.42,
            description="Primary driver based on 30-day average",
        )

        assert attr.feature == "historical_availability_mean"
        assert attr.contribution == 0.42
        assert attr.description == "Primary driver based on 30-day average"

    def test_contribution_validation_too_high(self):
        """Test that contribution > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="contribution must be between 0.0 and 1.0"):
            FeatureAttribution(
                feature="test_feature",
                contribution=1.5,
            )

    def test_contribution_validation_negative(self):
        """Test that negative contribution raises ValueError."""
        with pytest.raises(ValueError, match="contribution must be between 0.0 and 1.0"):
            FeatureAttribution(
                feature="test_feature",
                contribution=-0.1,
            )

    def test_contribution_edge_cases(self):
        """Test that 0.0 and 1.0 are valid contributions."""
        attr_zero = FeatureAttribution(feature="zero", contribution=0.0)
        assert attr_zero.contribution == 0.0

        attr_one = FeatureAttribution(feature="one", contribution=1.0)
        assert attr_one.contribution == 1.0


class TestDependencyImpact:
    """Tests for DependencyImpact entity."""

    def test_create_dependency_impact(self):
        """Test creating a valid dependency impact."""
        impact = DependencyImpact(
            composite_availability_bound=0.997,
            bottleneck_service="external-payment-api",
            bottleneck_contribution="Consumes 50% of error budget at 99.9% target",
            hard_dependency_count=3,
            soft_dependency_count=1,
        )

        assert impact.composite_availability_bound == 0.997
        assert impact.bottleneck_service == "external-payment-api"
        assert impact.bottleneck_contribution == "Consumes 50% of error budget at 99.9% target"
        assert impact.hard_dependency_count == 3
        assert impact.soft_dependency_count == 1

    def test_composite_bound_validation_too_high(self):
        """Test that composite bound > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="composite_availability_bound must be between 0.0 and 1.0"):
            DependencyImpact(composite_availability_bound=1.5)

    def test_composite_bound_validation_negative(self):
        """Test that negative composite bound raises ValueError."""
        with pytest.raises(ValueError, match="composite_availability_bound must be between 0.0 and 1.0"):
            DependencyImpact(composite_availability_bound=-0.1)

    def test_dependency_count_validation_negative_hard(self):
        """Test that negative hard dependency count raises ValueError."""
        with pytest.raises(ValueError, match="hard_dependency_count must be non-negative"):
            DependencyImpact(
                composite_availability_bound=0.99,
                hard_dependency_count=-1,
            )

    def test_dependency_count_validation_negative_soft(self):
        """Test that negative soft dependency count raises ValueError."""
        with pytest.raises(ValueError, match="soft_dependency_count must be non-negative"):
            DependencyImpact(
                composite_availability_bound=0.99,
                soft_dependency_count=-1,
            )


class TestDataQuality:
    """Tests for DataQuality entity."""

    def test_create_data_quality(self):
        """Test creating valid data quality metadata."""
        quality = DataQuality(
            data_completeness=0.97,
            telemetry_gaps=[
                {"start": "2026-01-15T00:00:00Z", "end": "2026-01-15T02:00:00Z", "reason": "Prometheus outage"}
            ],
            confidence_note="Based on 30 days of continuous data with 97% completeness",
            is_cold_start=False,
            lookback_days_actual=30,
        )

        assert quality.data_completeness == 0.97
        assert len(quality.telemetry_gaps) == 1
        assert quality.confidence_note == "Based on 30 days of continuous data with 97% completeness"
        assert quality.is_cold_start is False
        assert quality.lookback_days_actual == 30

    def test_data_completeness_validation_too_high(self):
        """Test that data completeness > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="data_completeness must be between 0.0 and 1.0"):
            DataQuality(data_completeness=1.5)

    def test_data_completeness_validation_negative(self):
        """Test that negative data completeness raises ValueError."""
        with pytest.raises(ValueError, match="data_completeness must be between 0.0 and 1.0"):
            DataQuality(data_completeness=-0.1)

    def test_lookback_days_validation_zero(self):
        """Test that zero lookback days raises ValueError."""
        with pytest.raises(ValueError, match="lookback_days_actual must be positive"):
            DataQuality(data_completeness=0.95, lookback_days_actual=0)

    def test_lookback_days_validation_negative(self):
        """Test that negative lookback days raises ValueError."""
        with pytest.raises(ValueError, match="lookback_days_actual must be positive"):
            DataQuality(data_completeness=0.95, lookback_days_actual=-5)

    def test_default_values(self):
        """Test that defaults are set correctly."""
        quality = DataQuality(data_completeness=1.0)

        assert quality.telemetry_gaps == []
        assert quality.confidence_note == ""
        assert quality.is_cold_start is False
        assert quality.lookback_days_actual == 30


class TestExplanation:
    """Tests for Explanation entity."""

    def test_create_explanation(self):
        """Test creating a valid explanation."""
        attributions = [
            FeatureAttribution("historical_availability_mean", 0.42),
            FeatureAttribution("downstream_dependency_risk", 0.28),
        ]
        impact = DependencyImpact(
            composite_availability_bound=0.997,
            bottleneck_service="payment-api",
            hard_dependency_count=3,
        )
        explanation = Explanation(
            summary="Service achieved 99.92% availability over 30 days",
            feature_attribution=attributions,
            dependency_impact=impact,
        )

        assert explanation.summary == "Service achieved 99.92% availability over 30 days"
        assert len(explanation.feature_attribution) == 2
        assert explanation.dependency_impact.composite_availability_bound == 0.997

    def test_default_values(self):
        """Test that defaults are set correctly."""
        explanation = Explanation(summary="Test summary")

        assert explanation.feature_attribution == []
        assert explanation.dependency_impact is None


class TestSloRecommendation:
    """Tests for SloRecommendation entity."""

    @pytest.fixture
    def sample_tiers(self):
        """Sample tiers for testing."""
        return {
            TierLevel.CONSERVATIVE: RecommendationTier(
                level=TierLevel.CONSERVATIVE,
                target=99.5,
                error_budget_monthly_minutes=219.6,
                estimated_breach_probability=0.02,
            ),
            TierLevel.BALANCED: RecommendationTier(
                level=TierLevel.BALANCED,
                target=99.9,
                error_budget_monthly_minutes=43.8,
                estimated_breach_probability=0.08,
            ),
            TierLevel.AGGRESSIVE: RecommendationTier(
                level=TierLevel.AGGRESSIVE,
                target=99.95,
                error_budget_monthly_minutes=21.9,
                estimated_breach_probability=0.18,
            ),
        }

    @pytest.fixture
    def sample_explanation(self):
        """Sample explanation for testing."""
        return Explanation(
            summary="Service achieved 99.92% availability",
            feature_attribution=[
                FeatureAttribution("historical_availability_mean", 0.5),
                FeatureAttribution("dependency_risk", 0.5),
            ],
        )

    @pytest.fixture
    def sample_data_quality(self):
        """Sample data quality for testing."""
        return DataQuality(data_completeness=0.97)

    def test_create_slo_recommendation(self, sample_tiers, sample_explanation, sample_data_quality):
        """Test creating a valid SLO recommendation."""
        service_id = uuid4()
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=30)

        rec = SloRecommendation(
            service_id=service_id,
            sli_type=SliType.AVAILABILITY,
            tiers=sample_tiers,
            explanation=sample_explanation,
            data_quality=sample_data_quality,
            lookback_window_start=start,
            lookback_window_end=now,
            metric="error_rate",
        )

        assert rec.service_id == service_id
        assert rec.sli_type == SliType.AVAILABILITY
        assert len(rec.tiers) == 3
        assert rec.metric == "error_rate"
        assert rec.status == RecommendationStatus.ACTIVE
        assert isinstance(rec.id, UUID)
        assert isinstance(rec.generated_at, datetime)
        assert rec.expires_at is not None

    def test_auto_compute_expiry(self, sample_tiers, sample_explanation, sample_data_quality):
        """Test that expiry is auto-computed as generated_at + 24h."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=30)

        rec = SloRecommendation(
            service_id=uuid4(),
            sli_type=SliType.AVAILABILITY,
            tiers=sample_tiers,
            explanation=sample_explanation,
            data_quality=sample_data_quality,
            lookback_window_start=start,
            lookback_window_end=now,
            metric="error_rate",
        )

        expected_expiry = rec.generated_at + timedelta(hours=24)
        # Allow 1 second tolerance for test execution time
        assert abs((rec.expires_at - expected_expiry).total_seconds()) < 1

    def test_explicit_expiry_preserved(self, sample_tiers, sample_explanation, sample_data_quality):
        """Test that explicitly set expiry is preserved."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=30)
        custom_expiry = now + timedelta(hours=48)

        rec = SloRecommendation(
            service_id=uuid4(),
            sli_type=SliType.AVAILABILITY,
            tiers=sample_tiers,
            explanation=sample_explanation,
            data_quality=sample_data_quality,
            lookback_window_start=start,
            lookback_window_end=now,
            metric="error_rate",
            expires_at=custom_expiry,
        )

        assert rec.expires_at == custom_expiry

    def test_empty_tiers_raises_error(self, sample_explanation, sample_data_quality):
        """Test that empty tiers dict raises ValueError."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=30)

        with pytest.raises(ValueError, match="tiers dict cannot be empty"):
            SloRecommendation(
                service_id=uuid4(),
                sli_type=SliType.AVAILABILITY,
                tiers={},
                explanation=sample_explanation,
                data_quality=sample_data_quality,
                lookback_window_start=start,
                lookback_window_end=now,
                metric="error_rate",
            )

    def test_invalid_lookback_window_raises_error(self, sample_tiers, sample_explanation, sample_data_quality):
        """Test that end <= start raises ValueError."""
        now = datetime.now(timezone.utc)
        later = now + timedelta(days=1)

        with pytest.raises(ValueError, match="lookback_window_end must be after lookback_window_start"):
            SloRecommendation(
                service_id=uuid4(),
                sli_type=SliType.AVAILABILITY,
                tiers=sample_tiers,
                explanation=sample_explanation,
                data_quality=sample_data_quality,
                lookback_window_start=later,
                lookback_window_end=now,
                metric="error_rate",
            )

    def test_supersede_method(self, sample_tiers, sample_explanation, sample_data_quality):
        """Test that supersede() changes status to SUPERSEDED."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=30)

        rec = SloRecommendation(
            service_id=uuid4(),
            sli_type=SliType.AVAILABILITY,
            tiers=sample_tiers,
            explanation=sample_explanation,
            data_quality=sample_data_quality,
            lookback_window_start=start,
            lookback_window_end=now,
            metric="error_rate",
        )

        assert rec.status == RecommendationStatus.ACTIVE
        rec.supersede()
        assert rec.status == RecommendationStatus.SUPERSEDED

    def test_expire_method(self, sample_tiers, sample_explanation, sample_data_quality):
        """Test that expire() changes status to EXPIRED."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=30)

        rec = SloRecommendation(
            service_id=uuid4(),
            sli_type=SliType.AVAILABILITY,
            tiers=sample_tiers,
            explanation=sample_explanation,
            data_quality=sample_data_quality,
            lookback_window_start=start,
            lookback_window_end=now,
            metric="error_rate",
        )

        assert rec.status == RecommendationStatus.ACTIVE
        rec.expire()
        assert rec.status == RecommendationStatus.EXPIRED

    def test_is_expired_property_not_expired(self, sample_tiers, sample_explanation, sample_data_quality):
        """Test is_expired returns False for non-expired recommendation."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=30)

        rec = SloRecommendation(
            service_id=uuid4(),
            sli_type=SliType.AVAILABILITY,
            tiers=sample_tiers,
            explanation=sample_explanation,
            data_quality=sample_data_quality,
            lookback_window_start=start,
            lookback_window_end=now,
            metric="error_rate",
        )

        assert rec.is_expired is False

    def test_is_expired_property_expired(self, sample_tiers, sample_explanation, sample_data_quality):
        """Test is_expired returns True for expired recommendation."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=30)
        past_expiry = now - timedelta(hours=1)

        rec = SloRecommendation(
            service_id=uuid4(),
            sli_type=SliType.AVAILABILITY,
            tiers=sample_tiers,
            explanation=sample_explanation,
            data_quality=sample_data_quality,
            lookback_window_start=start,
            lookback_window_end=now,
            metric="error_rate",
            expires_at=past_expiry,
        )

        assert rec.is_expired is True

    def test_is_expired_property_no_expiry(self, sample_tiers, sample_explanation, sample_data_quality):
        """Test is_expired returns False when expires_at is None."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=30)

        rec = SloRecommendation(
            service_id=uuid4(),
            sli_type=SliType.AVAILABILITY,
            tiers=sample_tiers,
            explanation=sample_explanation,
            data_quality=sample_data_quality,
            lookback_window_start=start,
            lookback_window_end=now,
            metric="error_rate",
        )
        # Manually set to None to test this edge case
        rec.expires_at = None

        assert rec.is_expired is False
