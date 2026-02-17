"""
SLO Recommendations API routes.

Implements the REST API for retrieving SLO recommendations.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from src.application.dtos.slo_recommendation_dto import (
    GetRecommendationRequest,
)
from src.application.use_cases.get_slo_recommendation import (
    GetSloRecommendationUseCase,
)
from src.infrastructure.api.dependencies import get_get_slo_recommendation_use_case
from src.infrastructure.api.middleware.auth import verify_api_key
from src.infrastructure.api.schemas.error_schema import ProblemDetails
from src.infrastructure.api.schemas.slo_recommendation_schema import (
    CounterfactualApiModel,
    DataProvenanceApiModel,
    DataQualityApiModel,
    DependencyImpactApiModel,
    ExplanationApiModel,
    FeatureAttributionApiModel,
    LookbackWindowApiModel,
    RecommendationApiModel,
    SloRecommendationApiResponse,
    TierApiModel,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/{service_id}/slo-recommendations",
    response_model=SloRecommendationApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Get SLO recommendations for a service",
    description="Retrieve computed SLO recommendations (availability/latency tiers) for a given service",
    responses={
        200: {"description": "Recommendations retrieved successfully"},
        400: {
            "model": ProblemDetails,
            "description": "Invalid query parameters",
        },
        401: {"model": ProblemDetails, "description": "Missing or invalid API key"},
        404: {"model": ProblemDetails, "description": "Service not found"},
        422: {
            "model": ProblemDetails,
            "description": "Insufficient telemetry data to generate recommendations",
        },
        429: {"model": ProblemDetails, "description": "Rate limit exceeded"},
        500: {"model": ProblemDetails, "description": "Internal server error"},
    },
)
async def get_slo_recommendations(
    service_id: str = Path(..., description="Service identifier"),
    sli_type: str = Query(
        "all",
        description="SLI type filter: availability, latency, or all",
        pattern="^(availability|latency|all)$",
    ),
    lookback_days: int = Query(
        30,
        ge=7,
        le=365,
        description="Lookback window in days (7-365)",
    ),
    force_regenerate: bool = Query(
        False,
        description="Bypass cached results and recompute recommendations",
    ),
    use_case: GetSloRecommendationUseCase = Depends(
        get_get_slo_recommendation_use_case
    ),
    current_user: str = Depends(verify_api_key),
) -> SloRecommendationApiResponse:
    """
    Get SLO recommendations for a service.

    This endpoint retrieves computed SLO recommendations for a service, including:
    - Three tiers (Conservative/Balanced/Aggressive) for availability and/or latency
    - Feature attribution explaining the recommendation
    - Dependency impact analysis (for availability)
    - Data quality metadata

    **SLI Type Filtering:**
    - `availability`: Return only availability recommendations
    - `latency`: Return only latency recommendations
    - `all`: Return both (default)

    **Force Regenerate:**
    - `false`: Returns cached recommendation if available (default)
    - `true`: Recomputes from telemetry data

    **Lookback Window:**
    - Default: 30 days
    - Cold-start services: Automatically extended to 90 days if data completeness < 90%

    **Rate Limit:** 60 requests/minute per API key
    **Performance:** Target p95 < 500ms for cached queries
    """
    try:
        logger.info(
            f"GET /services/{service_id}/slo-recommendations "
            f"(sli_type={sli_type}, lookback_days={lookback_days}, "
            f"force_regenerate={force_regenerate})"
        )

        # Create application DTO
        app_request = GetRecommendationRequest(
            service_id=service_id,
            sli_type=sli_type,
            lookback_days=lookback_days,
            force_regenerate=force_regenerate,
        )

        # Execute use case
        result = await use_case.execute(app_request)

        # Check if service not found
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service with ID '{service_id}' is not registered",
            )

        # Check if no recommendations generated (insufficient data)
        if not result.recommendations:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Insufficient telemetry data to generate SLO recommendations for '{service_id}'. "
                    f"Service may be newly registered or have incomplete telemetry coverage."
                ),
            )

        # Convert application DTOs to API models
        recommendations_api = []
        for rec in result.recommendations:
            # Convert tiers
            tiers_api = {}
            for tier_level, tier in rec.tiers.items():
                tier_api = TierApiModel(
                    level=tier.level,
                    target=tier.target,
                    error_budget_monthly_minutes=tier.error_budget_monthly_minutes,
                    confidence_interval=(
                        tuple(tier.confidence_interval)
                        if tier.confidence_interval
                        else None
                    ),
                    estimated_breach_probability=tier.estimated_breach_probability,
                    percentile=tier.percentile,
                    target_ms=tier.target_ms,
                )
                tiers_api[tier_level] = tier_api

            # Convert feature attribution
            feature_attribution_api = [
                FeatureAttributionApiModel(
                    feature=fa.feature,
                    contribution=fa.contribution,
                    description=fa.description,
                )
                for fa in rec.explanation.feature_attribution
            ]

            # Convert dependency impact (availability only)
            dependency_impact_api = None
            if rec.explanation.dependency_impact:
                dep = rec.explanation.dependency_impact
                dependency_impact_api = DependencyImpactApiModel(
                    composite_availability_bound=dep.composite_availability_bound,
                    bottleneck_service=dep.bottleneck_service,
                    bottleneck_contribution=dep.bottleneck_contribution,
                    hard_dependency_count=dep.hard_dependency_count,
                    soft_dependency_count=dep.soft_dependency_count,
                )

            # Convert counterfactuals (FR-7)
            counterfactuals_api = [
                CounterfactualApiModel(
                    condition=cf.condition,
                    result=cf.result,
                    feature=cf.feature,
                    original_value=cf.original_value,
                    perturbed_value=cf.perturbed_value,
                )
                for cf in (rec.explanation.counterfactuals or [])
            ]

            # Convert provenance (FR-7)
            provenance_api = None
            if rec.explanation.provenance:
                prov = rec.explanation.provenance
                provenance_api = DataProvenanceApiModel(
                    dependency_graph_version=prov.dependency_graph_version,
                    telemetry_window_start=prov.telemetry_window_start,
                    telemetry_window_end=prov.telemetry_window_end,
                    data_completeness=prov.data_completeness,
                    computation_method=prov.computation_method,
                    telemetry_source=prov.telemetry_source,
                )

            # Convert explanation
            explanation_api = ExplanationApiModel(
                summary=rec.explanation.summary,
                feature_attribution=feature_attribution_api,
                dependency_impact=dependency_impact_api,
                counterfactuals=counterfactuals_api,
                provenance=provenance_api,
            )

            # Convert data quality
            data_quality_api = DataQualityApiModel(
                data_completeness=rec.data_quality.data_completeness,
                telemetry_gaps=rec.data_quality.telemetry_gaps,
                confidence_note=rec.data_quality.confidence_note,
                is_cold_start=rec.data_quality.is_cold_start,
                lookback_days_actual=rec.data_quality.lookback_days_actual,
            )

            # Build recommendation
            rec_api = RecommendationApiModel(
                sli_type=rec.sli_type,
                metric=rec.metric,
                tiers=tiers_api,
                explanation=explanation_api,
                data_quality=data_quality_api,
            )
            recommendations_api.append(rec_api)

        # Convert lookback window (already ISO 8601 strings in DTO)
        lookback_window_api = LookbackWindowApiModel(
            start=result.lookback_window.start,
            end=result.lookback_window.end,
        )

        # Build response (generated_at is already ISO 8601 string in DTO)
        return SloRecommendationApiResponse(
            service_id=result.service_id,
            generated_at=result.generated_at,
            lookback_window=lookback_window_api,
            recommendations=recommendations_api,
        )

    except HTTPException:
        raise
    except ValueError as e:
        # Domain validation error
        logger.warning(f"Validation error for service {service_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        # Unexpected error
        logger.error(
            f"Unexpected error retrieving recommendations for {service_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing the request",
        ) from e
