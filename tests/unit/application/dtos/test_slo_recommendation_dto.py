"""Unit tests for SLO Recommendation DTOs (FR-2).

Tests all application layer data transfer objects.
"""

import pytest

from src.application.dtos.slo_recommendation_dto import (
    BatchComputeResult,
    DataQualityDTO,
    DependencyImpactDTO,
    ExplanationDTO,
    FeatureAttributionDTO,
    GenerateRecommendationRequest,
    GenerateRecommendationResponse,
    GetRecommendationRequest,
    GetRecommendationResponse,
    LookbackWindowDTO,
    RecommendationDTO,
    TierDTO,
)


# --- GenerateRecommendationRequest Tests ---


def test_generate_recommendation_request_defaults():
    """Should use default values for optional fields."""
    req = GenerateRecommendationRequest(service_id="test-service")
    assert req.service_id == "test-service"
    assert req.sli_type == "all"
    assert req.lookback_days == 30
    assert req.force_regenerate is False


def test_generate_recommendation_request_custom_values():
    """Should accept custom values for all fields."""
    req = GenerateRecommendationRequest(
        service_id="checkout-service",
        sli_type="availability",
        lookback_days=90,
        force_regenerate=True,
    )
    assert req.service_id == "checkout-service"
    assert req.sli_type == "availability"
    assert req.lookback_days == 90
    assert req.force_regenerate is True


# --- GetRecommendationRequest Tests ---


def test_get_recommendation_request_defaults():
    """Should use default values for optional fields."""
    req = GetRecommendationRequest(service_id="test-service")
    assert req.service_id == "test-service"
    assert req.sli_type == "all"
    assert req.lookback_days == 30
    assert req.force_regenerate is False


def test_get_recommendation_request_custom_values():
    """Should accept custom values for all fields."""
    req = GetRecommendationRequest(
        service_id="payment-service",
        sli_type="latency",
        lookback_days=60,
        force_regenerate=True,
    )
    assert req.service_id == "payment-service"
    assert req.sli_type == "latency"
    assert req.lookback_days == 60
    assert req.force_regenerate is True


# --- TierDTO Tests ---


def test_tier_dto_availability():
    """Should create availability tier with error budget."""
    tier = TierDTO(
        level="balanced",
        target=99.9,
        error_budget_monthly_minutes=43.8,
        estimated_breach_probability=0.08,
        confidence_interval=(99.8, 99.95),
    )
    assert tier.level == "balanced"
    assert tier.target == 99.9
    assert tier.error_budget_monthly_minutes == 43.8
    assert tier.estimated_breach_probability == 0.08
    assert tier.confidence_interval == (99.8, 99.95)
    assert tier.percentile is None
    assert tier.target_ms is None


def test_tier_dto_latency():
    """Should create latency tier with percentile and target_ms."""
    tier = TierDTO(
        level="conservative",
        target=1200.0,
        percentile="p99.9",
        target_ms=1200,
        estimated_breach_probability=0.01,
    )
    assert tier.level == "conservative"
    assert tier.target == 1200.0
    assert tier.percentile == "p99.9"
    assert tier.target_ms == 1200
    assert tier.estimated_breach_probability == 0.01
    assert tier.error_budget_monthly_minutes is None
    assert tier.confidence_interval is None


def test_tier_dto_minimal():
    """Should create tier with only required fields."""
    tier = TierDTO(level="aggressive", target=99.95)
    assert tier.level == "aggressive"
    assert tier.target == 99.95
    assert tier.estimated_breach_probability == 0.0
    assert tier.error_budget_monthly_minutes is None
    assert tier.confidence_interval is None
    assert tier.percentile is None
    assert tier.target_ms is None


# --- FeatureAttributionDTO Tests ---


def test_feature_attribution_dto():
    """Should create feature attribution with all fields."""
    attr = FeatureAttributionDTO(
        feature="historical_availability_mean",
        contribution=0.42,
        description="Primary driver of recommendation",
    )
    assert attr.feature == "historical_availability_mean"
    assert attr.contribution == 0.42
    assert attr.description == "Primary driver of recommendation"


def test_feature_attribution_dto_no_description():
    """Should default to empty description."""
    attr = FeatureAttributionDTO(feature="deployment_frequency", contribution=0.15)
    assert attr.feature == "deployment_frequency"
    assert attr.contribution == 0.15
    assert attr.description == ""


# --- DependencyImpactDTO Tests ---


def test_dependency_impact_dto_full():
    """Should create dependency impact with all fields."""
    impact = DependencyImpactDTO(
        composite_availability_bound=99.70,
        bottleneck_service="external-payment-api",
        bottleneck_contribution="Consumes 50% of error budget at 99.9% target",
        hard_dependency_count=3,
        soft_dependency_count=1,
    )
    assert impact.composite_availability_bound == 99.70
    assert impact.bottleneck_service == "external-payment-api"
    assert impact.bottleneck_contribution == "Consumes 50% of error budget at 99.9% target"
    assert impact.hard_dependency_count == 3
    assert impact.soft_dependency_count == 1


def test_dependency_impact_dto_minimal():
    """Should create dependency impact with defaults."""
    impact = DependencyImpactDTO(composite_availability_bound=99.9)
    assert impact.composite_availability_bound == 99.9
    assert impact.bottleneck_service is None
    assert impact.bottleneck_contribution == ""
    assert impact.hard_dependency_count == 0
    assert impact.soft_dependency_count == 0


# --- ExplanationDTO Tests ---


def test_explanation_dto_full():
    """Should create full explanation with all fields."""
    attribution = [
        FeatureAttributionDTO("historical_availability_mean", 0.42),
        FeatureAttributionDTO("downstream_dependency_risk", 0.28),
    ]
    impact = DependencyImpactDTO(
        composite_availability_bound=99.70,
        bottleneck_service="external-payment-api",
        hard_dependency_count=3,
    )
    explanation = ExplanationDTO(
        summary="checkout-service achieved 99.92% availability over 30 days.",
        feature_attribution=attribution,
        dependency_impact=impact,
    )
    assert explanation.summary == "checkout-service achieved 99.92% availability over 30 days."
    assert len(explanation.feature_attribution) == 2
    assert explanation.feature_attribution[0].feature == "historical_availability_mean"
    assert explanation.dependency_impact == impact


def test_explanation_dto_minimal():
    """Should create explanation with defaults."""
    explanation = ExplanationDTO(summary="Test summary")
    assert explanation.summary == "Test summary"
    assert explanation.feature_attribution == []
    assert explanation.dependency_impact is None


# --- DataQualityDTO Tests ---


def test_data_quality_dto_full():
    """Should create data quality with all fields."""
    quality = DataQualityDTO(
        data_completeness=0.97,
        telemetry_gaps=[{"start": "2026-01-01", "end": "2026-01-02"}],
        confidence_note="Based on 30 days of continuous data",
        is_cold_start=False,
        lookback_days_actual=30,
    )
    assert quality.data_completeness == 0.97
    assert len(quality.telemetry_gaps) == 1
    assert quality.telemetry_gaps[0]["start"] == "2026-01-01"
    assert quality.confidence_note == "Based on 30 days of continuous data"
    assert quality.is_cold_start is False
    assert quality.lookback_days_actual == 30


def test_data_quality_dto_minimal():
    """Should create data quality with defaults."""
    quality = DataQualityDTO(data_completeness=1.0)
    assert quality.data_completeness == 1.0
    assert quality.telemetry_gaps == []
    assert quality.confidence_note == ""
    assert quality.is_cold_start is False
    assert quality.lookback_days_actual == 30


def test_data_quality_dto_cold_start():
    """Should flag cold-start scenario."""
    quality = DataQualityDTO(
        data_completeness=0.65,
        is_cold_start=True,
        lookback_days_actual=90,
        confidence_note="Extended lookback to 90 days due to sparse data",
    )
    assert quality.is_cold_start is True
    assert quality.lookback_days_actual == 90
    assert "Extended lookback" in quality.confidence_note


# --- RecommendationDTO Tests ---


def test_recommendation_dto_availability():
    """Should create availability recommendation."""
    tiers = {
        "conservative": TierDTO("conservative", 99.5, error_budget_monthly_minutes=219.6),
        "balanced": TierDTO("balanced", 99.9, error_budget_monthly_minutes=43.8),
        "aggressive": TierDTO("aggressive", 99.95, error_budget_monthly_minutes=21.9),
    }
    explanation = ExplanationDTO(summary="Test summary")
    quality = DataQualityDTO(data_completeness=0.97)

    rec = RecommendationDTO(
        sli_type="availability",
        metric="error_rate",
        tiers=tiers,
        explanation=explanation,
        data_quality=quality,
    )
    assert rec.sli_type == "availability"
    assert rec.metric == "error_rate"
    assert len(rec.tiers) == 3
    assert "conservative" in rec.tiers
    assert rec.explanation == explanation
    assert rec.data_quality == quality


def test_recommendation_dto_latency():
    """Should create latency recommendation."""
    tiers = {
        "conservative": TierDTO("conservative", 1200.0, percentile="p99.9", target_ms=1200),
        "balanced": TierDTO("balanced", 800.0, percentile="p99", target_ms=800),
        "aggressive": TierDTO("aggressive", 500.0, percentile="p95", target_ms=500),
    }
    explanation = ExplanationDTO(summary="Latency summary")
    quality = DataQualityDTO(data_completeness=1.0)

    rec = RecommendationDTO(
        sli_type="latency",
        metric="p99_response_time_ms",
        tiers=tiers,
        explanation=explanation,
        data_quality=quality,
    )
    assert rec.sli_type == "latency"
    assert rec.metric == "p99_response_time_ms"
    assert len(rec.tiers) == 3
    assert "balanced" in rec.tiers
    assert rec.tiers["balanced"].target_ms == 800


# --- LookbackWindowDTO Tests ---


def test_lookback_window_dto():
    """Should create lookback window."""
    window = LookbackWindowDTO(start="2026-01-16T00:00:00Z", end="2026-02-15T00:00:00Z")
    assert window.start == "2026-01-16T00:00:00Z"
    assert window.end == "2026-02-15T00:00:00Z"


# --- GetRecommendationResponse Tests ---


def test_get_recommendation_response_empty():
    """Should create response with empty recommendations."""
    window = LookbackWindowDTO(start="2026-01-16T00:00:00Z", end="2026-02-15T00:00:00Z")
    response = GetRecommendationResponse(
        service_id="test-service",
        generated_at="2026-02-15T10:30:00Z",
        lookback_window=window,
    )
    assert response.service_id == "test-service"
    assert response.generated_at == "2026-02-15T10:30:00Z"
    assert response.lookback_window == window
    assert response.recommendations == []


def test_get_recommendation_response_with_recommendations():
    """Should create response with recommendations."""
    window = LookbackWindowDTO(start="2026-01-16T00:00:00Z", end="2026-02-15T00:00:00Z")
    tiers = {"balanced": TierDTO("balanced", 99.9)}
    explanation = ExplanationDTO(summary="Test")
    quality = DataQualityDTO(data_completeness=1.0)
    rec = RecommendationDTO("availability", "error_rate", tiers, explanation, quality)

    response = GetRecommendationResponse(
        service_id="checkout-service",
        generated_at="2026-02-15T10:30:00Z",
        lookback_window=window,
        recommendations=[rec],
    )
    assert response.service_id == "checkout-service"
    assert len(response.recommendations) == 1
    assert response.recommendations[0].sli_type == "availability"


# --- GenerateRecommendationResponse Tests ---


def test_generate_recommendation_response():
    """Should create generation response."""
    window = LookbackWindowDTO(start="2026-01-16T00:00:00Z", end="2026-02-15T00:00:00Z")
    response = GenerateRecommendationResponse(
        service_id="payment-service",
        generated_at="2026-02-15T11:00:00Z",
        lookback_window=window,
    )
    assert response.service_id == "payment-service"
    assert response.generated_at == "2026-02-15T11:00:00Z"
    assert response.lookback_window == window
    assert response.recommendations == []


# --- BatchComputeResult Tests ---


def test_batch_compute_result_success():
    """Should create successful batch result."""
    result = BatchComputeResult(
        total_services=100,
        successful=95,
        failed=3,
        skipped=2,
        duration_seconds=1245.6,
    )
    assert result.total_services == 100
    assert result.successful == 95
    assert result.failed == 3
    assert result.skipped == 2
    assert result.duration_seconds == 1245.6
    assert result.failures == []


def test_batch_compute_result_with_failures():
    """Should create batch result with failure details."""
    failures = [
        {"service_id": "broken-service-1", "error": "No telemetry data"},
        {"service_id": "broken-service-2", "error": "Timeout"},
    ]
    result = BatchComputeResult(
        total_services=50,
        successful=48,
        failed=2,
        skipped=0,
        duration_seconds=600.0,
        failures=failures,
    )
    assert result.total_services == 50
    assert result.successful == 48
    assert result.failed == 2
    assert len(result.failures) == 2
    assert result.failures[0]["service_id"] == "broken-service-1"
    assert result.failures[1]["error"] == "Timeout"


def test_batch_compute_result_all_skipped():
    """Should handle all services skipped."""
    result = BatchComputeResult(
        total_services=10,
        successful=0,
        failed=0,
        skipped=10,
        duration_seconds=5.0,
    )
    assert result.total_services == 10
    assert result.successful == 0
    assert result.skipped == 10
    assert result.failures == []
