"""
Dependency graph API routes.

Implements the REST API for dependency graph ingestion and querying.
"""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.application.dtos.common import ConflictInfo
from src.application.dtos.dependency_graph_dto import (
    CircularDependencyInfo,
    DependencyGraphIngestRequest,
    DependencyGraphIngestResponse,
    EdgeAttributesDTO,
    EdgeDTO,
    NodeDTO,
    RetryConfigDTO,
)
from src.application.dtos.dependency_subgraph_dto import (
    DependencySubgraphRequest,
)
from src.application.use_cases.ingest_dependency_graph import (
    IngestDependencyGraphUseCase,
)
from src.application.use_cases.query_dependency_subgraph import (
    QueryDependencySubgraphUseCase,
)
from src.infrastructure.api.dependencies import (
    get_ingest_dependency_graph_use_case,
    get_query_dependency_subgraph_use_case,
)
from src.infrastructure.api.middleware.auth import verify_api_key
from src.infrastructure.api.schemas.dependency_schema import (
    CircularDependencyInfoApiModel,
    ConflictInfoApiModel,
    DependencyGraphIngestApiRequest,
    DependencyGraphIngestApiResponse,
    DependencySubgraphApiResponse,
    DependencyEdgeApiModel,
    ServiceNodeApiModel,
    SubgraphStatisticsApiModel,
)
from src.infrastructure.api.schemas.error_schema import ProblemDetails

router = APIRouter()


@router.post(
    "/dependencies",
    response_model=DependencyGraphIngestApiResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest dependency graph",
    description="Bulk upsert of dependency graph (nodes + edges) from various discovery sources",
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
async def ingest_dependencies(
    request: DependencyGraphIngestApiRequest,
    use_case: IngestDependencyGraphUseCase = Depends(
        get_ingest_dependency_graph_use_case
    ),
    current_user: str = Depends(verify_api_key),
) -> DependencyGraphIngestApiResponse:
    """
    Ingest a dependency graph from a discovery source.

    This endpoint accepts a complete dependency graph (nodes and edges) and:
    - Upserts services (auto-creates placeholders for unknown services)
    - Upserts dependency edges with conflict resolution
    - Detects circular dependencies using Tarjan's algorithm
    - Returns detailed statistics and warnings

    **Rate Limit:** 10 requests/minute per API key
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

        # Execute use case
        result = await use_case.execute(app_request)

        # Convert application DTOs to API models
        return DependencyGraphIngestApiResponse(
            ingestion_id=str(result.ingestion_id),
            status=result.status,
            nodes_received=result.nodes_received,
            edges_received=result.edges_received,
            nodes_upserted=result.nodes_upserted,
            edges_upserted=result.edges_upserted,
            circular_dependencies_detected=[
                CircularDependencyInfoApiModel(
                    cycle_path=cd.cycle_path, alert_id=str(cd.alert_id)
                )
                for cd in result.circular_dependencies_detected
            ],
            conflicts_resolved=[
                ConflictInfoApiModel(
                    edge=c.edge,
                    existing_source=c.existing_source,
                    new_source=c.new_source,
                    resolution=c.resolution,
                )
                for c in result.conflicts_resolved
            ],
            warnings=result.warnings,
            estimated_completion_seconds=result.estimated_completion_seconds,
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


@router.get(
    "/{service_id}/dependencies",
    response_model=DependencySubgraphApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Query dependency subgraph",
    description="Retrieve the dependency subgraph for a service (upstream/downstream/both)",
    responses={
        200: {"description": "Subgraph retrieved successfully"},
        400: {"model": ProblemDetails, "description": "Invalid query parameters"},
        401: {"model": ProblemDetails, "description": "Missing or invalid API key"},
        404: {"model": ProblemDetails, "description": "Service not found"},
        429: {"model": ProblemDetails, "description": "Rate limit exceeded"},
        500: {"model": ProblemDetails, "description": "Internal server error"},
    },
)
async def query_dependencies(
    service_id: str,
    direction: str = Query(
        "both",
        description="Traversal direction: upstream, downstream, or both",
        pattern="^(upstream|downstream|both)$",
    ),
    depth: int = Query(
        3,
        description="Maximum traversal depth (1-10)",
        ge=1,
        le=10,
    ),
    include_stale: bool = Query(
        False,
        description="Include stale edges (not observed recently)",
    ),
    use_case: QueryDependencySubgraphUseCase = Depends(
        get_query_dependency_subgraph_use_case
    ),
    current_user: str = Depends(verify_api_key),
) -> DependencySubgraphApiResponse:
    """
    Query the dependency subgraph for a service.

    This endpoint performs graph traversal starting from the specified service and returns:
    - All nodes (services) in the subgraph up to the specified depth
    - All edges (dependencies) between those nodes
    - Statistics about the subgraph (counts, depth reached)

    **Traversal Directions:**
    - `upstream`: Services that call this service (incoming dependencies)
    - `downstream`: Services that this service calls (outgoing dependencies)
    - `both`: Both upstream and downstream

    **Rate Limit:** 60 requests/minute per API key
    **Performance:** Target p95 < 500ms for cached queries
    """
    try:
        # Create application DTO
        app_request = DependencySubgraphRequest(
            service_id=service_id,
            direction=direction,
            depth=depth,
            include_stale=include_stale,
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
        return DependencySubgraphApiResponse(
            service_id=result.service_id,
            direction=result.direction,
            depth=result.depth,
            nodes=[
                ServiceNodeApiModel(
                    service_id=node.service_id,
                    id=str(node.id),
                    team=node.team,
                    criticality=node.criticality,
                    metadata=node.metadata,
                )
                for node in result.nodes
            ],
            edges=[
                DependencyEdgeApiModel(
                    source=edge.source,
                    target=edge.target,
                    communication_mode=edge.communication_mode,
                    criticality=edge.criticality,
                    protocol=edge.protocol,
                    timeout_ms=edge.timeout_ms,
                    confidence_score=edge.confidence_score,
                    discovery_source=edge.discovery_source,
                    last_observed_at=edge.last_observed_at,
                    is_stale=edge.is_stale,
                )
                for edge in result.edges
            ],
            statistics=SubgraphStatisticsApiModel(
                total_nodes=result.statistics.total_nodes,
                total_edges=result.statistics.total_edges,
                upstream_services=result.statistics.upstream_services,
                downstream_services=result.statistics.downstream_services,
                max_depth_reached=result.statistics.max_depth_reached,
            ),
        )
    except HTTPException:
        raise
    except ValueError as e:
        # Domain validation error (e.g., depth > 10)
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
