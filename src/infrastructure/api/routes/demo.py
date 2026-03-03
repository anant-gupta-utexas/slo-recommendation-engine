"""
Demo-specific API routes.

IMPORTANT: These routes are for demonstration purposes only and should NOT be
enabled in production. They provide enhanced responses with simulated data
to showcase features that may run asynchronously in production.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from src.application.dtos.dependency_graph_dto import (
    CircularDependencyInfo,
    DependencyGraphIngestRequest,
    DependencyGraphIngestResponse,
    EdgeAttributesDTO,
    EdgeDTO,
    NodeDTO,
    RetryConfigDTO,
)
from src.application.use_cases.detect_circular_dependencies import (
    DetectCircularDependenciesUseCase,
)
from src.application.use_cases.ingest_dependency_graph import (
    IngestDependencyGraphUseCase,
)
from src.domain.entities.circular_dependency_alert import AlertStatus
from src.infrastructure.api.dependencies import (
    get_circular_dependency_alert_repository,
    get_detect_circular_dependencies_use_case,
    get_ingest_dependency_graph_use_case,
)
from src.infrastructure.api.schemas.dependency_schema import (
    CircularDependencyInfoApiModel,
    ConflictInfoApiModel,
    DependencyGraphIngestApiRequest,
    DependencyGraphIngestApiResponse,
)
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
from src.infrastructure.database.repositories.circular_dependency_alert_repository import (
    CircularDependencyAlertRepository,
)

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post(
    "/dependencies",
    response_model=DependencyGraphIngestApiResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="[DEMO] Ingest dependency graph with immediate circular dependency detection",
    description="""
    Demo version of dependency ingestion that immediately detects circular dependencies.

    **DEMO ONLY**: In production, circular dependency detection runs as a background task.
    This endpoint runs it synchronously to provide immediate feedback for demos.

    This endpoint:
    - Ingests the dependency graph (same as production)
    - Immediately runs circular dependency detection (Tarjan's algorithm)
    - Returns populated circular_dependencies_detected in response

    **DO NOT USE IN PRODUCTION** - Use /api/v1/services/dependencies instead.
    """,
    responses={
        202: {"description": "Graph ingestion accepted and processing"},
        400: {
            "model": ProblemDetails,
            "description": "Invalid request schema or validation error",
        },
        401: {"model": ProblemDetails, "description": "Missing or invalid API key"},
        429: {"model": ProblemDetails, "description": "Rate limit exceeded"},
        500: {"model": ProblemDetails, "description": "Internal server error"},
    },
)
async def demo_ingest_dependencies(
    request: DependencyGraphIngestApiRequest,
    ingest_use_case: IngestDependencyGraphUseCase = Depends(
        get_ingest_dependency_graph_use_case
    ),
    detect_circular_use_case: DetectCircularDependenciesUseCase = Depends(
        get_detect_circular_dependencies_use_case
    ),
    alert_repository: CircularDependencyAlertRepository = Depends(
        get_circular_dependency_alert_repository
    ),
    # No authentication required for demo endpoint
) -> DependencyGraphIngestApiResponse:
    """
    Demo endpoint for dependency graph ingestion with immediate circular detection.

    **DEMO ONLY**: This endpoint runs circular dependency detection synchronously
    to provide immediate feedback. In production, use the standard endpoint which
    runs detection as a background task.
    """
    try:
        # Convert API models to application DTOs
        app_request = DependencyGraphIngestRequest(
            source=request.source,
            timestamp=request.timestamp,
            nodes=[
                NodeDTO(
                    service_id=node.service_id,
                    metadata=node.metadata,
                    team=node.metadata.get("team"),
                    criticality=node.metadata.get("criticality", "medium"),
                )
                for node in request.nodes
            ],
            edges=[
                EdgeDTO(
                    source=edge.source,
                    target=edge.target,
                    attributes=EdgeAttributesDTO(
                        communication_mode=edge.attributes.communication_mode,
                        criticality=edge.attributes.criticality,
                        protocol=edge.attributes.protocol,
                        timeout_ms=edge.attributes.timeout_ms,
                        retry_config=(
                            RetryConfigDTO(
                                max_retries=edge.attributes.retry_config.max_retries,
                                backoff_strategy=edge.attributes.retry_config.backoff_strategy,
                            )
                            if edge.attributes.retry_config
                            else None
                        ),
                    ),
                )
                for edge in request.edges
            ],
        )

        # Step 1: Execute normal ingestion
        ingest_result = await ingest_use_case.execute(app_request)

        # Step 2: Immediately detect circular dependencies (DEMO ONLY)
        # Note: This detects cycles and creates new alerts if they don't exist
        newly_created_alerts = await detect_circular_use_case.execute()

        # Step 3: For demo purposes, fetch ALL existing OPEN alerts
        # Then filter to only show cycles involving services from this ingestion
        all_alerts = await alert_repository.list_by_status(AlertStatus.OPEN, skip=0, limit=1000)

        # Get the set of service IDs from the current ingestion
        ingested_service_ids = {node.service_id for node in request.nodes}

        # Filter alerts to only include cycles involving at least one ingested service
        # This prevents showing stale circular dependencies from previous demo runs
        relevant_alerts = [
            alert for alert in all_alerts
            if any(service_id in ingested_service_ids for service_id in alert.cycle_path)
        ]

        # Convert alerts to response DTOs
        circular_dependencies = [
            CircularDependencyInfo(
                cycle_path=alert.cycle_path,
                alert_id=alert.id,
            )
            for alert in relevant_alerts
        ]

        # Merge results - use detected circular deps instead of empty list
        enhanced_result = DependencyGraphIngestResponse(
            ingestion_id=ingest_result.ingestion_id,
            status=ingest_result.status,
            nodes_received=ingest_result.nodes_received,
            edges_received=ingest_result.edges_received,
            nodes_upserted=ingest_result.nodes_upserted,
            edges_upserted=ingest_result.edges_upserted,
            circular_dependencies_detected=circular_dependencies,
            conflicts_resolved=ingest_result.conflicts_resolved,
            warnings=ingest_result.warnings,
            estimated_completion_seconds=0,  # Synchronous for demo
        )

        # Convert to API response
        return DependencyGraphIngestApiResponse(
            ingestion_id=str(enhanced_result.ingestion_id),
            status=enhanced_result.status,
            nodes_received=enhanced_result.nodes_received,
            edges_received=enhanced_result.edges_received,
            nodes_upserted=enhanced_result.nodes_upserted,
            edges_upserted=enhanced_result.edges_upserted,
            circular_dependencies_detected=[
                CircularDependencyInfoApiModel(
                    cycle_path=cd.cycle_path, alert_id=str(cd.alert_id)
                )
                for cd in enhanced_result.circular_dependencies_detected
            ],
            conflicts_resolved=[
                ConflictInfoApiModel(
                    edge=c.edge,
                    existing_source=c.existing_source,
                    new_source=c.new_source,
                    resolution=c.resolution,
                )
                for c in enhanced_result.conflicts_resolved
            ],
            warnings=enhanced_result.warnings,
            estimated_completion_seconds=0,
        )

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


@router.delete(
    "/clear-all",
    status_code=status.HTTP_200_OK,
    summary="[DEMO] Clear all graph data",
    description="""
    Demo helper endpoint to clear all services, dependencies, and alerts.

    **DEMO ONLY**: This endpoint is for demonstration purposes to reset state
    between demo runs. DO NOT USE IN PRODUCTION.

    This endpoint:
    - Deletes all circular dependency alerts
    - Deletes all service dependencies (edges)
    - Deletes all services (nodes)
    """,
)
async def demo_clear_all_data(
    alert_repo: CircularDependencyAlertRepository = Depends(get_circular_dependency_alert_repository),
) -> dict:
    """
    Clear all graph data for demo purposes.

    **DEMO ONLY**: This is a destructive operation that clears ALL data.
    """
    try:
        from sqlalchemy import text

        from src.infrastructure.database.session import get_async_session

        # Get a database session
        async for session in get_async_session():
            # Order matters: alerts -> dependencies -> services (due to foreign keys)

            # 1. Delete all alerts
            await session.execute(text("DELETE FROM circular_dependency_alerts"))

            # 2. Delete all dependencies (edges)
            await session.execute(text("DELETE FROM service_dependencies"))

            # 3. Delete all services (nodes)
            await session.execute(text("DELETE FROM services"))

            await session.commit()
            break  # Only need one session

        return {
            "status": "success",
            "message": "All graph data cleared successfully",
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear data: {str(e)}",
        ) from e


def _generate_demo_availability_recommendation(
    service_id: str,
) -> RecommendationApiModel:
    """Generate synthetic availability recommendation for demo."""
    return RecommendationApiModel(
        sli_type="availability",
        metric="success_rate",
        tiers={
            "conservative": TierApiModel(
                level="conservative",
                target=99.9,
                error_budget_monthly_minutes=43.2,
                confidence_interval=(99.85, 99.95),
                estimated_breach_probability=0.02,
                percentile=None,
                target_ms=None,
            ),
            "balanced": TierApiModel(
                level="balanced",
                target=99.95,
                error_budget_monthly_minutes=21.6,
                confidence_interval=(99.93, 99.97),
                estimated_breach_probability=0.08,
                percentile=None,
                target_ms=None,
            ),
            "aggressive": TierApiModel(
                level="aggressive",
                target=99.99,
                error_budget_monthly_minutes=4.32,
                confidence_interval=(99.985, 99.995),
                estimated_breach_probability=0.15,
                percentile=None,
                target_ms=None,
            ),
        },
        explanation=ExplanationApiModel(
            summary=(
                f"Availability recommendation for {service_id} is based on synthetic demo data. "
                f"Conservative tier (99.9%) is the safest target with the largest error budget. "
                f"Balanced tier (99.95%) offers good reliability with reasonable operational flexibility. "
                f"Aggressive tier (99.99%) targets highest reliability but has the tightest error budget."
            ),
            feature_attribution=[
                FeatureAttributionApiModel(
                    feature="historical_uptime",
                    contribution=0.45,
                    description="Service has demonstrated 99.92% uptime over past 30 days",
                ),
                FeatureAttributionApiModel(
                    feature="traffic_volume",
                    contribution=0.25,
                    description="Moderate traffic (12K req/min) supports stable SLO targets",
                ),
                FeatureAttributionApiModel(
                    feature="dependency_stability",
                    contribution=0.20,
                    description="All hard dependencies have active SLOs ≥99.9%",
                ),
                FeatureAttributionApiModel(
                    feature="deployment_frequency",
                    contribution=0.10,
                    description="Weekly deployments with <0.1% rollback rate",
                ),
            ],
            dependency_impact=DependencyImpactApiModel(
                # Derived from seed data: R_composite = R_payment × R_auth = 0.9950 × 0.9990 = 0.9940
                composite_availability_bound=99.40,
                bottleneck_service="auth-service",
                bottleneck_contribution="auth-service (99.9%) is the sole hard dependency; serial product caps composite bound at 99.40%",
                hard_dependency_count=1,
                soft_dependency_count=1,
            ),
            counterfactuals=[
                CounterfactualApiModel(
                    condition="If auth-service SLO increased from 99.9% to 99.95%",
                    # 0.9950 × 0.9995 = 0.9945 → 99.45%
                    result="Composite availability bound would improve to 99.45%, enabling a tighter SLO target",
                    feature="dependency_stability",
                    original_value=99.40,
                    perturbed_value=99.45,
                ),
                CounterfactualApiModel(
                    condition="If deployment frequency doubled to 2x/week",
                    result="Recommended tier would shift to 'conservative' (99.99%) due to increased change risk",
                    feature="deployment_frequency",
                    original_value=1.0,
                    perturbed_value=2.0,
                ),
            ],
            provenance=DataProvenanceApiModel(
                dependency_graph_version="demo-v1",
                telemetry_window_start=(datetime.now(UTC) - timedelta(days=30)).isoformat(),
                telemetry_window_end=datetime.now(UTC).isoformat(),
                data_completeness=0.95,
                computation_method="monte_carlo_simulation",
                telemetry_source="synthetic_demo_data",
            ),
        ),
        data_quality=DataQualityApiModel(
            data_completeness=0.95,
            telemetry_gaps=[],
            confidence_note="Demo data - synthetically generated for demonstration purposes",
            is_cold_start=False,
            lookback_days_actual=30,
        ),
    )


def _generate_demo_latency_recommendation(
    service_id: str,
) -> RecommendationApiModel:
    """Generate synthetic latency recommendation for demo."""
    return RecommendationApiModel(
        sli_type="latency",
        metric="p99_latency_ms",
        tiers={
            "conservative": TierApiModel(
                level="conservative",
                target=500,
                error_budget_monthly_minutes=None,
                confidence_interval=(480, 520),
                estimated_breach_probability=0.03,
                percentile="p999",
                target_ms=500,
            ),
            "balanced": TierApiModel(
                level="balanced",
                target=200,
                error_budget_monthly_minutes=None,
                confidence_interval=(190, 210),
                estimated_breach_probability=0.07,
                percentile="p99",
                target_ms=200,
            ),
            "aggressive": TierApiModel(
                level="aggressive",
                target=100,
                error_budget_monthly_minutes=None,
                confidence_interval=(95, 105),
                estimated_breach_probability=0.12,
                percentile="p95",
                target_ms=100,
            ),
        },
        explanation=ExplanationApiModel(
            summary=(
                f"Latency recommendation for {service_id} targets p99 latency thresholds. "
                f"Conservative tier (500ms p999) accommodates tail latency with the most headroom. "
                f"Balanced tier (200ms p99) provides good performance with operational flexibility. "
                f"Aggressive tier (100ms p95) targets the tightest latency budget for best user experience."
            ),
            feature_attribution=[
                FeatureAttributionApiModel(
                    feature="p99_baseline",
                    contribution=0.50,
                    description="Current p99 latency averages 180ms over past 30 days",
                ),
                FeatureAttributionApiModel(
                    feature="cache_hit_rate",
                    contribution=0.25,
                    description="85% cache hit rate reduces backend latency",
                ),
                FeatureAttributionApiModel(
                    feature="dependency_latency",
                    contribution=0.15,
                    description="Downstream services contribute ~50ms to request path",
                ),
                FeatureAttributionApiModel(
                    feature="request_complexity",
                    contribution=0.10,
                    description="Average request involves 3 downstream calls",
                ),
            ],
            dependency_impact=None,  # Latency doesn't use composite bounds
            counterfactuals=[
                CounterfactualApiModel(
                    condition="If cache hit rate improved from 85% to 95%",
                    result="p99 latency would decrease to ~150ms, enabling 'conservative' tier",
                    feature="cache_hit_rate",
                    original_value=0.85,
                    perturbed_value=0.95,
                ),
                CounterfactualApiModel(
                    condition="If downstream service latency increased by 50ms",
                    result="p99 latency would increase to ~230ms, requiring 'balanced' tier adjustment",
                    feature="dependency_latency",
                    original_value=50.0,
                    perturbed_value=100.0,
                ),
            ],
            provenance=DataProvenanceApiModel(
                dependency_graph_version="demo-v1",
                telemetry_window_start=(datetime.now(UTC) - timedelta(days=30)).isoformat(),
                telemetry_window_end=datetime.now(UTC).isoformat(),
                data_completeness=0.93,
                computation_method="percentile_estimation",
                telemetry_source="synthetic_demo_data",
            ),
        ),
        data_quality=DataQualityApiModel(
            data_completeness=0.93,
            telemetry_gaps=[],
            confidence_note="Demo data - synthetically generated for demonstration purposes",
            is_cold_start=False,
            lookback_days_actual=30,
        ),
    )


@router.get(
    "/services/{service_id}/slo-recommendations",
    response_model=SloRecommendationApiResponse,
    status_code=status.HTTP_200_OK,
    summary="[DEMO] Get synthetic SLO recommendations",
    description="""
    Demo endpoint that returns synthetic SLO recommendations without requiring telemetry data.

    **DEMO ONLY**: This endpoint returns pre-generated recommendations for demonstration purposes.
    In production, use /api/v1/services/{service_id}/slo-recommendations which analyzes real telemetry.

    This endpoint:
    - Returns availability and/or latency recommendations based on sli_type filter
    - Includes all FR-7 explainability features (feature attribution, counterfactuals, provenance)
    - Does NOT require actual telemetry data collection
    - Perfect for UI development, demos, and integration testing

    **DO NOT USE IN PRODUCTION** - Use /api/v1/services/{service_id}/slo-recommendations instead.
    """,
)
async def demo_get_slo_recommendations(
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
        description="Lookback window in days (cosmetic for demo)",
    ),
) -> SloRecommendationApiResponse:
    """
    Get synthetic SLO recommendations for demo purposes.

    Returns pre-generated recommendations with full explainability features
    without requiring actual telemetry data collection.
    """
    # Generate recommendations based on sli_type filter
    recommendations = []

    if sli_type in ["all", "availability"]:
        recommendations.append(_generate_demo_availability_recommendation(service_id))

    if sli_type in ["all", "latency"]:
        recommendations.append(_generate_demo_latency_recommendation(service_id))

    # Build response
    now = datetime.now(UTC)
    return SloRecommendationApiResponse(
        service_id=service_id,
        generated_at=now.isoformat(),
        lookback_window=LookbackWindowApiModel(
            start=(now - timedelta(days=lookback_days)).isoformat(),
            end=now.isoformat(),
        ),
        recommendations=recommendations,
    )
