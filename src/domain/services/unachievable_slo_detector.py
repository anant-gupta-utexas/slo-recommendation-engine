"""Unachievable SLO detection service for FR-3.

Detects when a desired SLO target is mathematically impossible given dependency availability.
"""

from src.domain.entities.constraint_analysis import UnachievableWarning


class UnachievableSloDetector:
    """Detects unachievable SLO targets based on composite availability bounds.

    Uses the "10x rule": each dependency should have 10x better availability
    than the service's error budget allows. For example, with 3 hard dependencies:
    - Service SLO: 99.99% (0.01% error budget)
    - Per-dependency allocation: 0.01% / 4 = 0.0025%
    - Required dep availability: 1 - 0.0025% = 99.9975%
    """

    def check(
        self,
        desired_target_pct: float,
        composite_bound: float,
        hard_dependency_count: int,
    ) -> UnachievableWarning | None:
        """Check if desired SLO target is achievable given composite bound.

        Args:
            desired_target_pct: Desired SLO target as percentage (e.g., 99.99)
            composite_bound: Composite availability bound as ratio (0.0-1.0)
            hard_dependency_count: Number of hard sync dependencies

        Returns:
            UnachievableWarning if target is unachievable, None if achievable
        """
        desired_target_ratio = desired_target_pct / 100.0

        # Achievable: composite bound meets or exceeds desired target (with small tolerance)
        # Use tolerance of 1e-9 to handle floating point comparison
        if composite_bound > desired_target_ratio or abs(composite_bound - desired_target_ratio) < 1e-9:
            return None

        # Unachievable: compute gap and generate warning
        composite_bound_pct = composite_bound * 100.0
        gap = desired_target_pct - composite_bound_pct

        required_dep_availability_pct = self.compute_required_dep_availability(
            desired_target_pct, hard_dependency_count
        )

        message = self.generate_warning_message(desired_target_pct, composite_bound_pct)

        guidance = self.generate_remediation_guidance(
            desired_target_pct, required_dep_availability_pct, hard_dependency_count
        )

        return UnachievableWarning(
            desired_target=desired_target_pct,
            composite_bound=composite_bound_pct,
            gap=gap,
            message=message,
            remediation_guidance=guidance,
            required_dep_availability=required_dep_availability_pct,
        )

    def compute_required_dep_availability(
        self,
        desired_target_pct: float,
        hard_dependency_count: int,
    ) -> float:
        """Compute required dependency availability using the 10x rule.

        Formula: 1 - (1 - target/100) / (N + 1)
        where N is the number of hard dependencies.

        The denominator (N + 1) accounts for the service itself plus N dependencies.

        Examples:
        - 99.99% with 0 deps → 99.99% (target itself)
        - 99.99% with 3 deps → 1 - 0.0001/4 = 1 - 0.000025 = 99.9975%

        Args:
            desired_target_pct: Desired SLO target as percentage (e.g., 99.99)
            hard_dependency_count: Number of hard sync dependencies

        Returns:
            Required dependency availability as percentage
        """
        # Edge case: no dependencies → required = target itself
        if hard_dependency_count == 0:
            return desired_target_pct

        target_ratio = desired_target_pct / 100.0
        error_budget = 1.0 - target_ratio

        # Allocate error budget: service + N dependencies = N+1 components
        per_component_budget = error_budget / (hard_dependency_count + 1)

        # Required availability = 1 - allocated error budget
        required_ratio = 1.0 - per_component_budget
        return required_ratio * 100.0

    def generate_warning_message(
        self,
        desired_target_pct: float,
        composite_bound_pct: float,
    ) -> str:
        """Generate warning message for unachievable SLO.

        Format per TRD: "The desired target of X% is unachievable. Composite
        availability bound is Y% given current dependency chain."

        Args:
            desired_target_pct: Desired SLO target as percentage
            composite_bound_pct: Composite availability bound as percentage

        Returns:
            Human-readable warning message
        """
        return (
            f"The desired target of {desired_target_pct}% is unachievable. "
            f"Composite availability bound is {composite_bound_pct:.2f}% "
            f"given current dependency chain."
        )

    def generate_remediation_guidance(
        self,
        desired_target_pct: float,
        required_pct: float,
        n_hard_deps: int,
    ) -> str:
        """Generate actionable remediation guidance.

        Provides 3 concrete suggestions:
        1. Add redundant paths for critical dependencies
        2. Convert some sync calls to async (removes from critical path)
        3. Relax the target to be more realistic

        Args:
            desired_target_pct: Desired SLO target as percentage
            required_pct: Required dependency availability as percentage
            n_hard_deps: Number of hard sync dependencies

        Returns:
            Multi-line remediation guidance string
        """
        lines = [
            "Suggested remediations:",
            "1. Add redundant paths: Deploy replicas for critical dependencies to achieve parallel availability.",
            f"2. Convert to async: Move {n_hard_deps} hard sync dependencies to async/queue-based communication.",
            f"3. Relax target: Consider a more achievable target given {n_hard_deps} hard dependencies (each needs {required_pct:.4f}% availability).",
        ]
        return "\n".join(lines)
