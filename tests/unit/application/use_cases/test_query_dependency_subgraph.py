"""Unit tests for QueryDependencySubgraphUseCase."""

import pytest
from datetime import datetime
from uuid import uuid4
from unittest.mock import AsyncMock

from src.application.use_cases.query_dependency_subgraph import QueryDependencySubgraphUseCase
from src.application.dtos.dependency_subgraph_dto import DependencySubgraphRequest
from src.domain.entities.service import Service, Criticality
from src.domain.entities.service_dependency import (
    ServiceDependency,
    CommunicationMode,
    DependencyCriticality,
    DiscoverySource,
)
from src.domain.services.graph_traversal_service import TraversalDirection


class TestQueryDependencySubgraphUseCase:
    """Test QueryDependencySubgraphUseCase."""

    @pytest.fixture
    def mock_service_repo(self):
        """Create mock service repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_dependency_repo(self):
        """Create mock dependency repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_graph_traversal_service(self):
        """Create mock graph traversal service."""
        return AsyncMock()

    @pytest.fixture
    def use_case(self, mock_service_repo, mock_dependency_repo, mock_graph_traversal_service):
        """Create use case instance with mocked dependencies."""
        return QueryDependencySubgraphUseCase(
            service_repository=mock_service_repo,
            dependency_repository=mock_dependency_repo,
            graph_traversal_service=mock_graph_traversal_service
        )

    @pytest.mark.asyncio
    async def test_query_nonexistent_service_returns_none(
        self, use_case, mock_service_repo
    ):
        """Test querying non-existent service returns None."""
        # Arrange
        request = DependencySubgraphRequest(
            service_id="nonexistent-service",
            direction="both",
            depth=3,
            include_stale=False
        )

        mock_service_repo.get_by_service_id.return_value = None

        # Act
        response = await use_case.execute(request)

        # Assert
        assert response is None
        mock_service_repo.get_by_service_id.assert_called_once_with("nonexistent-service")

    @pytest.mark.asyncio
    async def test_query_isolated_service_returns_empty_graph(
        self, use_case, mock_service_repo, mock_graph_traversal_service
    ):
        """Test querying service with no dependencies returns empty graph."""
        # Arrange
        service_uuid = uuid4()
        service = Service(
            id=service_uuid,
            service_id="isolated-service",
            team="platform",
            criticality=Criticality.MEDIUM,
            metadata={"team": "platform"}
        )

        request = DependencySubgraphRequest(
            service_id="isolated-service",
            direction="both",
            depth=3,
            include_stale=False
        )

        mock_service_repo.get_by_service_id.return_value = service

        # Mock graph traversal returns empty results
        mock_graph_traversal_service.get_subgraph.return_value = ([], [])

        # Act
        response = await use_case.execute(request)

        # Assert
        assert response is not None
        assert response.service_id == "isolated-service"
        assert response.direction == "both"
        assert response.depth == 3
        # Root service is always included even with no dependencies
        assert len(response.nodes) == 1
        assert response.nodes[0].service_id == "isolated-service"
        assert len(response.edges) == 0
        assert response.statistics.total_nodes == 1
        assert response.statistics.total_edges == 0

    @pytest.mark.asyncio
    async def test_query_downstream_dependencies(
        self, use_case, mock_service_repo, mock_graph_traversal_service
    ):
        """Test querying downstream dependencies."""
        # Arrange
        service_a_uuid = uuid4()
        service_b_uuid = uuid4()

        service_a = Service(
            id=service_a_uuid,
            service_id="service-a",
            team="platform",
            criticality=Criticality.HIGH,
            metadata={"team": "platform"}
        )

        service_b = Service(
            id=service_b_uuid,
            service_id="service-b",
            team="platform",
            criticality=Criticality.MEDIUM,
            metadata={"team": "platform"}
        )

        dependency = ServiceDependency(
            id=uuid4(),
            source_service_id=service_a_uuid,
            target_service_id=service_b_uuid,
            communication_mode=CommunicationMode.SYNC,
            criticality=DependencyCriticality.HARD,
            protocol="grpc",
            timeout_ms=5000,
            discovery_source=DiscoverySource.MANUAL,
            confidence_score=1.0
        )

        request = DependencySubgraphRequest(
            service_id="service-a",
            direction="downstream",
            depth=3,
            include_stale=False
        )

        mock_service_repo.get_by_service_id.return_value = service_a

        # Mock graph traversal returns service-b as downstream
        mock_graph_traversal_service.get_subgraph.return_value = (
            [service_b],
            [dependency]
        )

        # Mock the helper to return service_ids from UUIDs
        use_case._get_service_id_from_uuid = lambda uuid, nodes: {
            service_a_uuid: "service-a",
            service_b_uuid: "service-b",
        }.get(uuid, str(uuid))

        # Act
        response = await use_case.execute(request)

        # Assert
        assert response is not None
        assert response.service_id == "service-a"
        assert response.direction == "downstream"
        # Root service + 1 downstream = 2 nodes
        assert len(response.nodes) == 2
        assert len(response.edges) == 1
        node_ids = {n.service_id for n in response.nodes}
        assert "service-a" in node_ids
        assert "service-b" in node_ids
        assert response.edges[0].source == "service-a"
        assert response.edges[0].target == "service-b"
        assert response.statistics.total_nodes == 2
        assert response.statistics.total_edges == 1
        assert response.statistics.downstream_services == 1
        assert response.statistics.upstream_services == 0

    @pytest.mark.asyncio
    async def test_query_upstream_dependencies(
        self, use_case, mock_service_repo, mock_graph_traversal_service
    ):
        """Test querying upstream dependencies."""
        # Arrange
        service_a_uuid = uuid4()
        service_b_uuid = uuid4()

        service_a = Service(
            id=service_a_uuid,
            service_id="service-a",
            team="platform",
            criticality=Criticality.HIGH,
            metadata={}
        )

        service_b = Service(
            id=service_b_uuid,
            service_id="service-b",
            team="platform",
            criticality=Criticality.MEDIUM,
            metadata={}
        )

        # service-a calls service-b (so service-a is upstream of service-b)
        dependency = ServiceDependency(
            id=uuid4(),
            source_service_id=service_a_uuid,
            target_service_id=service_b_uuid,
            communication_mode=CommunicationMode.SYNC,
            criticality=DependencyCriticality.HARD,
            discovery_source=DiscoverySource.MANUAL,
            confidence_score=1.0
        )

        request = DependencySubgraphRequest(
            service_id="service-b",
            direction="upstream",
            depth=3,
            include_stale=False
        )

        mock_service_repo.get_by_service_id.return_value = service_b

        # Mock graph traversal returns service-a as upstream
        mock_graph_traversal_service.get_subgraph.return_value = (
            [service_a],
            [dependency]
        )

        # Mock the helper to return service_ids from UUIDs
        use_case._get_service_id_from_uuid = lambda uuid, nodes: {
            service_a_uuid: "service-a",
            service_b_uuid: "service-b",
        }.get(uuid, str(uuid))

        # Act
        response = await use_case.execute(request)

        # Assert
        assert response is not None
        assert response.service_id == "service-b"
        assert response.direction == "upstream"
        # Root service + 1 upstream = 2 nodes
        assert len(response.nodes) == 2
        assert len(response.edges) == 1
        assert response.statistics.upstream_services == 1
        assert response.statistics.downstream_services == 0

    @pytest.mark.asyncio
    async def test_query_both_directions(
        self, use_case, mock_service_repo, mock_graph_traversal_service
    ):
        """Test querying both upstream and downstream dependencies."""
        # Arrange
        service_a_uuid = uuid4()
        service_b_uuid = uuid4()
        service_c_uuid = uuid4()

        service_a = Service(id=service_a_uuid, service_id="service-a", metadata={})
        service_b = Service(id=service_b_uuid, service_id="service-b", metadata={})
        service_c = Service(id=service_c_uuid, service_id="service-c", metadata={})

        # service-a → service-b (a is upstream of b)
        # service-b → service-c (c is downstream of b)

        dep1 = ServiceDependency(
            id=uuid4(),
            source_service_id=service_a_uuid,
            target_service_id=service_b_uuid,
            communication_mode=CommunicationMode.SYNC,
            criticality=DependencyCriticality.HARD,
            discovery_source=DiscoverySource.MANUAL,
            confidence_score=1.0
        )

        dep2 = ServiceDependency(
            id=uuid4(),
            source_service_id=service_b_uuid,
            target_service_id=service_c_uuid,
            communication_mode=CommunicationMode.SYNC,
            criticality=DependencyCriticality.HARD,
            discovery_source=DiscoverySource.MANUAL,
            confidence_score=1.0
        )

        request = DependencySubgraphRequest(
            service_id="service-b",
            direction="both",
            depth=3,
            include_stale=False
        )

        mock_service_repo.get_by_service_id.return_value = service_b

        # Mock graph traversal returns both upstream and downstream
        mock_graph_traversal_service.get_subgraph.return_value = (
            [service_a, service_c],
            [dep1, dep2]
        )

        # Mock the helper to return service_ids from UUIDs
        use_case._get_service_id_from_uuid = lambda uuid, nodes: {
            service_a_uuid: "service-a",
            service_b_uuid: "service-b",
            service_c_uuid: "service-c",
        }.get(uuid, str(uuid))

        # Act
        response = await use_case.execute(request)

        # Assert
        assert response is not None
        assert response.direction == "both"
        # Root service + upstream + downstream = 3 nodes
        assert len(response.nodes) == 3
        assert len(response.edges) == 2
        assert response.statistics.total_nodes == 3
        assert response.statistics.total_edges == 2

    @pytest.mark.asyncio
    async def test_query_with_custom_depth(
        self, use_case, mock_service_repo, mock_graph_traversal_service
    ):
        """Test querying with custom depth parameter."""
        # Arrange
        service_uuid = uuid4()
        service = Service(id=service_uuid, service_id="service-a", metadata={})

        request = DependencySubgraphRequest(
            service_id="service-a",
            direction="downstream",
            depth=5,  # Custom depth
            include_stale=False
        )

        mock_service_repo.get_by_service_id.return_value = service
        mock_graph_traversal_service.get_subgraph.return_value = ([], [])

        # Act
        response = await use_case.execute(request)

        # Assert
        mock_graph_traversal_service.get_subgraph.assert_called_once()
        call_args = mock_graph_traversal_service.get_subgraph.call_args
        assert call_args[1]["max_depth"] == 5

    @pytest.mark.asyncio
    async def test_query_with_include_stale(
        self, use_case, mock_service_repo, mock_graph_traversal_service
    ):
        """Test querying with include_stale=True."""
        # Arrange
        service_uuid = uuid4()
        service = Service(id=service_uuid, service_id="service-a", metadata={})

        service_b_uuid = uuid4()
        service_b = Service(id=service_b_uuid, service_id="service-b", metadata={})

        # Stale dependency
        stale_dep = ServiceDependency(
            id=uuid4(),
            source_service_id=service_uuid,
            target_service_id=service_b_uuid,
            communication_mode=CommunicationMode.SYNC,
            criticality=DependencyCriticality.SOFT,
            discovery_source=DiscoverySource.KUBERNETES,
            confidence_score=0.75,
            is_stale=True
        )

        request = DependencySubgraphRequest(
            service_id="service-a",
            direction="downstream",
            depth=3,
            include_stale=True  # Include stale edges
        )

        mock_service_repo.get_by_service_id.return_value = service
        mock_graph_traversal_service.get_subgraph.return_value = (
            [service_b],
            [stale_dep]
        )

        # Act
        response = await use_case.execute(request)

        # Assert
        assert len(response.edges) == 1
        assert response.edges[0].is_stale is True

        mock_graph_traversal_service.get_subgraph.assert_called_once()
        call_args = mock_graph_traversal_service.get_subgraph.call_args
        assert call_args[1]["include_stale"] is True

    @pytest.mark.asyncio
    async def test_statistics_calculation(
        self, use_case, mock_service_repo, mock_graph_traversal_service
    ):
        """Test that statistics are calculated correctly."""
        # Arrange
        service_a_uuid = uuid4()
        service_b_uuid = uuid4()
        service_c_uuid = uuid4()

        service_a = Service(id=service_a_uuid, service_id="service-a", metadata={})
        service_b = Service(id=service_b_uuid, service_id="service-b", metadata={})
        service_c = Service(id=service_c_uuid, service_id="service-c", metadata={})

        # a → b, a → c (2 downstream from a)
        dep1 = ServiceDependency(
            id=uuid4(),
            source_service_id=service_a_uuid,
            target_service_id=service_b_uuid,
            communication_mode=CommunicationMode.SYNC,
            criticality=DependencyCriticality.HARD,
            discovery_source=DiscoverySource.MANUAL,
            confidence_score=1.0
        )

        dep2 = ServiceDependency(
            id=uuid4(),
            source_service_id=service_a_uuid,
            target_service_id=service_c_uuid,
            communication_mode=CommunicationMode.ASYNC,
            criticality=DependencyCriticality.SOFT,
            discovery_source=DiscoverySource.OTEL_SERVICE_GRAPH,
            confidence_score=0.85
        )

        request = DependencySubgraphRequest(
            service_id="service-a",
            direction="downstream",
            depth=3,
            include_stale=False
        )

        mock_service_repo.get_by_service_id.return_value = service_a
        mock_graph_traversal_service.get_subgraph.return_value = (
            [service_b, service_c],
            [dep1, dep2]
        )

        # Mock the helper to return service_ids from UUIDs
        use_case._get_service_id_from_uuid = lambda uuid, nodes: {
            service_a_uuid: "service-a",
            service_b_uuid: "service-b",
            service_c_uuid: "service-c",
        }.get(uuid, str(uuid))

        # Act
        response = await use_case.execute(request)

        # Assert - root service + 2 downstream = 3 nodes
        assert response.statistics.total_nodes == 3
        assert response.statistics.total_edges == 2
        assert response.statistics.downstream_services == 2
        assert response.statistics.upstream_services == 0
        # Max depth is determined by traversal, not counted by use case
        assert response.statistics.max_depth_reached >= 0
