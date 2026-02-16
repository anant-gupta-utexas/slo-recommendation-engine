"""Ingest dependency graph use case.

This module implements the use case for ingesting dependency graphs from
various discovery sources.
"""

from uuid import uuid4

from src.application.dtos.dependency_graph_dto import (
    DependencyGraphIngestRequest,
    DependencyGraphIngestResponse,
)
from src.domain.entities.service import Criticality, Service
from src.domain.entities.service_dependency import (
    CommunicationMode,
    DependencyCriticality,
    DiscoverySource,
    RetryConfig,
    ServiceDependency,
)
from src.domain.repositories.dependency_repository import DependencyRepositoryInterface
from src.domain.repositories.service_repository import ServiceRepositoryInterface
from src.domain.services.edge_merge_service import EdgeMergeService


class IngestDependencyGraphUseCase:
    """Use case for ingesting dependency graphs.

    This use case orchestrates the full ingestion workflow:
    1. Validate input DTO
    2. Auto-create unknown services with discovered=true
    3. Merge edges using EdgeMergeService
    4. Bulk upsert services and dependencies
    5. Return response with stats and warnings
    """

    def __init__(
        self,
        service_repository: ServiceRepositoryInterface,
        dependency_repository: DependencyRepositoryInterface,
        edge_merge_service: EdgeMergeService,
    ):
        """Initialize the use case.

        Args:
            service_repository: Repository for service operations
            dependency_repository: Repository for dependency operations
            edge_merge_service: Service for merging edges
        """
        self.service_repository = service_repository
        self.dependency_repository = dependency_repository
        self.edge_merge_service = edge_merge_service

    async def execute(
        self, request: DependencyGraphIngestRequest
    ) -> DependencyGraphIngestResponse:
        """Execute the ingest dependency graph use case.

        Args:
            request: Ingestion request with source, nodes, and edges

        Returns:
            DependencyGraphIngestResponse with stats and warnings

        Raises:
            ValueError: If input validation fails
        """
        ingestion_id = str(uuid4())
        warnings: list[str] = []

        # Validate discovery source
        valid_sources = {"manual", "otel_service_graph", "kubernetes", "service_mesh"}
        if request.source not in valid_sources:
            raise ValueError(
                f"source must be one of {valid_sources}, got: {request.source}"
            )

        # Map discovery source string to enum
        source_map = {
            "manual": DiscoverySource.MANUAL,
            "otel_service_graph": DiscoverySource.OTEL_SERVICE_GRAPH,
            "kubernetes": DiscoverySource.KUBERNETES,
            "service_mesh": DiscoverySource.SERVICE_MESH,
        }
        discovery_source = source_map[request.source]

        # Step 1: Convert NodeDTOs to Service entities
        services_to_upsert: list[Service] = []
        service_id_map: dict[str, Service] = {}  # service_id -> Service entity

        for node_dto in request.nodes:
            # Validate and map criticality
            criticality = self._map_criticality(node_dto.criticality)

            service = Service(
                service_id=node_dto.service_id,
                metadata=node_dto.metadata,
                criticality=criticality,
                team=node_dto.team,
                discovered=False,  # Explicitly provided nodes are not discovered
            )

            services_to_upsert.append(service)
            service_id_map[node_dto.service_id] = service

        # Step 2: Identify unknown services referenced in edges
        unknown_service_ids = set()

        for edge_dto in request.edges:
            if edge_dto.source not in service_id_map:
                unknown_service_ids.add(edge_dto.source)
            if edge_dto.target not in service_id_map:
                unknown_service_ids.add(edge_dto.target)

        # Step 3: Auto-create placeholder services for unknown references
        for unknown_id in unknown_service_ids:
            service = Service(
                service_id=unknown_id,
                metadata={"source": "auto_discovered"},
                criticality=Criticality.MEDIUM,
                team=None,
                discovered=True,
            )
            services_to_upsert.append(service)
            service_id_map[unknown_id] = service

        if unknown_service_ids:
            warnings.append(
                f"{len(unknown_service_ids)} unknown services auto-created "
                "as placeholders"
            )

        # Step 4: Bulk upsert services
        upserted_services = await self.service_repository.bulk_upsert(
            services_to_upsert
        )

        # Build UUID lookup: service_id -> UUID
        service_uuid_map: dict[str, str] = {
            svc.service_id: svc.id for svc in upserted_services
        }

        # Step 5: Convert EdgeDTOs to ServiceDependency entities
        new_dependencies: list[ServiceDependency] = []

        for edge_dto in request.edges:
            source_uuid = service_uuid_map[edge_dto.source]
            target_uuid = service_uuid_map[edge_dto.target]

            # Validate and map communication mode
            comm_mode = self._map_communication_mode(
                edge_dto.attributes.communication_mode
            )

            # Validate and map dependency criticality
            dep_criticality = self._map_dependency_criticality(
                edge_dto.attributes.criticality
            )

            # Map retry config if provided
            retry_config = None
            if edge_dto.attributes.retry_config:
                retry_config = RetryConfig(
                    max_retries=edge_dto.attributes.retry_config.max_retries,
                    backoff_strategy=edge_dto.attributes.retry_config.backoff_strategy,
                )

            # Compute confidence score
            confidence_score = self.edge_merge_service.compute_confidence_score(
                source=discovery_source, observation_count=1
            )

            dependency = ServiceDependency(
                source_service_id=source_uuid,
                target_service_id=target_uuid,
                communication_mode=comm_mode,
                criticality=dep_criticality,
                protocol=edge_dto.attributes.protocol,
                timeout_ms=edge_dto.attributes.timeout_ms,
                retry_config=retry_config,
                discovery_source=discovery_source,
                confidence_score=confidence_score,
                last_observed_at=request.timestamp,
            )

            new_dependencies.append(dependency)

        # Step 6: Bulk upsert dependencies (ON CONFLICT handles merging)
        # Note: For MVP, database ON CONFLICT handles edge merging.
        # Full conflict resolution with EdgeMergeService deferred to Phase 4.
        upserted_deps = await self.dependency_repository.bulk_upsert(new_dependencies)

        # Simplified: No conflicts tracked in MVP (ON CONFLICT UPDATE in DB)
        conflicts: list[dict] = []

        # Step 7: Build response
        response = DependencyGraphIngestResponse(
            ingestion_id=ingestion_id,
            status="completed",
            nodes_received=len(request.nodes),
            edges_received=len(request.edges),
            nodes_upserted=len(upserted_services),
            edges_upserted=len(upserted_deps),
            circular_dependencies_detected=[],  # Will be populated by background task
            conflicts_resolved=[],  # Simplified for MVP - DB handles conflicts
            warnings=warnings,
            estimated_completion_seconds=0,  # Synchronous for MVP
        )

        return response

    def _map_criticality(self, criticality_str: str) -> Criticality:
        """Map criticality string to enum.

        Args:
            criticality_str: Criticality as string

        Returns:
            Criticality enum value

        Raises:
            ValueError: If criticality is invalid
        """
        criticality_map = {
            "critical": Criticality.CRITICAL,
            "high": Criticality.HIGH,
            "medium": Criticality.MEDIUM,
            "low": Criticality.LOW,
        }

        if criticality_str not in criticality_map:
            raise ValueError(
                f"criticality must be one of {list(criticality_map.keys())}, "
                f"got: {criticality_str}"
            )

        return criticality_map[criticality_str]

    def _map_communication_mode(self, mode_str: str) -> CommunicationMode:
        """Map communication mode string to enum.

        Args:
            mode_str: Communication mode as string

        Returns:
            CommunicationMode enum value

        Raises:
            ValueError: If mode is invalid
        """
        mode_map = {
            "sync": CommunicationMode.SYNC,
            "async": CommunicationMode.ASYNC,
        }

        if mode_str not in mode_map:
            raise ValueError(
                f"communication_mode must be one of {list(mode_map.keys())}, "
                f"got: {mode_str}"
            )

        return mode_map[mode_str]

    def _map_dependency_criticality(
        self, criticality_str: str
    ) -> DependencyCriticality:
        """Map dependency criticality string to enum.

        Args:
            criticality_str: Dependency criticality as string

        Returns:
            DependencyCriticality enum value

        Raises:
            ValueError: If criticality is invalid
        """
        criticality_map = {
            "hard": DependencyCriticality.HARD,
            "soft": DependencyCriticality.SOFT,
            "degraded": DependencyCriticality.DEGRADED,
        }

        if criticality_str not in criticality_map:
            raise ValueError(
                f"dependency criticality must be one of "
                f"{list(criticality_map.keys())}, got: {criticality_str}"
            )

        return criticality_map[criticality_str]

