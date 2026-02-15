"""
Pydantic schemas for dependency graph API endpoints.

These schemas define the API request/response contracts and provide validation.
They are separate from application layer DTOs (which use dataclasses).
"""

from datetime import datetime

from pydantic import BaseModel, Field


# ============================================================================
# Ingestion Endpoint Schemas
# ============================================================================


class RetryConfigApiModel(BaseModel):
    """Retry configuration for a dependency edge."""

    max_retries: int = Field(..., ge=0, description="Maximum number of retries")
    backoff_strategy: str = Field(
        ..., description="Backoff strategy: exponential, linear, or constant"
    )


class EdgeAttributesApiModel(BaseModel):
    """Attributes for a dependency edge."""

    communication_mode: str = Field(
        ..., description="Communication mode: sync or async"
    )
    criticality: str = Field(
        ..., description="Dependency criticality: hard, soft, or degraded"
    )
    protocol: str | None = Field(None, description="Protocol: grpc, http, kafka, etc.")
    timeout_ms: int | None = Field(None, ge=1, description="Timeout in milliseconds")
    retry_config: RetryConfigApiModel | None = None


class NodeApiModel(BaseModel):
    """A service node in the dependency graph."""

    service_id: str = Field(..., description="Unique service identifier")
    metadata: dict = Field(
        default_factory=dict, description="Service metadata (team, criticality, etc.)"
    )


class EdgeApiModel(BaseModel):
    """An edge in the dependency graph."""

    source: str = Field(..., description="Source service ID")
    target: str = Field(..., description="Target service ID")
    attributes: EdgeAttributesApiModel


class DependencyGraphIngestApiRequest(BaseModel):
    """Request to ingest a dependency graph."""

    source: str = Field(
        ...,
        description="Discovery source: manual, otel_service_graph, kubernetes, service_mesh",
    )
    timestamp: datetime = Field(..., description="When this graph was observed")
    nodes: list[NodeApiModel] = Field(
        default_factory=list, description="Service nodes"
    )
    edges: list[EdgeApiModel] = Field(default_factory=list, description="Dependency edges")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "source": "manual",
                "timestamp": "2026-02-14T10:00:00Z",
                "nodes": [
                    {
                        "service_id": "checkout-service",
                        "metadata": {
                            "team": "payments",
                            "criticality": "high",
                            "tier": 1,
                        },
                    }
                ],
                "edges": [
                    {
                        "source": "checkout-service",
                        "target": "payment-service",
                        "attributes": {
                            "communication_mode": "sync",
                            "criticality": "hard",
                            "protocol": "grpc",
                            "timeout_ms": 5000,
                            "retry_config": {
                                "max_retries": 3,
                                "backoff_strategy": "exponential",
                            },
                        },
                    }
                ],
            }
        }


class CircularDependencyInfoApiModel(BaseModel):
    """Information about a detected circular dependency."""

    cycle_path: list[str] = Field(..., description="Service IDs forming the cycle")
    alert_id: str = Field(..., description="UUID of the created alert")


class ConflictInfoApiModel(BaseModel):
    """Information about a conflict during edge merge."""

    edge: dict = Field(..., description="The edge that had a conflict")
    existing_source: str = Field(
        ..., description="Discovery source of existing edge"
    )
    new_source: str = Field(..., description="Discovery source of new edge")
    resolution: str = Field(..., description="How the conflict was resolved")


class DependencyGraphIngestApiResponse(BaseModel):
    """Response from dependency graph ingestion."""

    ingestion_id: str = Field(..., description="UUID of this ingestion operation")
    status: str = Field(
        ..., description="processing, completed, or failed"
    )
    nodes_received: int = Field(..., description="Number of nodes in request")
    edges_received: int = Field(..., description="Number of edges in request")
    nodes_upserted: int = Field(..., description="Number of nodes upserted")
    edges_upserted: int = Field(..., description="Number of edges upserted")
    circular_dependencies_detected: list[CircularDependencyInfoApiModel] = Field(
        default_factory=list, description="Circular dependencies found"
    )
    conflicts_resolved: list[ConflictInfoApiModel] = Field(
        default_factory=list, description="Conflicts that were resolved"
    )
    warnings: list[str] = Field(default_factory=list, description="Warning messages")
    estimated_completion_seconds: int | None = Field(
        None, description="Estimated seconds until completion (if async)"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "ingestion_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "completed",
                "nodes_received": 150,
                "edges_received": 420,
                "nodes_upserted": 148,
                "edges_upserted": 415,
                "circular_dependencies_detected": [
                    {
                        "cycle_path": [
                            "service-a",
                            "service-b",
                            "service-c",
                            "service-a",
                        ],
                        "alert_id": "660e8400-e29b-41d4-a716-446655440001",
                    }
                ],
                "conflicts_resolved": [
                    {
                        "edge": {"source": "svc-a", "target": "svc-b"},
                        "existing_source": "otel_service_graph",
                        "new_source": "manual",
                        "resolution": "kept_higher_priority",
                    }
                ],
                "warnings": ["3 unknown services auto-created as placeholders"],
                "estimated_completion_seconds": None,
            }
        }


# ============================================================================
# Query Endpoint Schemas
# ============================================================================


class ServiceNodeApiModel(BaseModel):
    """A service node in a subgraph response."""

    service_id: str
    id: str  # UUID
    team: str | None
    criticality: str
    metadata: dict


class DependencyEdgeApiModel(BaseModel):
    """A dependency edge in a subgraph response."""

    source: str
    target: str
    communication_mode: str
    criticality: str
    protocol: str | None
    timeout_ms: int | None
    confidence_score: float
    discovery_source: str
    last_observed_at: datetime
    is_stale: bool


class SubgraphStatisticsApiModel(BaseModel):
    """Statistics about the returned subgraph."""

    total_nodes: int
    total_edges: int
    upstream_services: int
    downstream_services: int
    max_depth_reached: int


class DependencySubgraphApiResponse(BaseModel):
    """Response containing a dependency subgraph."""

    service_id: str
    direction: str
    depth: int
    nodes: list[ServiceNodeApiModel]
    edges: list[DependencyEdgeApiModel]
    statistics: SubgraphStatisticsApiModel

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "service_id": "checkout-service",
                "direction": "both",
                "depth": 3,
                "nodes": [
                    {
                        "service_id": "checkout-service",
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "team": "payments",
                        "criticality": "high",
                        "metadata": {"tier": 1},
                    }
                ],
                "edges": [
                    {
                        "source": "checkout-service",
                        "target": "payment-service",
                        "communication_mode": "sync",
                        "criticality": "hard",
                        "protocol": "grpc",
                        "timeout_ms": 5000,
                        "confidence_score": 0.95,
                        "discovery_source": "otel_service_graph",
                        "last_observed_at": "2026-02-14T09:45:00Z",
                        "is_stale": False,
                    }
                ],
                "statistics": {
                    "total_nodes": 15,
                    "total_edges": 42,
                    "upstream_services": 3,
                    "downstream_services": 11,
                    "max_depth_reached": 3,
                },
            }
        }
