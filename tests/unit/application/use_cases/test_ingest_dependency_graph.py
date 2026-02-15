"""Unit tests for IngestDependencyGraphUseCase."""

import pytest
from datetime import datetime
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

from src.application.use_cases.ingest_dependency_graph import IngestDependencyGraphUseCase
from src.application.dtos.dependency_graph_dto import (
    DependencyGraphIngestRequest,
    NodeDTO,
    EdgeDTO,
    EdgeAttributesDTO,
    RetryConfigDTO,
)
from src.domain.entities.service import Service, Criticality
from src.domain.entities.service_dependency import (
    ServiceDependency,
    CommunicationMode,
    DependencyCriticality,
    DiscoverySource,
)


class TestIngestDependencyGraphUseCase:
    """Test IngestDependencyGraphUseCase."""

    @pytest.fixture
    def mock_service_repo(self):
        """Create mock service repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_dependency_repo(self):
        """Create mock dependency repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_edge_merge_service(self):
        """Create mock edge merge service."""
        mock = MagicMock()
        mock.compute_confidence_score.return_value = 1.0
        return mock

    @pytest.fixture
    def use_case(self, mock_service_repo, mock_dependency_repo, mock_edge_merge_service):
        """Create use case instance with mocked repositories."""
        return IngestDependencyGraphUseCase(
            service_repository=mock_service_repo,
            dependency_repository=mock_dependency_repo,
            edge_merge_service=mock_edge_merge_service
        )

    @pytest.mark.asyncio
    async def test_ingest_single_service_no_edges(self, use_case, mock_service_repo, mock_dependency_repo):
        """Test ingesting a single service with no edges."""
        # Arrange
        node = NodeDTO(
            service_id="test-service",
            metadata={"team": "platform", "criticality": "high"}
        )

        request = DependencyGraphIngestRequest(
            source="manual",
            timestamp=datetime.now(),
            nodes=[node],
            edges=[]
        )

        service_uuid = uuid4()
        created_service = Service(
            id=service_uuid,
            service_id="test-service",
            team="platform",
            criticality=Criticality.HIGH,
            metadata={"team": "platform", "criticality": "high"}
        )

        mock_service_repo.bulk_upsert.return_value = [created_service]
        mock_dependency_repo.bulk_upsert.return_value = []

        # Act
        response = await use_case.execute(request)

        # Assert
        assert response.nodes_received == 1
        assert response.edges_received == 0
        assert response.nodes_upserted == 1
        assert response.edges_upserted == 0
        assert response.status == "completed"
        assert len(response.circular_dependencies_detected) == 0
        assert len(response.warnings) == 0

        mock_service_repo.bulk_upsert.assert_called_once()
        mock_dependency_repo.bulk_upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_ingest_with_edges(self, use_case, mock_service_repo, mock_dependency_repo):
        """Test ingesting services with dependencies."""
        # Arrange
        node_a = NodeDTO(service_id="service-a", metadata={"team": "platform"})
        node_b = NodeDTO(service_id="service-b", metadata={"team": "platform"})

        attrs = EdgeAttributesDTO(
            communication_mode="sync",
            criticality="hard",
            protocol="grpc",
            timeout_ms=5000
        )

        edge = EdgeDTO(
            source="service-a",
            target="service-b",
            attributes=attrs
        )

        request = DependencyGraphIngestRequest(
            source="manual",
            timestamp=datetime.now(),
            nodes=[node_a, node_b],
            edges=[edge]
        )

        # Mock service creation
        service_a_uuid = uuid4()
        service_b_uuid = uuid4()

        service_a = Service(
            id=service_a_uuid,
            service_id="service-a",
            team="platform",
            criticality=Criticality.MEDIUM,
            metadata={"team": "platform"}
        )

        service_b = Service(
            id=service_b_uuid,
            service_id="service-b",
            team="platform",
            criticality=Criticality.MEDIUM,
            metadata={"team": "platform"}
        )

        mock_service_repo.bulk_upsert.return_value = [service_a, service_b]

        # Mock dependency creation
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

        mock_dependency_repo.bulk_upsert.return_value = [dependency]

        # Mock get_by_service_id calls
        mock_service_repo.get_by_service_id.side_effect = [service_a, service_b]

        # Act
        response = await use_case.execute(request)

        # Assert
        assert response.nodes_received == 2
        assert response.edges_received == 1
        assert response.nodes_upserted == 2
        assert response.edges_upserted == 1
        assert response.status == "completed"

    @pytest.mark.asyncio
    async def test_ingest_with_unknown_services_auto_creation(
        self, use_case, mock_service_repo, mock_dependency_repo
    ):
        """Test that unknown services referenced in edges are auto-created."""
        # Arrange - edge references service-b which is not in nodes list
        node_a = NodeDTO(service_id="service-a", metadata={"team": "platform"})

        attrs = EdgeAttributesDTO(
            communication_mode="sync",
            criticality="hard"
        )

        edge = EdgeDTO(
            source="service-a",
            target="service-b",  # Unknown service
            attributes=attrs
        )

        request = DependencyGraphIngestRequest(
            source="manual",
            timestamp=datetime.now(),
            nodes=[node_a],
            edges=[edge]
        )

        service_a_uuid = uuid4()
        service_b_uuid = uuid4()

        service_a = Service(
            id=service_a_uuid,
            service_id="service-a",
            team="platform",
            criticality=Criticality.MEDIUM,
            metadata={"team": "platform"}
        )

        # Service B will be auto-created
        service_b = Service(
            id=service_b_uuid,
            service_id="service-b",
            discovered=True,
            metadata={"source": "auto_discovered"}
        )

        # bulk_upsert is called once with both explicit and auto-discovered services
        mock_service_repo.bulk_upsert.return_value = [service_a, service_b]

        dependency = ServiceDependency(
            id=uuid4(),
            source_service_id=service_a_uuid,
            target_service_id=service_b_uuid,
            communication_mode=CommunicationMode.SYNC,
            criticality=DependencyCriticality.HARD,
            discovery_source=DiscoverySource.MANUAL,
            confidence_score=1.0
        )

        mock_dependency_repo.bulk_upsert.return_value = [dependency]

        # Act
        response = await use_case.execute(request)

        # Assert
        assert response.nodes_received == 1
        assert response.edges_received == 1
        assert "1 unknown service" in response.warnings[0] or "auto-created" in response.warnings[0].lower()

    @pytest.mark.asyncio
    async def test_ingest_with_otel_source(self, use_case, mock_service_repo, mock_dependency_repo):
        """Test ingesting from OTel Service Graph source."""
        # Arrange
        node_a = NodeDTO(service_id="service-a", metadata={})

        attrs = EdgeAttributesDTO(
            communication_mode="sync",
            criticality="hard"
        )

        edge = EdgeDTO(
            source="service-a",
            target="service-b",
            attributes=attrs
        )

        request = DependencyGraphIngestRequest(
            source="otel_service_graph",
            timestamp=datetime.now(),
            nodes=[node_a],
            edges=[edge]
        )

        service_a_uuid = uuid4()
        service_b_uuid = uuid4()

        service_a = Service(
            id=service_a_uuid,
            service_id="service-a",
            criticality=Criticality.MEDIUM,
            metadata={}
        )

        service_b = Service(
            id=service_b_uuid,
            service_id="service-b",
            discovered=True,
            metadata={"source": "auto_discovered"}
        )

        # bulk_upsert is called once with both explicit and auto-discovered services
        mock_service_repo.bulk_upsert.return_value = [service_a, service_b]

        # Dependency from OTel has discovery_source set to OTEL_SERVICE_GRAPH
        dependency = ServiceDependency(
            id=uuid4(),
            source_service_id=service_a_uuid,
            target_service_id=service_b_uuid,
            communication_mode=CommunicationMode.SYNC,
            criticality=DependencyCriticality.HARD,
            discovery_source=DiscoverySource.OTEL_SERVICE_GRAPH,
            confidence_score=0.85  # Lower confidence for OTel
        )

        mock_dependency_repo.bulk_upsert.return_value = [dependency]

        # Act
        response = await use_case.execute(request)

        # Assert
        assert response.status == "completed"
        assert response.edges_upserted == 1

    @pytest.mark.asyncio
    async def test_ingest_with_retry_config(self, use_case, mock_service_repo, mock_dependency_repo):
        """Test ingesting edge with retry configuration."""
        # Arrange
        node_a = NodeDTO(service_id="service-a", metadata={})

        retry_config = RetryConfigDTO(max_retries=5, backoff_strategy="linear")

        attrs = EdgeAttributesDTO(
            communication_mode="async",
            criticality="soft",
            protocol="kafka",
            timeout_ms=30000,
            retry_config=retry_config
        )

        edge = EdgeDTO(
            source="service-a",
            target="service-b",
            attributes=attrs
        )

        request = DependencyGraphIngestRequest(
            source="manual",
            timestamp=datetime.now(),
            nodes=[node_a],
            edges=[edge]
        )

        service_a_uuid = uuid4()
        service_b_uuid = uuid4()

        service_a = Service(id=service_a_uuid, service_id="service-a", metadata={})
        service_b = Service(id=service_b_uuid, service_id="service-b", discovered=True, metadata={})

        # bulk_upsert is called once with both explicit and auto-discovered services
        mock_service_repo.bulk_upsert.return_value = [service_a, service_b]

        dependency = ServiceDependency(
            id=uuid4(),
            source_service_id=service_a_uuid,
            target_service_id=service_b_uuid,
            communication_mode=CommunicationMode.ASYNC,
            criticality=DependencyCriticality.SOFT,
            protocol="kafka",
            timeout_ms=30000,
            discovery_source=DiscoverySource.MANUAL,
            confidence_score=1.0
        )

        mock_dependency_repo.bulk_upsert.return_value = [dependency]

        # Act
        response = await use_case.execute(request)

        # Assert
        assert response.status == "completed"
        assert response.edges_upserted == 1

    @pytest.mark.asyncio
    async def test_ingest_empty_request(self, use_case, mock_service_repo, mock_dependency_repo):
        """Test ingesting empty graph (no nodes, no edges)."""
        # Arrange
        request = DependencyGraphIngestRequest(
            source="manual",
            timestamp=datetime.now(),
            nodes=[],
            edges=[]
        )

        mock_service_repo.bulk_upsert.return_value = []
        mock_dependency_repo.bulk_upsert.return_value = []

        # Act
        response = await use_case.execute(request)

        # Assert
        assert response.nodes_received == 0
        assert response.edges_received == 0
        assert response.nodes_upserted == 0
        assert response.edges_upserted == 0
        assert response.status == "completed"
        assert len(response.warnings) == 0
