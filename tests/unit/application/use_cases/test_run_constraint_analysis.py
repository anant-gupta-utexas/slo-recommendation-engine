"""Unit tests for RunConstraintAnalysisUseCase."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from src.application.dtos.constraint_analysis_dto import ConstraintAnalysisRequest
from src.application.use_cases.run_constraint_analysis import (
    RunConstraintAnalysisUseCase,
)
from src.domain.entities.circular_dependency_alert import CircularDependencyAlert
from src.domain.entities.constraint_analysis import (
    DependencyRiskAssessment,
    ErrorBudgetBreakdown,
    ExternalProviderProfile,
    RiskLevel,
    ServiceType,
    UnachievableWarning,
)
from src.domain.entities.service import Service
from src.domain.entities.service_dependency import (
    CommunicationMode,
    DependencyCriticality,
    ServiceDependency,
)
from src.domain.entities.sli_data import AvailabilitySliData
from src.domain.services.composite_availability_service import CompositeResult


def create_avail_sli(service_id: str, availability: float) -> AvailabilitySliData:
    """Helper to create AvailabilitySliData with valid time windows."""
    now = datetime.now(timezone.utc)
    return AvailabilitySliData(
        service_id=service_id,
        good_events=int(availability * 100000),
        total_events=100000,
        availability_ratio=availability,
        window_start=now - timedelta(days=30),
        window_end=now,
        sample_count=100000,
    )


def create_external_service(service_id: str, published_sla: float) -> Service:
    """Helper to create an external service with service_type attribute."""
    service = Service(id=uuid4(), service_id=service_id)
    # Manually set attributes that don't exist in dataclass yet
    service.service_type = ServiceType.EXTERNAL
    service.published_sla = published_sla
    return service


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
def mock_alert_repo():
    """Mock alert repository."""
    return AsyncMock()


@pytest.fixture
def mock_graph_traversal():
    """Mock graph traversal service."""
    return AsyncMock()


@pytest.fixture
def mock_composite():
    """Mock composite availability service."""
    mock = Mock()
    mock.compute_composite_bound.return_value = CompositeResult(
        composite_bound=0.9970, bottleneck_service_id=None
    )
    return mock


@pytest.fixture
def mock_external_buffer():
    """Mock external buffer service."""
    mock = Mock()
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
    mock = Mock()
    mock.compute_breakdown.return_value = ErrorBudgetBreakdown(
        service_id="checkout-service",
        slo_target=99.9,
        total_error_budget_minutes=43.2,
        self_consumption_pct=8.0,
    )
    return mock


@pytest.fixture
def mock_unachievable_detector():
    """Mock unachievable SLO detector."""
    mock = Mock()
    mock.check.return_value = None  # Default: achievable
    return mock


@pytest.fixture
def use_case(
    mock_service_repo,
    mock_dependency_repo,
    mock_telemetry,
    mock_alert_repo,
    mock_graph_traversal,
    mock_composite,
    mock_external_buffer,
    mock_budget_analyzer,
    mock_unachievable_detector,
):
    """Create use case instance with mocked dependencies."""
    return RunConstraintAnalysisUseCase(
        service_repository=mock_service_repo,
        dependency_repository=mock_dependency_repo,
        telemetry_service=mock_telemetry,
        alert_repository=mock_alert_repo,
        graph_traversal_service=mock_graph_traversal,
        composite_service=mock_composite,
        external_buffer_service=mock_external_buffer,
        error_budget_analyzer=mock_budget_analyzer,
        unachievable_detector=mock_unachievable_detector,
    )


@pytest.mark.asyncio
class TestRunConstraintAnalysisUseCase:
    """Tests for RunConstraintAnalysisUseCase."""

    async def test_service_not_found_returns_none(
        self, use_case, mock_service_repo
    ) -> None:
        """Test that None is returned when service doesn't exist."""
        mock_service_repo.get_by_service_id.return_value = None

        request = ConstraintAnalysisRequest(service_id="nonexistent-service")
        result = await use_case.execute(request)

        assert result is None
        mock_service_repo.get_by_service_id.assert_called_once_with(
            "nonexistent-service"
        )

    async def test_no_dependencies_raises_value_error(
        self, use_case, mock_service_repo, mock_graph_traversal
    ) -> None:
        """Test that ValueError is raised when service has no dependencies."""
        service = Service(id=uuid4(), service_id="isolated-service")
        mock_service_repo.get_by_service_id.return_value = service
        mock_graph_traversal.get_subgraph.return_value = ([], [])  # No edges

        request = ConstraintAnalysisRequest(service_id="isolated-service")

        with pytest.raises(
            ValueError, match="has no dependencies registered"
        ):
            await use_case.execute(request)

    async def test_happy_path_with_internal_dependencies(
        self,
        use_case,
        mock_service_repo,
        mock_graph_traversal,
        mock_telemetry,
        mock_alert_repo,
        mock_composite,
        mock_budget_analyzer,
        mock_unachievable_detector,
    ) -> None:
        """Test successful analysis with internal dependencies."""
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
            create_avail_sli("payment-service", 0.9995),
            create_avail_sli("inventory-service", 0.9990),
            create_avail_sli("checkout-service", 0.9992),
        ]

        # Setup composite result
        mock_composite.compute_composite_bound.return_value = CompositeResult(
            composite_bound=0.9977
        )

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

        # Setup unachievable detector (achievable)
        mock_unachievable_detector.check.return_value = None

        # Setup alerts (no cycles)
        mock_alert_repo.list_by_status.return_value = []

        # Execute
        request = ConstraintAnalysisRequest(
            service_id="checkout-service", lookback_days=30, max_depth=3
        )
        result = await use_case.execute(request)

        # Assertions
        assert result is not None
        assert result.service_id == "checkout-service"
        assert abs(result.composite_availability_bound_pct - 99.77) < 0.01
        assert result.is_achievable is True
        assert result.total_hard_dependencies == 2
        assert result.total_soft_dependencies == 0
        assert result.total_external_dependencies == 0
        assert result.lookback_days == 30

    async def test_external_dependency_uses_adaptive_buffer(
        self,
        use_case,
        mock_service_repo,
        mock_graph_traversal,
        mock_telemetry,
        mock_alert_repo,
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
            create_avail_sli("external-payment-api", 0.9960),
            create_avail_sli("checkout-service", 0.9992),
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

        mock_alert_repo.list_by_status.return_value = []

        # Execute
        request = ConstraintAnalysisRequest(service_id="checkout-service")
        result = await use_case.execute(request)

        # Verify external buffer was called
        assert result is not None
        mock_external_buffer.build_profile.assert_called_once()
        mock_external_buffer.compute_effective_availability.assert_called_once_with(
            profile
        )
        assert result.total_external_dependencies == 1

    async def test_missing_telemetry_defaults_to_conservative(
        self,
        use_case,
        mock_service_repo,
        mock_graph_traversal,
        mock_telemetry,
        mock_alert_repo,
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

        mock_alert_repo.list_by_status.return_value = []

        # Execute
        request = ConstraintAnalysisRequest(service_id="checkout-service")
        result = await use_case.execute(request)

        # Should still succeed with defaults
        assert result is not None
        assert result.service_id == "checkout-service"

    async def test_unachievable_slo_includes_warning(
        self,
        use_case,
        mock_service_repo,
        mock_graph_traversal,
        mock_telemetry,
        mock_alert_repo,
        mock_unachievable_detector,
    ) -> None:
        """Test that unachievable SLO produces warning in response."""
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
            create_avail_sli("payment-service", 0.9950),
            create_avail_sli("checkout-service", 0.9992),
        ]

        # Setup unachievable warning
        warning = UnachievableWarning(
            desired_target=99.99,
            composite_bound=99.70,
            gap=0.29,
            message="The desired target of 99.99% is unachievable.",
            remediation_guidance="Consider adding redundant paths.",
            required_dep_availability=99.9975,
        )
        mock_unachievable_detector.check.return_value = warning

        mock_alert_repo.list_by_status.return_value = []

        # Execute with high target
        request = ConstraintAnalysisRequest(
            service_id="checkout-service", desired_target_pct=99.99
        )
        result = await use_case.execute(request)

        # Assertions
        assert result is not None
        assert result.is_achievable is False
        assert result.unachievable_warning is not None
        assert result.unachievable_warning.desired_target_pct == 99.99
        assert "unachievable" in result.unachievable_warning.message.lower()

    async def test_soft_dependencies_excluded_from_composite(
        self,
        use_case,
        mock_service_repo,
        mock_graph_traversal,
        mock_telemetry,
        mock_alert_repo,
    ) -> None:
        """Test that soft dependencies are listed but excluded from composite."""
        # Setup service
        service_id = uuid4()
        service = Service(id=service_id, service_id="checkout-service")
        mock_service_repo.get_by_service_id.return_value = service

        # Setup dependencies: 1 hard, 1 soft
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

        mock_telemetry.get_availability_sli.side_effect = [
            create_avail_sli("payment-service", 0.9995),
            create_avail_sli("checkout-service", 0.9992),
        ]

        mock_alert_repo.list_by_status.return_value = []

        # Execute
        request = ConstraintAnalysisRequest(service_id="checkout-service")
        result = await use_case.execute(request)

        # Assertions
        assert result is not None
        assert result.total_hard_dependencies == 1
        assert result.total_soft_dependencies == 1
        assert "recommendation-service" in result.soft_dependency_risks

    async def test_circular_dependencies_reported(
        self,
        use_case,
        mock_service_repo,
        mock_graph_traversal,
        mock_telemetry,
        mock_alert_repo,
    ) -> None:
        """Test that circular dependency cycles are reported."""
        # Setup service
        service_id = uuid4()
        service = Service(id=service_id, service_id="service-a")
        mock_service_repo.get_by_service_id.return_value = service

        # Setup dependency
        dep_id = uuid4()
        dep = Service(id=dep_id, service_id="service-b")

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
            create_avail_sli("service-b", 0.9990),
            create_avail_sli("service-a", 0.9992),
        ]

        # Setup circular dependency alert
        from src.domain.entities.circular_dependency_alert import AlertStatus
        alert = CircularDependencyAlert(
            id=uuid4(),
            cycle_path=["service-a", "service-b", "service-c", "service-a"],
            status=AlertStatus.OPEN,
        )
        mock_alert_repo.list_by_status.return_value = [alert]

        # Execute
        request = ConstraintAnalysisRequest(service_id="service-a")
        result = await use_case.execute(request)

        # Assertions
        assert result is not None
        assert len(result.scc_supernodes) == 1
        assert "service-a" in result.scc_supernodes[0]
        assert "service-b" in result.scc_supernodes[0]

    async def test_uses_desired_target_from_request(
        self,
        use_case,
        mock_service_repo,
        mock_graph_traversal,
        mock_telemetry,
        mock_alert_repo,
        mock_budget_analyzer,
    ) -> None:
        """Test that desired_target_pct from request is used."""
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
            create_avail_sli("payment-service", 0.9995),
            create_avail_sli("checkout-service", 0.9992),
        ]

        mock_alert_repo.list_by_status.return_value = []

        # Execute with custom target
        request = ConstraintAnalysisRequest(
            service_id="checkout-service", desired_target_pct=99.95
        )
        await use_case.execute(request)

        # Verify budget analyzer was called with correct target
        mock_budget_analyzer.compute_breakdown.assert_called_once()
        call_args = mock_budget_analyzer.compute_breakdown.call_args
        assert call_args.kwargs["slo_target"] == 99.95
