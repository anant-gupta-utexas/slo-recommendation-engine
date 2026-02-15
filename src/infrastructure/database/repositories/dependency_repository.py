"""Dependency repository implementation using PostgreSQL.

This module implements the DependencyRepositoryInterface using SQLAlchemy
with recursive CTEs for efficient graph traversal.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import and_, func, literal_column, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.service import Service
from src.domain.entities.service_dependency import (
    CommunicationMode,
    DependencyCriticality,
    DiscoverySource,
    RetryConfig,
    ServiceDependency,
)
from src.domain.repositories.dependency_repository import (
    DependencyRepositoryInterface,
)
from src.domain.services.graph_traversal_service import TraversalDirection
from src.infrastructure.database.models import (
    ServiceDependencyModel,
    ServiceModel,
)


class DependencyRepository(DependencyRepositoryInterface):
    """PostgreSQL implementation of DependencyRepositoryInterface.

    This repository handles mapping between domain ServiceDependency entities
    and ServiceDependencyModel SQLAlchemy models. Implements efficient graph
    traversal using PostgreSQL recursive CTEs.
    """

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self._session = session

    async def get_by_id(self, dependency_id: UUID) -> ServiceDependency | None:
        """Get dependency by UUID.

        Args:
            dependency_id: Internal UUID of the dependency

        Returns:
            ServiceDependency entity if found, None otherwise
        """
        stmt = select(ServiceDependencyModel).where(
            ServiceDependencyModel.id == dependency_id
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        return self._to_entity(model) if model else None

    async def list_by_source(self, source_service_id: UUID) -> list[ServiceDependency]:
        """Get all outgoing dependencies from a service.

        Args:
            source_service_id: UUID of the source service

        Returns:
            List of ServiceDependency entities where this service is the source
        """
        stmt = (
            select(ServiceDependencyModel)
            .where(ServiceDependencyModel.source_service_id == source_service_id)
            .order_by(ServiceDependencyModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [self._to_entity(model) for model in models]

    async def list_by_target(self, target_service_id: UUID) -> list[ServiceDependency]:
        """Get all incoming dependencies to a service.

        Args:
            target_service_id: UUID of the target service

        Returns:
            List of ServiceDependency entities where this service is the target
        """
        stmt = (
            select(ServiceDependencyModel)
            .where(ServiceDependencyModel.target_service_id == target_service_id)
            .order_by(ServiceDependencyModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [self._to_entity(model) for model in models]

    async def bulk_upsert(
        self, dependencies: list[ServiceDependency]
    ) -> list[ServiceDependency]:
        """Bulk upsert dependencies.

        Inserts new dependencies or updates existing ones based on
        (source, target, discovery_source) unique constraint.

        Args:
            dependencies: List of ServiceDependency entities to upsert

        Returns:
            List of upserted ServiceDependency entities with updated audit fields
        """
        if not dependencies:
            return []

        # Convert dependencies to dictionaries for bulk insert
        values = [self._to_dict(dep) for dep in dependencies]

        # PostgreSQL INSERT ... ON CONFLICT ... DO UPDATE
        stmt = pg_insert(ServiceDependencyModel).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_service_id", "target_service_id", "discovery_source"],
            set_={
                "communication_mode": stmt.excluded.communication_mode,
                "criticality": stmt.excluded.criticality,
                "protocol": stmt.excluded.protocol,
                "timeout_ms": stmt.excluded.timeout_ms,
                "retry_config": stmt.excluded.retry_config,
                "confidence_score": stmt.excluded.confidence_score,
                "last_observed_at": stmt.excluded.last_observed_at,
                "is_stale": stmt.excluded.is_stale,
                "updated_at": stmt.excluded.updated_at,
            },
        ).returning(ServiceDependencyModel)

        result = await self._session.execute(stmt)
        models: Sequence[ServiceDependencyModel] = result.scalars().all()

        return [self._to_entity(model) for model in models]

    async def traverse_graph(
        self,
        service_id: UUID,
        direction: TraversalDirection,
        max_depth: int,
        include_stale: bool,
    ) -> tuple[list[Service], list[ServiceDependency]]:
        """Execute recursive graph traversal using PostgreSQL CTE.

        This method uses a recursive Common Table Expression to efficiently
        traverse the dependency graph starting from service_id.

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
        # Build recursive CTE based on traversal direction
        if direction == TraversalDirection.DOWNSTREAM:
            edges, visited_services = await self._traverse_downstream(
                service_id, max_depth, include_stale
            )
        elif direction == TraversalDirection.UPSTREAM:
            edges, visited_services = await self._traverse_upstream(
                service_id, max_depth, include_stale
            )
        else:  # TraversalDirection.BOTH
            # Execute both traversals and merge results
            downstream_edges, downstream_services = await self._traverse_downstream(
                service_id, max_depth, include_stale
            )
            upstream_edges, upstream_services = await self._traverse_upstream(
                service_id, max_depth, include_stale
            )

            # Merge and deduplicate
            edges = self._merge_edges(downstream_edges, upstream_edges)
            visited_services = list(set(downstream_services + upstream_services))

        # Fetch full service entities for all visited services
        services = await self._fetch_services(visited_services)

        return services, edges

    async def _traverse_downstream(
        self, service_id: UUID, max_depth: int, include_stale: bool
    ) -> tuple[list[ServiceDependency], list[UUID]]:
        """Traverse downstream dependencies (services this service calls).

        Args:
            service_id: Starting service UUID
            max_depth: Maximum traversal depth
            include_stale: Whether to include stale edges

        Returns:
            Tuple of (edges, visited_service_ids)
        """
        # Build recursive CTE for downstream traversal
        # Base case: Direct dependencies
        stale_condition = (
            ServiceDependencyModel.is_stale == False
            if not include_stale
            else literal_column("true")
        )

        base_query = (
            select(
                ServiceDependencyModel,
                literal_column("1").label("depth"),
                func.array([service_id, ServiceDependencyModel.target_service_id]).label(
                    "path"
                ),
            )
            .where(
                and_(
                    ServiceDependencyModel.source_service_id == service_id,
                    stale_condition,
                )
            )
            .cte(name="dependency_tree", recursive=True)
        )

        # Recursive case: Transitive dependencies
        recursive_query = (
            select(
                ServiceDependencyModel,
                (base_query.c.depth + 1).label("depth"),
                func.array_append(base_query.c.path, ServiceDependencyModel.target_service_id).label(
                    "path"
                ),
            )
            .select_from(ServiceDependencyModel)
            .join(
                base_query,
                ServiceDependencyModel.source_service_id
                == base_query.c.target_service_id,
            )
            .where(
                and_(
                    base_query.c.depth < max_depth,
                    stale_condition,
                    # Cycle prevention: target not in path
                    ~ServiceDependencyModel.target_service_id.in_(
                        func.unnest(base_query.c.path)
                    ),
                )
            )
        )

        # Union base and recursive cases
        cte = base_query.union_all(recursive_query)

        # Execute final query
        final_stmt = select(cte).distinct(cte.c.id)
        result = await self._session.execute(final_stmt)

        # Map to entities and extract visited services
        edges = []
        visited_services = [service_id]  # Include starting service

        for row in result:
            model = ServiceDependencyModel(
                id=row.id,
                source_service_id=row.source_service_id,
                target_service_id=row.target_service_id,
                communication_mode=row.communication_mode,
                criticality=row.criticality,
                protocol=row.protocol,
                timeout_ms=row.timeout_ms,
                retry_config=row.retry_config,
                discovery_source=row.discovery_source,
                confidence_score=row.confidence_score,
                last_observed_at=row.last_observed_at,
                is_stale=row.is_stale,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            edges.append(self._to_entity(model))
            visited_services.extend([row.source_service_id, row.target_service_id])

        return edges, list(set(visited_services))

    async def _traverse_upstream(
        self, service_id: UUID, max_depth: int, include_stale: bool
    ) -> tuple[list[ServiceDependency], list[UUID]]:
        """Traverse upstream dependencies (services that call this service).

        Args:
            service_id: Starting service UUID
            max_depth: Maximum traversal depth
            include_stale: Whether to include stale edges

        Returns:
            Tuple of (edges, visited_service_ids)
        """
        # Build recursive CTE for upstream traversal (reverse direction)
        stale_condition = (
            ServiceDependencyModel.is_stale == False
            if not include_stale
            else literal_column("true")
        )

        base_query = (
            select(
                ServiceDependencyModel,
                literal_column("1").label("depth"),
                func.array([ServiceDependencyModel.source_service_id, service_id]).label(
                    "path"
                ),
            )
            .where(
                and_(
                    ServiceDependencyModel.target_service_id == service_id,
                    stale_condition,
                )
            )
            .cte(name="dependency_tree", recursive=True)
        )

        # Recursive case: Transitive dependencies (upstream)
        recursive_query = (
            select(
                ServiceDependencyModel,
                (base_query.c.depth + 1).label("depth"),
                func.array_prepend(ServiceDependencyModel.source_service_id, base_query.c.path).label(
                    "path"
                ),
            )
            .select_from(ServiceDependencyModel)
            .join(
                base_query,
                ServiceDependencyModel.target_service_id
                == base_query.c.source_service_id,
            )
            .where(
                and_(
                    base_query.c.depth < max_depth,
                    stale_condition,
                    # Cycle prevention: source not in path
                    ~ServiceDependencyModel.source_service_id.in_(
                        func.unnest(base_query.c.path)
                    ),
                )
            )
        )

        # Union base and recursive cases
        cte = base_query.union_all(recursive_query)

        # Execute final query
        final_stmt = select(cte).distinct(cte.c.id)
        result = await self._session.execute(final_stmt)

        # Map to entities and extract visited services
        edges = []
        visited_services = [service_id]  # Include starting service

        for row in result:
            model = ServiceDependencyModel(
                id=row.id,
                source_service_id=row.source_service_id,
                target_service_id=row.target_service_id,
                communication_mode=row.communication_mode,
                criticality=row.criticality,
                protocol=row.protocol,
                timeout_ms=row.timeout_ms,
                retry_config=row.retry_config,
                discovery_source=row.discovery_source,
                confidence_score=row.confidence_score,
                last_observed_at=row.last_observed_at,
                is_stale=row.is_stale,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            edges.append(self._to_entity(model))
            visited_services.extend([row.source_service_id, row.target_service_id])

        return edges, list(set(visited_services))

    async def _fetch_services(self, service_ids: list[UUID]) -> list[Service]:
        """Fetch full service entities for given UUIDs.

        Args:
            service_ids: List of service UUIDs to fetch

        Returns:
            List of Service entities
        """
        if not service_ids:
            return []

        stmt = select(ServiceModel).where(ServiceModel.id.in_(service_ids))
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        # Import here to avoid circular import
        from src.domain.entities.service import Criticality

        return [
            Service(
                id=model.id,
                service_id=model.service_id,
                metadata=model.metadata,
                criticality=Criticality(model.criticality),
                team=model.team,
                discovered=model.discovered,
                created_at=model.created_at,
                updated_at=model.updated_at,
            )
            for model in models
        ]

    def _merge_edges(
        self,
        edges1: list[ServiceDependency],
        edges2: list[ServiceDependency],
    ) -> list[ServiceDependency]:
        """Merge and deduplicate edge lists.

        Args:
            edges1: First list of edges
            edges2: Second list of edges

        Returns:
            Deduplicated list of edges
        """
        # Use edge ID for deduplication
        edge_map = {edge.id: edge for edge in edges1}
        for edge in edges2:
            if edge.id not in edge_map:
                edge_map[edge.id] = edge

        return list(edge_map.values())

    async def get_adjacency_list(self) -> dict[UUID, list[UUID]]:
        """Get full graph as adjacency list for cycle detection.

        Returns adjacency list representation of the graph where each
        service maps to a list of its target services. Excludes stale edges.

        Returns:
            Map of source service UUID → list of target service UUIDs
        """
        stmt = (
            select(
                ServiceDependencyModel.source_service_id,
                func.array_agg(ServiceDependencyModel.target_service_id).label("targets"),
            )
            .where(ServiceDependencyModel.is_stale == False)
            .group_by(ServiceDependencyModel.source_service_id)
        )

        result = await self._session.execute(stmt)

        adjacency_list: dict[UUID, list[UUID]] = {}
        for row in result:
            adjacency_list[row.source_service_id] = row.targets

        return adjacency_list

    async def mark_stale_edges(self, staleness_threshold_hours: int = 168) -> int:
        """Mark edges as stale if not observed within threshold.

        Updates is_stale flag for edges where last_observed_at is older
        than the threshold.

        Args:
            staleness_threshold_hours: Threshold in hours (default: 168 = 7 days)

        Returns:
            Number of edges marked as stale
        """
        threshold_time = datetime.now(timezone.utc) - timedelta(
            hours=staleness_threshold_hours
        )

        stmt = (
            update(ServiceDependencyModel)
            .where(
                and_(
                    ServiceDependencyModel.last_observed_at < threshold_time,
                    ServiceDependencyModel.is_stale == False,
                )
            )
            .values(
                is_stale=True,
                updated_at=datetime.now(timezone.utc),
            )
        )

        result = await self._session.execute(stmt)
        return result.rowcount

    def _to_entity(self, model: ServiceDependencyModel) -> ServiceDependency:
        """Convert SQLAlchemy model to domain entity.

        Args:
            model: ServiceDependencyModel instance

        Returns:
            ServiceDependency domain entity
        """
        # Parse retry_config from JSONB if present
        retry_config = None
        if model.retry_config:
            retry_config = RetryConfig(
                max_retries=model.retry_config.get("max_retries", 3),
                backoff_strategy=model.retry_config.get("backoff_strategy", "exponential"),
            )

        return ServiceDependency(
            id=model.id,
            source_service_id=model.source_service_id,
            target_service_id=model.target_service_id,
            communication_mode=CommunicationMode(model.communication_mode),
            criticality=DependencyCriticality(model.criticality),
            protocol=model.protocol,
            timeout_ms=model.timeout_ms,
            retry_config=retry_config,
            discovery_source=DiscoverySource(model.discovery_source),
            confidence_score=model.confidence_score,
            last_observed_at=model.last_observed_at,
            is_stale=model.is_stale,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_dict(self, entity: ServiceDependency) -> dict[str, Any]:
        """Convert domain entity to dictionary for bulk operations.

        Args:
            entity: ServiceDependency domain entity

        Returns:
            Dictionary representation suitable for SQLAlchemy insert
        """
        # Convert retry_config to JSONB dict if present
        retry_config_dict = None
        if entity.retry_config:
            retry_config_dict = {
                "max_retries": entity.retry_config.max_retries,
                "backoff_strategy": entity.retry_config.backoff_strategy,
            }

        return {
            "id": entity.id,
            "source_service_id": entity.source_service_id,
            "target_service_id": entity.target_service_id,
            "communication_mode": entity.communication_mode.value,
            "criticality": entity.criticality.value,
            "protocol": entity.protocol,
            "timeout_ms": entity.timeout_ms,
            "retry_config": retry_config_dict,
            "discovery_source": entity.discovery_source.value,
            "confidence_score": entity.confidence_score,
            "last_observed_at": entity.last_observed_at,
            "is_stale": entity.is_stale,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
        }
