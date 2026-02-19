"""
Demo-specific API routes.

IMPORTANT: These routes are for demonstration purposes only and should NOT be
enabled in production. They provide enhanced responses with simulated data
to showcase features that may run asynchronously in production.
"""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.dtos.dependency_graph_dto import (
    CircularDependencyInfo,
    DependencyGraphIngestRequest,
    DependencyGraphIngestResponse,
    EdgeAttributesDTO,
    EdgeDTO,
    NodeDTO,
    RetryConfigDTO,
)
from src.domain.entities.circular_dependency_alert import AlertStatus
from src.application.use_cases.detect_circular_dependencies import (
    DetectCircularDependenciesUseCase,
)
from src.application.use_cases.ingest_dependency_graph import (
    IngestDependencyGraphUseCase,
)
from src.infrastructure.api.dependencies import (
    get_circular_dependency_alert_repository,
    get_detect_circular_dependencies_use_case,
    get_ingest_dependency_graph_use_case,
)
from src.infrastructure.database.repositories.circular_dependency_alert_repository import (
    CircularDependencyAlertRepository,
)
from src.infrastructure.api.middleware.auth import verify_api_key
from src.infrastructure.api.schemas.dependency_schema import (
    CircularDependencyInfoApiModel,
    ConflictInfoApiModel,
    DependencyGraphIngestApiRequest,
    DependencyGraphIngestApiResponse,
)
from src.infrastructure.api.schemas.error_schema import ProblemDetails

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
