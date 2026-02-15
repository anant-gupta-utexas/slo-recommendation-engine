"""Integration tests for DependencyRepository.

This module tests the DependencyRepository implementation against
a real PostgreSQL database, including critical recursive CTE graph traversal.
"""

import time
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.service import Criticality, Service
from src.domain.entities.service_dependency import (
    CommunicationMode,
    DependencyCriticality,
    DiscoverySource,
    RetryConfig,
    ServiceDependency,
)
from src.domain.services.graph_traversal_service import TraversalDirection
from src.infrastructure.database.repositories.dependency_repository import (
    DependencyRepository,
)
from src.infrastructure.database.repositories.service_repository import (
    ServiceRepository,
)


@pytest.mark.integration
class TestDependencyRepository:
    """Integration tests for DependencyRepository."""

    @pytest.fixture
    def service_repo(self, db_session: AsyncSession) -> ServiceRepository:
        """Create ServiceRepository instance for testing.

        Args:
            db_session: Database session fixture

        Returns:
            ServiceRepository instance
        """
        return ServiceRepository(db_session)

    @pytest.fixture
    def repository(self, db_session: AsyncSession) -> DependencyRepository:
        """Create DependencyRepository instance for testing.

        Args:
            db_session: Database session fixture

        Returns:
            DependencyRepository instance
        """
        return DependencyRepository(db_session)

    @pytest.fixture
    async def sample_services(
        self, service_repo: ServiceRepository
    ) -> dict[str, Service]:
        """Create sample services for testing.

        Args:
            service_repo: ServiceRepository instance

        Returns:
            Dictionary mapping service names to Service entities
        """
        services = {
            "api-gateway": Service(
                service_id="api-gateway",
                criticality=Criticality.CRITICAL,
                team="platform",
            ),
            "auth-service": Service(
                service_id="auth-service",
                criticality=Criticality.HIGH,
                team="security",
            ),
            "user-service": Service(
                service_id="user-service",
                criticality=Criticality.HIGH,
                team="users",
            ),
            "order-service": Service(
                service_id="order-service",
                criticality=Criticality.HIGH,
                team="orders",
            ),
            "payment-service": Service(
                service_id="payment-service",
                criticality=Criticality.CRITICAL,
                team="payments",
            ),
        }

        # Create all services
        created_services = {}
        for name, service in services.items():
            created = await service_repo.create(service)
            created_services[name] = created

        return created_services

    async def test_create_dependency(
        self,
        repository: DependencyRepository,
        sample_services: dict[str, Service],
    ):
        """Test creating a new dependency.

        Args:
            repository: DependencyRepository instance
            sample_services: Sample services
        """
        # Arrange
        dependency = ServiceDependency(
            source_service_id=sample_services["api-gateway"].id,
            target_service_id=sample_services["auth-service"].id,
            communication_mode=CommunicationMode.SYNC,
            criticality=DependencyCriticality.HARD,
            protocol="grpc",
            timeout_ms=5000,
            retry_config=RetryConfig(max_retries=3, backoff_strategy="exponential"),
            discovery_source=DiscoverySource.MANUAL,
            confidence_score=1.0,
        )

        # Act
        result = await repository.bulk_upsert([dependency])

        # Assert
        assert len(result) == 1
        created = result[0]
        assert created.id is not None
        assert created.source_service_id == sample_services["api-gateway"].id
        assert created.target_service_id == sample_services["auth-service"].id
        assert created.communication_mode == CommunicationMode.SYNC
        assert created.protocol == "grpc"
        assert created.timeout_ms == 5000
        assert created.retry_config is not None
        assert created.retry_config.max_retries == 3

    async def test_get_by_id(
        self,
        repository: DependencyRepository,
        sample_services: dict[str, Service],
    ):
        """Test retrieving a dependency by UUID.

        Args:
            repository: DependencyRepository instance
            sample_services: Sample services
        """
        # Arrange
        dependency = ServiceDependency(
            source_service_id=sample_services["api-gateway"].id,
            target_service_id=sample_services["user-service"].id,
            communication_mode=CommunicationMode.SYNC,
        )
        created = (await repository.bulk_upsert([dependency]))[0]

        # Act
        retrieved = await repository.get_by_id(created.id)

        # Assert
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.source_service_id == created.source_service_id
        assert retrieved.target_service_id == created.target_service_id

    async def test_get_by_id_not_found(self, repository: DependencyRepository):
        """Test that get_by_id returns None for non-existent dependency.

        Args:
            repository: DependencyRepository instance
        """
        # Act
        result = await repository.get_by_id(uuid4())

        # Assert
        assert result is None

    async def test_list_by_source(
        self,
        repository: DependencyRepository,
        sample_services: dict[str, Service],
    ):
        """Test listing outgoing dependencies from a service.

        Args:
            repository: DependencyRepository instance
            sample_services: Sample services
        """
        # Arrange - Create dependencies from api-gateway
        dependencies = [
            ServiceDependency(
                source_service_id=sample_services["api-gateway"].id,
                target_service_id=sample_services["auth-service"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
            ServiceDependency(
                source_service_id=sample_services["api-gateway"].id,
                target_service_id=sample_services["user-service"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
            ServiceDependency(
                source_service_id=sample_services["user-service"].id,
                target_service_id=sample_services["auth-service"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
        ]
        await repository.bulk_upsert(dependencies)

        # Act
        result = await repository.list_by_source(sample_services["api-gateway"].id)

        # Assert
        assert len(result) == 2
        target_ids = {dep.target_service_id for dep in result}
        assert sample_services["auth-service"].id in target_ids
        assert sample_services["user-service"].id in target_ids

    async def test_list_by_target(
        self,
        repository: DependencyRepository,
        sample_services: dict[str, Service],
    ):
        """Test listing incoming dependencies to a service.

        Args:
            repository: DependencyRepository instance
            sample_services: Sample services
        """
        # Arrange - Create dependencies to auth-service
        dependencies = [
            ServiceDependency(
                source_service_id=sample_services["api-gateway"].id,
                target_service_id=sample_services["auth-service"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
            ServiceDependency(
                source_service_id=sample_services["user-service"].id,
                target_service_id=sample_services["auth-service"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
            ServiceDependency(
                source_service_id=sample_services["user-service"].id,
                target_service_id=sample_services["order-service"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
        ]
        await repository.bulk_upsert(dependencies)

        # Act
        result = await repository.list_by_target(sample_services["auth-service"].id)

        # Assert
        assert len(result) == 2
        source_ids = {dep.source_service_id for dep in result}
        assert sample_services["api-gateway"].id in source_ids
        assert sample_services["user-service"].id in source_ids

    async def test_bulk_upsert_insert_new_dependencies(
        self,
        repository: DependencyRepository,
        sample_services: dict[str, Service],
    ):
        """Test bulk upsert with all new dependencies.

        Args:
            repository: DependencyRepository instance
            sample_services: Sample services
        """
        # Arrange
        dependencies = [
            ServiceDependency(
                source_service_id=sample_services["api-gateway"].id,
                target_service_id=sample_services["auth-service"].id,
                communication_mode=CommunicationMode.SYNC,
                discovery_source=DiscoverySource.MANUAL,
            ),
            ServiceDependency(
                source_service_id=sample_services["api-gateway"].id,
                target_service_id=sample_services["user-service"].id,
                communication_mode=CommunicationMode.SYNC,
                discovery_source=DiscoverySource.MANUAL,
            ),
        ]

        # Act
        result = await repository.bulk_upsert(dependencies)

        # Assert
        assert len(result) == 2
        for dep in result:
            assert dep.id is not None
            assert dep.created_at is not None

    async def test_bulk_upsert_update_existing_dependencies(
        self,
        repository: DependencyRepository,
        sample_services: dict[str, Service],
    ):
        """Test bulk upsert updating existing dependencies.

        Args:
            repository: DependencyRepository instance
            sample_services: Sample services
        """
        # Arrange - Create initial dependency
        initial = ServiceDependency(
            source_service_id=sample_services["api-gateway"].id,
            target_service_id=sample_services["auth-service"].id,
            communication_mode=CommunicationMode.SYNC,
            discovery_source=DiscoverySource.MANUAL,
            timeout_ms=1000,
        )
        created = (await repository.bulk_upsert([initial]))[0]
        initial_id = created.id

        # Modify dependency
        updated = ServiceDependency(
            source_service_id=sample_services["api-gateway"].id,
            target_service_id=sample_services["auth-service"].id,
            communication_mode=CommunicationMode.ASYNC,  # Changed
            discovery_source=DiscoverySource.MANUAL,
            timeout_ms=5000,  # Changed
        )

        # Act
        result = await repository.bulk_upsert([updated])

        # Assert
        assert len(result) == 1
        assert result[0].id == initial_id  # Same ID
        assert result[0].communication_mode == CommunicationMode.ASYNC
        assert result[0].timeout_ms == 5000

    async def test_bulk_upsert_unique_constraint_per_source(
        self,
        repository: DependencyRepository,
        sample_services: dict[str, Service],
    ):
        """Test that unique constraint is per discovery source.

        Args:
            repository: DependencyRepository instance
            sample_services: Sample services
        """
        # Arrange - Same edge from different discovery sources
        dependencies = [
            ServiceDependency(
                source_service_id=sample_services["api-gateway"].id,
                target_service_id=sample_services["auth-service"].id,
                communication_mode=CommunicationMode.SYNC,
                discovery_source=DiscoverySource.MANUAL,
            ),
            ServiceDependency(
                source_service_id=sample_services["api-gateway"].id,
                target_service_id=sample_services["auth-service"].id,
                communication_mode=CommunicationMode.SYNC,
                discovery_source=DiscoverySource.OTEL_SERVICE_GRAPH,
            ),
        ]

        # Act
        result = await repository.bulk_upsert(dependencies)

        # Assert - Should create 2 separate edges
        assert len(result) == 2
        assert result[0].id != result[1].id
        assert result[0].discovery_source != result[1].discovery_source

    async def test_traverse_graph_downstream_single_hop(
        self,
        repository: DependencyRepository,
        sample_services: dict[str, Service],
    ):
        """Test downstream graph traversal with single hop.

        Args:
            repository: DependencyRepository instance
            sample_services: Sample services
        """
        # Arrange - Create simple dependency chain
        # api-gateway -> auth-service -> user-service
        dependencies = [
            ServiceDependency(
                source_service_id=sample_services["api-gateway"].id,
                target_service_id=sample_services["auth-service"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
            ServiceDependency(
                source_service_id=sample_services["auth-service"].id,
                target_service_id=sample_services["user-service"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
        ]
        await repository.bulk_upsert(dependencies)

        # Act - Traverse 1 hop from api-gateway
        result = await repository.traverse_graph(
            service_id=sample_services["api-gateway"].id,
            direction=TraversalDirection.DOWNSTREAM,
            max_depth=1,
            include_stale=False,
        )

        # Assert
        assert len(result["services"]) == 1  # Only auth-service
        assert result["services"][0].id == sample_services["auth-service"].id
        assert len(result["edges"]) == 1
        assert result["edges"][0].target_service_id == sample_services["auth-service"].id

    async def test_traverse_graph_downstream_multi_hop(
        self,
        repository: DependencyRepository,
        sample_services: dict[str, Service],
    ):
        """Test downstream graph traversal with multiple hops.

        Args:
            repository: DependencyRepository instance
            sample_services: Sample services
        """
        # Arrange - Create dependency chain
        # api-gateway -> auth-service -> user-service -> order-service
        dependencies = [
            ServiceDependency(
                source_service_id=sample_services["api-gateway"].id,
                target_service_id=sample_services["auth-service"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
            ServiceDependency(
                source_service_id=sample_services["auth-service"].id,
                target_service_id=sample_services["user-service"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
            ServiceDependency(
                source_service_id=sample_services["user-service"].id,
                target_service_id=sample_services["order-service"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
        ]
        await repository.bulk_upsert(dependencies)

        # Act - Traverse 3 hops from api-gateway
        result = await repository.traverse_graph(
            service_id=sample_services["api-gateway"].id,
            direction=TraversalDirection.DOWNSTREAM,
            max_depth=3,
            include_stale=False,
        )

        # Assert - Should find all 3 downstream services
        assert len(result["services"]) == 3
        service_ids = {s.id for s in result["services"]}
        assert sample_services["auth-service"].id in service_ids
        assert sample_services["user-service"].id in service_ids
        assert sample_services["order-service"].id in service_ids
        assert len(result["edges"]) == 3

    async def test_traverse_graph_upstream(
        self,
        repository: DependencyRepository,
        sample_services: dict[str, Service],
    ):
        """Test upstream graph traversal.

        Args:
            repository: DependencyRepository instance
            sample_services: Sample services
        """
        # Arrange - Create dependency chain
        # api-gateway -> auth-service -> user-service
        dependencies = [
            ServiceDependency(
                source_service_id=sample_services["api-gateway"].id,
                target_service_id=sample_services["auth-service"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
            ServiceDependency(
                source_service_id=sample_services["auth-service"].id,
                target_service_id=sample_services["user-service"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
        ]
        await repository.bulk_upsert(dependencies)

        # Act - Traverse upstream from user-service
        result = await repository.traverse_graph(
            service_id=sample_services["user-service"].id,
            direction=TraversalDirection.UPSTREAM,
            max_depth=2,
            include_stale=False,
        )

        # Assert - Should find both upstream services
        assert len(result["services"]) == 2
        service_ids = {s.id for s in result["services"]}
        assert sample_services["api-gateway"].id in service_ids
        assert sample_services["auth-service"].id in service_ids
        assert len(result["edges"]) == 2

    async def test_traverse_graph_bidirectional(
        self,
        repository: DependencyRepository,
        sample_services: dict[str, Service],
    ):
        """Test bidirectional graph traversal.

        Args:
            repository: DependencyRepository instance
            sample_services: Sample services
        """
        # Arrange - Create dependency graph
        # api-gateway -> auth-service -> user-service
        # order-service -> auth-service
        dependencies = [
            ServiceDependency(
                source_service_id=sample_services["api-gateway"].id,
                target_service_id=sample_services["auth-service"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
            ServiceDependency(
                source_service_id=sample_services["auth-service"].id,
                target_service_id=sample_services["user-service"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
            ServiceDependency(
                source_service_id=sample_services["order-service"].id,
                target_service_id=sample_services["auth-service"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
        ]
        await repository.bulk_upsert(dependencies)

        # Act - Traverse bidirectionally from auth-service
        result = await repository.traverse_graph(
            service_id=sample_services["auth-service"].id,
            direction=TraversalDirection.BOTH,
            max_depth=1,
            include_stale=False,
        )

        # Assert - Should find upstream and downstream neighbors
        assert len(result["services"]) == 3
        service_ids = {s.id for s in result["services"]}
        assert sample_services["api-gateway"].id in service_ids  # Upstream
        assert sample_services["order-service"].id in service_ids  # Upstream
        assert sample_services["user-service"].id in service_ids  # Downstream
        assert len(result["edges"]) == 3

    async def test_traverse_graph_cycle_prevention(
        self,
        repository: DependencyRepository,
        sample_services: dict[str, Service],
    ):
        """Test that graph traversal prevents infinite loops in cycles.

        Args:
            repository: DependencyRepository instance
            sample_services: Sample services
        """
        # Arrange - Create circular dependency
        # api-gateway -> auth-service -> user-service -> api-gateway
        dependencies = [
            ServiceDependency(
                source_service_id=sample_services["api-gateway"].id,
                target_service_id=sample_services["auth-service"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
            ServiceDependency(
                source_service_id=sample_services["auth-service"].id,
                target_service_id=sample_services["user-service"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
            ServiceDependency(
                source_service_id=sample_services["user-service"].id,
                target_service_id=sample_services["api-gateway"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
        ]
        await repository.bulk_upsert(dependencies)

        # Act - Traverse with high depth limit
        result = await repository.traverse_graph(
            service_id=sample_services["api-gateway"].id,
            direction=TraversalDirection.DOWNSTREAM,
            max_depth=10,
            include_stale=False,
        )

        # Assert - Should visit each service only once
        assert len(result["services"]) == 2  # auth-service, user-service
        assert len(result["edges"]) == 3  # All 3 edges in cycle

    async def test_traverse_graph_exclude_stale_edges(
        self,
        repository: DependencyRepository,
        sample_services: dict[str, Service],
    ):
        """Test that stale edges are excluded from traversal.

        Args:
            repository: DependencyRepository instance
            sample_services: Sample services
        """
        # Arrange - Create dependencies with one stale
        dependencies = [
            ServiceDependency(
                source_service_id=sample_services["api-gateway"].id,
                target_service_id=sample_services["auth-service"].id,
                communication_mode=CommunicationMode.SYNC,
                is_stale=False,
            ),
            ServiceDependency(
                source_service_id=sample_services["api-gateway"].id,
                target_service_id=sample_services["user-service"].id,
                communication_mode=CommunicationMode.SYNC,
                is_stale=True,  # Stale edge
            ),
        ]
        await repository.bulk_upsert(dependencies)

        # Act - Traverse excluding stale edges
        result = await repository.traverse_graph(
            service_id=sample_services["api-gateway"].id,
            direction=TraversalDirection.DOWNSTREAM,
            max_depth=1,
            include_stale=False,
        )

        # Assert - Should only find auth-service
        assert len(result["services"]) == 1
        assert result["services"][0].id == sample_services["auth-service"].id

    async def test_traverse_graph_include_stale_edges(
        self,
        repository: DependencyRepository,
        sample_services: dict[str, Service],
    ):
        """Test that stale edges are included when requested.

        Args:
            repository: DependencyRepository instance
            sample_services: Sample services
        """
        # Arrange - Create dependencies with one stale
        dependencies = [
            ServiceDependency(
                source_service_id=sample_services["api-gateway"].id,
                target_service_id=sample_services["auth-service"].id,
                communication_mode=CommunicationMode.SYNC,
                is_stale=False,
            ),
            ServiceDependency(
                source_service_id=sample_services["api-gateway"].id,
                target_service_id=sample_services["user-service"].id,
                communication_mode=CommunicationMode.SYNC,
                is_stale=True,  # Stale edge
            ),
        ]
        await repository.bulk_upsert(dependencies)

        # Act - Traverse including stale edges
        result = await repository.traverse_graph(
            service_id=sample_services["api-gateway"].id,
            direction=TraversalDirection.DOWNSTREAM,
            max_depth=1,
            include_stale=True,
        )

        # Assert - Should find both services
        assert len(result["services"]) == 2
        service_ids = {s.id for s in result["services"]}
        assert sample_services["auth-service"].id in service_ids
        assert sample_services["user-service"].id in service_ids

    async def test_get_adjacency_list(
        self,
        repository: DependencyRepository,
        sample_services: dict[str, Service],
    ):
        """Test getting adjacency list representation of graph.

        Args:
            repository: DependencyRepository instance
            sample_services: Sample services
        """
        # Arrange - Create dependency graph
        dependencies = [
            ServiceDependency(
                source_service_id=sample_services["api-gateway"].id,
                target_service_id=sample_services["auth-service"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
            ServiceDependency(
                source_service_id=sample_services["api-gateway"].id,
                target_service_id=sample_services["user-service"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
            ServiceDependency(
                source_service_id=sample_services["auth-service"].id,
                target_service_id=sample_services["user-service"].id,
                communication_mode=CommunicationMode.SYNC,
            ),
        ]
        await repository.bulk_upsert(dependencies)

        # Act
        adjacency_list = await repository.get_adjacency_list()

        # Assert
        assert sample_services["api-gateway"].id in adjacency_list
        assert len(adjacency_list[sample_services["api-gateway"].id]) == 2
        assert sample_services["auth-service"].id in adjacency_list[
            sample_services["api-gateway"].id
        ]
        assert sample_services["user-service"].id in adjacency_list[
            sample_services["api-gateway"].id
        ]

    async def test_mark_stale_edges(
        self,
        repository: DependencyRepository,
        sample_services: dict[str, Service],
    ):
        """Test marking edges as stale based on last_observed_at.

        Args:
            repository: DependencyRepository instance
            sample_services: Sample services
        """
        # Arrange - Create dependencies with different observation times
        old_time = datetime.now(timezone.utc) - timedelta(days=10)
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)

        dependencies = [
            ServiceDependency(
                source_service_id=sample_services["api-gateway"].id,
                target_service_id=sample_services["auth-service"].id,
                communication_mode=CommunicationMode.SYNC,
                last_observed_at=old_time,  # Old
            ),
            ServiceDependency(
                source_service_id=sample_services["api-gateway"].id,
                target_service_id=sample_services["user-service"].id,
                communication_mode=CommunicationMode.SYNC,
                last_observed_at=recent_time,  # Recent
            ),
        ]
        await repository.bulk_upsert(dependencies)

        # Act - Mark edges older than 7 days as stale
        count = await repository.mark_stale_edges(staleness_threshold_hours=168)

        # Assert
        assert count == 1  # Only one edge should be marked stale

        # Verify
        all_deps = await repository.list_by_source(sample_services["api-gateway"].id)
        stale_deps = [d for d in all_deps if d.is_stale]
        assert len(stale_deps) == 1
        assert stale_deps[0].target_service_id == sample_services["auth-service"].id


@pytest.mark.integration
class TestDependencyRepositoryPerformance:
    """Performance tests for DependencyRepository graph traversal."""

    @pytest.fixture
    def service_repo(self, db_session: AsyncSession) -> ServiceRepository:
        """Create ServiceRepository instance."""
        return ServiceRepository(db_session)

    @pytest.fixture
    def repository(self, db_session: AsyncSession) -> DependencyRepository:
        """Create DependencyRepository instance."""
        return DependencyRepository(db_session)

    async def test_traverse_graph_performance_large_graph(
        self,
        repository: DependencyRepository,
        service_repo: ServiceRepository,
    ):
        """Test graph traversal performance on large graph.

        Target: <100ms for 3-hop traversal on 5000 nodes.

        Args:
            repository: DependencyRepository instance
            service_repo: ServiceRepository instance
        """
        # Arrange - Create 100 services (scaled down for test speed)
        # In production, this would be 5000 nodes
        num_services = 100
        services = [
            Service(
                service_id=f"service-{i:04d}",
                criticality=Criticality.MEDIUM,
            )
            for i in range(num_services)
        ]
        created_services = await service_repo.bulk_upsert(services)

        # Create dependencies - each service depends on 2-3 others
        dependencies = []
        for i, service in enumerate(created_services):
            # Create 2-3 outgoing dependencies per service
            for j in range(1, 4):
                target_idx = (i + j) % num_services
                if target_idx != i:  # Avoid self-loops
                    dependencies.append(
                        ServiceDependency(
                            source_service_id=service.id,
                            target_service_id=created_services[target_idx].id,
                            communication_mode=CommunicationMode.SYNC,
                        )
                    )

        await repository.bulk_upsert(dependencies)

        # Act - Measure traversal time
        start_time = time.perf_counter()
        result = await repository.traverse_graph(
            service_id=created_services[0].id,
            direction=TraversalDirection.DOWNSTREAM,
            max_depth=3,
            include_stale=False,
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Assert
        assert len(result["services"]) > 0
        assert len(result["edges"]) > 0
        # Performance assertion - should be fast even with 100 nodes
        # With 5000 nodes, target is <100ms
        assert elapsed_ms < 500, f"Traversal took {elapsed_ms:.2f}ms (expected <500ms)"
        print(f"\n3-hop traversal on {num_services} nodes: {elapsed_ms:.2f}ms")
