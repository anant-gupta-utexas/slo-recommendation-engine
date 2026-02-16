"""Unit tests for GetSloRecommendationUseCase."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.application.dtos.slo_recommendation_dto import (
    DataQualityDTO,
    DependencyImpactDTO,
    ExplanationDTO,
    FeatureAttributionDTO,
    GenerateRecommendationRequest,
    GenerateRecommendationResponse,
    GetRecommendationRequest,
    LookbackWindowDTO,
    RecommendationDTO,
    TierDTO,
)
from src.application.use_cases.generate_slo_recommendation import (
    GenerateSloRecommendationUseCase,
)
from src.application.use_cases.get_slo_recommendation import (
    GetSloRecommendationUseCase,
)
from src.domain.entities.service import Criticality, Service
from src.domain.repositories.service_repository import ServiceRepositoryInterface


@pytest.fixture
def mock_service_repo():
    """Mock service repository."""
    return AsyncMock(spec=ServiceRepositoryInterface)


@pytest.fixture
def mock_generate_use_case():
    """Mock generate use case."""
    return AsyncMock(spec=GenerateSloRecommendationUseCase)


@pytest.fixture
def use_case(mock_service_repo, mock_generate_use_case):
    """GetSloRecommendationUseCase instance."""
    return GetSloRecommendationUseCase(
        service_repo=mock_service_repo,
        generate_use_case=mock_generate_use_case,
    )


@pytest.fixture
def test_service() -> Service:
    """Test service entity."""
    return Service(
        id=uuid4(),
        service_id="test-service",
        criticality=Criticality.CRITICAL,
        team="platform",
    )


@pytest.fixture
def mock_recommendation_response() -> GenerateRecommendationResponse:
    """Mock generate recommendation response."""
    now = datetime.now(timezone.utc)
    return GenerateRecommendationResponse(
        service_id="test-service",
        generated_at=now.isoformat(),
        lookback_window=LookbackWindowDTO(
            start=(now - timedelta(days=30)).isoformat(),
            end=now.isoformat(),
        ),
        recommendations=[
            RecommendationDTO(
                sli_type="availability",
                metric="error_rate",
                tiers={
                    "conservative": TierDTO(
                        level="conservative",
                        target=99.9,
                        error_budget_monthly_minutes=43.2,
                        confidence_interval=(99.85, 99.95),
                        estimated_breach_probability=0.05,
                    ),
                    "balanced": TierDTO(
                        level="balanced",
                        target=99.5,
                        error_budget_monthly_minutes=216.0,
                        confidence_interval=(99.4, 99.6),
                        estimated_breach_probability=0.15,
                    ),
                    "aggressive": TierDTO(
                        level="aggressive",
                        target=99.0,
                        error_budget_monthly_minutes=432.0,
                        confidence_interval=(98.9, 99.1),
                        estimated_breach_probability=0.30,
                    ),
                },
                explanation=ExplanationDTO(
                    summary="Conservative capped by composite availability",
                    feature_attribution=[
                        FeatureAttributionDTO(
                            feature="historical_availability",
                            contribution=0.40,
                        )
                    ],
                    dependency_impact=DependencyImpactDTO(
                        composite_availability_bound=0.999,
                        bottleneck_service="db-service",
                        hard_dependency_count=3,
                        soft_dependency_count=1,
                    ),
                ),
                data_quality=DataQualityDTO(
                    data_completeness=0.95,
                    is_cold_start=False,
                    lookback_days_actual=30,
                ),
            )
        ],
    )


class TestGetSloRecommendationExecute:
    """Tests for GetSloRecommendationUseCase.execute()."""

    @pytest.mark.asyncio
    async def test_returns_none_when_service_not_found(
        self, use_case, mock_service_repo
    ):
        """Should return None if service does not exist."""
        # Arrange
        mock_service_repo.get_by_service_id.return_value = None
        request = GetRecommendationRequest(service_id="nonexistent-service")

        # Act
        result = await use_case.execute(request)

        # Assert
        assert result is None
        mock_service_repo.get_by_service_id.assert_called_once_with(
            "nonexistent-service"
        )

    @pytest.mark.asyncio
    async def test_force_regenerate_delegates_to_generate_use_case(
        self,
        use_case,
        mock_service_repo,
        mock_generate_use_case,
        test_service,
        mock_recommendation_response,
    ):
        """Should delegate to GenerateSloRecommendationUseCase when force_regenerate=True."""
        # Arrange
        mock_service_repo.get_by_service_id.return_value = test_service
        mock_generate_use_case.execute.return_value = mock_recommendation_response

        request = GetRecommendationRequest(
            service_id="test-service",
            sli_type="availability",
            force_regenerate=True,
        )

        # Act
        result = await use_case.execute(request)

        # Assert
        assert result is not None
        assert result.service_id == "test-service"
        assert len(result.recommendations) == 1
        assert result.recommendations[0].sli_type == "availability"
        mock_generate_use_case.execute.assert_called_once()

        call_args = mock_generate_use_case.execute.call_args[0][0]
        assert call_args.service_id == "test-service"
        assert call_args.sli_type == "availability"
        assert call_args.force_regenerate is True

    @pytest.mark.asyncio
    async def test_force_regenerate_with_custom_lookback_days(
        self,
        use_case,
        mock_service_repo,
        mock_generate_use_case,
        test_service,
        mock_recommendation_response,
    ):
        """Should pass custom lookback_days to generate use case."""
        # Arrange
        mock_service_repo.get_by_service_id.return_value = test_service
        mock_generate_use_case.execute.return_value = mock_recommendation_response

        request = GetRecommendationRequest(
            service_id="test-service",
            lookback_days=60,
            force_regenerate=True,
        )

        # Act
        await use_case.execute(request)

        # Assert
        call_args = mock_generate_use_case.execute.call_args[0][0]
        assert call_args.lookback_days == 60

    @pytest.mark.asyncio
    async def test_force_regenerate_returns_none_if_generation_fails(
        self,
        use_case,
        mock_service_repo,
        mock_generate_use_case,
        test_service,
    ):
        """Should return None if generate use case returns None."""
        # Arrange
        mock_service_repo.get_by_service_id.return_value = test_service
        mock_generate_use_case.execute.return_value = None

        request = GetRecommendationRequest(
            service_id="test-service",
            force_regenerate=True,
        )

        # Act
        result = await use_case.execute(request)

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_falls_back_to_generation_when_no_force_regenerate(
        self,
        use_case,
        mock_service_repo,
        mock_generate_use_case,
        test_service,
        mock_recommendation_response,
    ):
        """Should fall back to generation when repository not implemented (Phase 2)."""
        # Arrange
        mock_service_repo.get_by_service_id.return_value = test_service
        mock_generate_use_case.execute.return_value = mock_recommendation_response

        request = GetRecommendationRequest(service_id="test-service")

        # Act
        result = await use_case.execute(request)

        # Assert
        assert result is not None
        assert result.service_id == "test-service"
        mock_generate_use_case.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_sli_type_filter_to_generate_use_case(
        self,
        use_case,
        mock_service_repo,
        mock_generate_use_case,
        test_service,
        mock_recommendation_response,
    ):
        """Should pass sli_type filter to generate use case."""
        # Arrange
        mock_service_repo.get_by_service_id.return_value = test_service
        mock_generate_use_case.execute.return_value = mock_recommendation_response

        request = GetRecommendationRequest(
            service_id="test-service",
            sli_type="latency",
        )

        # Act
        await use_case.execute(request)

        # Assert
        call_args = mock_generate_use_case.execute.call_args[0][0]
        assert call_args.sli_type == "latency"

    @pytest.mark.asyncio
    async def test_converts_generate_response_to_get_response(
        self,
        use_case,
        mock_service_repo,
        mock_generate_use_case,
        test_service,
        mock_recommendation_response,
    ):
        """Should correctly convert GenerateRecommendationResponse to GetRecommendationResponse."""
        # Arrange
        mock_service_repo.get_by_service_id.return_value = test_service
        mock_generate_use_case.execute.return_value = mock_recommendation_response

        request = GetRecommendationRequest(
            service_id="test-service",
            force_regenerate=True,
        )

        # Act
        result = await use_case.execute(request)

        # Assert
        assert result is not None
        assert result.service_id == mock_recommendation_response.service_id
        assert result.generated_at == mock_recommendation_response.generated_at
        assert (
            result.lookback_window.start
            == mock_recommendation_response.lookback_window.start
        )
        assert (
            result.lookback_window.end
            == mock_recommendation_response.lookback_window.end
        )
        assert result.recommendations == mock_recommendation_response.recommendations
