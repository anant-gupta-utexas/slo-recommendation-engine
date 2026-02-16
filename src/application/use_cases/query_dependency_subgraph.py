"""Query dependency subgraph use case.

This module implements the use case for querying dependency subgraphs.
"""

from uuid import UUID

from src.application.dtos.common import SubgraphStatistics
from src.application.dtos.dependency_subgraph_dto import (
    DependencyEdgeDTO,
    DependencySubgraphRequest,
    DependencySubgraphResponse,
    ServiceNodeDTO,
)
from src.domain.repositories.dependency_repository import DependencyRepositoryInterface
from src.domain.repositories.service_repository import ServiceRepositoryInterface
from src.domain.services.graph_traversal_service import (
    GraphTraversalService,
    TraversalDirection,
)


class QueryDependencySubgraphUseCase:
    """Use case for querying dependency subgraphs.

    This use case orchestrates the workflow for retrieving a dependency subgraph
    starting from a given service.
    """

    def __init__(
        self,
        service_repository: ServiceRepositoryInterface,
        dependency_repository: DependencyRepositoryInterface,
        graph_traversal_service: GraphTraversalService,
    ):
        """Initialize the use case.

        Args:
            service_repository: Repository for service operations
            dependency_repository: Repository for dependency operations
            graph_traversal_service: Service for graph traversal
        """
        self.service_repository = service_repository
        self.dependency_repository = dependency_repository
        self.graph_traversal_service = graph_traversal_service

    async def execute(
        self, request: DependencySubgraphRequest
    ) -> DependencySubgraphResponse | None:
        """Execute the query dependency subgraph use case.

        Args:
            request: Query request with service_id, direction, depth

        Returns:
            DependencySubgraphResponse if service exists, None otherwise

        Raises:
            ValueError: If depth is invalid (not in range 1-10)
        """
        # Validate depth
        if not (1 <= request.depth <= 10):
            raise ValueError(
                f"depth must be between 1 and 10, got: {request.depth}"
            )

        # Validate direction
        valid_directions = {"upstream", "downstream", "both"}
        if request.direction not in valid_directions:
            raise ValueError(
                f"direction must be one of {valid_directions}, "
                f"got: {request.direction}"
            )

        # Get the service by service_id (business identifier)
        service = await self.service_repository.get_by_service_id(request.service_id)
        if not service:
            return None

        # Map string direction to TraversalDirection enum
        direction_map = {
            "upstream": TraversalDirection.UPSTREAM,
            "downstream": TraversalDirection.DOWNSTREAM,
            "both": TraversalDirection.BOTH,
        }
        direction = direction_map[request.direction]

        # Call graph traversal service
        nodes, edges = await self.graph_traversal_service.get_subgraph(
            service_id=service.id,
            direction=direction,
            repository=self.dependency_repository,
            max_depth=request.depth,
            include_stale=request.include_stale,
        )

        # Ensure the root service is always included in the results
        root_in_nodes = any(n.id == service.id for n in nodes)
        if not root_in_nodes:
            nodes = [service] + list(nodes)

        # Map domain entities to DTOs
        node_dtos = [
            ServiceNodeDTO(
                service_id=node.service_id,
                id=str(node.id),
                team=node.team,
                criticality=node.criticality.value,
                metadata=node.metadata,
            )
            for node in nodes
        ]

        edge_dtos = [
            DependencyEdgeDTO(
                source=self._get_service_id_from_uuid(edge.source_service_id, nodes),
                target=self._get_service_id_from_uuid(edge.target_service_id, nodes),
                communication_mode=edge.communication_mode.value,
                criticality=edge.criticality.value,
                protocol=edge.protocol,
                timeout_ms=edge.timeout_ms,
                confidence_score=edge.confidence_score,
                discovery_source=edge.discovery_source.value,
                last_observed_at=edge.last_observed_at,
                is_stale=edge.is_stale,
            )
            for edge in edges
        ]

        # Compute statistics: count unique services excluding the starting service
        upstream_count = 0
        downstream_count = 0

        # Collect unique upstream and downstream service IDs from edges
        upstream_service_ids: set[str] = set()
        downstream_service_ids: set[str] = set()

        for edge in edges:
            source_id = self._get_service_id_from_uuid(
                edge.source_service_id, nodes
            )
            target_id = self._get_service_id_from_uuid(
                edge.target_service_id, nodes
            )

            if request.direction in ("downstream", "both"):
                # Target services in edges are downstream
                if target_id != request.service_id:
                    downstream_service_ids.add(target_id)
            if request.direction in ("upstream", "both"):
                # Source services in edges are upstream
                if source_id != request.service_id:
                    upstream_service_ids.add(source_id)

        upstream_count = len(upstream_service_ids)
        downstream_count = len(downstream_service_ids)

        statistics = SubgraphStatistics(
            total_nodes=len(nodes),
            total_edges=len(edges),
            upstream_services=upstream_count,
            downstream_services=downstream_count,
            max_depth_reached=request.depth,
        )

        return DependencySubgraphResponse(
            service_id=request.service_id,
            direction=request.direction,
            depth=request.depth,
            nodes=node_dtos,
            edges=edge_dtos,
            statistics=statistics,
        )

    def _get_service_id_from_uuid(self, uuid: UUID, nodes: list) -> str:
        """Helper to get service_id from UUID.

        Args:
            uuid: Service UUID
            nodes: List of Service entities

        Returns:
            Service business identifier
        """
        for node in nodes:
            if node.id == uuid:
                return node.service_id
        return str(uuid)  # Fallback if not found
