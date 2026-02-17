"""Application DTOs for constraint analysis and error budget breakdown.

These DTOs are used for communication between the application layer (use cases)
and the infrastructure layer (API routes). They follow dataclass conventions
and use the _pct suffix for percentage values.
"""

from dataclasses import dataclass, field


@dataclass
class ConstraintAnalysisRequest:
    """Request for full constraint propagation analysis.

    Attributes:
        service_id: Business identifier of the service to analyze
        desired_target_pct: Desired SLO target as percentage (e.g., 99.9)
                           If None, uses active SLO or 99.9% default
        lookback_days: Lookback window for telemetry data (days)
        max_depth: Maximum dependency chain depth to analyze
    """

    service_id: str
    desired_target_pct: float | None = None
    lookback_days: int = 30
    max_depth: int = 3


@dataclass
class ErrorBudgetBreakdownRequest:
    """Request for error budget breakdown analysis.

    Attributes:
        service_id: Business identifier of the service to analyze
        slo_target_pct: SLO target for budget calculation as percentage
        lookback_days: Lookback window for telemetry data (days)
    """

    service_id: str
    slo_target_pct: float = 99.9
    lookback_days: int = 30


@dataclass
class DependencyRiskDTO:
    """Risk assessment for a single dependency.

    Attributes:
        service_id: Business identifier of the dependency
        availability_pct: Effective availability as percentage (0-100)
        error_budget_consumption_pct: Percentage of error budget consumed (0-100+)
        risk_level: Risk classification ("low", "moderate", "high")
        is_external: Whether this is an external dependency
        communication_mode: Communication pattern ("sync", "async")
        criticality: Dependency type ("hard", "soft", "degraded")
        published_sla_pct: Published SLA as percentage (external only)
        observed_availability_pct: Measured availability as percentage
        effective_availability_note: Explanation of how availability was computed
    """

    service_id: str
    availability_pct: float
    error_budget_consumption_pct: float
    risk_level: str
    is_external: bool = False
    communication_mode: str = "sync"
    criticality: str = "hard"
    published_sla_pct: float | None = None
    observed_availability_pct: float | None = None
    effective_availability_note: str = ""


@dataclass
class UnachievableWarningDTO:
    """Warning when a desired SLO target is mathematically unachievable.

    Attributes:
        desired_target_pct: Desired SLO target as percentage
        composite_bound_pct: Composite availability bound as percentage
        gap_pct: Difference between desired and achievable (percentage points)
        message: Human-readable warning message
        remediation_guidance: Actionable advice for addressing the issue
        required_dep_availability_pct: What each dependency would need (10x rule)
    """

    desired_target_pct: float
    composite_bound_pct: float
    gap_pct: float
    message: str
    remediation_guidance: str
    required_dep_availability_pct: float


@dataclass
class ErrorBudgetBreakdownDTO:
    """Per-dependency error budget breakdown for a service.

    Attributes:
        service_id: Business identifier of the service
        slo_target_pct: SLO target used for budget computation
        total_error_budget_minutes: Monthly error budget in minutes
        self_consumption_pct: Percentage of budget consumed by service itself
        dependency_risks: Per-dependency risk assessments
        high_risk_dependencies: Service IDs consuming >30% of budget
        total_dependency_consumption_pct: Sum of all dependency consumption
    """

    service_id: str
    slo_target_pct: float
    total_error_budget_minutes: float
    self_consumption_pct: float
    dependency_risks: list[DependencyRiskDTO] = field(default_factory=list)
    high_risk_dependencies: list[str] = field(default_factory=list)
    total_dependency_consumption_pct: float = 0.0


@dataclass
class ConstraintAnalysisResponse:
    """Complete constraint propagation analysis result.

    Attributes:
        service_id: Business identifier of the service analyzed
        analyzed_at: ISO 8601 timestamp of analysis
        composite_availability_bound_pct: Composite bound as percentage
        is_achievable: Whether the SLO target is achievable
        has_high_risk_dependencies: Whether any dependency is high risk
        error_budget_breakdown: Detailed error budget breakdown
        unachievable_warning: Warning if SLO is unachievable (None if achievable)
        soft_dependency_risks: Service IDs of soft/degraded dependencies
        scc_supernodes: Circular dependency cycles (list of service ID lists)
        dependency_chain_depth: Maximum depth reached in analysis
        total_hard_dependencies: Count of hard sync dependencies
        total_soft_dependencies: Count of soft/degraded dependencies
        total_external_dependencies: Count of external dependencies
        lookback_days: Lookback window used for analysis
    """

    service_id: str
    analyzed_at: str
    composite_availability_bound_pct: float
    is_achievable: bool
    has_high_risk_dependencies: bool
    error_budget_breakdown: ErrorBudgetBreakdownDTO
    unachievable_warning: UnachievableWarningDTO | None
    soft_dependency_risks: list[str]
    scc_supernodes: list[list[str]]
    dependency_chain_depth: int
    total_hard_dependencies: int
    total_soft_dependencies: int
    total_external_dependencies: int
    lookback_days: int


@dataclass
class ErrorBudgetBreakdownResponse:
    """Error budget breakdown response (lighter-weight alternative).

    Attributes:
        service_id: Business identifier of the service
        analyzed_at: ISO 8601 timestamp of analysis
        slo_target_pct: SLO target used for budget computation
        total_error_budget_minutes: Monthly error budget in minutes
        self_consumption_pct: Percentage of budget consumed by service itself
        dependency_risks: Per-dependency risk assessments
        high_risk_dependencies: Service IDs consuming >30% of budget
        total_dependency_consumption_pct: Sum of all dependency consumption
    """

    service_id: str
    analyzed_at: str
    slo_target_pct: float
    total_error_budget_minutes: float
    self_consumption_pct: float
    dependency_risks: list[DependencyRiskDTO] = field(default_factory=list)
    high_risk_dependencies: list[str] = field(default_factory=list)
    total_dependency_consumption_pct: float = 0.0
