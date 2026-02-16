"""Unit tests for CompositeAvailabilityService."""

import pytest
from uuid import uuid4

from src.domain.services.composite_availability_service import (
    CompositeAvailabilityService,
    CompositeResult,
    DependencyWithAvailability,
)


class TestDependencyWithAvailability:
    """Test DependencyWithAvailability value object."""

    def test_create_dependency_valid(self):
        """Should create dependency with valid availability."""
        dep = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="payment-service",
            availability=0.999,
            is_hard=True,
            is_redundant_group=False,
        )
        assert dep.availability == 0.999
        assert dep.is_hard is True
        assert dep.is_redundant_group is False

    def test_create_dependency_defaults(self):
        """Should use default values for optional fields."""
        dep = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="auth-service",
            availability=0.9999,
        )
        assert dep.is_hard is True
        assert dep.is_redundant_group is False

    def test_create_dependency_invalid_availability_low(self):
        """Should reject availability below 0.0."""
        with pytest.raises(ValueError, match="Availability must be in"):
            DependencyWithAvailability(
                service_id=uuid4(),
                service_name="bad-service",
                availability=-0.01,
            )

    def test_create_dependency_invalid_availability_high(self):
        """Should reject availability above 1.0."""
        with pytest.raises(ValueError, match="Availability must be in"):
            DependencyWithAvailability(
                service_id=uuid4(),
                service_name="bad-service",
                availability=1.01,
            )

    def test_create_dependency_boundary_values(self):
        """Should accept boundary values 0.0 and 1.0."""
        dep_min = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="min-service",
            availability=0.0,
        )
        dep_max = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="max-service",
            availability=1.0,
        )
        assert dep_min.availability == 0.0
        assert dep_max.availability == 1.0


class TestCompositeResult:
    """Test CompositeResult value object."""

    def test_create_result_valid(self):
        """Should create result with valid composite bound."""
        result = CompositeResult(
            composite_bound=0.998,
            bottleneck_service_id=uuid4(),
            bottleneck_service_name="slow-service",
            bottleneck_contribution="Weakest link",
        )
        assert result.composite_bound == 0.998
        assert result.bottleneck_service_name == "slow-service"

    def test_create_result_invalid_bound_low(self):
        """Should reject composite bound below 0.0."""
        with pytest.raises(ValueError, match="Composite bound must be in"):
            CompositeResult(composite_bound=-0.01)

    def test_create_result_invalid_bound_high(self):
        """Should reject composite bound above 1.0."""
        with pytest.raises(ValueError, match="Composite bound must be in"):
            CompositeResult(composite_bound=1.01)


class TestCompositeAvailabilityService:
    """Test CompositeAvailabilityService."""

    @pytest.fixture
    def service(self):
        """Fixture for CompositeAvailabilityService."""
        return CompositeAvailabilityService()

    # Edge Cases

    def test_no_dependencies(self, service):
        """Should return service availability when no dependencies exist."""
        result = service.compute_composite_bound(
            service_availability=0.9995,
            dependencies=[],
        )
        assert result.composite_bound == 0.9995
        assert result.bottleneck_service_id is None
        assert result.bottleneck_service_name is None
        assert result.bottleneck_contribution == "No dependencies"
        assert result.per_dependency_contributions == {}

    def test_only_soft_dependencies(self, service):
        """Should ignore soft dependencies and return service availability."""
        soft_dep = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="cache-service",
            availability=0.95,
            is_hard=False,
        )
        result = service.compute_composite_bound(
            service_availability=0.999,
            dependencies=[soft_dep],
        )
        assert result.composite_bound == 0.999
        assert result.bottleneck_service_id is None
        assert "1 soft dependencies" in result.bottleneck_contribution

    def test_invalid_service_availability_low(self, service):
        """Should reject service availability below 0.0."""
        with pytest.raises(ValueError, match="Service availability must be in"):
            service.compute_composite_bound(
                service_availability=-0.01,
                dependencies=[],
            )

    def test_invalid_service_availability_high(self, service):
        """Should reject service availability above 1.0."""
        with pytest.raises(ValueError, match="Service availability must be in"):
            service.compute_composite_bound(
                service_availability=1.01,
                dependencies=[],
            )

    # Serial Hard Dependencies

    def test_single_hard_dependency(self, service):
        """Should compute serial product for single hard dependency."""
        dep_id = uuid4()
        dep = DependencyWithAvailability(
            service_id=dep_id,
            service_name="database",
            availability=0.9990,
            is_hard=True,
        )
        result = service.compute_composite_bound(
            service_availability=0.9995,
            dependencies=[dep],
        )
        # Expected: 0.9995 * 0.9990 = 0.9985005
        assert result.composite_bound == pytest.approx(0.9985005, rel=1e-6)
        assert result.bottleneck_service_id == dep_id
        assert result.bottleneck_service_name == "database"
        assert "0.9990" in result.bottleneck_contribution

    def test_multiple_serial_dependencies(self, service):
        """Should compute serial product for multiple hard dependencies."""
        dep1 = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="auth-service",
            availability=0.9999,
            is_hard=True,
        )
        dep2 = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="payment-service",
            availability=0.9990,
            is_hard=True,
        )
        dep3 = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="inventory-service",
            availability=0.9995,
            is_hard=True,
        )
        result = service.compute_composite_bound(
            service_availability=0.9998,
            dependencies=[dep1, dep2, dep3],
        )
        # Expected: 0.9998 * 0.9999 * 0.9990 * 0.9995 = 0.99820014
        assert result.composite_bound == pytest.approx(0.99820014, rel=1e-6)
        # Bottleneck should be payment-service (lowest at 0.9990)
        assert result.bottleneck_service_name == "payment-service"

    def test_serial_bottleneck_identification(self, service):
        """Should identify weakest serial dependency as bottleneck."""
        strong_dep = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="strong-service",
            availability=0.9999,
            is_hard=True,
        )
        weak_dep_id = uuid4()
        weak_dep = DependencyWithAvailability(
            service_id=weak_dep_id,
            service_name="weak-service",
            availability=0.95,
            is_hard=True,
        )
        result = service.compute_composite_bound(
            service_availability=0.9995,
            dependencies=[strong_dep, weak_dep],
        )
        assert result.bottleneck_service_id == weak_dep_id
        assert result.bottleneck_service_name == "weak-service"
        # Should mention contribution percentage
        assert "5.000%" in result.bottleneck_contribution  # (1 - 0.95) * 100

    # Parallel Redundant Dependencies

    def test_parallel_redundant_group(self, service):
        """Should compute parallel availability for redundant group."""
        replica1 = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="replica-1",
            availability=0.99,
            is_hard=True,
            is_redundant_group=True,
        )
        replica2 = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="replica-2",
            availability=0.99,
            is_hard=True,
            is_redundant_group=True,
        )
        result = service.compute_composite_bound(
            service_availability=0.9995,
            dependencies=[replica1, replica2],
        )
        # Parallel: R = 1 - (1-0.99)(1-0.99) = 1 - 0.0001 = 0.9999
        # Composite: 0.9995 * 0.9999 = 0.99940005
        assert result.composite_bound == pytest.approx(0.99940005, rel=1e-6)

    def test_parallel_three_replicas(self, service):
        """Should handle three replicas in parallel group."""
        replicas = [
            DependencyWithAvailability(
                service_id=uuid4(),
                service_name=f"replica-{i}",
                availability=0.95,
                is_hard=True,
                is_redundant_group=True,
            )
            for i in range(3)
        ]
        result = service.compute_composite_bound(
            service_availability=1.0,
            dependencies=replicas,
        )
        # Parallel: R = 1 - (1-0.95)^3 = 1 - 0.000125 = 0.999875
        assert result.composite_bound == pytest.approx(0.999875, rel=1e-6)
        assert "3 replicas" in result.bottleneck_contribution

    def test_parallel_bottleneck_identification(self, service):
        """Should identify weakest member of redundant group as bottleneck."""
        strong_replica = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="replica-strong",
            availability=0.999,
            is_hard=True,
            is_redundant_group=True,
        )
        weak_replica_id = uuid4()
        weak_replica = DependencyWithAvailability(
            service_id=weak_replica_id,
            service_name="replica-weak",
            availability=0.99,
            is_hard=True,
            is_redundant_group=True,
        )
        result = service.compute_composite_bound(
            service_availability=1.0,
            dependencies=[strong_replica, weak_replica],
        )
        # Bottleneck should be weakest member of group
        assert result.bottleneck_service_id == weak_replica_id
        assert result.bottleneck_service_name == "replica-weak"
        assert "Redundant group" in result.bottleneck_contribution

    # Mixed Serial and Parallel

    def test_mixed_serial_and_parallel(self, service):
        """Should correctly compute mixed serial and parallel dependencies."""
        serial_dep = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="database",
            availability=0.999,
            is_hard=True,
        )
        parallel_dep1 = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="cache-replica-1",
            availability=0.95,
            is_hard=True,
            is_redundant_group=True,
        )
        parallel_dep2 = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="cache-replica-2",
            availability=0.95,
            is_hard=True,
            is_redundant_group=True,
        )
        result = service.compute_composite_bound(
            service_availability=0.9999,
            dependencies=[serial_dep, parallel_dep1, parallel_dep2],
        )
        # Parallel group: 1 - (1-0.95)^2 = 0.9975
        # Serial: 0.9999 * 0.999 * 0.9975 = 0.996402849750
        assert result.composite_bound == pytest.approx(0.996402849750, rel=1e-6)

    def test_mixed_serial_soft_and_parallel(self, service):
        """Should exclude soft deps from composite calculation."""
        hard_dep = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="database",
            availability=0.999,
            is_hard=True,
        )
        soft_dep = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="analytics",
            availability=0.90,
            is_hard=False,
        )
        parallel_dep1 = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="cache-1",
            availability=0.98,
            is_hard=True,
            is_redundant_group=True,
        )
        parallel_dep2 = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="cache-2",
            availability=0.98,
            is_hard=True,
            is_redundant_group=True,
        )
        result = service.compute_composite_bound(
            service_availability=0.9995,
            dependencies=[hard_dep, soft_dep, parallel_dep1, parallel_dep2],
        )
        # Soft dep should be ignored
        # Parallel: 1 - (1-0.98)^2 = 0.9996
        # Serial: 0.9995 * 0.999 * 0.9996 = 0.99810205
        assert result.composite_bound == pytest.approx(0.99810205, rel=1e-6)

    # Extreme Scenarios

    def test_very_low_dependency_availability(self, service):
        """Should handle very low dependency availability."""
        weak_dep = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="flaky-service",
            availability=0.50,
            is_hard=True,
        )
        result = service.compute_composite_bound(
            service_availability=0.9999,
            dependencies=[weak_dep],
        )
        # 0.9999 * 0.50 = 0.49995
        assert result.composite_bound == pytest.approx(0.49995, rel=1e-6)
        assert "50.000%" in result.bottleneck_contribution

    def test_zero_availability_dependency(self, service):
        """Should handle zero availability dependency."""
        dead_dep = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="dead-service",
            availability=0.0,
            is_hard=True,
        )
        result = service.compute_composite_bound(
            service_availability=0.9999,
            dependencies=[dead_dep],
        )
        assert result.composite_bound == 0.0

    def test_perfect_availability_dependency(self, service):
        """Should handle perfect (1.0) availability dependency."""
        perfect_dep = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="perfect-service",
            availability=1.0,
            is_hard=True,
        )
        result = service.compute_composite_bound(
            service_availability=0.9995,
            dependencies=[perfect_dep],
        )
        assert result.composite_bound == 0.9995

    def test_many_serial_dependencies(self, service):
        """Should handle many serial dependencies (realistic chain)."""
        # Simulate 10 dependencies at 99.9% each
        deps = [
            DependencyWithAvailability(
                service_id=uuid4(),
                service_name=f"service-{i}",
                availability=0.999,
                is_hard=True,
            )
            for i in range(10)
        ]
        result = service.compute_composite_bound(
            service_availability=0.999,
            dependencies=deps,
        )
        # 0.999^11 ≈ 0.989054835
        assert result.composite_bound == pytest.approx(0.989054835, rel=1e-5)

    def test_per_dependency_contributions(self, service):
        """Should track per-dependency contributions."""
        dep1_id = uuid4()
        dep2_id = uuid4()
        dep1 = DependencyWithAvailability(
            service_id=dep1_id,
            service_name="service-1",
            availability=0.999,
            is_hard=True,
        )
        dep2 = DependencyWithAvailability(
            service_id=dep2_id,
            service_name="service-2",
            availability=0.998,
            is_hard=True,
        )
        result = service.compute_composite_bound(
            service_availability=0.9995,
            dependencies=[dep1, dep2],
        )
        assert result.per_dependency_contributions is not None
        assert result.per_dependency_contributions[dep1_id] == 0.999
        assert result.per_dependency_contributions[dep2_id] == 0.998

    def test_bottleneck_with_equal_availability(self, service):
        """Should handle bottleneck identification when multiple deps have same availability."""
        dep1 = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="service-1",
            availability=0.995,
            is_hard=True,
        )
        dep2 = DependencyWithAvailability(
            service_id=uuid4(),
            service_name="service-2",
            availability=0.995,
            is_hard=True,
        )
        result = service.compute_composite_bound(
            service_availability=0.999,
            dependencies=[dep1, dep2],
        )
        # Either dep1 or dep2 should be identified (deterministic based on list order)
        assert result.bottleneck_service_name in ["service-1", "service-2"]
        assert "0.9950" in result.bottleneck_contribution
