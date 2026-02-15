"""Graph traversal service module.

This module defines the GraphTraversalService for traversing the dependency graph.
"""

from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from src.domain.entities.service import Service
    from src.domain.entities.service_dependency import ServiceDependency
    from src.domain.repositories.dependency_repository import (
        DependencyRepositoryInterface,
    )


class TraversalDirection(str, Enum):
    """Direction for graph traversal."""

    UPSTREAM = "upstream"  # Dependencies that call this service
    DOWNSTREAM = "downstream"  # Dependencies this service calls
    BOTH = "both"


class GraphTraversalService:
    """Domain service for graph traversal operations.

    Uses repository to execute recursive CTE queries.
    """

    async def get_subgraph(
        self,
        service_id: UUID,
        direction: TraversalDirection,
        repository: "DependencyRepositoryInterface",
        max_depth: int = 3,
        include_stale: bool = False,
    ) -> tuple[list["Service"], list["ServiceDependency"]]:
        """Retrieve subgraph starting from service_id.

        Args:
            service_id: Starting point for traversal
            direction: Which edges to follow
            repository: Dependency repository for data access
            max_depth: Maximum traversal depth (default 3, max 10)
            include_stale: Whether to include stale edges

        Returns:
            Tuple of (nodes, edges) in the subgraph

        Raises:
            ValueError: If max_depth > 10 or max_depth < 1
        """
        if max_depth > 10:
            raise ValueError("max_depth cannot exceed 10")

        if max_depth < 1:
            raise ValueError("max_depth must be at least 1")

        # Delegate to repository's recursive CTE implementation
        return await repository.traverse_graph(
            service_id=service_id,
            direction=direction,
            max_depth=max_depth,
            include_stale=include_stale,
        )
