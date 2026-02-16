"""Domain entities for FR-3 Dependency-Aware Constraint Propagation.

This module defines the core entities used for constraint analysis:
- ExternalProviderProfile: External dependency reliability characteristics
- DependencyRiskAssessment: Per-dependency error budget impact
- UnachievableWarning: Warning when SLO target is mathematically impossible
- ErrorBudgetBreakdown: Per-dependency error budget consumption
- ConstraintAnalysis: Complete constraint propagation analysis result
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4


class RiskLevel(str, Enum):
    """Risk level for a dependency's error budget consumption."""

    LOW = "low"  # < 20% error budget consumption
    MODERATE = "moderate"  # 20-30% error budget consumption
    HIGH = "high"  # > 30% error budget consumption


class ServiceType(str, Enum):
    """Service type classification."""

    INTERNAL = "internal"
    EXTERNAL = "external"


@dataclass
class ExternalProviderProfile:
    """Profile for an external dependency's reliability characteristics.

    Captures both the published SLA and observed availability to compute
    the adaptive buffer per TRD 3.3.

    Attributes:
        service_id: Business identifier of the external service
        service_uuid: Internal UUID of the external service
        published_sla: Published SLA as ratio (e.g., 0.9999 for 99.99%)
        observed_availability: Measured availability as ratio
        observation_window_days: Number of days of observation data
    """

    service_id: str
    service_uuid: UUID
    published_sla: float | None = None  # e.g., 0.9999 (99.99%)
    observed_availability: float | None = None
    observation_window_days: int = 0

    @property
    def effective_availability(self) -> float:
        """Compute effective availability using adaptive buffer strategy.

        Rules per TRD 3.3:
        - If both observed and published available:
          min(observed, published_adjusted) where published_adjusted = 1 - (1-published)*11
        - If only observed available: use observed
        - If only published available: use published × adjustment
        - If neither available: default to 0.999 (99.9%)

        Returns:
            Effective availability as ratio (0.0 to 1.0)
        """
        published_adjusted = (
            self._compute_pessimistic_adjustment(self.published_sla)
            if self.published_sla is not None
            else None
        )

        if self.observed_availability is not None and published_adjusted is not None:
            return min(self.observed_availability, published_adjusted)
        elif self.observed_availability is not None:
            return self.observed_availability
        elif published_adjusted is not None:
            return published_adjusted
        else:
            return 0.999  # Conservative default

    @staticmethod
    def _compute_pessimistic_adjustment(published_sla: float) -> float:
        """Apply 10x pessimistic adjustment to published SLA.

        Formula: published_adjusted = 1 - (1 - published) * 11
        Example: 99.99% → 1 - (0.0001 * 11) = 1 - 0.0011 = 0.9989 (99.89%)

        Args:
            published_sla: Published SLA as ratio (0.0 to 1.0)

        Returns:
            Adjusted SLA as ratio, floored at 0.0
        """
        unavailability = 1.0 - published_sla
        adjusted = 1.0 - unavailability * 11  # Add 10x unavailability margin
        return max(adjusted, 0.0)  # Floor at 0.0


@dataclass
class DependencyRiskAssessment:
    """Risk assessment for a single dependency's error budget impact.

    Attributes:
        service_id: Business identifier of the dependency
        service_uuid: Internal UUID of the dependency
        availability: Effective availability used for computation (0.0-1.0)
        error_budget_consumption_pct: Percentage of parent's error budget consumed (0-100+)
        risk_level: Computed risk level based on consumption
        is_external: Whether this is an external dependency
        communication_mode: sync/async
        criticality: hard/soft/degraded
        published_sla: Published SLA as ratio (external only)
        observed_availability: Measured availability as ratio
        effective_availability_note: Explanation of how effective availability was computed
    """

    service_id: str
    service_uuid: UUID
    availability: float
    error_budget_consumption_pct: float  # 0.0 to 100.0+ (can exceed 100)
    risk_level: RiskLevel
    is_external: bool = False
    communication_mode: str = "sync"
    criticality: str = "hard"
    published_sla: float | None = None
    observed_availability: float | None = None
    effective_availability_note: str = ""

    def __post_init__(self):
        """Validate error budget consumption percentage."""
        if self.error_budget_consumption_pct < 0.0:
            raise ValueError(
                f"error_budget_consumption_pct must be >= 0.0, "
                f"got: {self.error_budget_consumption_pct}"
            )


@dataclass
class UnachievableWarning:
    """Warning when a desired SLO target is mathematically unachievable.

    Generated when composite_bound < desired_target.

    Attributes:
        desired_target: Desired SLO target as percentage (e.g., 99.99)
        composite_bound: Composite availability bound as percentage (e.g., 99.70)
        gap: Gap between desired and composite (desired - composite)
        message: Human-readable warning
        remediation_guidance: Actionable advice
        required_dep_availability: What each dep would need (10x rule) as percentage
    """

    desired_target: float  # e.g., 99.99
    composite_bound: float  # e.g., 99.70
    gap: float  # e.g., 0.29
    message: str
    remediation_guidance: str
    required_dep_availability: float  # e.g., 99.9975


@dataclass
class ErrorBudgetBreakdown:
    """Per-dependency breakdown of error budget consumption for a service.

    Attributes:
        service_id: Business identifier of the service being analyzed
        slo_target: The SLO target used for budget computation (e.g., 99.9)
        total_error_budget_minutes: Monthly error budget in minutes
        self_consumption_pct: Percentage of budget consumed by the service itself
        dependency_assessments: Per-dependency risk assessments
        high_risk_dependencies: Service IDs consuming >30% of budget
        total_dependency_consumption_pct: Sum of all dependency consumption
    """

    service_id: str
    slo_target: float
    total_error_budget_minutes: float
    self_consumption_pct: float
    dependency_assessments: list[DependencyRiskAssessment] = field(default_factory=list)
    high_risk_dependencies: list[str] = field(default_factory=list)  # service_ids
    total_dependency_consumption_pct: float = 0.0


@dataclass
class ConstraintAnalysis:
    """Complete constraint propagation analysis result for a service.

    This is the primary output entity for FR-3, combining composite bounds,
    error budget breakdown, and unachievability detection.

    Attributes:
        service_id: Business identifier of the service
        service_uuid: Internal UUID of the service
        composite_availability_bound: Composite bound as ratio (0.0-1.0)
        composite_availability_bound_pct: Composite bound as percentage (0.0-100.0)
        error_budget_breakdown: Per-dependency error budget breakdown
        unachievable_warning: Warning if SLO is unachievable (None if achievable)
        soft_dependency_risks: Service IDs of soft/degraded dependencies
        scc_supernodes: List of circular dependency paths
        dependency_chain_depth: Maximum depth of dependency chain analyzed
        total_hard_dependencies: Count of hard sync dependencies
        total_soft_dependencies: Count of soft/degraded dependencies
        total_external_dependencies: Count of external dependencies
        id: Unique analysis ID
        analyzed_at: Timestamp of analysis
        lookback_days: Lookback window used for telemetry data
    """

    service_id: str
    service_uuid: UUID
    composite_availability_bound: float  # 0.0 to 1.0 (ratio)
    composite_availability_bound_pct: float  # 0.0 to 100.0 (percentage)
    error_budget_breakdown: ErrorBudgetBreakdown
    unachievable_warning: UnachievableWarning | None = None
    soft_dependency_risks: list[str] = field(default_factory=list)  # service_ids
    scc_supernodes: list[list[str]] = field(default_factory=list)  # cycle paths
    dependency_chain_depth: int = 0
    total_hard_dependencies: int = 0
    total_soft_dependencies: int = 0
    total_external_dependencies: int = 0

    # Metadata
    id: UUID = field(default_factory=uuid4)
    analyzed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    lookback_days: int = 30

    @property
    def is_achievable(self) -> bool:
        """Whether the SLO target is achievable given constraints.

        Returns:
            True if achievable, False if unachievable_warning is present
        """
        return self.unachievable_warning is None

    @property
    def has_high_risk_dependencies(self) -> bool:
        """Whether any dependency consumes >30% of error budget.

        Returns:
            True if any high-risk dependencies exist
        """
        return len(self.error_budget_breakdown.high_risk_dependencies) > 0
