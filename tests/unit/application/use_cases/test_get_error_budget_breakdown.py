"""Unit tests for GetErrorBudgetBreakdownUseCase."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.dtos.constraint_analysis_dto import (
    ErrorBudgetBreakdownRequest,
)
from src.application.use_cases.get_error_budget_breakdown import (
    GetErrorBudgetBreakdownUseCase,
)
from src.domain.entities.constraint_analysis import (
    ErrorBudgetBreakdown,
    ExternalProviderProfile,
    ServiceType,
)
from src.domain.entities.service import Service
from src.domain.entities.service_dependency import (
    CommunicationMode,
    DependencyCriticality,
    ServiceDependency,
)
from src.domain.entities.sli_data import AvailabilitySliData


@pytest.fixture
def mock_service_repo():
    """Mock service repository."""
    return AsyncMock()


@pytest.fixture
def mock_dependency_repo():
    """Mock dependency repository."""
    return AsyncMock()


@pytest.fixture
def mock_telemetry():
    """Mock telemetry service."""
    return AsyncMock()


@pytest.fixture
def mock_graph_traversal():
    """Mock graph traversal service."""
    return AsyncMock()


@pytest.fixture
def mock_external_buffer():
    """Mock external buffer service."""
    mock = AsyncMock()
    mock.build_profile.return_value = ExternalProviderProfile(
        service_id="external-api",
        service_uuid=uuid4(),
        published_sla=0.9999,
        observed_availability=0.9960,
    )
    mock.compute_effective_availability.return_value = 0.9960
    return mock


@pytest.fixture
def mock_budget_analyzer():
    """Mock error budget analyzer."""
    mock = AsyncMock()
    mock.compute_breakdown.return_value = ErrorBudgetBreakdown(
        service_id="checkout-service",
        slo_target=99.9,
        total_error_budget_minutes=43.2,
        self_consumption_pct=8.0,
    )
    return mock


@pytest.fixture
def use_case(
    mock_service_repo,
    mock_dependency_repo,
    mock_telemetry,
    mock_graph_traversal,
    mock_external_buffer,
    mock_budget_analyzer,
):
    """Create use case instance with mocked dependencies."""
    return GetErrorBudgetBreakdownUseCase(
        service_repository=mock_service_repo,
        dependency_repository=mock_dependency_repo,
        telemetry_service=mock_telemetry,
        graph_traversal_service=mock_graph_traversal,
        external_buffer_service=mock_external_buffer,
        error_budget_analyzer=mock_budget_analyzer,
    )


@pytest.mark.asyncio
class TestGetErrorBudgetBreakdownUseCase:
    """Tests for GetErrorBudgetBreakdownUseCase."""

    async def test_service_not_found_returns_none(
        self, use_case, mock_service_repo
    ) -> None:
        """Test that None is returned when service doesn't exist."""
        mock_service_repo.get_by_service_id.return_value = None

        request = ErrorBudgetBreakdownRequest(service_id="nonexistent-service")
        result = await use_case.execute(request)

        assert result is None
        mock_service_repo.get_by_service_id.assert_called_once_with(
            "nonexistent-service"
        )

    async def test_happy_path_with_hard_dependencies(
        self,
        use_case,
        mock_service_repo,
        mock_graph_traversal,
        mock_telemetry,
        mock_budget_analyzer,
    ) -> None:
        """Test successful breakdown with hard sync dependencies."""
        # Setup service
        service_id = uuid4()
        service = Service(id=service_id, service_id="checkout-service")
        mock_service_repo.get_by_service_id.return_value = service

        # Setup dependencies
        dep1_id = uuid4()
        dep2_id = uuid4()
        dep1 = Service(id=dep1_id, service_id="payment-service")
        dep2 = Service(id=dep2_id, service_id="inventory-service")

        edge1 = ServiceDependency(
            source_service_id=service_id,
            target_service_id=dep1_id,
            criticality=DependencyCriticality.HARD,
            communication_mode=CommunicationMode.SYNC,
        )
        edge2 = ServiceDependency(
            source_service_id=service_id,
            target_service_id=dep2_id,
            criticality=DependencyCriticality.HARD,
            communication_mode=CommunicationMode.SYNC,
        )

        mock_graph_traversal.get_subgraph.return_value = (
            [service, dep1, dep2],
            [edge1, edge2],
        )

        # Setup telemetry
        mock_telemetry.get_availability_sli.side_effect = [
            AvailabilitySliData(
                service_id="payment-service",
                good_events=99950,
                total_events=100000,
                availability_ratio=0.9995,
                window_start=datetime.now(timezone.utc),
                window_end=datetime.now(timezone.utc),
                sample_count=100000,
            ),
            AvailabilitySliData(
                service_id="inventory-service",
                good_events=99900,
                total_events=100000,
                availability_ratio=0.9990,
                window_start=datetime.now(timezone.utc),
                window_end=datetime.now(timezone.utc),
                sample_count=100000,
            ),
            AvailabilitySliData(
                service_id="checkout-service",
                good_events=99920,
                total_events=100000,
                availability_ratio=0.9992,
                window_start=datetime.now(timezone.utc),
                window_end=datetime.now(timezone.utc),
                sample_count=100000,
            ),
        ]

        # Setup budget breakdown
        mock_budget_analyzer.compute_breakdown.return_value = (
            ErrorBudgetBreakdown(
                service_id="checkout-service",
                slo_target=99.9,
                total_error_budget_minutes=43.2,
                self_consumption_pct=8.0,
                dependency_assessments=[],
            )
        )

        # Execute
        request = ErrorBudgetBreakdownRequest(
            service_id="checkout-service", slo_target_pct=99.9, lookback_days=30
        )
        result = await use_case.execute(request)

        # Assertions
        assert result is not None
        assert result.service_id == "checkout-service"
        assert result.slo_target_pct == 99.9
        assert result.total_error_budget_minutes == 43.2
        assert result.self_consumption_pct == 8.0

    async def test_external_dependency_uses_adaptive_buffer(
        self,
        use_case,
        mock_service_repo,
        mock_graph_traversal,
        mock_telemetry,
        mock_external_buffer,
    ) -> None:
        """Test that external dependencies use adaptive buffer."""
        # Setup service
        service_id = uuid4()
        service = Service(id=service_id, service_id="checkout-service")
        mock_service_repo.get_by_service_id.return_value = service

        # Setup external dependency
        ext_id = uuid4()
        external_service = Service(
            id=ext_id,
            service_id="external-payment-api",
            service_type=ServiceType.EXTERNAL,
            published_sla=0.9999,
        )

        edge = ServiceDependency(
            source_service_id=service_id,
            target_service_id=ext_id,
            criticality=DependencyCriticality.HARD,
            communication_mode=CommunicationMode.SYNC,
        )

        mock_graph_traversal.get_subgraph.return_value = (
            [service, external_service],
            [edge],
        )

        # Setup telemetry for external service
        mock_telemetry.get_availability_sli.side_effect = [
            AvailabilitySliData(
                service_id="external-payment-api",
                good_events=99600,
                total_events=100000,
                availability_ratio=0.9960,
                window_start=datetime.now(timezone.utc),
                window_end=datetime.now(timezone.utc),
                sample_count=100000,
            ),
            AvailabilitySliData(
                service_id="checkout-service",
                good_events=99920,
                total_events=100000,
                availability_ratio=0.9992,
                window_start=datetime.now(timezone.utc),
                window_end=datetime.now(timezone.utc),
                sample_count=100000,
            ),
        ]

        # Setup external buffer
        profile = ExternalProviderProfile(
            service_id="external-payment-api",
            service_uuid=ext_id,
            published_sla=0.9999,
            observed_availability=0.9960,
        )
        mock_external_buffer.build_profile.return_value = profile
        mock_external_buffer.compute_effective_availability.return_value = (
            0.9960
        )

        # Execute
        request = ErrorBudgetBreakdownRequest(service_id="checkout-service")
        result = await use_case.execute(request)

        # Verify external buffer was called
        assert result is not None
        mock_external_buffer.build_profile.assert_called_once()
        mock_external_buffer.compute_effective_availability.assert_called_once_with(
            profile
        )

    async def test_filters_to_hard_sync_dependencies_only(
        self,
        use_case,
        mock_service_repo,
        mock_graph_traversal,
        mock_telemetry,
        mock_budget_analyzer,
    ) -> None:
        """Test that only hard sync dependencies are included."""
        # Setup service
        service_id = uuid4()
        service = Service(id=service_id, service_id="checkout-service")
        mock_service_repo.get_by_service_id.return_value = service

        # Setup dependencies: 1 hard sync, 1 soft async
        hard_id = uuid4()
        soft_id = uuid4()
        hard_dep = Service(id=hard_id, service_id="payment-service")
        soft_dep = Service(id=soft_id, service_id="recommendation-service")

        edge_hard = ServiceDependency(
            source_service_id=service_id,
            target_service_id=hard_id,
            criticality=DependencyCriticality.HARD,
            communication_mode=CommunicationMode.SYNC,
        )
        edge_soft = ServiceDependency(
            source_service_id=service_id,
            target_service_id=soft_id,
            criticality=DependencyCriticality.SOFT,
            communication_mode=CommunicationMode.ASYNC,
        )

        mock_graph_traversal.get_subgraph.return_value = (
            [service, hard_dep, soft_dep],
            [edge_hard, edge_soft],
        )

        # Setup telemetry (only for hard dep and service itself)
        mock_telemetry.get_availability_sli.side_effect = [
            AvailabilitySliData(
                service_id="payment-service",
                good_events=99950,
                total_events=100000,
                availability_ratio=0.9995,
                window_start=datetime.now(timezone.utc),
                window_end=datetime.now(timezone.utc),
                sample_count=100000,
            ),
            AvailabilitySliData(
                service_id="checkout-service",
                good_events=99920,
                total_events=100000,
                availability_ratio=0.9992,
                window_start=datetime.now(timezone.utc),
                window_end=datetime.now(timezone.utc),
                sample_count=100000,
            ),
        ]

        # Execute
        request = ErrorBudgetBreakdownRequest(service_id="checkout-service")
        result = await use_case.execute(request)

        # Should succeed, soft dep ignored
        assert result is not None

        # Verify budget analyzer was called with only 1 dependency (hard)
        mock_budget_analyzer.compute_breakdown.assert_called_once()
        call_args = mock_budget_analyzer.compute_breakdown.call_args
        deps = call_args.kwargs["dependencies"]
        assert len(deps) == 1
        assert deps[0].service_name == "payment-service"

    async def test_uses_depth_1_only(
        self, use_case, mock_service_repo, mock_graph_traversal, mock_telemetry
    ) -> None:
        """Test that only direct dependencies (depth=1) are retrieved."""
        # Setup service
        service_id = uuid4()
        service = Service(id=service_id, service_id="checkout-service")
        mock_service_repo.get_by_service_id.return_value = service

        # Setup dependency
        dep_id = uuid4()
        dep = Service(id=dep_id, service_id="payment-service")

        edge = ServiceDependency(
            source_service_id=service_id,
            target_service_id=dep_id,
            criticality=DependencyCriticality.HARD,
            communication_mode=CommunicationMode.SYNC,
        )

        mock_graph_traversal.get_subgraph.return_value = (
            [service, dep],
            [edge],
        )

        mock_telemetry.get_availability_sli.side_effect = [
            AvailabilitySliData(
                service_id="payment-service",
                good_events=99950,
                total_events=100000,
                availability_ratio=0.9995,
                window_start=datetime.now(timezone.utc),
                window_end=datetime.now(timezone.utc),
                sample_count=100000,
            ),
            AvailabilitySliData(
                service_id="checkout-service",
                good_events=99920,
                total_events=100000,
                availability_ratio=0.9992,
                window_start=datetime.now(timezone.utc),
                window_end=datetime.now(timezone.utc),
                sample_count=100000,
            ),
        ]

        # Execute
        request = ErrorBudgetBreakdownRequest(service_id="checkout-service")
        await use_case.execute(request)

        # Verify depth=1 was used
        mock_graph_traversal.get_subgraph.assert_called_once()
        call_args = mock_graph_traversal.get_subgraph.call_args
        assert call_args.kwargs["max_depth"] == 1

    async def test_missing_telemetry_defaults_to_conservative(
        self, use_case, mock_service_repo, mock_graph_traversal, mock_telemetry
    ) -> None:
        """Test that missing telemetry data defaults to 99.9%."""
        # Setup service
        service_id = uuid4()
        service = Service(id=service_id, service_id="checkout-service")
        mock_service_repo.get_by_service_id.return_value = service

        # Setup dependency
        dep_id = uuid4()
        dep = Service(id=dep_id, service_id="payment-service")

        edge = ServiceDependency(
            source_service_id=service_id,
            target_service_id=dep_id,
            criticality=DependencyCriticality.HARD,
            communication_mode=CommunicationMode.SYNC,
        )

        mock_graph_traversal.get_subgraph.return_value = (
            [service, dep],
            [edge],
        )

        # Setup telemetry to return None (no data)
        mock_telemetry.get_availability_sli.side_effect = [None, None]

        # Execute
        request = ErrorBudgetBreakdownRequest(service_id="checkout-service")
        result = await use_case.execute(request)

        # Should still succeed with defaults
        assert result is not None
        assert result.service_id == "checkout-service"

    async def test_no_hard_dependencies_only_self_consumption(
        self,
        use_case,
        mock_service_repo,
        mock_graph_traversal,
        mock_telemetry,
        mock_budget_analyzer,
    ) -> None:
        """Test breakdown when service has no hard sync dependencies."""
        # Setup service
        service_id = uuid4()
        service = Service(id=service_id, service_id="isolated-service")
        mock_service_repo.get_by_service_id.return_value = service

        # Setup only soft dependency
        soft_id = uuid4()
        soft_dep = Service(id=soft_id, service_id="cache-service")

        edge_soft = ServiceDependency(
            source_service_id=service_id,
            target_service_id=soft_id,
            criticality=DependencyCriticality.SOFT,
            communication_mode=CommunicationMode.ASYNC,
        )

        mock_graph_traversal.get_subgraph.return_value = (
            [service, soft_dep],
            [edge_soft],
        )

        # Setup telemetry
        mock_telemetry.get_availability_sli.return_value = (
            AvailabilitySliData(
                service_id="isolated-service",
                good_events=99920,
                total_events=100000,
                availability_ratio=0.9992,
                window_start=datetime.now(timezone.utc),
                window_end=datetime.now(timezone.utc),
                sample_count=100000,
            )
        )

        # Setup budget breakdown with only self consumption
        mock_budget_analyzer.compute_breakdown.return_value = (
            ErrorBudgetBreakdown(
                service_id="isolated-service",
                slo_target=99.9,
                total_error_budget_minutes=43.2,
                self_consumption_pct=8.0,
                dependency_assessments=[],
            )
        )

        # Execute
        request = ErrorBudgetBreakdownRequest(service_id="isolated-service")
        result = await use_case.execute(request)

        # Assertions
        assert result is not None
        assert result.service_id == "isolated-service"
        assert len(result.dependency_risks) == 0
        assert result.self_consumption_pct == 8.0

    async def test_uses_custom_slo_target(
        self,
        use_case,
        mock_service_repo,
        mock_graph_traversal,
        mock_telemetry,
        mock_budget_analyzer,
    ) -> None:
        """Test that custom SLO target is used."""
        # Setup service and dependencies
        service_id = uuid4()
        service = Service(id=service_id, service_id="checkout-service")
        mock_service_repo.get_by_service_id.return_value = service

        dep_id = uuid4()
        dep = Service(id=dep_id, service_id="payment-service")

        edge = ServiceDependency(
            source_service_id=service_id,
            target_service_id=dep_id,
            criticality=DependencyCriticality.HARD,
            communication_mode=CommunicationMode.SYNC,
        )

        mock_graph_traversal.get_subgraph.return_value = (
            [service, dep],
            [edge],
        )

        mock_telemetry.get_availability_sli.side_effect = [
            AvailabilitySliData(
                service_id="payment-service",
                good_events=99950,
                total_events=100000,
                availability_ratio=0.9995,
                window_start=datetime.now(timezone.utc),
                window_end=datetime.now(timezone.utc),
                sample_count=100000,
            ),
            AvailabilitySliData(
                service_id="checkout-service",
                good_events=99920,
                total_events=100000,
                availability_ratio=0.9992,
                window_start=datetime.now(timezone.utc),
                window_end=datetime.now(timezone.utc),
                sample_count=100000,
            ),
        ]

        # Execute with custom target
        request = ErrorBudgetBreakdownRequest(
            service_id="checkout-service", slo_target_pct=99.95
        )
        await use_case.execute(request)

        # Verify budget analyzer was called with correct target
        mock_budget_analyzer.compute_breakdown.assert_called_once()
        call_args = mock_budget_analyzer.compute_breakdown.call_args
        assert call_args.kwargs["slo_target"] == 99.95
