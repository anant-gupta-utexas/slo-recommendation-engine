"""
Unit tests for SLO recommendation Pydantic API schemas.

Tests validation rules, field constraints, and schema structure.
"""

import pytest
from pydantic import ValidationError

from src.infrastructure.api.schemas.slo_recommendation_schema import (
    DataQualityApiModel,
    DependencyImpactApiModel,
    ExplanationApiModel,
    FeatureAttributionApiModel,
    LookbackWindowApiModel,
    RecommendationApiModel,
    SloRecommendationApiResponse,
    SloRecommendationQueryParams,
    TierApiModel,
)


# ============================================================================
# Query Parameters Tests
# ============================================================================


class TestSloRecommendationQueryParams:
    """Tests for SloRecommendationQueryParams validation."""

    def test_default_values(self):
        """Default values should match spec."""
        params = SloRecommendationQueryParams()
        assert params.sli_type == "all"
        assert params.lookback_days == 30
        assert params.force_regenerate is False

    def test_valid_sli_types(self):
        """Valid sli_type values should be accepted."""
        for sli_type in ["availability", "latency", "all"]:
            params = SloRecommendationQueryParams(sli_type=sli_type)
            assert params.sli_type == sli_type

    def test_invalid_sli_type(self):
        """Invalid sli_type should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            SloRecommendationQueryParams(sli_type="invalid")
        assert "sli_type" in str(exc_info.value)

    def test_lookback_days_minimum(self):
        """lookback_days minimum should be 7."""
        params = SloRecommendationQueryParams(lookback_days=7)
        assert params.lookback_days == 7

    def test_lookback_days_maximum(self):
        """lookback_days maximum should be 365."""
        params = SloRecommendationQueryParams(lookback_days=365)
        assert params.lookback_days == 365

    def test_lookback_days_below_minimum(self):
        """lookback_days below 7 should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            SloRecommendationQueryParams(lookback_days=6)
        assert "lookback_days" in str(exc_info.value)

    def test_lookback_days_above_maximum(self):
        """lookback_days above 365 should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            SloRecommendationQueryParams(lookback_days=366)
        assert "lookback_days" in str(exc_info.value)

    def test_force_regenerate_true(self):
        """force_regenerate=True should be accepted."""
        params = SloRecommendationQueryParams(force_regenerate=True)
        assert params.force_regenerate is True

    def test_all_parameters_custom(self):
        """All parameters with custom values should work."""
        params = SloRecommendationQueryParams(
            sli_type="availability", lookback_days=90, force_regenerate=True
        )
        assert params.sli_type == "availability"
        assert params.lookback_days == 90
        assert params.force_regenerate is True


# ============================================================================
# Tier Model Tests
# ============================================================================


class TestTierApiModel:
    """Tests for TierApiModel."""

    def test_minimal_tier(self):
        """Minimal tier with only required fields."""
        tier = TierApiModel(level="balanced", target=99.9)
        assert tier.level == "balanced"
        assert tier.target == 99.9
        assert tier.error_budget_monthly_minutes is None
        assert tier.confidence_interval is None
        assert tier.estimated_breach_probability == 0.0
        assert tier.percentile is None
        assert tier.target_ms is None

    def test_availability_tier(self):
        """Availability tier with all relevant fields."""
        tier = TierApiModel(
            level="balanced",
            target=99.9,
            error_budget_monthly_minutes=43.8,
            confidence_interval=(99.8, 99.95),
            estimated_breach_probability=0.08,
        )
        assert tier.error_budget_monthly_minutes == 43.8
        assert tier.confidence_interval == (99.8, 99.95)
        assert tier.estimated_breach_probability == 0.08

    def test_latency_tier(self):
        """Latency tier with all relevant fields."""
        tier = TierApiModel(
            level="balanced",
            target=800.0,
            percentile="p99",
            target_ms=800,
            estimated_breach_probability=0.05,
        )
        assert tier.percentile == "p99"
        assert tier.target_ms == 800
        assert tier.estimated_breach_probability == 0.05

    def test_breach_probability_validation(self):
        """Breach probability must be between 0.0 and 1.0."""
        # Valid values
        TierApiModel(level="balanced", target=99.9, estimated_breach_probability=0.0)
        TierApiModel(level="balanced", target=99.9, estimated_breach_probability=0.5)
        TierApiModel(level="balanced", target=99.9, estimated_breach_probability=1.0)

        # Invalid values
        with pytest.raises(ValidationError):
            TierApiModel(level="balanced", target=99.9, estimated_breach_probability=-0.1)
        with pytest.raises(ValidationError):
            TierApiModel(level="balanced", target=99.9, estimated_breach_probability=1.1)

    def test_target_ms_validation(self):
        """target_ms must be non-negative."""
        TierApiModel(level="balanced", target=500.0, target_ms=0)
        TierApiModel(level="balanced", target=500.0, target_ms=500)

        with pytest.raises(ValidationError):
            TierApiModel(level="balanced", target=500.0, target_ms=-1)


# ============================================================================
# Feature Attribution Model Tests
# ============================================================================


class TestFeatureAttributionApiModel:
    """Tests for FeatureAttributionApiModel."""

    def test_minimal_attribution(self):
        """Minimal attribution with required fields."""
        attr = FeatureAttributionApiModel(
            feature="historical_availability_mean", contribution=0.42
        )
        assert attr.feature == "historical_availability_mean"
        assert attr.contribution == 0.42
        assert attr.description == ""

    def test_attribution_with_description(self):
        """Attribution with description."""
        attr = FeatureAttributionApiModel(
            feature="historical_availability_mean",
            contribution=0.42,
            description="Historical performance",
        )
        assert attr.description == "Historical performance"

    def test_contribution_validation(self):
        """Contribution must be between 0.0 and 1.0."""
        FeatureAttributionApiModel(feature="test", contribution=0.0)
        FeatureAttributionApiModel(feature="test", contribution=0.5)
        FeatureAttributionApiModel(feature="test", contribution=1.0)

        with pytest.raises(ValidationError):
            FeatureAttributionApiModel(feature="test", contribution=-0.1)
        with pytest.raises(ValidationError):
            FeatureAttributionApiModel(feature="test", contribution=1.1)


# ============================================================================
# Dependency Impact Model Tests
# ============================================================================


class TestDependencyImpactApiModel:
    """Tests for DependencyImpactApiModel."""

    def test_minimal_dependency_impact(self):
        """Minimal dependency impact with only required field."""
        impact = DependencyImpactApiModel(composite_availability_bound=99.7)
        assert impact.composite_availability_bound == 99.7
        assert impact.bottleneck_service is None
        assert impact.bottleneck_contribution == ""
        assert impact.hard_dependency_count == 0
        assert impact.soft_dependency_count == 0

    def test_full_dependency_impact(self):
        """Dependency impact with all fields."""
        impact = DependencyImpactApiModel(
            composite_availability_bound=99.7,
            bottleneck_service="external-payment-api",
            bottleneck_contribution="Consumes 50% of error budget",
            hard_dependency_count=3,
            soft_dependency_count=1,
        )
        assert impact.bottleneck_service == "external-payment-api"
        assert impact.bottleneck_contribution == "Consumes 50% of error budget"
        assert impact.hard_dependency_count == 3
        assert impact.soft_dependency_count == 1

    def test_composite_bound_validation(self):
        """Composite bound must be between 0.0 and 100.0."""
        DependencyImpactApiModel(composite_availability_bound=0.0)
        DependencyImpactApiModel(composite_availability_bound=50.0)
        DependencyImpactApiModel(composite_availability_bound=100.0)

        with pytest.raises(ValidationError):
            DependencyImpactApiModel(composite_availability_bound=-0.1)
        with pytest.raises(ValidationError):
            DependencyImpactApiModel(composite_availability_bound=100.1)

    def test_dependency_count_validation(self):
        """Dependency counts must be non-negative."""
        DependencyImpactApiModel(
            composite_availability_bound=99.7, hard_dependency_count=0, soft_dependency_count=0
        )

        with pytest.raises(ValidationError):
            DependencyImpactApiModel(
                composite_availability_bound=99.7, hard_dependency_count=-1
            )
        with pytest.raises(ValidationError):
            DependencyImpactApiModel(
                composite_availability_bound=99.7, soft_dependency_count=-1
            )


# ============================================================================
# Explanation Model Tests
# ============================================================================


class TestExplanationApiModel:
    """Tests for ExplanationApiModel."""

    def test_minimal_explanation(self):
        """Minimal explanation with only summary."""
        explanation = ExplanationApiModel(
            summary="Service achieved 99.9% availability."
        )
        assert explanation.summary == "Service achieved 99.9% availability."
        assert explanation.feature_attribution == []
        assert explanation.dependency_impact is None

    def test_explanation_with_attribution(self):
        """Explanation with feature attribution."""
        explanation = ExplanationApiModel(
            summary="Service achieved 99.9% availability.",
            feature_attribution=[
                FeatureAttributionApiModel(feature="historical_mean", contribution=0.42)
            ],
        )
        assert len(explanation.feature_attribution) == 1
        assert explanation.feature_attribution[0].feature == "historical_mean"

    def test_explanation_with_dependency_impact(self):
        """Explanation with dependency impact."""
        explanation = ExplanationApiModel(
            summary="Service achieved 99.9% availability.",
            dependency_impact=DependencyImpactApiModel(composite_availability_bound=99.7),
        )
        assert explanation.dependency_impact.composite_availability_bound == 99.7

    def test_full_explanation(self):
        """Full explanation with all fields."""
        explanation = ExplanationApiModel(
            summary="Service achieved 99.9% availability.",
            feature_attribution=[
                FeatureAttributionApiModel(feature="historical_mean", contribution=0.6),
                FeatureAttributionApiModel(feature="dependency_risk", contribution=0.4),
            ],
            dependency_impact=DependencyImpactApiModel(
                composite_availability_bound=99.7,
                bottleneck_service="external-api",
                hard_dependency_count=2,
            ),
        )
        assert len(explanation.feature_attribution) == 2
        assert explanation.dependency_impact.bottleneck_service == "external-api"


# ============================================================================
# Data Quality Model Tests
# ============================================================================


class TestDataQualityApiModel:
    """Tests for DataQualityApiModel."""

    def test_minimal_data_quality(self):
        """Minimal data quality with only required field."""
        quality = DataQualityApiModel(data_completeness=0.97)
        assert quality.data_completeness == 0.97
        assert quality.telemetry_gaps == []
        assert quality.confidence_note == ""
        assert quality.is_cold_start is False
        assert quality.lookback_days_actual == 30

    def test_full_data_quality(self):
        """Data quality with all fields."""
        quality = DataQualityApiModel(
            data_completeness=0.85,
            telemetry_gaps=[{"start": "2026-01-10", "end": "2026-01-12"}],
            confidence_note="Extended lookback due to data gaps",
            is_cold_start=True,
            lookback_days_actual=90,
        )
        assert quality.data_completeness == 0.85
        assert len(quality.telemetry_gaps) == 1
        assert quality.confidence_note == "Extended lookback due to data gaps"
        assert quality.is_cold_start is True
        assert quality.lookback_days_actual == 90

    def test_completeness_validation(self):
        """Data completeness must be between 0.0 and 1.0."""
        DataQualityApiModel(data_completeness=0.0)
        DataQualityApiModel(data_completeness=0.5)
        DataQualityApiModel(data_completeness=1.0)

        with pytest.raises(ValidationError):
            DataQualityApiModel(data_completeness=-0.1)
        with pytest.raises(ValidationError):
            DataQualityApiModel(data_completeness=1.1)

    def test_lookback_days_validation(self):
        """Lookback days must be between 7 and 365."""
        DataQualityApiModel(data_completeness=0.97, lookback_days_actual=7)
        DataQualityApiModel(data_completeness=0.97, lookback_days_actual=365)

        with pytest.raises(ValidationError):
            DataQualityApiModel(data_completeness=0.97, lookback_days_actual=6)
        with pytest.raises(ValidationError):
            DataQualityApiModel(data_completeness=0.97, lookback_days_actual=366)


# ============================================================================
# Recommendation Model Tests
# ============================================================================


class TestRecommendationApiModel:
    """Tests for RecommendationApiModel."""

    def test_minimal_recommendation(self):
        """Minimal recommendation with required fields."""
        recommendation = RecommendationApiModel(
            sli_type="availability",
            metric="error_rate",
            tiers={
                "balanced": TierApiModel(level="balanced", target=99.9),
            },
            explanation=ExplanationApiModel(summary="Test summary"),
            data_quality=DataQualityApiModel(data_completeness=0.97),
        )
        assert recommendation.sli_type == "availability"
        assert recommendation.metric == "error_rate"
        assert "balanced" in recommendation.tiers

    def test_full_availability_recommendation(self):
        """Full availability recommendation with all tiers."""
        recommendation = RecommendationApiModel(
            sli_type="availability",
            metric="error_rate",
            tiers={
                "conservative": TierApiModel(
                    level="conservative",
                    target=99.5,
                    error_budget_monthly_minutes=219.6,
                    estimated_breach_probability=0.02,
                ),
                "balanced": TierApiModel(
                    level="balanced",
                    target=99.9,
                    error_budget_monthly_minutes=43.8,
                    estimated_breach_probability=0.08,
                ),
                "aggressive": TierApiModel(
                    level="aggressive",
                    target=99.95,
                    error_budget_monthly_minutes=21.9,
                    estimated_breach_probability=0.18,
                ),
            },
            explanation=ExplanationApiModel(
                summary="Test summary",
                feature_attribution=[
                    FeatureAttributionApiModel(feature="historical_mean", contribution=1.0)
                ],
                dependency_impact=DependencyImpactApiModel(composite_availability_bound=99.7),
            ),
            data_quality=DataQualityApiModel(data_completeness=0.97),
        )
        assert len(recommendation.tiers) == 3
        assert recommendation.explanation.dependency_impact is not None

    def test_full_latency_recommendation(self):
        """Full latency recommendation with all tiers."""
        recommendation = RecommendationApiModel(
            sli_type="latency",
            metric="p99_response_time_ms",
            tiers={
                "conservative": TierApiModel(
                    level="conservative",
                    target=1200.0,
                    target_ms=1200,
                    percentile="p99.9",
                    estimated_breach_probability=0.01,
                ),
                "balanced": TierApiModel(
                    level="balanced",
                    target=800.0,
                    target_ms=800,
                    percentile="p99",
                    estimated_breach_probability=0.05,
                ),
                "aggressive": TierApiModel(
                    level="aggressive",
                    target=500.0,
                    target_ms=500,
                    percentile="p95",
                    estimated_breach_probability=0.12,
                ),
            },
            explanation=ExplanationApiModel(
                summary="Latency summary",
                feature_attribution=[
                    FeatureAttributionApiModel(feature="p99_historical", contribution=0.5)
                ],
            ),
            data_quality=DataQualityApiModel(data_completeness=0.97),
        )
        assert recommendation.sli_type == "latency"
        assert len(recommendation.tiers) == 3
        assert recommendation.tiers["balanced"].target_ms == 800


# ============================================================================
# Lookback Window Model Tests
# ============================================================================


class TestLookbackWindowApiModel:
    """Tests for LookbackWindowApiModel."""

    def test_lookback_window(self):
        """Lookback window with ISO 8601 timestamps."""
        window = LookbackWindowApiModel(
            start="2026-01-16T00:00:00Z", end="2026-02-15T00:00:00Z"
        )
        assert window.start == "2026-01-16T00:00:00Z"
        assert window.end == "2026-02-15T00:00:00Z"


# ============================================================================
# Response Model Tests
# ============================================================================


class TestSloRecommendationApiResponse:
    """Tests for SloRecommendationApiResponse."""

    def test_minimal_response(self):
        """Minimal response with empty recommendations."""
        response = SloRecommendationApiResponse(
            service_id="test-service",
            generated_at="2026-02-15T10:30:00Z",
            lookback_window=LookbackWindowApiModel(
                start="2026-01-16T00:00:00Z", end="2026-02-15T00:00:00Z"
            ),
            recommendations=[],
        )
        assert response.service_id == "test-service"
        assert response.recommendations == []

    def test_response_with_single_recommendation(self):
        """Response with a single recommendation."""
        response = SloRecommendationApiResponse(
            service_id="test-service",
            generated_at="2026-02-15T10:30:00Z",
            lookback_window=LookbackWindowApiModel(
                start="2026-01-16T00:00:00Z", end="2026-02-15T00:00:00Z"
            ),
            recommendations=[
                RecommendationApiModel(
                    sli_type="availability",
                    metric="error_rate",
                    tiers={
                        "balanced": TierApiModel(level="balanced", target=99.9),
                    },
                    explanation=ExplanationApiModel(summary="Test"),
                    data_quality=DataQualityApiModel(data_completeness=0.97),
                )
            ],
        )
        assert len(response.recommendations) == 1
        assert response.recommendations[0].sli_type == "availability"

    def test_response_with_multiple_recommendations(self):
        """Response with both availability and latency recommendations."""
        response = SloRecommendationApiResponse(
            service_id="checkout-service",
            generated_at="2026-02-15T10:30:00Z",
            lookback_window=LookbackWindowApiModel(
                start="2026-01-16T00:00:00Z", end="2026-02-15T00:00:00Z"
            ),
            recommendations=[
                RecommendationApiModel(
                    sli_type="availability",
                    metric="error_rate",
                    tiers={
                        "balanced": TierApiModel(level="balanced", target=99.9),
                    },
                    explanation=ExplanationApiModel(summary="Availability summary"),
                    data_quality=DataQualityApiModel(data_completeness=0.97),
                ),
                RecommendationApiModel(
                    sli_type="latency",
                    metric="p99_response_time_ms",
                    tiers={
                        "balanced": TierApiModel(
                            level="balanced", target=800.0, target_ms=800, percentile="p99"
                        ),
                    },
                    explanation=ExplanationApiModel(summary="Latency summary"),
                    data_quality=DataQualityApiModel(data_completeness=0.97),
                ),
            ],
        )
        assert len(response.recommendations) == 2
        assert response.recommendations[0].sli_type == "availability"
        assert response.recommendations[1].sli_type == "latency"

    def test_response_json_serialization(self):
        """Response can be serialized to JSON."""
        response = SloRecommendationApiResponse(
            service_id="test-service",
            generated_at="2026-02-15T10:30:00Z",
            lookback_window=LookbackWindowApiModel(
                start="2026-01-16T00:00:00Z", end="2026-02-15T00:00:00Z"
            ),
            recommendations=[],
        )
        json_str = response.model_dump_json()
        assert "test-service" in json_str
        assert "2026-02-15T10:30:00Z" in json_str
