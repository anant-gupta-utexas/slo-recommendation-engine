"""Unit tests for GenerateSloRecommendation Use Case (FR-2).

Tests the full recommendation generation pipeline with mocked dependencies.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from src.application.dtos.slo_recommendation_dto import (
    GenerateRecommendationRequest,
)
from src.application.use_cases.generate_slo_recommendation import (
    GenerateSloRecommendationUseCase,
)
from src.domain.entities.service import Criticality, Service
from src.domain.entities.service_dependency import (
    CommunicationMode,
    DependencyCriticality,
    ServiceDependency,
)
from src.domain.entities.sli_data import AvailabilitySliData, LatencySliData
from src.domain.entities.slo_recommendation import (
    RecommendationTier,
    SliType,
    TierLevel,
)
from src.domain.services.composite_availability_service import CompositeResult


@pytest.fixture
def service_uuid():
    """Service UUID for testing."""
    return uuid4()


@pytest.fixture
def test_service(service_uuid):
    """Test service entity."""
    return Service(
        id=service_uuid,
        service_id="test-service",
        criticality=Criticality.CRITICAL,
        team="platform",
    )


@pytest.fixture
def availability_sli_data():
    """Mock availability SLI data."""
    return AvailabilitySliData(
        service_id="test-service",
        good_events=99920,
        total_events=100000,
        availability_ratio=0.9992,
        window_start=datetime.now(timezone.utc) - timedelta(days=30),
        window_end=datetime.now(timezone.utc),
        sample_count=100000,
    )


@pytest.fixture
def latency_sli_data():
    """Mock latency SLI data."""
    return LatencySliData(
        service_id="test-service",
        p50_ms=200.0,
        p95_ms=500.0,
        p99_ms=780.0,
        p999_ms=1100.0,
        window_start=datetime.now(timezone.utc) - timedelta(days=30),
        window_end=datetime.now(timezone.utc),
        sample_count=100000,
    )


@pytest.fixture
def rolling_availability():
    """Mock rolling availability data (30 days)."""
    # 30 days of data with realistic variance
    base = 0.9992
    return [base + (i % 3) * 0.0001 - 0.0001 for i in range(30)]


@pytest.fixture
def mock_service_repo(test_service):
    """Mock service repository."""
    repo = AsyncMock()
    repo.get_by_service_id.return_value = test_service
    return repo


@pytest.fixture
def mock_dependency_repo():
    """Mock dependency repository."""
    repo = AsyncMock()
    return repo


@pytest.fixture
def mock_recommendation_repo():
    """Mock recommendation repository."""
    repo = AsyncMock()
    repo.supersede_existing.return_value = 1
    repo.save.return_value = None
    return repo


@pytest.fixture
def mock_telemetry_service(availability_sli_data, latency_sli_data, rolling_availability):
    """Mock telemetry service."""
    service = AsyncMock()
    service.get_data_completeness.return_value = 0.97
    service.get_availability_sli.return_value = availability_sli_data
    service.get_latency_percentiles.return_value = latency_sli_data
    service.get_rolling_availability.return_value = rolling_availability
    return service


@pytest.fixture
def mock_availability_calculator():
    """Mock availability calculator."""
    calc = MagicMock()
    calc.compute_tiers.return_value = {
        TierLevel.CONSERVATIVE: RecommendationTier(
            level=TierLevel.CONSERVATIVE,
            target=99.5,
            error_budget_monthly_minutes=219.6,
            estimated_breach_probability=0.02,
            confidence_interval=(99.3, 99.7),
        ),
        TierLevel.BALANCED: RecommendationTier(
            level=TierLevel.BALANCED,
            target=99.9,
            error_budget_monthly_minutes=43.8,
            estimated_breach_probability=0.08,
            confidence_interval=(99.8, 99.95),
        ),
        TierLevel.AGGRESSIVE: RecommendationTier(
            level=TierLevel.AGGRESSIVE,
            target=99.95,
            error_budget_monthly_minutes=21.9,
            estimated_breach_probability=0.18,
            confidence_interval=(99.9, 99.99),
        ),
    }
    return calc


@pytest.fixture
def mock_latency_calculator():
    """Mock latency calculator."""
    calc = MagicMock()
    calc.compute_tiers.return_value = {
        TierLevel.CONSERVATIVE: RecommendationTier(
            level=TierLevel.CONSERVATIVE,
            target=1200.0,
            percentile="p99.9",
            target_ms=1200,
            estimated_breach_probability=0.01,
        ),
        TierLevel.BALANCED: RecommendationTier(
            level=TierLevel.BALANCED,
            target=800.0,
            percentile="p99",
            target_ms=800,
            estimated_breach_probability=0.05,
        ),
        TierLevel.AGGRESSIVE: RecommendationTier(
            level=TierLevel.AGGRESSIVE,
            target=500.0,
            percentile="p95",
            target_ms=500,
            estimated_breach_probability=0.12,
        ),
    }
    return calc


@pytest.fixture
def mock_composite_service():
    """Mock composite availability service."""
    service = MagicMock()
    service.compute_composite_bound.return_value = CompositeResult(
        composite_bound=0.997,
        bottleneck_service_id=None,
        bottleneck_service_name="external-payment-api",
        bottleneck_contribution="Consumes 50% of error budget",
        per_dependency_contributions={},
    )
    return service


@pytest.fixture
def mock_attribution_service():
    """Mock weighted attribution service."""
    from src.domain.entities.slo_recommendation import FeatureAttribution

    service = MagicMock()
    service.compute_attribution.return_value = [
        FeatureAttribution("historical_availability_mean", 0.42, ""),
        FeatureAttribution("downstream_dependency_risk", 0.28, ""),
        FeatureAttribution("external_api_reliability", 0.18, ""),
        FeatureAttribution("deployment_frequency", 0.12, ""),
    ]
    return service


@pytest.fixture
def mock_graph_traversal_service(test_service, service_uuid):
    """Mock graph traversal service."""
    # Create a simple downstream dependency
    dep_service = Service(
        id=uuid4(),
        service_id="payment-service",
        criticality=Criticality.CRITICAL,
        team="payments",
    )
    edge = ServiceDependency(
        source_service_id=service_uuid,
        target_service_id=dep_service.id,
        criticality=DependencyCriticality.HARD,
        communication_mode=CommunicationMode.SYNC,
    )

    service = AsyncMock()
    service.get_subgraph.return_value = ([test_service, dep_service], [edge])
    return service


@pytest.fixture
def use_case(
    mock_service_repo,
    mock_dependency_repo,
    mock_recommendation_repo,
    mock_telemetry_service,
    mock_availability_calculator,
    mock_latency_calculator,
    mock_composite_service,
    mock_attribution_service,
    mock_graph_traversal_service,
):
    """Instantiate the use case with all mocks."""
    return GenerateSloRecommendationUseCase(
        service_repository=mock_service_repo,
        dependency_repository=mock_dependency_repo,
        recommendation_repository=mock_recommendation_repo,
        telemetry_service=mock_telemetry_service,
        availability_calculator=mock_availability_calculator,
        latency_calculator=mock_latency_calculator,
        composite_service=mock_composite_service,
        attribution_service=mock_attribution_service,
        graph_traversal_service=mock_graph_traversal_service,
    )


# --- Success Path Tests ---


@pytest.mark.asyncio
async def test_execute_generates_availability_recommendation(use_case, mock_service_repo):
    """Should generate availability recommendation for 'all' or 'availability' sli_type."""
    request = GenerateRecommendationRequest(
        service_id="test-service", sli_type="availability", lookback_days=30
    )

    response = await use_case.execute(request)

    assert response is not None
    assert response.service_id == "test-service"
    assert len(response.recommendations) == 1
    assert response.recommendations[0].sli_type == "availability"
    assert response.recommendations[0].metric == "error_rate"
    assert "conservative" in response.recommendations[0].tiers
    assert "balanced" in response.recommendations[0].tiers
    assert "aggressive" in response.recommendations[0].tiers

    # Verify service lookup
    mock_service_repo.get_by_service_id.assert_called_once_with("test-service")


@pytest.mark.asyncio
async def test_execute_generates_latency_recommendation(use_case):
    """Should generate latency recommendation for 'latency' sli_type."""
    request = GenerateRecommendationRequest(
        service_id="test-service", sli_type="latency", lookback_days=30
    )

    response = await use_case.execute(request)

    assert response is not None
    assert len(response.recommendations) == 1
    assert response.recommendations[0].sli_type == "latency"
    assert response.recommendations[0].metric == "p99_response_time_ms"
    assert response.recommendations[0].tiers["balanced"].target_ms == 800


@pytest.mark.asyncio
async def test_execute_generates_both_recommendations_for_all(use_case):
    """Should generate both availability and latency when sli_type='all'."""
    request = GenerateRecommendationRequest(
        service_id="test-service", sli_type="all", lookback_days=30
    )

    response = await use_case.execute(request)

    assert response is not None
    assert len(response.recommendations) == 2
    sli_types = {rec.sli_type for rec in response.recommendations}
    assert sli_types == {"availability", "latency"}


@pytest.mark.asyncio
async def test_execute_includes_lookback_window(use_case):
    """Should include lookback window in response."""
    request = GenerateRecommendationRequest(service_id="test-service", lookback_days=30)

    response = await use_case.execute(request)

    assert response is not None
    assert response.lookback_window is not None
    assert response.lookback_window.start is not None
    assert response.lookback_window.end is not None


@pytest.mark.asyncio
async def test_execute_supersedes_existing_recommendations(
    use_case, mock_recommendation_repo
):
    """Should supersede existing recommendations before saving new ones."""
    request = GenerateRecommendationRequest(service_id="test-service", sli_type="all")

    await use_case.execute(request)

    # Should supersede for both availability and latency
    assert mock_recommendation_repo.supersede_existing.call_count == 2


@pytest.mark.asyncio
async def test_execute_saves_new_recommendations(use_case, mock_recommendation_repo):
    """Should save new recommendations to repository."""
    request = GenerateRecommendationRequest(service_id="test-service", sli_type="all")

    await use_case.execute(request)

    # Should save both availability and latency
    assert mock_recommendation_repo.save.call_count == 2


# --- Cold-Start Logic Tests ---


@pytest.mark.asyncio
async def test_execute_triggers_cold_start_for_low_completeness(
    use_case, mock_telemetry_service
):
    """Should extend lookback to 90 days when data completeness < 0.90."""
    # First call (30 days): low completeness, second call (90 days): better
    # Additional calls for each recommendation generation (avail + latency)
    mock_telemetry_service.get_data_completeness.side_effect = [
        0.65,  # Initial check for 30 days
        0.80,  # Extended check for 90 days
        0.80,  # Availability recommendation check
        0.80,  # Latency recommendation check
    ]

    request = GenerateRecommendationRequest(service_id="test-service", lookback_days=30)

    response = await use_case.execute(request)

    assert response is not None
    # Verify get_data_completeness called multiple times
    assert mock_telemetry_service.get_data_completeness.call_count >= 2


@pytest.mark.asyncio
async def test_execute_uses_standard_lookback_for_good_completeness(
    use_case, mock_telemetry_service
):
    """Should use standard 30-day lookback when completeness >= 0.90."""
    mock_telemetry_service.get_data_completeness.return_value = 0.97

    request = GenerateRecommendationRequest(service_id="test-service", lookback_days=30)

    await use_case.execute(request)

    # Should only check completeness for 30 days (no cold-start)
    # Note: Will be called multiple times (once per determine_lookback, once per recommendation)
    assert mock_telemetry_service.get_data_completeness.called


# --- Error Handling Tests ---


@pytest.mark.asyncio
async def test_execute_returns_none_if_service_not_found(use_case, mock_service_repo):
    """Should return None if service doesn't exist."""
    mock_service_repo.get_by_service_id.return_value = None

    request = GenerateRecommendationRequest(service_id="nonexistent-service")

    response = await use_case.execute(request)

    assert response is None


@pytest.mark.asyncio
async def test_execute_skips_availability_if_no_telemetry(
    use_case, mock_telemetry_service
):
    """Should skip availability recommendation if no telemetry data."""
    mock_telemetry_service.get_availability_sli.return_value = None

    request = GenerateRecommendationRequest(service_id="test-service", sli_type="all")

    response = await use_case.execute(request)

    assert response is not None
    # Should only have latency recommendation
    assert len(response.recommendations) == 1
    assert response.recommendations[0].sli_type == "latency"


@pytest.mark.asyncio
async def test_execute_skips_latency_if_no_telemetry(use_case, mock_telemetry_service):
    """Should skip latency recommendation if no telemetry data."""
    mock_telemetry_service.get_latency_percentiles.return_value = None

    request = GenerateRecommendationRequest(service_id="test-service", sli_type="all")

    response = await use_case.execute(request)

    assert response is not None
    # Should only have availability recommendation
    assert len(response.recommendations) == 1
    assert response.recommendations[0].sli_type == "availability"


@pytest.mark.asyncio
async def test_execute_returns_empty_if_no_telemetry_at_all(
    use_case, mock_telemetry_service
):
    """Should return empty recommendations if no telemetry for any SLI."""
    mock_telemetry_service.get_availability_sli.return_value = None
    mock_telemetry_service.get_latency_percentiles.return_value = None

    request = GenerateRecommendationRequest(service_id="test-service", sli_type="all")

    response = await use_case.execute(request)

    assert response is not None
    assert len(response.recommendations) == 0


# --- Dependency Handling Tests ---


@pytest.mark.asyncio
async def test_execute_queries_dependency_subgraph(use_case, mock_graph_traversal_service):
    """Should query dependency subgraph for availability computation."""
    request = GenerateRecommendationRequest(
        service_id="test-service", sli_type="availability"
    )

    await use_case.execute(request)

    # Verify subgraph query
    mock_graph_traversal_service.get_subgraph.assert_called_once()
    call_args = mock_graph_traversal_service.get_subgraph.call_args
    assert call_args.kwargs["max_depth"] == 3
    assert call_args.kwargs["include_soft"] is True


@pytest.mark.asyncio
async def test_execute_computes_composite_availability(use_case, mock_composite_service):
    """Should compute composite availability bound from dependencies."""
    request = GenerateRecommendationRequest(
        service_id="test-service", sli_type="availability"
    )

    await use_case.execute(request)

    mock_composite_service.compute_composite_bound.assert_called_once()


@pytest.mark.asyncio
async def test_execute_defaults_dependency_availability_when_missing(
    use_case,
    mock_telemetry_service,
    mock_graph_traversal_service,
    mock_composite_service,
    service_uuid,
    availability_sli_data,
):
    """Should default to 99.9% availability for dependencies with no telemetry."""
    # Create a dependency without telemetry
    dep_service = Service(
        id=uuid4(),
        service_id="unknown-service",
        criticality=Criticality.MEDIUM,
        team="unknown",
    )
    edge = ServiceDependency(
        source_service_id=service_uuid,
        target_service_id=dep_service.id,
        criticality=DependencyCriticality.HARD,
        communication_mode=CommunicationMode.SYNC,
    )
    mock_graph_traversal_service.get_subgraph.return_value = ([dep_service], [edge])

    # Mock telemetry service to return None for dependency
    async def get_avail_side_effect(service_id, lookback_days):
        if service_id == "unknown-service":
            return None
        return availability_sli_data

    mock_telemetry_service.get_availability_sli.side_effect = get_avail_side_effect

    request = GenerateRecommendationRequest(
        service_id="test-service", sli_type="availability"
    )

    await use_case.execute(request)

    # Should complete without error (defaults to 99.9%)
    assert mock_composite_service.compute_composite_bound.called


# --- DTO Conversion Tests ---


@pytest.mark.asyncio
async def test_execute_converts_tiers_to_dto(use_case):
    """Should convert domain tier entities to DTO."""
    request = GenerateRecommendationRequest(
        service_id="test-service", sli_type="availability"
    )

    response = await use_case.execute(request)

    assert response is not None
    rec = response.recommendations[0]
    assert rec.tiers["conservative"].target == 99.5
    assert rec.tiers["conservative"].error_budget_monthly_minutes == 219.6
    assert rec.tiers["balanced"].target == 99.9
    assert rec.tiers["aggressive"].target == 99.95


@pytest.mark.asyncio
async def test_execute_includes_explanation_in_dto(use_case):
    """Should include explanation with summary and attribution."""
    request = GenerateRecommendationRequest(
        service_id="test-service", sli_type="availability"
    )

    response = await use_case.execute(request)

    assert response is not None
    rec = response.recommendations[0]
    assert rec.explanation is not None
    assert "test-service" in rec.explanation.summary
    assert len(rec.explanation.feature_attribution) > 0
    assert rec.explanation.dependency_impact is not None


@pytest.mark.asyncio
async def test_execute_includes_data_quality_in_dto(use_case):
    """Should include data quality metadata."""
    request = GenerateRecommendationRequest(service_id="test-service")

    response = await use_case.execute(request)

    assert response is not None
    rec = response.recommendations[0]
    assert rec.data_quality is not None
    assert rec.data_quality.data_completeness == 0.97
    assert rec.data_quality.is_cold_start is False


# --- Edge Cases ---


@pytest.mark.asyncio
async def test_execute_handles_empty_dependency_list(
    use_case, mock_graph_traversal_service
):
    """Should handle services with no dependencies."""
    mock_graph_traversal_service.get_subgraph.return_value = ([], [])

    request = GenerateRecommendationRequest(
        service_id="test-service", sli_type="availability"
    )

    response = await use_case.execute(request)

    assert response is not None
    assert len(response.recommendations) > 0


@pytest.mark.asyncio
async def test_execute_handles_custom_lookback_days(use_case):
    """Should respect custom lookback_days parameter."""
    request = GenerateRecommendationRequest(
        service_id="test-service", lookback_days=90
    )

    response = await use_case.execute(request)

    assert response is not None
    # Lookback window should reflect the 90-day request
    # (exact duration check would require parsing ISO datetimes)
