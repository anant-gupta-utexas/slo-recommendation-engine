"""Dependency graph ingestion DTOs.

This module defines data transfer objects for dependency graph ingestion workflows.
Uses dataclasses for application layer (not Pydantic - that's for infrastructure/API).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RetryConfigDTO:
    """Retry configuration for a dependency.

    Attributes:
        max_retries: Maximum number of retry attempts
        backoff_strategy: Strategy for retry backoff (exponential, linear, constant)
    """

    max_retries: int = 3
    backoff_strategy: str = "exponential"


@dataclass
class EdgeAttributesDTO:
    """Attributes for a dependency edge.

    Attributes:
        communication_mode: How services communicate (sync/async)
        criticality: How critical this dependency is (hard/soft/degraded)
        protocol: Communication protocol (grpc, http, kafka, etc.)
        timeout_ms: Timeout in milliseconds
        retry_config: Retry configuration
    """

    communication_mode: str  # sync or async
    criticality: str = "hard"  # hard, soft, or degraded
    protocol: str | None = None
    timeout_ms: int | None = None
    retry_config: RetryConfigDTO | None = None


@dataclass
class NodeDTO:
    """Service node in the dependency graph.

    Attributes:
        service_id: Business identifier (e.g., "checkout-service")
        metadata: Additional service metadata
        team: Owning team identifier
        criticality: Service criticality level (critical/high/medium/low)
    """

    service_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    team: str | None = None
    criticality: str = "medium"


@dataclass
class EdgeDTO:
    """Dependency edge in the graph.

    Attributes:
        source: Source service identifier
        target: Target service identifier
        attributes: Edge attributes (communication mode, criticality, etc.)
    """

    source: str
    target: str
    attributes: EdgeAttributesDTO


@dataclass
class DependencyGraphIngestRequest:
    """Request to ingest a dependency graph.

    Attributes:
        source: Discovery source (manual, otel_service_graph, kubernetes, service_mesh)
        timestamp: Timestamp when the graph was observed
        nodes: List of service nodes
        edges: List of dependency edges
    """

    source: str
    timestamp: datetime
    nodes: list[NodeDTO]
    edges: list[EdgeDTO]


@dataclass
class CircularDependencyInfo:
    """Information about a detected circular dependency.

    Attributes:
        cycle_path: List of service identifiers forming the cycle
        alert_id: UUID of the created alert
    """

    cycle_path: list[str]
    alert_id: str


@dataclass
class DependencyGraphIngestResponse:
    """Response from dependency graph ingestion.

    Attributes:
        ingestion_id: UUID of the ingestion operation
        status: Status of ingestion (processing/completed/failed)
        nodes_received: Number of nodes in the request
        edges_received: Number of edges in the request
        nodes_upserted: Number of nodes actually upserted
        edges_upserted: Number of edges actually upserted
        circular_dependencies_detected: List of detected circular dependencies
        conflicts_resolved: List of conflicts that were resolved
        warnings: List of warning messages
        estimated_completion_seconds: Estimated time to completion (for async)
    """

    ingestion_id: str
    status: str
    nodes_received: int
    edges_received: int
    nodes_upserted: int
    edges_upserted: int
    circular_dependencies_detected: list[CircularDependencyInfo] = field(
        default_factory=list
    )
    conflicts_resolved: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    estimated_completion_seconds: int = 0
