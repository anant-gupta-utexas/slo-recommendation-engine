"""Dependency repository interface module.

This module defines the abstract interface for ServiceDependency operations.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from src.domain.entities.service import Service
    from src.domain.entities.service_dependency import ServiceDependency
    from src.domain.services.graph_traversal_service import TraversalDirection


class DependencyRepositoryInterface(ABC):
    """Repository interface for ServiceDependency operations.

    This interface defines the contract for persisting and querying
    dependency graph data. Implementations should handle database-specific
    details including recursive CTE queries for graph traversal.
    """

    @abstractmethod
    async def get_by_id(self, dependency_id: UUID) -> "ServiceDependency | None":
        """Get dependency by UUID.

        Args:
            dependency_id: Internal UUID of the dependency

        Returns:
            ServiceDependency entity if found, None otherwise
        """
        pass

    @abstractmethod
    async def list_by_source(
        self, source_service_id: UUID
    ) -> list["ServiceDependency"]:
        """Get all outgoing dependencies from a service.

        Args:
            source_service_id: UUID of the source service

        Returns:
            List of ServiceDependency entities where this service is the source
        """
        pass

    @abstractmethod
    async def list_by_target(
        self, target_service_id: UUID
    ) -> list["ServiceDependency"]:
        """Get all incoming dependencies to a service.

        Args:
            target_service_id: UUID of the target service

        Returns:
            List of ServiceDependency entities where this service is the target
        """
        pass

    @abstractmethod
    async def bulk_upsert(
        self, dependencies: list["ServiceDependency"]
    ) -> list["ServiceDependency"]:
        """Bulk upsert dependencies.

        Inserts new dependencies or updates existing ones based on
        (source, target, discovery_source) unique constraint.

        Args:
            dependencies: List of ServiceDependency entities to upsert

        Returns:
            List of upserted ServiceDependency entities with updated audit fields
        """
        pass

    @abstractmethod
    async def traverse_graph(
        self,
        service_id: UUID,
        direction: "TraversalDirection",
        max_depth: int,
        include_stale: bool,
    ) -> tuple[list["Service"], list["ServiceDependency"]]:
        """Execute recursive graph traversal using PostgreSQL CTE.

        This method should use a recursive Common Table Expression to
        efficiently traverse the dependency graph starting from service_id.

        Args:
            service_id: Starting service UUID for traversal
            direction: Direction to traverse (upstream/downstream/both)
            max_depth: Maximum depth to traverse (1-10)
            include_stale: Whether to include stale edges in traversal

        Returns:
            Tuple of (nodes, edges) in the subgraph:
            - nodes: List of Service entities in the subgraph
            - edges: List of ServiceDependency entities in the subgraph
        """
        pass

    @abstractmethod
    async def get_adjacency_list(self) -> dict[UUID, list[UUID]]:
        """Get full graph as adjacency list for cycle detection.

        Returns adjacency list representation of the graph where each
        service maps to a list of its target services. Excludes stale edges.

        Returns:
            Map of source service UUID → list of target service UUIDs

        Example:
            {
                UUID('service-a-uuid'): [UUID('service-b-uuid'), UUID('service-c-uuid')],
                UUID('service-b-uuid'): [UUID('service-c-uuid')],
                UUID('service-c-uuid'): []
            }
        """
        pass

    @abstractmethod
    async def mark_stale_edges(self, staleness_threshold_hours: int = 168) -> int:
        """Mark edges as stale if not observed within threshold.

        Updates is_stale flag for edges where last_observed_at is older
        than the threshold.

        Args:
            staleness_threshold_hours: Threshold in hours (default: 168 = 7 days)

        Returns:
            Number of edges marked as stale
        """
        pass
