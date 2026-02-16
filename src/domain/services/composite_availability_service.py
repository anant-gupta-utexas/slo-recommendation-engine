"""Composite availability computation service.

This service computes composite availability bounds from dependency chains,
accounting for serial hard dependencies, parallel redundant paths, and soft dependencies.
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass
class DependencyWithAvailability:
    """A dependency with its historical availability.

    Attributes:
        service_id: UUID of the dependency service
        service_name: Human-readable name of the dependency
        availability: Historical availability (0.0-1.0)
        is_hard: True if synchronous/critical, False if soft/async
        is_redundant_group: True if part of a parallel redundant path
    """

    service_id: UUID
    service_name: str
    availability: float
    is_hard: bool = True
    is_redundant_group: bool = False

    def __post_init__(self):
        """Validate dependency availability constraints."""
        if not (0.0 <= self.availability <= 1.0):
            raise ValueError(
                f"Availability must be in [0.0, 1.0], got {self.availability}"
            )


@dataclass
class CompositeResult:
    """Result of composite availability computation.

    Attributes:
        composite_bound: Upper bound on achievable availability (0.0-1.0)
        bottleneck_service_id: UUID of the weakest dependency
        bottleneck_service_name: Name of the weakest dependency
        bottleneck_contribution: Description of bottleneck's impact
        per_dependency_contributions: Map of service_id to availability contribution
    """

    composite_bound: float
    bottleneck_service_id: UUID | None = None
    bottleneck_service_name: str | None = None
    bottleneck_contribution: str = ""
    per_dependency_contributions: dict[UUID, float] | None = None

    def __post_init__(self):
        """Validate composite result constraints."""
        if not (0.0 <= self.composite_bound <= 1.0):
            raise ValueError(
                f"Composite bound must be in [0.0, 1.0], got {self.composite_bound}"
            )


class CompositeAvailabilityService:
    """Computes composite availability bounds from dependency chains.

    Handles:
    - Serial hard dependencies: R_composite = R_self * R_dep1 * R_dep2
    - Parallel redundant paths: R = 1 - (1-R_primary)(1-R_fallback)
    - Soft dependencies: excluded from composite, noted as risk
    - SCCs (circular): weakest-link member used as supernode availability

    Mathematical foundation:
    - Serial reliability: R_total = R1 * R2 * ... * Rn
    - Parallel reliability: R_total = 1 - (1-R1)(1-R2)...(1-Rn)
    - Mixed: Apply parallel formula to redundant groups, then serial across groups
    """

    def compute_composite_bound(
        self,
        service_availability: float,
        dependencies: list[DependencyWithAvailability],
    ) -> CompositeResult:
        """Compute composite availability bound.

        Algorithm:
        1. Filter to hard dependencies only (soft deps excluded)
        2. Group by redundant paths (parallel) vs serial
        3. Compute parallel group reliabilities
        4. Compute final serial product: R_self * R_group1 * R_group2 * ...
        5. Identify bottleneck (lowest individual or group contribution)

        Args:
            service_availability: Historical availability of the service itself (0.0-1.0)
            dependencies: List of dependencies with their availabilities

        Returns:
            CompositeResult with bound, bottleneck info, and per-dep contributions

        Raises:
            ValueError: If service_availability is not in [0.0, 1.0]
        """
        if not (0.0 <= service_availability <= 1.0):
            raise ValueError(
                f"Service availability must be in [0.0, 1.0], got {service_availability}"
            )

        # Edge case: no dependencies
        if not dependencies:
            return CompositeResult(
                composite_bound=service_availability,
                bottleneck_service_id=None,
                bottleneck_service_name=None,
                bottleneck_contribution="No dependencies",
                per_dependency_contributions={},
            )

        # Filter to hard dependencies only
        hard_deps = [dep for dep in dependencies if dep.is_hard]
        soft_deps = [dep for dep in dependencies if not dep.is_hard]

        # Edge case: only soft dependencies
        if not hard_deps:
            return CompositeResult(
                composite_bound=service_availability,
                bottleneck_service_id=None,
                bottleneck_service_name=None,
                bottleneck_contribution=f"{len(soft_deps)} soft dependencies (excluded from bound)",
                per_dependency_contributions={},
            )

        # Group dependencies: redundant groups vs serial
        redundant_groups: list[list[DependencyWithAvailability]] = []
        serial_deps: list[DependencyWithAvailability] = []

        # Separate redundant from serial
        redundant_deps = [dep for dep in hard_deps if dep.is_redundant_group]
        serial_deps = [dep for dep in hard_deps if not dep.is_redundant_group]

        # For MVP: treat all redundant deps as a single parallel group
        # (Future: parse group IDs for multiple redundant groups)
        if redundant_deps:
            redundant_groups.append(redundant_deps)

        # Compute availability for each redundant group (parallel)
        group_availabilities: list[float] = []
        per_dep_contributions: dict[UUID, float] = {}

        for group in redundant_groups:
            # Parallel formula: R = 1 - (1-R1)(1-R2)...(1-Rn)
            unavailability_product = 1.0
            for dep in group:
                unavailability_product *= (1.0 - dep.availability)
                per_dep_contributions[dep.service_id] = dep.availability

            group_availability = 1.0 - unavailability_product
            group_availabilities.append(group_availability)

        # Track serial contributions
        for dep in serial_deps:
            per_dep_contributions[dep.service_id] = dep.availability

        # Compute final serial product: R_self * (serial deps) * (redundant groups)
        composite = service_availability

        # Multiply by all serial dependencies
        for dep in serial_deps:
            composite *= dep.availability

        # Multiply by all redundant group availabilities
        for group_avail in group_availabilities:
            composite *= group_avail

        # Identify bottleneck
        bottleneck_id, bottleneck_name, bottleneck_desc = self.identify_bottleneck(
            hard_deps, group_availabilities, redundant_groups
        )

        return CompositeResult(
            composite_bound=composite,
            bottleneck_service_id=bottleneck_id,
            bottleneck_service_name=bottleneck_name,
            bottleneck_contribution=bottleneck_desc,
            per_dependency_contributions=per_dep_contributions,
        )

    def identify_bottleneck(
        self,
        dependencies: list[DependencyWithAvailability],
        group_availabilities: list[float],
        redundant_groups: list[list[DependencyWithAvailability]],
    ) -> tuple[UUID | None, str | None, str]:
        """Identify the dependency contributing most to composite degradation.

        Bottleneck is the dependency (or redundant group) with the lowest availability.

        Args:
            dependencies: List of all hard dependencies
            group_availabilities: Computed availabilities for redundant groups
            redundant_groups: List of redundant dependency groups

        Returns:
            Tuple of (bottleneck_service_id, bottleneck_service_name, description)
        """
        if not dependencies:
            return None, None, "No hard dependencies"

        # Find minimum availability among serial dependencies
        serial_deps = [dep for dep in dependencies if not dep.is_redundant_group]
        min_serial_avail = min(
            (dep.availability for dep in serial_deps),
            default=1.0
        )

        # Find minimum availability among redundant groups
        min_group_avail = min(group_availabilities, default=1.0)

        # Compare and identify bottleneck
        if serial_deps and min_serial_avail <= min_group_avail:
            # Bottleneck is a serial dependency
            bottleneck = min(serial_deps, key=lambda d: d.availability)
            unavailability_pct = (1.0 - bottleneck.availability) * 100
            return (
                bottleneck.service_id,
                bottleneck.service_name,
                f"Single dependency at {bottleneck.availability:.4f} (contributes {unavailability_pct:.3f}% unavailability)"
            )
        elif redundant_groups:
            # Bottleneck is a redundant group
            min_group_idx = group_availabilities.index(min_group_avail)
            group = redundant_groups[min_group_idx]

            # Return the weakest member of the bottleneck group
            weakest = min(group, key=lambda d: d.availability)
            group_unavailability_pct = (1.0 - min_group_avail) * 100

            return (
                weakest.service_id,
                weakest.service_name,
                f"Redundant group at {min_group_avail:.4f} (contributes {group_unavailability_pct:.3f}% unavailability, {len(group)} replicas)"
            )
        else:
            return None, None, "No bottleneck identified"
