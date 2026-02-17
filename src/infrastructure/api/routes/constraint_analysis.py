"""
Constraint analysis API routes.

Implements the REST API for dependency-aware constraint propagation and error budget analysis.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.dtos.constraint_analysis_dto import (
    ConstraintAnalysisRequest,
    ErrorBudgetBreakdownRequest,
)
from src.application.use_cases.get_error_budget_breakdown import (
    GetErrorBudgetBreakdownUseCase,
)
from src.application.use_cases.run_constraint_analysis import (
    RunConstraintAnalysisUseCase,
)
from src.infrastructure.api.dependencies import (
    get_get_error_budget_breakdown_use_case,
    get_run_constraint_analysis_use_case,
)
from src.infrastructure.api.middleware.auth import verify_api_key
from src.infrastructure.api.schemas.constraint_analysis_schema import (
    ConstraintAnalysisApiResponse,
    ConstraintAnalysisQueryParams,
    DependencyRiskApiModel,
    ErrorBudgetBreakdownApiModel,
    ErrorBudgetBreakdownApiResponse,
    ErrorBudgetBreakdownQueryParams,
    UnachievableWarningApiModel,
)
from src.infrastructure.api.schemas.error_schema import ProblemDetails

router = APIRouter()


@router.get(
    "/{service_id}/constraint-analysis",
    response_model=ConstraintAnalysisApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyze constraint propagation",
    description="Analyze if a desired SLO target is achievable given dependency constraints",
    responses={
        200: {"description": "Constraint analysis completed successfully"},
        400: {
            "model": ProblemDetails,
            "description": "Invalid query parameters",
        },
        401: {"model": ProblemDetails, "description": "Missing or invalid API key"},
        404: {"model": ProblemDetails, "description": "Service not found"},
        422: {
            "model": ProblemDetails,
            "description": "Service has no dependencies to analyze",
        },
        429: {"model": ProblemDetails, "description": "Rate limit exceeded"},
        500: {"model": ProblemDetails, "description": "Internal server error"},
    },
)
async def analyze_constraints(
    service_id: str,
    params: ConstraintAnalysisQueryParams = Depends(),
    use_case: RunConstraintAnalysisUseCase = Depends(
        get_run_constraint_analysis_use_case
    ),
    current_user: str = Depends(verify_api_key),
) -> ConstraintAnalysisApiResponse:
    """
    Analyze if a desired SLO target is achievable given dependency constraints.

    This endpoint performs comprehensive constraint propagation analysis:
    - Traverses dependency chain and computes composite availability bound
    - Applies adaptive buffer to external API dependencies (10x multiplier)
    - Computes error budget consumption per dependency
    - Detects unachievable SLO targets and provides remediation guidance
    - Identifies circular dependencies (SCC supernodes)

    **Rate Limit:** 30 requests/minute per API key
    **Performance:** Target p95 < 2s for typical graphs (50 services)

    **External API Buffer Formula:**
    `effective = min(observed, 1 - (1-published)*11)`

    Example: Published SLA 99.99% → effective 99.89% (assumes 10x error rate)
    """
    try:
        # Create application DTO
        app_request = ConstraintAnalysisRequest(
            service_id=service_id,
            desired_target_pct=params.desired_target_pct,
            lookback_days=params.lookback_days,
            max_depth=params.max_depth,
        )

        # Execute use case
        result = await use_case.execute(app_request)

        # Check if service not found
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service with ID '{service_id}' is not registered",
            )

        # Convert application DTOs to API models
        return ConstraintAnalysisApiResponse(
            service_id=result.service_id,
            analyzed_at=result.analyzed_at,
            composite_availability_bound_pct=result.composite_availability_bound_pct,
            is_achievable=result.is_achievable,
            has_high_risk_dependencies=result.has_high_risk_dependencies,
            dependency_chain_depth=result.dependency_chain_depth,
            total_hard_dependencies=result.total_hard_dependencies,
            total_soft_dependencies=result.total_soft_dependencies,
            total_external_dependencies=result.total_external_dependencies,
            lookback_days=result.lookback_days,
            error_budget_breakdown=ErrorBudgetBreakdownApiModel(
                service_id=result.error_budget_breakdown.service_id,
                slo_target_pct=result.error_budget_breakdown.slo_target_pct,
                total_error_budget_minutes=result.error_budget_breakdown.total_error_budget_minutes,
                self_consumption_pct=result.error_budget_breakdown.self_consumption_pct,
                total_dependency_consumption_pct=result.error_budget_breakdown.total_dependency_consumption_pct,
                high_risk_dependencies=result.error_budget_breakdown.high_risk_dependencies,
                dependency_risks=[
                    DependencyRiskApiModel(
                        service_id=dep.service_id,
                        availability_pct=dep.availability_pct,
                        error_budget_consumption_pct=dep.error_budget_consumption_pct,
                        risk_level=dep.risk_level,
                        is_external=dep.is_external,
                        communication_mode=dep.communication_mode,
                        criticality=dep.criticality,
                        published_sla_pct=dep.published_sla_pct,
                        observed_availability_pct=dep.observed_availability_pct,
                        effective_availability_note=dep.effective_availability_note,
                    )
                    for dep in result.error_budget_breakdown.dependency_risks
                ],
            ),
            unachievable_warning=(
                UnachievableWarningApiModel(
                    desired_target_pct=result.unachievable_warning.desired_target_pct,
                    composite_bound_pct=result.unachievable_warning.composite_bound_pct,
                    gap_pct=result.unachievable_warning.gap_pct,
                    message=result.unachievable_warning.message,
                    remediation_guidance=result.unachievable_warning.remediation_guidance,
                    required_dep_availability_pct=result.unachievable_warning.required_dep_availability_pct,
                )
                if result.unachievable_warning
                else None
            ),
            soft_dependency_risks=result.soft_dependency_risks,
            scc_supernodes=result.scc_supernodes,
        )
    except HTTPException:
        raise
    except ValueError as e:
        # Domain validation error
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        # Unexpected error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing the request",
        ) from e


@router.get(
    "/{service_id}/error-budget-breakdown",
    response_model=ErrorBudgetBreakdownApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Get error budget breakdown",
    description="Get detailed error budget breakdown for a service and its direct dependencies",
    responses={
        200: {"description": "Error budget breakdown retrieved successfully"},
        400: {
            "model": ProblemDetails,
            "description": "Invalid query parameters",
        },
        401: {"model": ProblemDetails, "description": "Missing or invalid API key"},
        404: {"model": ProblemDetails, "description": "Service not found"},
        429: {"model": ProblemDetails, "description": "Rate limit exceeded"},
        500: {"model": ProblemDetails, "description": "Internal server error"},
    },
)
async def get_error_budget_breakdown(
    service_id: str,
    params: ErrorBudgetBreakdownQueryParams = Depends(),
    use_case: GetErrorBudgetBreakdownUseCase = Depends(
        get_get_error_budget_breakdown_use_case
    ),
    current_user: str = Depends(verify_api_key),
) -> ErrorBudgetBreakdownApiResponse:
    """
    Get detailed error budget breakdown for a service and its direct dependencies.

    This endpoint provides a lightweight analysis focused on error budget consumption:
    - Only analyzes direct (depth=1) hard sync dependencies
    - Computes per-dependency error budget consumption percentage
    - Classifies risk levels: LOW (<20%), MODERATE (20-30%), HIGH (>30%)
    - Applies adaptive buffer to external API dependencies
    - Does not perform full constraint propagation (use /constraint-analysis for that)

    **Rate Limit:** 60 requests/minute per API key
    **Performance:** Target p95 < 1s for typical services

    **Error Budget Formula:**
    `consumption% = (1 - dep_availability) / (1 - target/100)`

    Example: Dep at 99.5% with target 99.9% → 500% consumption (uses 5x budget)
    """
    try:
        # Create application DTO
        app_request = ErrorBudgetBreakdownRequest(
            service_id=service_id,
            slo_target_pct=params.slo_target_pct,
            lookback_days=params.lookback_days,
        )

        # Execute use case
        result = await use_case.execute(app_request)

        # Check if service not found
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service with ID '{service_id}' is not registered",
            )

        # Convert application DTOs to API models
        return ErrorBudgetBreakdownApiResponse(
            service_id=result.service_id,
            analyzed_at=result.analyzed_at,
            slo_target_pct=result.slo_target_pct,
            total_error_budget_minutes=result.total_error_budget_minutes,
            self_consumption_pct=result.self_consumption_pct,
            total_dependency_consumption_pct=result.total_dependency_consumption_pct,
            high_risk_dependencies=result.high_risk_dependencies,
            dependency_risks=[
                DependencyRiskApiModel(
                    service_id=dep.service_id,
                    availability_pct=dep.availability_pct,
                    error_budget_consumption_pct=dep.error_budget_consumption_pct,
                    risk_level=dep.risk_level,
                    is_external=dep.is_external,
                    communication_mode=dep.communication_mode,
                    criticality=dep.criticality,
                    published_sla_pct=dep.published_sla_pct,
                    observed_availability_pct=dep.observed_availability_pct,
                    effective_availability_note=dep.effective_availability_note,
                )
                for dep in result.dependency_risks
            ],
        )
    except HTTPException:
        raise
    except ValueError as e:
        # Domain validation error
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        # Unexpected error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing the request",
        ) from e
