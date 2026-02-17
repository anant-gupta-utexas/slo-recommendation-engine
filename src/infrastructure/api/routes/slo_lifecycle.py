"""FR-5: SLO Recommendation Lifecycle API routes.

Implements accept/modify/reject workflow, active SLO retrieval, and audit history.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, status

from src.application.dtos.slo_lifecycle_dto import ManageSloRequest, SloModifications
from src.application.use_cases.manage_slo_lifecycle import ManageSloLifecycleUseCase
from src.infrastructure.api.middleware.auth import verify_api_key
from src.infrastructure.api.schemas.error_schema import ProblemDetails
from src.infrastructure.api.schemas.slo_lifecycle_schema import (
    ActiveSloApiResponse,
    AuditEntryApiModel,
    AuditHistoryApiResponse,
    ManageSloApiRequest,
    ManageSloApiResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def get_manage_slo_lifecycle_use_case() -> ManageSloLifecycleUseCase:
    """Get ManageSloLifecycleUseCase instance."""
    return ManageSloLifecycleUseCase()


@router.post(
    "/{service_id}/slos",
    response_model=ManageSloApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Accept, modify, or reject an SLO recommendation",
    description="Manage the lifecycle of SLO recommendations for a service",
    responses={
        200: {"description": "Action performed successfully"},
        400: {"model": ProblemDetails, "description": "Invalid request"},
        401: {"model": ProblemDetails, "description": "Missing or invalid API key"},
    },
)
async def manage_slo(
    body: ManageSloApiRequest,
    service_id: str = Path(..., description="Service identifier"),
    use_case: ManageSloLifecycleUseCase = Depends(get_manage_slo_lifecycle_use_case),
    current_user: str = Depends(verify_api_key),
) -> ManageSloApiResponse:
    """Accept, modify, or reject an SLO recommendation."""
    try:
        modifications = None
        if body.modifications:
            modifications = SloModifications(
                availability_target=body.modifications.availability_target,
                latency_p95_target_ms=body.modifications.latency_p95_target_ms,
                latency_p99_target_ms=body.modifications.latency_p99_target_ms,
            )

        request = ManageSloRequest(
            service_id=service_id,
            action=body.action,
            actor=body.actor,
            selected_tier=body.selected_tier,
            recommendation_id=body.recommendation_id,
            modifications=modifications,
            rationale=body.rationale,
        )

        result = await use_case.execute(request)

        active_slo_api = None
        if result.active_slo:
            active_slo_api = ActiveSloApiResponse(
                service_id=result.active_slo.service_id,
                slo_id=result.active_slo.slo_id,
                availability_target=result.active_slo.availability_target,
                latency_p95_target_ms=result.active_slo.latency_p95_target_ms,
                latency_p99_target_ms=result.active_slo.latency_p99_target_ms,
                source=result.active_slo.source,
                recommendation_id=result.active_slo.recommendation_id,
                selected_tier=result.active_slo.selected_tier,
                activated_at=result.active_slo.activated_at,
                activated_by=result.active_slo.activated_by,
            )

        return ManageSloApiResponse(
            service_id=result.service_id,
            status=result.status,
            action=result.action,
            active_slo=active_slo_api,
            modification_delta=result.modification_delta,
            message=result.message,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Error managing SLO for {service_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
        ) from e


@router.get(
    "/{service_id}/slos",
    response_model=ActiveSloApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the active SLO for a service",
    description="Retrieve the currently active SLO target for a service",
    responses={
        200: {"description": "Active SLO retrieved"},
        404: {"model": ProblemDetails, "description": "No active SLO found"},
        401: {"model": ProblemDetails, "description": "Missing or invalid API key"},
    },
)
async def get_active_slo(
    service_id: str = Path(..., description="Service identifier"),
    use_case: ManageSloLifecycleUseCase = Depends(get_manage_slo_lifecycle_use_case),
    current_user: str = Depends(verify_api_key),
) -> ActiveSloApiResponse:
    """Get the active SLO for a service."""
    result = await use_case.get_active_slo(service_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active SLO found for service '{service_id}'. Accept a recommendation first.",
        )

    return ActiveSloApiResponse(
        service_id=result.service_id,
        slo_id=result.slo_id,
        availability_target=result.availability_target,
        latency_p95_target_ms=result.latency_p95_target_ms,
        latency_p99_target_ms=result.latency_p99_target_ms,
        source=result.source,
        recommendation_id=result.recommendation_id,
        selected_tier=result.selected_tier,
        activated_at=result.activated_at,
        activated_by=result.activated_by,
    )


@router.get(
    "/{service_id}/slo-history",
    response_model=AuditHistoryApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Get SLO audit history for a service",
    description="Retrieve the full audit trail of SLO lifecycle actions",
    responses={
        200: {"description": "Audit history retrieved"},
        401: {"model": ProblemDetails, "description": "Missing or invalid API key"},
    },
)
async def get_slo_history(
    service_id: str = Path(..., description="Service identifier"),
    use_case: ManageSloLifecycleUseCase = Depends(get_manage_slo_lifecycle_use_case),
    current_user: str = Depends(verify_api_key),
) -> AuditHistoryApiResponse:
    """Get the SLO audit history for a service."""
    result = await use_case.get_audit_history(service_id)

    return AuditHistoryApiResponse(
        service_id=result.service_id,
        entries=[
            AuditEntryApiModel(
                id=e.id,
                service_id=e.service_id,
                action=e.action,
                actor=e.actor,
                timestamp=e.timestamp,
                selected_tier=e.selected_tier,
                rationale=e.rationale,
                recommendation_id=e.recommendation_id,
                previous_slo=e.previous_slo,
                new_slo=e.new_slo,
                modification_delta=e.modification_delta,
            )
            for e in result.entries
        ],
        total_count=result.total_count,
    )
