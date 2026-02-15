"""Application layer DTOs.

This package contains data transfer objects (DTOs) for the application layer.
Uses dataclasses (not Pydantic) per Clean Architecture principles.
"""

from src.application.dtos.common import (
    ConflictInfo,
    ErrorDetail,
    SubgraphStatistics,
)
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
    DependencyEdgeDTO,
    DependencySubgraphRequest,
    DependencySubgraphResponse,
    ServiceNodeDTO,
)

__all__ = [
    # Common
    "ErrorDetail",
    "ConflictInfo",
    "SubgraphStatistics",
    # Ingestion
    "RetryConfigDTO",
    "EdgeAttributesDTO",
    "NodeDTO",
    "EdgeDTO",
    "DependencyGraphIngestRequest",
    "CircularDependencyInfo",
    "DependencyGraphIngestResponse",
    # Query
    "DependencySubgraphRequest",
    "ServiceNodeDTO",
    "DependencyEdgeDTO",
    "DependencySubgraphResponse",
]
