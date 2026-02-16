"""Get SLO Recommendations Use Case (FR-2).

Retrieves stored recommendations or triggers regeneration.
"""

import logging
from datetime import datetime, timezone

from src.application.dtos.slo_recommendation_dto import (
    GetRecommendationRequest,
    GetRecommendationResponse,
    LookbackWindowDTO,
    RecommendationDTO,
    GenerateRecommendationRequest,
)
from src.application.use_cases.generate_slo_recommendation import (
    GenerateSloRecommendationUseCase,
)
from src.domain.repositories.service_repository import ServiceRepositoryInterface
from src.domain.repositories.slo_recommendation_repository import (
    SloRecommendationRepositoryInterface,
)

logger = logging.getLogger(__name__)


class GetSloRecommendationUseCase:
    """Retrieve SLO recommendations for a service.

    Retrieves active recommendations from storage. If force_regenerate=True,
    delegates to GenerateSloRecommendationUseCase to create new recommendations.
    """

    def __init__(
        self,
        service_repo: ServiceRepositoryInterface,
        generate_use_case: GenerateSloRecommendationUseCase,
    ):
        """Initialize use case with dependencies.

        Args:
            service_repo: Repository for service lookups
            generate_use_case: Use case to generate new recommendations
        """
        self._service_repo = service_repo
        self._generate_use_case = generate_use_case

    async def execute(
        self, request: GetRecommendationRequest
    ) -> GetRecommendationResponse | None:
        """Retrieve or generate SLO recommendations for a service.

        Args:
            request: Request containing service_id, sli_type filter, and flags

        Returns:
            Response with recommendations list, or None if service not found
        """
        logger.info(
            f"GetSloRecommendation.execute for service_id={request.service_id}, "
            f"sli_type={request.sli_type}, force_regenerate={request.force_regenerate}"
        )

        # 1. Verify service exists
        service = await self._service_repo.get_by_service_id(request.service_id)
        if not service:
            logger.warning(f"Service not found: {request.service_id}")
            return None

        # 2. If force_regenerate=True, delegate to generate use case
        if request.force_regenerate:
            logger.info(
                f"Force regenerate requested, delegating to GenerateSloRecommendation for {request.service_id}"
            )
            generate_request = GenerateRecommendationRequest(
                service_id=request.service_id,
                sli_type=request.sli_type,
                lookback_days=request.lookback_days,
                force_regenerate=True,
            )
            generate_response = await self._generate_use_case.execute(
                generate_request
            )
            if not generate_response:
                return None

            # Convert GenerateRecommendationResponse to GetRecommendationResponse
            return GetRecommendationResponse(
                service_id=generate_response.service_id,
                generated_at=generate_response.generated_at,
                lookback_window=generate_response.lookback_window,
                recommendations=generate_response.recommendations,
            )

        # 3. TODO: Otherwise, retrieve stored active recommendations from repository
        # For now, fall back to generation since repository is not implemented yet
        logger.warning(
            f"Repository not implemented yet, falling back to generation for {request.service_id}"
        )
        generate_request = GenerateRecommendationRequest(
            service_id=request.service_id,
            sli_type=request.sli_type,
            lookback_days=request.lookback_days,
        )
        generate_response = await self._generate_use_case.execute(generate_request)
        if not generate_response:
            return None

        return GetRecommendationResponse(
            service_id=generate_response.service_id,
            generated_at=generate_response.generated_at,
            lookback_window=generate_response.lookback_window,
            recommendations=generate_response.recommendations,
        )
