"""FR-4: Impact Analysis API routes.

Implements the POST /api/v1/slos/impact-analysis endpoint for computing
the cascading impact of a proposed SLO change on upstream services.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.dtos.impact_analysis_dto import (
    ImpactAnalysisRequest,
    ProposedChangeDTO,
)
from src.application.use_cases.run_impact_analysis import RunImpactAnalysisUseCase
from src.domain.services.composite_availability_service import CompositeAvailabilityService
from src.domain.services.graph_traversal_service import GraphTraversalService
from src.domain.services.impact_analysis_service import ImpactAnalysisService
from src.infrastructure.api.middleware.auth import verify_api_key
from src.infrastructure.api.schemas.error_schema import ProblemDetails
from src.infrastructure.api.schemas.impact_analysis_schema import (
    ImpactAnalysisApiRequest,
    ImpactAnalysisApiResponse,
    ImpactedServiceApiModel,
    ImpactSummaryApiModel,
    ProposedChangeApiModel,
)
from src.infrastructure.database.repositories.dependency_repository import DependencyRepository
from src.infrastructure.database.repositories.service_repository import ServiceRepository
from src.infrastructure.database.session import get_async_session
from src.infrastructure.telemetry.mock_prometheus_client import MockPrometheusClient

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_impact_analysis_use_case(
    session: AsyncSession = Depends(get_async_session),
) -> RunImpactAnalysisUseCase:
    """Build RunImpactAnalysisUseCase with all dependencies."""
    service_repo = ServiceRepository(session)
    dependency_repo = DependencyRepository(session)
    telemetry_service = MockPrometheusClient()
    graph_traversal = GraphTraversalService()
    composite_service = CompositeAvailabilityService()
    impact_service = ImpactAnalysisService(composite_service)

    return RunImpactAnalysisUseCase(
        service_repository=service_repo,
        dependency_repository=dependency_repo,
        telemetry_service=telemetry_service,
        graph_traversal_service=graph_traversal,
        impact_analysis_service=impact_service,
    )


@router.post(
    "/impact-analysis",
    response_model=ImpactAnalysisApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Run impact analysis for a proposed SLO change",
    description=(
        "Given a proposed SLO change for a service, compute the cascading impact "
        "on all upstream services. Shows which services' composite SLOs would be "
        "affected and identifies services at risk of SLO breach."
    ),
    responses={
        200: {"description": "Impact analysis completed"},
        400: {"model": ProblemDetails, "description": "Invalid request"},
        401: {"model": ProblemDetails, "description": "Missing or invalid API key"},
        404: {"model": ProblemDetails, "description": "Service not found"},
    },
)
async def run_impact_analysis(
    body: ImpactAnalysisApiRequest,
    use_case: RunImpactAnalysisUseCase = Depends(get_impact_analysis_use_case),
    current_user: str = Depends(verify_api_key),
) -> ImpactAnalysisApiResponse:
    """Run impact analysis for a proposed SLO change."""
    try:
        request = ImpactAnalysisRequest(
            service_id=body.service_id,
            proposed_change=ProposedChangeDTO(
                sli_type=body.proposed_change.sli_type,
                current_target=body.proposed_change.current_target,
                proposed_target=body.proposed_change.proposed_target,
            ),
            max_depth=body.max_depth,
        )

        result = await use_case.execute(request)

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service '{body.service_id}' is not registered.",
            )

        return ImpactAnalysisApiResponse(
            analysis_id=result.analysis_id,
            service_id=result.service_id,
            proposed_change=ProposedChangeApiModel(
                sli_type=result.proposed_change.sli_type,
                current_target=result.proposed_change.current_target,
                proposed_target=result.proposed_change.proposed_target,
            ),
            impacted_services=[
                ImpactedServiceApiModel(
                    service_id=s.service_id,
                    relationship=s.relationship,
                    current_composite_availability=s.current_composite_availability,
                    projected_composite_availability=s.projected_composite_availability,
                    delta=s.delta,
                    current_slo_target=s.current_slo_target,
                    slo_at_risk=s.slo_at_risk,
                    risk_detail=s.risk_detail,
                )
                for s in result.impacted_services
            ],
            summary=ImpactSummaryApiModel(
                total_impacted=result.summary.total_impacted,
                slos_at_risk=result.summary.slos_at_risk,
                recommendation=result.summary.recommendation,
                latency_note=result.summary.latency_note,
            ),
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Error running impact analysis: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during impact analysis",
        ) from e
