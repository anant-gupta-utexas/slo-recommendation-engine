"""Dependency subgraph query DTOs.

This module defines data transfer objects for querying dependency subgraphs.
Uses dataclasses for application layer.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from src.application.dtos.common import SubgraphStatistics


@dataclass
class DependencySubgraphRequest:
    """Request to query a dependency subgraph.

    Attributes:
        service_id: Service identifier to start traversal from
        direction: Direction to traverse (upstream/downstream/both)
        depth: Maximum depth to traverse (1-10)
        include_stale: Whether to include stale edges
        include_external: Whether to include external services (not used in MVP)
    """

    service_id: str
    direction: str = "both"
    depth: int = 3
    include_stale: bool = False
    include_external: bool = True


@dataclass
class ServiceNodeDTO:
    """Service node in a subgraph response.

    Attributes:
        service_id: Business identifier
        id: Internal UUID
        team: Owning team
        criticality: Service criticality level
        metadata: Additional metadata
    """

    service_id: str
    id: str
    team: str | None
    criticality: str
    metadata: dict[str, Any]


@dataclass
class DependencyEdgeDTO:
    """Dependency edge in a subgraph response.

    Attributes:
        source: Source service identifier
        target: Target service identifier
        communication_mode: How services communicate (sync/async)
        criticality: Dependency criticality (hard/soft/degraded)
        protocol: Communication protocol
        timeout_ms: Timeout in milliseconds
        confidence_score: Confidence in this dependency (0.0-1.0)
        discovery_source: How this dependency was discovered
        last_observed_at: Last time this dependency was observed
        is_stale: Whether this dependency is stale
    """

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


@dataclass
class DependencySubgraphResponse:
    """Response containing a dependency subgraph.

    Attributes:
        service_id: Service identifier that was queried
        direction: Direction of traversal
        depth: Depth of traversal
        nodes: List of service nodes in the subgraph
        edges: List of dependency edges in the subgraph
        statistics: Subgraph statistics
    """

    service_id: str
    direction: str
    depth: int
    nodes: list[ServiceNodeDTO]
    edges: list[DependencyEdgeDTO]
    statistics: SubgraphStatistics
