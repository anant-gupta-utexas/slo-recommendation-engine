"""Unit tests for BatchComputeRecommendationsUseCase."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.application.dtos.slo_recommendation_dto import (
    DataQualityDTO,
    GenerateRecommendationResponse,
    LookbackWindowDTO,
    RecommendationDTO,
    TierDTO,
    ExplanationDTO,
    FeatureAttributionDTO,
)
from src.application.use_cases.batch_compute_recommendations import (
    BatchComputeRecommendationsUseCase,
)
from src.application.use_cases.generate_slo_recommendation import (
    GenerateSloRecommendationUseCase,
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
    """BatchComputeRecommendationsUseCase instance."""
    return BatchComputeRecommendationsUseCase(
        service_repo=mock_service_repo,
        generate_use_case=mock_generate_use_case,
    )


@pytest.fixture
def test_services() -> list[Service]:
    """List of test services."""
    return [
        Service(
            id=uuid4(),
            service_id="service-1",
            criticality=Criticality.CRITICAL,
            team="team-a",
        ),
        Service(
            id=uuid4(),
            service_id="service-2",
            criticality=Criticality.HIGH,
            team="team-b",
        ),
        Service(
            id=uuid4(),
            service_id="service-3",
            criticality=Criticality.MEDIUM,
            team="team-c",
        ),
    ]


@pytest.fixture
def mock_generate_response() -> GenerateRecommendationResponse:
    """Mock successful generate response."""
    now = datetime.now(timezone.utc)
    return GenerateRecommendationResponse(
        service_id="service-1",
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
                    "conservative": TierDTO(level="conservative", target=99.9),
                },
                explanation=ExplanationDTO(
                    summary="Test",
                    feature_attribution=[],
                ),
                data_quality=DataQualityDTO(
                    data_completeness=0.95,
                    is_cold_start=False,
                    lookback_days_actual=30,
                ),
            )
        ],
    )


class TestBatchComputeRecommendationsExecute:
    """Tests for BatchComputeRecommendationsUseCase.execute()."""

    @pytest.mark.asyncio
    async def test_computes_recommendations_for_all_services(
        self,
        use_case,
        mock_service_repo,
        mock_generate_use_case,
        test_services,
        mock_generate_response,
    ):
        """Should compute recommendations for all services."""
        # Arrange
        mock_service_repo.list_all.return_value = test_services
        mock_generate_use_case.execute.return_value = mock_generate_response

        # Act
        result = await use_case.execute()

        # Assert
        assert result.total_services == 3
        assert result.successful == 3
        assert result.failed == 0
        assert result.skipped == 0
        assert result.duration_seconds >= 0
        assert len(result.failures) == 0
        assert mock_generate_use_case.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_excludes_discovered_only_services(
        self,
        use_case,
        mock_service_repo,
        mock_generate_use_case,
        mock_generate_response,
    ):
        """Should skip services marked as is_discovered=True when exclude_discovered_only=True."""
        # Arrange
        services_with_discovered = [
            Service(
                id=uuid4(),
                service_id="service-1",
                criticality=Criticality.CRITICAL,
                team="team-a",
            ),
            MagicMock(
                service_id="discovered-service",
                is_discovered=True,
            ),
            Service(
                id=uuid4(),
                service_id="service-3",
                criticality=Criticality.HIGH,
                team="team-b",
            ),
        ]
        mock_service_repo.list_all.return_value = services_with_discovered
        mock_generate_use_case.execute.return_value = mock_generate_response

        # Act
        result = await use_case.execute(exclude_discovered_only=True)

        # Assert
        assert result.total_services == 2  # Only non-discovered
        assert result.skipped == 1  # discovered-service skipped
        assert result.successful == 2
        assert mock_generate_use_case.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_includes_discovered_services_when_flag_is_false(
        self,
        use_case,
        mock_service_repo,
        mock_generate_use_case,
        mock_generate_response,
    ):
        """Should include discovered services when exclude_discovered_only=False."""
        # Arrange
        services_with_discovered = [
            Service(
                id=uuid4(),
                service_id="service-1",
                criticality=Criticality.CRITICAL,
                team="team-a",
            ),
            MagicMock(
                service_id="discovered-service",
                is_discovered=True,
            ),
        ]
        mock_service_repo.list_all.return_value = services_with_discovered
        mock_generate_use_case.execute.return_value = mock_generate_response

        # Act
        result = await use_case.execute(exclude_discovered_only=False)

        # Assert
        assert result.total_services == 2
        assert result.skipped == 0
        assert mock_generate_use_case.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_handles_partial_failures(
        self,
        use_case,
        mock_service_repo,
        mock_generate_use_case,
        test_services,
        mock_generate_response,
    ):
        """Should continue processing when some services fail."""
        # Arrange
        mock_service_repo.list_all.return_value = test_services

        # First service succeeds, second fails, third succeeds
        mock_generate_use_case.execute.side_effect = [
            mock_generate_response,  # service-1 success
            Exception("Insufficient data"),  # service-2 failure
            mock_generate_response,  # service-3 success
        ]

        # Act
        result = await use_case.execute()

        # Assert
        assert result.total_services == 3
        assert result.successful == 2
        assert result.failed == 1
        assert len(result.failures) == 1
        assert result.failures[0]["service_id"] == "service-2"
        assert "Insufficient data" in result.failures[0]["error"]

    @pytest.mark.asyncio
    async def test_handles_all_failures(
        self,
        use_case,
        mock_service_repo,
        mock_generate_use_case,
        test_services,
    ):
        """Should handle case where all services fail."""
        # Arrange
        mock_service_repo.list_all.return_value = test_services
        mock_generate_use_case.execute.side_effect = Exception("Network error")

        # Act
        result = await use_case.execute()

        # Assert
        assert result.total_services == 3
        assert result.successful == 0
        assert result.failed == 3
        assert len(result.failures) == 3

    @pytest.mark.asyncio
    async def test_passes_sli_type_parameter(
        self,
        use_case,
        mock_service_repo,
        mock_generate_use_case,
        test_services,
        mock_generate_response,
    ):
        """Should pass sli_type parameter to generate use case."""
        # Arrange
        mock_service_repo.list_all.return_value = test_services
        mock_generate_use_case.execute.return_value = mock_generate_response

        # Act
        await use_case.execute(sli_type="latency")

        # Assert
        # Check first call's request
        first_call_request = mock_generate_use_case.execute.call_args_list[0][0][0]
        assert first_call_request.sli_type == "latency"

    @pytest.mark.asyncio
    async def test_passes_lookback_days_parameter(
        self,
        use_case,
        mock_service_repo,
        mock_generate_use_case,
        test_services,
        mock_generate_response,
    ):
        """Should pass lookback_days parameter to generate use case."""
        # Arrange
        mock_service_repo.list_all.return_value = test_services
        mock_generate_use_case.execute.return_value = mock_generate_response

        # Act
        await use_case.execute(lookback_days=60)

        # Assert
        first_call_request = mock_generate_use_case.execute.call_args_list[0][0][0]
        assert first_call_request.lookback_days == 60

    @pytest.mark.asyncio
    async def test_handles_empty_service_list(
        self,
        use_case,
        mock_service_repo,
        mock_generate_use_case,
    ):
        """Should handle case with no services."""
        # Arrange
        mock_service_repo.list_all.return_value = []

        # Act
        result = await use_case.execute()

        # Assert
        assert result.total_services == 0
        assert result.successful == 0
        assert result.failed == 0
        assert result.skipped == 0
        mock_generate_use_case.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_collects_multiple_failure_details(
        self,
        use_case,
        mock_service_repo,
        mock_generate_use_case,
        test_services,
    ):
        """Should collect detailed error information for multiple failures."""
        # Arrange
        mock_service_repo.list_all.return_value = test_services
        mock_generate_use_case.execute.side_effect = [
            Exception("Error A"),
            Exception("Error B"),
            Exception("Error C"),
        ]

        # Act
        result = await use_case.execute()

        # Assert
        assert len(result.failures) == 3
        assert result.failures[0]["service_id"] == "service-1"
        assert "Error A" in result.failures[0]["error"]
        assert result.failures[1]["service_id"] == "service-2"
        assert "Error B" in result.failures[1]["error"]
        assert result.failures[2]["service_id"] == "service-3"
        assert "Error C" in result.failures[2]["error"]

    @pytest.mark.asyncio
    async def test_execution_time_measurement(
        self,
        use_case,
        mock_service_repo,
        mock_generate_use_case,
        test_services,
        mock_generate_response,
    ):
        """Should measure and report execution duration."""
        # Arrange
        mock_service_repo.list_all.return_value = test_services
        mock_generate_use_case.execute.return_value = mock_generate_response

        # Act
        result = await use_case.execute()

        # Assert
        assert result.duration_seconds >= 0
        assert isinstance(result.duration_seconds, float)

    @pytest.mark.asyncio
    async def test_handles_none_response_from_generate_use_case(
        self,
        use_case,
        mock_service_repo,
        mock_generate_use_case,
        test_services,
    ):
        """Should handle None response from generate use case (e.g., service not found)."""
        # Arrange
        mock_service_repo.list_all.return_value = test_services
        # Return None for all services (e.g., insufficient data)
        mock_generate_use_case.execute.return_value = None

        # Act
        result = await use_case.execute()

        # Assert
        # None responses are treated as successful (just no recommendations generated)
        assert result.total_services == 3
        assert result.successful == 3
        assert result.failed == 0
