"""Unit tests for DetectCircularDependenciesUseCase."""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock

from src.application.use_cases.detect_circular_dependencies import DetectCircularDependenciesUseCase
from src.domain.entities.service import Service
from src.domain.entities.circular_dependency_alert import CircularDependencyAlert, AlertStatus
from src.domain.services.circular_dependency_detector import CircularDependencyDetector


class TestDetectCircularDependenciesUseCase:
    """Test DetectCircularDependenciesUseCase."""

    @pytest.fixture
    def mock_service_repo(self):
        """Create mock service repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_dependency_repo(self):
        """Create mock dependency repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_alert_repo(self):
        """Create mock circular dependency alert repository."""
        return AsyncMock()

    @pytest.fixture
    def detector(self):
        """Create real circular dependency detector."""
        return CircularDependencyDetector()

    @pytest.fixture
    def use_case(self, mock_service_repo, mock_dependency_repo, mock_alert_repo, detector):
        """Create use case instance with mocked repositories."""
        return DetectCircularDependenciesUseCase(
            service_repository=mock_service_repo,
            dependency_repository=mock_dependency_repo,
            alert_repository=mock_alert_repo,
            detector=detector
        )

    @pytest.mark.asyncio
    async def test_detect_no_cycles_empty_graph(
        self, use_case, mock_dependency_repo, mock_alert_repo
    ):
        """Test detection on empty graph returns no cycles."""
        # Arrange
        mock_dependency_repo.get_adjacency_list.return_value = {}

        # Act
        cycles = await use_case.execute()

        # Assert
        assert len(cycles) == 0
        mock_alert_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_detect_no_cycles_dag(
        self, use_case, mock_service_repo, mock_dependency_repo, mock_alert_repo
    ):
        """Test detection on DAG (no cycles) returns empty list."""
        # Arrange
        # Graph: A → B → C (DAG, no cycle)
        service_a_uuid = uuid4()
        service_b_uuid = uuid4()
        service_c_uuid = uuid4()

        adjacency_list = {
            service_a_uuid: [service_b_uuid],
            service_b_uuid: [service_c_uuid],
            service_c_uuid: []
        }

        mock_dependency_repo.get_adjacency_list.return_value = adjacency_list

        # Act
        cycles = await use_case.execute()

        # Assert
        assert len(cycles) == 0
        mock_alert_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_detect_simple_cycle(
        self, use_case, mock_service_repo, mock_dependency_repo, mock_alert_repo
    ):
        """Test detecting a simple 2-node cycle."""
        # Arrange
        # Graph: A → B → A (cycle)
        service_a_uuid = uuid4()
        service_b_uuid = uuid4()

        service_a = Service(id=service_a_uuid, service_id="service-a", metadata={})
        service_b = Service(id=service_b_uuid, service_id="service-b", metadata={})

        adjacency_list = {
            service_a_uuid: [service_b_uuid],
            service_b_uuid: [service_a_uuid]
        }

        mock_dependency_repo.get_adjacency_list.return_value = adjacency_list

        # Mock service lookups
        async def get_by_id_side_effect(uuid):
            if uuid == service_a_uuid:
                return service_a
            elif uuid == service_b_uuid:
                return service_b
            return None

        mock_service_repo.get_by_id.side_effect = get_by_id_side_effect

        # Mock alert creation to check if cycle was reported
        mock_alert_repo.exists_for_cycle.return_value = False
        mock_alert_repo.create.return_value = CircularDependencyAlert(
            cycle_path=["service-a", "service-b"]
        )

        # Act
        cycles = await use_case.execute()

        # Assert
        assert len(cycles) == 1
        assert isinstance(cycles[0], CircularDependencyAlert)
        assert set(cycles[0].cycle_path) == {"service-a", "service-b"}

        # Verify alert was created
        mock_alert_repo.create.assert_called_once()
        created_alert = mock_alert_repo.create.call_args[0][0]
        assert len(created_alert.cycle_path) == 2
        assert set(created_alert.cycle_path) == {"service-a", "service-b"}

    @pytest.mark.asyncio
    async def test_detect_three_node_cycle(
        self, use_case, mock_service_repo, mock_dependency_repo, mock_alert_repo
    ):
        """Test detecting a 3-node cycle."""
        # Arrange
        # Graph: A → B → C → A (cycle)
        service_a_uuid = uuid4()
        service_b_uuid = uuid4()
        service_c_uuid = uuid4()

        service_a = Service(id=service_a_uuid, service_id="service-a", metadata={})
        service_b = Service(id=service_b_uuid, service_id="service-b", metadata={})
        service_c = Service(id=service_c_uuid, service_id="service-c", metadata={})

        adjacency_list = {
            service_a_uuid: [service_b_uuid],
            service_b_uuid: [service_c_uuid],
            service_c_uuid: [service_a_uuid]
        }

        mock_dependency_repo.get_adjacency_list.return_value = adjacency_list

        async def get_by_id_side_effect(uuid):
            mapping = {
                service_a_uuid: service_a,
                service_b_uuid: service_b,
                service_c_uuid: service_c
            }
            return mapping.get(uuid)

        mock_service_repo.get_by_id.side_effect = get_by_id_side_effect

        mock_alert_repo.exists_for_cycle.return_value = False
        mock_alert_repo.create.return_value = CircularDependencyAlert(
            cycle_path=["service-a", "service-b", "service-c"]
        )

        # Act
        cycles = await use_case.execute()

        # Assert
        assert len(cycles) == 1
        assert isinstance(cycles[0], CircularDependencyAlert)
        assert set(cycles[0].cycle_path) == {"service-a", "service-b", "service-c"}

        mock_alert_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_detect_multiple_cycles(
        self, use_case, mock_service_repo, mock_dependency_repo, mock_alert_repo
    ):
        """Test detecting multiple disjoint cycles."""
        # Arrange
        # Graph has two separate cycles:
        # Cycle 1: A → B → A
        # Cycle 2: C → D → C
        service_a_uuid = uuid4()
        service_b_uuid = uuid4()
        service_c_uuid = uuid4()
        service_d_uuid = uuid4()

        service_a = Service(id=service_a_uuid, service_id="service-a", metadata={})
        service_b = Service(id=service_b_uuid, service_id="service-b", metadata={})
        service_c = Service(id=service_c_uuid, service_id="service-c", metadata={})
        service_d = Service(id=service_d_uuid, service_id="service-d", metadata={})

        adjacency_list = {
            service_a_uuid: [service_b_uuid],
            service_b_uuid: [service_a_uuid],
            service_c_uuid: [service_d_uuid],
            service_d_uuid: [service_c_uuid]
        }

        mock_dependency_repo.get_adjacency_list.return_value = adjacency_list

        async def get_by_id_side_effect(uuid):
            mapping = {
                service_a_uuid: service_a,
                service_b_uuid: service_b,
                service_c_uuid: service_c,
                service_d_uuid: service_d
            }
            return mapping.get(uuid)

        mock_service_repo.get_by_id.side_effect = get_by_id_side_effect

        mock_alert_repo.exists_for_cycle.return_value = False

        alert_call_count = 0

        def create_alert_side_effect(alert):
            nonlocal alert_call_count
            alert_call_count += 1
            return alert

        mock_alert_repo.create.side_effect = create_alert_side_effect

        # Act
        cycles = await use_case.execute()

        # Assert
        assert len(cycles) == 2
        assert alert_call_count == 2

    @pytest.mark.asyncio
    async def test_deduplication_existing_alert(
        self, use_case, mock_service_repo, mock_dependency_repo, mock_alert_repo
    ):
        """Test that existing alerts are not re-created."""
        # Arrange
        service_a_uuid = uuid4()
        service_b_uuid = uuid4()

        service_a = Service(id=service_a_uuid, service_id="service-a", metadata={})
        service_b = Service(id=service_b_uuid, service_id="service-b", metadata={})

        adjacency_list = {
            service_a_uuid: [service_b_uuid],
            service_b_uuid: [service_a_uuid]
        }

        mock_dependency_repo.get_adjacency_list.return_value = adjacency_list

        async def get_by_id_side_effect(uuid):
            if uuid == service_a_uuid:
                return service_a
            elif uuid == service_b_uuid:
                return service_b
            return None

        mock_service_repo.get_by_id.side_effect = get_by_id_side_effect

        # Alert already exists for this cycle
        mock_alert_repo.exists_for_cycle.return_value = True

        # Act
        cycles = await use_case.execute()

        # Assert
        # When alert already exists, use case returns empty list (no new alerts created)
        assert len(cycles) == 0
        mock_alert_repo.create.assert_not_called()  # Alert not created (already exists)

    @pytest.mark.asyncio
    async def test_cycle_with_self_loop_excluded(
        self, use_case, mock_service_repo, mock_dependency_repo, mock_alert_repo
    ):
        """Test that self-loops are not reported as cycles."""
        # Arrange
        # Note: Domain entity validation should prevent self-loops,
        # but Tarjan's filters out single-node SCCs anyway

        service_a_uuid = uuid4()
        service_b_uuid = uuid4()

        service_a = Service(id=service_a_uuid, service_id="service-a", metadata={})
        service_b = Service(id=service_b_uuid, service_id="service-b", metadata={})

        # A → A (self-loop, should be filtered)
        # A → B → A (real cycle)
        adjacency_list = {
            service_a_uuid: [service_a_uuid, service_b_uuid],
            service_b_uuid: [service_a_uuid]
        }

        mock_dependency_repo.get_adjacency_list.return_value = adjacency_list

        async def get_by_id_side_effect(uuid):
            if uuid == service_a_uuid:
                return service_a
            elif uuid == service_b_uuid:
                return service_b
            return None

        mock_service_repo.get_by_id.side_effect = get_by_id_side_effect

        mock_alert_repo.exists_for_cycle.return_value = False
        mock_alert_repo.create.return_value = CircularDependencyAlert(
            cycle_path=["service-a", "service-b"]
        )

        # Act
        cycles = await use_case.execute()

        # Assert
        # Only the A-B cycle should be detected, not the A-A self-loop
        assert len(cycles) == 1
        assert isinstance(cycles[0], CircularDependencyAlert)
        assert set(cycles[0].cycle_path) == {"service-a", "service-b"}

    @pytest.mark.asyncio
    async def test_large_graph_performance(
        self, use_case, mock_service_repo, mock_dependency_repo, mock_alert_repo
    ):
        """Test detection on a moderately large graph completes quickly."""
        # Arrange - Create a graph with 50 services and 1 cycle
        service_uuids = [uuid4() for _ in range(50)]
        services = [
            Service(id=uuid, service_id=f"service-{i}", metadata={})
            for i, uuid in enumerate(service_uuids)
        ]

        # Create a DAG with one cycle at the end
        adjacency_list = {}
        for i in range(49):
            adjacency_list[service_uuids[i]] = [service_uuids[i + 1]]

        # Add cycle: last service points back to service 47
        adjacency_list[service_uuids[49]] = [service_uuids[47]]

        mock_dependency_repo.get_adjacency_list.return_value = adjacency_list

        async def get_by_id_side_effect(uuid):
            for service in services:
                if service.id == uuid:
                    return service
            return None

        mock_service_repo.get_by_id.side_effect = get_by_id_side_effect

        mock_alert_repo.exists_for_cycle.return_value = False
        mock_alert_repo.create.return_value = CircularDependencyAlert(
            cycle_path=["service-47", "service-48", "service-49"]
        )

        # Act
        import time
        start = time.time()
        cycles = await use_case.execute()
        duration = time.time() - start

        # Assert
        assert len(cycles) == 1
        assert duration < 1.0  # Should complete in under 1 second for 50 nodes
