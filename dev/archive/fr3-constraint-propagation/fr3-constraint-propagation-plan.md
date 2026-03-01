# FR-3: Dependency-Aware Constraint Propagation — Technical Requirements Specification

**Created:** 2026-02-15
**Status:** Draft
**Corresponds to:** TRD Section 3.3 (FR-3), PRD F3
**Depends on:** FR-1 (Production Ready), FR-2 (Not Started — prerequisites included as Phase 0)

---

## 1. Overview & Scope

### Objective

Implement the **Dependency-Aware Constraint Propagation** system — an extension of FR-2's `CompositeAvailabilityService` that provides advanced constraint analysis across service dependency chains. This feature answers a critical question for SRE teams: *"Is the SLO I want for my service even achievable given its dependency chain, and if not, what's consuming my error budget?"*

FR-3 builds on the composite availability math already designed in FR-2 (serial `R = R1×R2×...×Rn`, parallel `R = 1 − Π(1−Ri)`) by adding:

1. **External API adaptive buffers** — Use `min(observed, published_SLA) × 0.9` for external dependency availability rather than trusting published SLAs at face value
2. **Error budget consumption analysis** — Per-dependency breakdown of error budget consumption with a fixed 30% threshold for "high dependency risk" flagging
3. **Unachievable SLO detection** — Proactive identification of services whose desired SLOs are mathematically impossible given their dependency chain, with actionable guidance
4. **Dedicated constraint analysis API** — Separate endpoints for detailed constraint propagation and error budget breakdown results
5. **External service type tracking** — `service_type` field on the `services` table to distinguish internal vs. external services

### Scope Boundaries

**In scope (FR-3):**
- External API adaptive buffer computation: `min(observed, published) × 0.9`
- Per-dependency error budget consumption breakdown
- High dependency risk flagging at >30% error budget consumption
- Unachievable SLO detection with remediation guidance
- `service_type` field on `services` table (`internal` | `external`)
- `published_sla` field on `services` metadata for external services
- `GET /api/v1/services/{id}/constraint-analysis` endpoint
- `GET /api/v1/services/{id}/error-budget-breakdown` endpoint
- Domain entities: `ConstraintAnalysis`, `ErrorBudgetBreakdown`, `DependencyRiskAssessment`
- Domain services: `ExternalApiBufferService`, `ErrorBudgetAnalyzer`, `UnachievableSloDetector`
- Extend `CompositeAvailabilityService` with external API handling
- Phase 0 prerequisites: minimal FR-2 components needed for FR-3 to compile and test

**Out of scope (deferred):**
- Weighted blend of observed/published SLA (decided: use min+pessimistic instead)
- Configurable per-service error budget thresholds (decided: fixed 30%)
- Real Prometheus integration for external API monitoring (uses mock stub, same as FR-2)
- Monte Carlo simulation for complex mixed topologies (PRD F15, deferred)
- What-if scenario modeling (PRD F16, deferred)
- Impact analysis endpoint (FR-4, separate feature)
- Active SLO storage and lifecycle (FR-5)
- Counterfactual analysis (Phase 5 ML features)
- Circuit breaker detection / async queue modeling

### Key Design Decisions (Confirmed)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| FR-2 relationship | Extend FR-2's `CompositeAvailabilityService` | Avoids duplication; FR-3 adds advanced features on top of FR-2 math |
| External API buffer | `min(observed, published) × 0.9` pessimistic adjustment | Matches TRD recommendation; conservative and simple |
| API surface | Dedicated endpoints for constraint analysis + error budget | Cleaner separation; FR-2 response stays focused on recommendations |
| Error budget threshold | Fixed 30% per single dependency | Matches TRD; keeps MVP simple |
| External service tracking | `service_type` field on `services` table | Minimal schema change; clean data model |
| FR-2 dependency | Phase 0 includes FR-2 prerequisites | Self-contained plan; no blocking on FR-2 completion |
| Telemetry source | Mock Prometheus stub (same as FR-2) | Enables development without real Prometheus |

---

## 2. Requirements Summary

### Functional Requirements

| ID | Requirement | Source |
|----|-------------|--------|
| FR3-01 | Compute composite availability bounds for serial hard dependencies: `R = R_self × Π(R_hard_dep_i)` | TRD 3.3, FR-2 |
| FR3-02 | Compute composite availability bounds for parallel/redundant dependencies: `R = 1 − Π(1 − R_replica_j)` | TRD 3.3, FR-2 |
| FR3-03 | For external dependencies, use `min(observed_availability, published_SLA × 0.9)` as effective availability | TRD 3.3 |
| FR3-04 | If no monitoring data exists for external dep, use `published_SLA × 0.9` (10% pessimistic adjustment) | TRD 3.3 |
| FR3-05 | Compute per-dependency error budget consumption as `(1 − R_dep) / (1 − SLO_target)` | TRD 3.3, PRD F3 |
| FR3-06 | Flag any single dependency consuming >30% of error budget as "high dependency risk" | TRD 3.3 |
| FR3-07 | When `composite_bound < desired_SLO_target`, return explicit unachievable warning with guidance | TRD 3.3 |
| FR3-08 | Exclude soft/degraded dependencies from composite math, report them as risk factors | TRD 3.3 |
| FR3-09 | Handle circular dependencies by contracting SCCs to supernodes using weakest-link member | TRD 3.3 |
| FR3-10 | Add `service_type` field to `services` table (`internal` \| `external`) | Decision |
| FR3-11 | Expose `GET /api/v1/services/{id}/constraint-analysis` endpoint | Decision |
| FR3-12 | Expose `GET /api/v1/services/{id}/error-budget-breakdown` endpoint | Decision |
| FR3-13 | Suggest the "10x rule" when SLO is unachievable: each critical dep must be ≥10× more reliable | TRD 3.3 |

### Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR3-01 | Constraint analysis response time (p95) | < 2s (involves graph traversal + telemetry queries) |
| NFR3-02 | Error budget breakdown response time (p95) | < 1s |
| NFR3-03 | Support graphs up to 5,000 services, 10,000+ edges | Same as FR-1/FR-2 targets |
| NFR3-04 | Domain layer test coverage | > 90% |
| NFR3-05 | Application layer test coverage | > 85% |
| NFR3-06 | Infrastructure layer test coverage | > 75% |

---

## 3. Detailed Component Design

### 3.1 Architecture Overview (Clean Architecture Layers)

```
┌─────────────────────────────────────────────────────────────────┐
│ Infrastructure Layer                                             │
│ ┌────────────────────────┐ ┌──────────────────────────────────┐ │
│ │ API Routes              │ │ Database                          │ │
│ │ constraint_analysis.py  │ │ (Reuses FR-2 repositories +      │ │
│ │                         │ │  FR-1 service repository)         │ │
│ └──────────┬─────────────┘ └────────────────┬─────────────────┘ │
│ ┌──────────┴─────────────┐ ┌────────────────┴─────────────────┐ │
│ │ Pydantic Schemas        │ │ Telemetry                        │ │
│ │ constraint_analysis_    │ │ (Reuses FR-2 mock Prometheus)    │ │
│ │ schema.py               │ │                                  │ │
│ └────────────────────────┘ └──────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│ Application Layer                                                │
│ ┌───────────────────────────────────────────────────────────┐   │
│ │ Use Cases                                                  │   │
│ │ - RunConstraintAnalysisUseCase                             │   │
│ │ - GetErrorBudgetBreakdownUseCase                           │   │
│ │ DTOs                                                       │   │
│ │ - ConstraintAnalysisDTO, ErrorBudgetBreakdownDTO           │   │
│ │ - DependencyRiskDTO, UnachievableWarningDTO                │   │
│ └──────────────────────────┬────────────────────────────────┘   │
├──────────────────────────────┼──────────────────────────────────┤
│ Domain Layer                 │                                    │
│ ┌────────────────────────────┴──────────────────────────────┐   │
│ │ Entities                                                   │   │
│ │ - ConstraintAnalysis, ErrorBudgetBreakdown                 │   │
│ │ - DependencyRiskAssessment, UnachievableWarning            │   │
│ │ - ExternalProviderProfile                                  │   │
│ │                                                            │   │
│ │ Services                                                   │   │
│ │ - ExternalApiBufferService (NEW)                           │   │
│ │ - ErrorBudgetAnalyzer (NEW)                                │   │
│ │ - UnachievableSloDetector (NEW)                            │   │
│ │ - CompositeAvailabilityService (EXTENDED from FR-2)        │   │
│ │                                                            │   │
│ │ Repositories (Interfaces)                                  │   │
│ │ - (Reuses) ServiceRepositoryInterface                      │   │
│ │ - (Reuses) DependencyRepositoryInterface                   │   │
│ │ - (Reuses) TelemetryQueryServiceInterface                  │   │
│ └────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Domain Layer

#### Entities

**`src/domain/entities/constraint_analysis.py`**

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4


class RiskLevel(str, Enum):
    """Risk level for a dependency's error budget consumption."""
    LOW = "low"           # < 20% error budget consumption
    MODERATE = "moderate"  # 20-30% error budget consumption
    HIGH = "high"         # > 30% error budget consumption


class ServiceType(str, Enum):
    """Service type classification."""
    INTERNAL = "internal"
    EXTERNAL = "external"


@dataclass
class ExternalProviderProfile:
    """Profile for an external dependency's reliability characteristics.

    Captures both the published SLA and observed availability to compute
    the adaptive buffer per TRD 3.3.
    """
    service_id: str
    service_uuid: UUID
    published_sla: float | None = None   # e.g., 0.9999 (99.99%)
    observed_availability: float | None = None
    observation_window_days: int = 0

    @property
    def effective_availability(self) -> float:
        """Compute effective availability using min(observed, published×0.9).

        Rules:
        - If both observed and published available: min(observed, published × 0.9)
        - If only observed available: use observed
        - If only published available: use published × 0.9 (10% pessimistic)
        - If neither available: default to 0.999 (99.9%)
        """
        published_adjusted = (
            self.published_sla * 0.9 if self.published_sla is not None else None
        )

        if self.observed_availability is not None and published_adjusted is not None:
            return min(self.observed_availability, published_adjusted)
        elif self.observed_availability is not None:
            return self.observed_availability
        elif published_adjusted is not None:
            return published_adjusted
        else:
            return 0.999  # Conservative default


@dataclass
class DependencyRiskAssessment:
    """Risk assessment for a single dependency's error budget impact.

    Attributes:
        service_id: Business identifier of the dependency
        service_uuid: Internal UUID of the dependency
        availability: Effective availability used for computation
        error_budget_consumption_pct: Percentage of parent's error budget consumed
        risk_level: Computed risk level based on consumption
        is_external: Whether this is an external dependency
        communication_mode: sync/async
        criticality: hard/soft/degraded
        published_sla: Published SLA (external only)
        observed_availability: Measured availability
        effective_availability_note: Explanation of how effective availability was computed
    """
    service_id: str
    service_uuid: UUID
    availability: float
    error_budget_consumption_pct: float  # 0.0 to 100.0 (percentage)
    risk_level: RiskLevel
    is_external: bool = False
    communication_mode: str = "sync"
    criticality: str = "hard"
    published_sla: float | None = None
    observed_availability: float | None = None
    effective_availability_note: str = ""

    def __post_init__(self):
        if not (0.0 <= self.error_budget_consumption_pct <= 100.0):
            raise ValueError(
                f"error_budget_consumption_pct must be between 0.0 and 100.0, "
                f"got: {self.error_budget_consumption_pct}"
            )


@dataclass
class UnachievableWarning:
    """Warning when a desired SLO target is mathematically unachievable.

    Generated when composite_bound < desired_target.
    """
    desired_target: float          # e.g., 99.99
    composite_bound: float         # e.g., 99.70
    gap: float                     # desired - composite (e.g., 0.29)
    message: str                   # Human-readable warning
    remediation_guidance: str      # Actionable advice
    required_dep_availability: float  # What each dep would need (10x rule)


@dataclass
class ErrorBudgetBreakdown:
    """Per-dependency breakdown of error budget consumption for a service.

    Attributes:
        service_id: Business identifier of the service being analyzed
        slo_target: The SLO target used for budget computation (e.g., 99.9)
        total_error_budget_minutes: Monthly error budget in minutes
        self_consumption_pct: Percentage of budget consumed by the service itself
        dependency_assessments: Per-dependency risk assessments
        high_risk_dependencies: Dependencies consuming >30% of budget
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
    """
    service_id: str
    service_uuid: UUID
    composite_availability_bound: float      # 0.0 to 1.0 (ratio)
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
        """Whether the SLO target is achievable given constraints."""
        return self.unachievable_warning is None

    @property
    def has_high_risk_dependencies(self) -> bool:
        """Whether any dependency consumes >30% of error budget."""
        return len(self.error_budget_breakdown.high_risk_dependencies) > 0
```

#### Domain Services

**`src/domain/services/external_api_buffer_service.py`**

```python
class ExternalApiBufferService:
    """Computes effective availability for external dependencies.

    Applies the adaptive buffer strategy per TRD 3.3:
    - If both observed and published SLA are available:
      effective = min(observed, published × 0.9)
    - If only observed: use observed
    - If only published: use published × 0.9 (10% pessimistic)
    - If neither: default to 99.9%

    This service is deliberately simple and deterministic.
    """

    PESSIMISTIC_FACTOR: float = 0.9   # 10% pessimistic adjustment
    DEFAULT_EXTERNAL_AVAILABILITY: float = 0.999  # 99.9% conservative default

    def compute_effective_availability(
        self,
        profile: ExternalProviderProfile,
    ) -> float:
        """Compute effective availability for an external dependency.

        Args:
            profile: External provider profile with published SLA and observed data

        Returns:
            Effective availability ratio (0.0 to 1.0)
        """

    def build_profile(
        self,
        service_id: str,
        service_uuid: UUID,
        published_sla: float | None,
        observed_availability: float | None,
        observation_window_days: int,
    ) -> ExternalProviderProfile:
        """Build an ExternalProviderProfile from raw inputs.

        Args:
            service_id: Business identifier
            service_uuid: Internal UUID
            published_sla: Published SLA as ratio (e.g., 0.9999)
            observed_availability: Measured availability ratio
            observation_window_days: Days of observation data

        Returns:
            Populated ExternalProviderProfile
        """

    def generate_availability_note(
        self,
        profile: ExternalProviderProfile,
        effective: float,
    ) -> str:
        """Generate human-readable note explaining how effective availability was computed.

        Examples:
        - "Using min(observed 99.85%, published 99.89%) = 99.85%"
        - "No monitoring data; using published SLA 99.99% × 0.9 = 99.89%"
        - "No published SLA or monitoring data; using conservative default 99.9%"
        """
```

**`src/domain/services/error_budget_analyzer.py`**

```python
class ErrorBudgetAnalyzer:
    """Computes per-dependency error budget consumption analysis.

    For each hard dependency in the chain, computes what fraction of the
    target service's error budget is consumed by that dependency's
    unavailability.

    Formula per dependency:
        consumption = (1 - R_dep) / (1 - SLO_target)

    Example: If SLO target = 99.9% (budget = 0.1%) and dep availability = 99.5%:
        consumption = (1 - 0.995) / (1 - 0.999) = 0.005 / 0.001 = 5.0 (500%)
        This means the dependency alone consumes 500% of the error budget.

    Risk thresholds (fixed):
        HIGH:     > 30% consumption
        MODERATE: 20-30% consumption
        LOW:      < 20% consumption
    """

    HIGH_RISK_THRESHOLD: float = 0.30   # 30%
    MODERATE_RISK_THRESHOLD: float = 0.20  # 20%
    MONTHLY_MINUTES: float = 43200.0  # 30 days × 24 hours × 60 minutes

    def compute_breakdown(
        self,
        service_id: str,
        slo_target: float,                # as percentage, e.g., 99.9
        service_availability: float,      # as ratio, e.g., 0.9992
        dependencies: list[DependencyWithAvailability],
    ) -> ErrorBudgetBreakdown:
        """Compute full error budget breakdown across all dependencies.

        Args:
            service_id: Business identifier of the target service
            slo_target: Desired SLO target as percentage (e.g., 99.9)
            service_availability: Historical availability of the service itself
            dependencies: Dependencies with their effective availabilities

        Returns:
            ErrorBudgetBreakdown with per-dependency risk assessments
        """

    def compute_single_dependency_consumption(
        self,
        dep_availability: float,   # ratio 0.0-1.0
        slo_target: float,         # percentage e.g. 99.9
    ) -> float:
        """Compute error budget consumption for a single dependency.

        Returns consumption as a ratio (0.0 to N). Values > 1.0 mean the
        dependency alone exceeds the total error budget.
        """

    def classify_risk(self, consumption_pct: float) -> RiskLevel:
        """Classify risk level based on consumption percentage.

        Args:
            consumption_pct: Consumption as percentage (0-100)

        Returns:
            RiskLevel enum value
        """

    @staticmethod
    def compute_error_budget_minutes(slo_target_pct: float) -> float:
        """Compute monthly error budget in minutes.

        Budget = (1 - target/100) × 43200 minutes (30 days)
        Example: 99.9% → (1 - 0.999) × 43200 = 43.2 minutes
        """
```

**`src/domain/services/unachievable_slo_detector.py`**

```python
class UnachievableSloDetector:
    """Detects when a desired SLO target is mathematically unachievable.

    A target is unachievable when the composite availability bound
    (computed from all hard dependencies) is lower than the desired target.

    Also computes the "10x rule" guidance: to achieve target T, each critical
    dependency must provide availability ≥ 1 - (1-T)/N where N is the number
    of serial hard dependencies.
    """

    def check(
        self,
        desired_target_pct: float,        # e.g., 99.99
        composite_bound: float,           # ratio, e.g., 0.9970
        hard_dependency_count: int,
    ) -> UnachievableWarning | None:
        """Check if the desired SLO target is achievable.

        Args:
            desired_target_pct: Desired SLO target as percentage
            composite_bound: Composite availability bound as ratio
            hard_dependency_count: Number of serial hard dependencies

        Returns:
            UnachievableWarning if unachievable, None if achievable
        """

    def compute_required_dep_availability(
        self,
        desired_target_pct: float,
        hard_dependency_count: int,
    ) -> float:
        """Compute what each dependency would need to achieve the target.

        Uses the "10x rule" approximation:
            required = 1 - (1 - target) / (N + 1)

        Where N is the number of hard dependencies and +1 accounts for the
        service itself.

        Example: Target 99.99% with 3 hard deps:
            required = 1 - (1 - 0.9999) / 4 = 1 - 0.000025 = 99.9975%
        """

    def generate_warning_message(
        self,
        desired_target_pct: float,
        composite_bound_pct: float,
    ) -> str:
        """Generate human-readable warning message.

        Example: "The desired target of 99.99% is unachievable.
                 Composite availability bound is 99.70% given current
                 dependency chain."
        """

    def generate_remediation_guidance(
        self,
        desired_target_pct: float,
        required_dep_availability_pct: float,
        hard_dependency_count: int,
    ) -> str:
        """Generate actionable remediation guidance.

        Example: "To achieve 99.99%, each of the 3 critical dependencies
                 must provide at least 99.9975% availability.
                 Consider: (1) Adding redundant paths for critical deps,
                 (2) Converting hard sync deps to async soft deps,
                 (3) Relaxing the target to ≤99.70%."
        """
```

**Extending `src/domain/services/composite_availability_service.py` (from FR-2)**

FR-3 extends the FR-2 `CompositeAvailabilityService` to accept `ExternalProviderProfile` objects and use the `ExternalApiBufferService` for external deps. The extension adds one new method:

```python
# Added to CompositeAvailabilityService

def compute_composite_bound_with_externals(
    self,
    service_availability: float,
    internal_dependencies: list[DependencyWithAvailability],
    external_profiles: list[ExternalProviderProfile],
    external_api_buffer_service: ExternalApiBufferService,
) -> CompositeResult:
    """Compute composite bound with external API adaptive buffers.

    Replaces external dependency availability values with effective
    availability computed by ExternalApiBufferService before running
    standard composite math.
    """
```

#### Value Objects

**`src/domain/entities/dependency_with_availability.py`** (shared with FR-2)

```python
@dataclass
class DependencyWithAvailability:
    """A dependency edge paired with its resolved availability data.

    Used as input to CompositeAvailabilityService and ErrorBudgetAnalyzer.
    """
    dependency: ServiceDependency         # The graph edge
    service_id: str                       # Business identifier of the target
    service_uuid: UUID                    # Internal UUID
    availability: float                   # Effective availability (ratio 0.0-1.0)
    is_external: bool = False
    published_sla: float | None = None
    observed_availability: float | None = None
    effective_availability_note: str = ""
```

#### Repository Interfaces

FR-3 does not introduce new repository interfaces. It reuses:
- `ServiceRepositoryInterface` (FR-1) — for service lookup and service_type
- `DependencyRepositoryInterface` (FR-1) — for graph traversal
- `TelemetryQueryServiceInterface` (FR-2) — for availability data
- `SloRecommendationRepositoryInterface` (FR-2) — for active recommendation lookup (optional, for default SLO target)

The `ServiceRepositoryInterface` requires one new method:

```python
# Added to ServiceRepositoryInterface

@abstractmethod
async def get_external_services(self) -> list["Service"]:
    """Get all services with service_type='external'.

    Returns:
        List of Service entities of type external
    """
    pass
```

### 3.3 Application Layer

#### Use Cases

**`src/application/use_cases/run_constraint_analysis.py`**

```python
class RunConstraintAnalysisUseCase:
    """Run full constraint propagation analysis for a service.

    Pipeline:
    1. Validate service exists
    2. Retrieve dependency subgraph (downstream, depth=3)
    3. Classify dependencies: hard/soft, internal/external
    4. For external deps: build profiles, compute effective availability
    5. For internal deps: fetch observed availability from telemetry
    6. Compute composite availability bound
    7. Determine desired SLO target (from active SLO or balanced tier default)
    8. Compute error budget breakdown
    9. Check for unachievable SLOs
    10. Identify SCC supernodes from circular dependencies
    11. Build and return ConstraintAnalysis result
    """

    def __init__(
        self,
        service_repository: ServiceRepositoryInterface,
        dependency_repository: DependencyRepositoryInterface,
        telemetry_service: TelemetryQueryServiceInterface,
        graph_traversal_service: GraphTraversalService,
        composite_service: CompositeAvailabilityService,
        external_buffer_service: ExternalApiBufferService,
        error_budget_analyzer: ErrorBudgetAnalyzer,
        unachievable_detector: UnachievableSloDetector,
    ): ...

    async def execute(
        self, request: ConstraintAnalysisRequest
    ) -> ConstraintAnalysisResponse | None: ...
```

**`src/application/use_cases/get_error_budget_breakdown.py`**

```python
class GetErrorBudgetBreakdownUseCase:
    """Retrieve error budget breakdown for a service at a given SLO target.

    A lighter-weight operation than full constraint analysis — focuses only
    on per-dependency error budget consumption without composite computation.

    Pipeline:
    1. Validate service exists
    2. Retrieve direct dependencies (depth=1, hard deps only)
    3. For each dep: fetch availability, compute budget consumption
    4. Classify risk levels
    5. Return ErrorBudgetBreakdown
    """

    def __init__(
        self,
        service_repository: ServiceRepositoryInterface,
        dependency_repository: DependencyRepositoryInterface,
        telemetry_service: TelemetryQueryServiceInterface,
        external_buffer_service: ExternalApiBufferService,
        error_budget_analyzer: ErrorBudgetAnalyzer,
    ): ...

    async def execute(
        self, request: ErrorBudgetBreakdownRequest
    ) -> ErrorBudgetBreakdownResponse | None: ...
```

#### DTOs

**`src/application/dtos/constraint_analysis_dto.py`**

```python
@dataclass
class ConstraintAnalysisRequest:
    service_id: str                 # Business identifier
    desired_target_pct: float | None = None  # e.g., 99.9; None = use active SLO or default
    lookback_days: int = 30
    max_depth: int = 3

@dataclass
class ErrorBudgetBreakdownRequest:
    service_id: str
    slo_target_pct: float = 99.9   # Default SLO target for budget calculation
    lookback_days: int = 30

@dataclass
class DependencyRiskDTO:
    service_id: str
    availability_pct: float
    error_budget_consumption_pct: float
    risk_level: str                # "low" | "moderate" | "high"
    is_external: bool
    communication_mode: str
    criticality: str
    published_sla_pct: float | None = None
    observed_availability_pct: float | None = None
    effective_availability_note: str = ""

@dataclass
class UnachievableWarningDTO:
    desired_target_pct: float
    composite_bound_pct: float
    gap_pct: float
    message: str
    remediation_guidance: str
    required_dep_availability_pct: float

@dataclass
class ErrorBudgetBreakdownDTO:
    service_id: str
    slo_target_pct: float
    total_error_budget_minutes: float
    self_consumption_pct: float
    dependency_risks: list[DependencyRiskDTO]
    high_risk_dependencies: list[str]
    total_dependency_consumption_pct: float

@dataclass
class ConstraintAnalysisResponse:
    service_id: str
    analyzed_at: str                     # ISO 8601
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
    service_id: str
    analyzed_at: str
    slo_target_pct: float
    total_error_budget_minutes: float
    self_consumption_pct: float
    dependency_risks: list[DependencyRiskDTO]
    high_risk_dependencies: list[str]
    total_dependency_consumption_pct: float
```

### 3.4 Infrastructure Layer

**Pydantic Schemas:** `src/infrastructure/api/schemas/constraint_analysis_schema.py`

Pydantic v2 models mirroring the DTOs for API request validation and response serialization.

**API Route:** `src/infrastructure/api/routes/constraint_analysis.py`

Two GET endpoints registered under the existing FastAPI app.

**Database Migration:** `alembic/versions/XXX_add_service_type_to_services.py`

Adds `service_type` column and `published_sla` to `services` table.

---

## 4. API Specification

### `GET /api/v1/services/{service_id}/constraint-analysis`

**Description:** Run full dependency-aware constraint propagation analysis for a service. Returns composite availability bounds, per-dependency error budget consumption, unachievable SLO warnings, and remediation guidance.

**Authentication:** API Key (`X-API-Key` header)

**Rate Limit:** 30 req/min (involves graph traversal + telemetry queries)

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `service_id` | string | Business identifier (e.g., "checkout-service") |

**Query Parameters:**

| Parameter | Type | Default | Validation | Description |
|-----------|------|---------|------------|-------------|
| `desired_target_pct` | float | `null` | 90.0 ≤ x ≤ 99.9999 | Desired SLO target as percentage. If omitted, uses active SLO target or 99.9% default. |
| `lookback_days` | integer | `30` | min: 7, max: 365 | Lookback window for telemetry data |
| `max_depth` | integer | `3` | min: 1, max: 10 | Maximum dependency chain depth to analyze |

**Success Response (200 OK):**

```json
{
  "service_id": "checkout-service",
  "analyzed_at": "2026-02-15T14:00:00Z",
  "composite_availability_bound_pct": 99.70,
  "is_achievable": true,
  "has_high_risk_dependencies": true,
  "dependency_chain_depth": 3,
  "total_hard_dependencies": 3,
  "total_soft_dependencies": 1,
  "total_external_dependencies": 1,
  "lookback_days": 30,
  "error_budget_breakdown": {
    "service_id": "checkout-service",
    "slo_target_pct": 99.9,
    "total_error_budget_minutes": 43.2,
    "self_consumption_pct": 8.0,
    "dependency_risks": [
      {
        "service_id": "payment-service",
        "availability_pct": 99.95,
        "error_budget_consumption_pct": 50.0,
        "risk_level": "high",
        "is_external": false,
        "communication_mode": "sync",
        "criticality": "hard",
        "published_sla_pct": null,
        "observed_availability_pct": 99.95,
        "effective_availability_note": "Using observed availability 99.95%"
      },
      {
        "service_id": "external-payment-api",
        "availability_pct": 99.50,
        "error_budget_consumption_pct": 500.0,
        "risk_level": "high",
        "is_external": true,
        "communication_mode": "sync",
        "criticality": "hard",
        "published_sla_pct": 99.99,
        "observed_availability_pct": 99.60,
        "effective_availability_note": "Using min(observed 99.60%, published×0.9 99.89%) = 99.60%"
      },
      {
        "service_id": "inventory-service",
        "availability_pct": 99.90,
        "error_budget_consumption_pct": 100.0,
        "risk_level": "high",
        "is_external": false,
        "communication_mode": "sync",
        "criticality": "hard",
        "published_sla_pct": null,
        "observed_availability_pct": 99.90,
        "effective_availability_note": "Using observed availability 99.90%"
      }
    ],
    "high_risk_dependencies": [
      "payment-service",
      "external-payment-api",
      "inventory-service"
    ],
    "total_dependency_consumption_pct": 650.0
  },
  "unachievable_warning": null,
  "soft_dependency_risks": ["recommendation-service"],
  "scc_supernodes": []
}
```

**Example — Unachievable SLO Response (200 OK with warning):**

```json
{
  "service_id": "checkout-service",
  "analyzed_at": "2026-02-15T14:00:00Z",
  "composite_availability_bound_pct": 99.70,
  "is_achievable": false,
  "has_high_risk_dependencies": true,
  "unachievable_warning": {
    "desired_target_pct": 99.99,
    "composite_bound_pct": 99.70,
    "gap_pct": 0.29,
    "message": "The desired target of 99.99% is unachievable. Composite availability bound is 99.70% given current dependency chain.",
    "remediation_guidance": "To achieve 99.99%, each of the 3 critical dependencies must provide at least 99.9975% availability. Consider: (1) Adding redundant paths for critical deps, (2) Converting hard sync deps to async soft deps, (3) Relaxing the target to ≤99.70%.",
    "required_dep_availability_pct": 99.9975
  }
}
```

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 404 | Service not registered | RFC 7807: `"Service with ID 'xyz' is not registered."` |
| 400 | Invalid query params | RFC 7807: `"desired_target_pct must be between 90.0 and 99.9999"` |
| 422 | No dependency data | RFC 7807: `"Service 'xyz' has no dependencies registered."` |
| 429 | Rate limit exceeded | RFC 7807 + `Retry-After` header |
| 500 | Internal error | RFC 7807: generic server error |

---

### `GET /api/v1/services/{service_id}/error-budget-breakdown`

**Description:** Retrieve per-dependency error budget consumption breakdown for a service at a given SLO target. A lighter-weight alternative to full constraint analysis.

**Authentication:** API Key (`X-API-Key` header)

**Rate Limit:** 60 req/min

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `service_id` | string | Business identifier (e.g., "checkout-service") |

**Query Parameters:**

| Parameter | Type | Default | Validation | Description |
|-----------|------|---------|------------|-------------|
| `slo_target_pct` | float | `99.9` | 90.0 ≤ x ≤ 99.9999 | SLO target for budget calculation |
| `lookback_days` | integer | `30` | min: 7, max: 365 | Lookback window for telemetry data |

**Success Response (200 OK):**

```json
{
  "service_id": "checkout-service",
  "analyzed_at": "2026-02-15T14:00:00Z",
  "slo_target_pct": 99.9,
  "total_error_budget_minutes": 43.2,
  "self_consumption_pct": 8.0,
  "dependency_risks": [
    {
      "service_id": "external-payment-api",
      "availability_pct": 99.50,
      "error_budget_consumption_pct": 500.0,
      "risk_level": "high",
      "is_external": true,
      "communication_mode": "sync",
      "criticality": "hard",
      "published_sla_pct": 99.99,
      "observed_availability_pct": 99.60,
      "effective_availability_note": "Using min(observed 99.60%, published×0.9 99.89%) = 99.60%"
    }
  ],
  "high_risk_dependencies": ["external-payment-api"],
  "total_dependency_consumption_pct": 500.0
}
```

**Error Responses:** Same as constraint-analysis endpoint.

---

## 5. Database Design

### 5.1 Schema Change: `services` Table

**Migration: `XXX_add_service_type_to_services.py`**

```sql
-- Add service_type column to services table
ALTER TABLE services
    ADD COLUMN service_type VARCHAR(20) NOT NULL DEFAULT 'internal';

ALTER TABLE services
    ADD CONSTRAINT ck_service_type CHECK (service_type IN ('internal', 'external'));

-- Add published_sla column (external services only)
ALTER TABLE services
    ADD COLUMN published_sla DECIMAL(8,6) DEFAULT NULL;

-- Partial index for external service lookups
CREATE INDEX idx_services_external
    ON services(service_type) WHERE service_type = 'external';
```

**Column Details:**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `service_type` | `VARCHAR(20)` | NOT NULL | `'internal'` | `'internal'` or `'external'` |
| `published_sla` | `DECIMAL(8,6)` | NULL | NULL | Published SLA as ratio (e.g., 0.9999). Only for external services. |

**Backward Compatibility:** Both columns have defaults (`'internal'` and `NULL`), so existing data and FR-1/FR-2 code is unaffected.

### 5.2 No New Tables

FR-3 does not create new tables. The `ConstraintAnalysis` entity is computed on-demand (not persisted) because:
1. Results depend on real-time telemetry and the current dependency graph state
2. Caching constraint analysis would introduce staleness without clear benefit
3. API response times target < 2s, which is achievable with on-demand computation

If caching becomes necessary (load testing reveals latency issues), a `constraint_analysis_cache` table can be added later with a TTL-based invalidation strategy.

### 5.3 Data Access Patterns

| Query | Frequency | Index Used |
|-------|-----------|------------|
| Get service by business ID | Per API request | Existing `services.service_id` UNIQUE |
| Get external services | Startup / periodic | `idx_services_external` (new) |
| Traverse downstream deps (depth=3) | Per constraint analysis | Existing recursive CTE indexes |
| Get dep availability from telemetry | Per dependency per analysis | Mock stub (no DB query in MVP) |

### 5.4 Migration Strategy

Single additive migration:
1. `ALTER TABLE services ADD COLUMN service_type` — default `'internal'`, no data migration needed
2. `ALTER TABLE services ADD COLUMN published_sla` — nullable, no data migration needed
3. Create partial index for external service lookups
4. Migration is fully reversible (downgrade drops columns and index)

---

## 6. Algorithm & Logic Design

### 6.1 Full Constraint Analysis Pipeline

```
Input: service_id, desired_target_pct (optional), lookback_days, max_depth

Step 1: VALIDATE SERVICE
    service = service_repo.get_by_service_id(service_id)
    IF service is None:
        RETURN error: "Service not found"

Step 2: DETERMINE DESIRED TARGET
    IF desired_target_pct is provided:
        target = desired_target_pct
    ELSE IF service has active SLO (FR-5, future):
        target = active_slo.availability_target
    ELSE:
        target = 99.9  # Default balanced tier

Step 3: RETRIEVE DEPENDENCY SUBGRAPH
    nodes, edges = graph_traversal.get_subgraph(
        service.id, direction=DOWNSTREAM, max_depth=max_depth
    )
    IF len(edges) == 0:
        RETURN error: "Service has no dependencies"

Step 4: CLASSIFY DEPENDENCIES
    hard_sync_deps = []
    soft_deps = []
    external_deps = []

    FOR EACH edge IN edges:
        target_service = find_service(edge.target_service_id, nodes)

        IF edge.criticality == HARD AND edge.communication_mode == SYNC:
            hard_sync_deps.append(edge)
        ELSE IF edge.criticality IN [SOFT, DEGRADED]:
            soft_deps.append(edge)

        IF target_service.service_type == 'external':
            external_deps.append(edge)

Step 5: RESOLVE DEPENDENCY AVAILABILITIES
    deps_with_availability = []

    FOR EACH dep IN hard_sync_deps:
        target_service = find_service(dep.target_service_id, nodes)

        IF target_service.service_type == 'external':
            # Build external provider profile
            profile = external_buffer_service.build_profile(
                service_id=target_service.service_id,
                service_uuid=target_service.id,
                published_sla=target_service.published_sla,
                observed_availability=telemetry.get_availability_sli(
                    target_service.service_id, lookback_days
                )?.availability_ratio,
                observation_window_days=lookback_days,
            )
            effective = external_buffer_service.compute_effective_availability(profile)
            note = external_buffer_service.generate_availability_note(profile, effective)
        ELSE:
            # Internal: use observed availability
            avail_sli = telemetry.get_availability_sli(
                target_service.service_id, lookback_days
            )
            effective = avail_sli.availability_ratio IF avail_sli ELSE 0.999
            note = f"Using observed availability {effective*100:.2f}%" IF avail_sli
                   ELSE "No telemetry data; using conservative default 99.9%"

        deps_with_availability.append(DependencyWithAvailability(
            dependency=dep,
            service_id=target_service.service_id,
            service_uuid=target_service.id,
            availability=effective,
            is_external=(target_service.service_type == 'external'),
            published_sla=target_service.published_sla,
            observed_availability=avail_sli?.availability_ratio,
            effective_availability_note=note,
        ))

Step 6: FETCH SERVICE'S OWN AVAILABILITY
    self_avail_sli = telemetry.get_availability_sli(service.service_id, lookback_days)
    self_availability = self_avail_sli.availability_ratio IF self_avail_sli ELSE 0.999

Step 7: COMPUTE COMPOSITE BOUND
    composite_result = composite_service.compute_composite_bound(
        service_availability=self_availability,
        dependencies=deps_with_availability,
    )
    composite_bound = composite_result.bound

Step 8: COMPUTE ERROR BUDGET BREAKDOWN
    breakdown = error_budget_analyzer.compute_breakdown(
        service_id=service.service_id,
        slo_target=target,
        service_availability=self_availability,
        dependencies=deps_with_availability,
    )

Step 9: CHECK UNACHIEVABILITY
    warning = unachievable_detector.check(
        desired_target_pct=target,
        composite_bound=composite_bound,
        hard_dependency_count=len(hard_sync_deps),
    )

Step 10: IDENTIFY SCC SUPERNODES
    # Reuse FR-1 circular dependency detection results
    scc_cycles = [alert.cycle_path for alert in
                  alert_repo.list_by_status("open")]
    relevant_sccs = [cycle for cycle in scc_cycles
                     if service.service_id in cycle]

Step 11: BUILD RESULT
    analysis = ConstraintAnalysis(
        service_id=service.service_id,
        service_uuid=service.id,
        composite_availability_bound=composite_bound,
        composite_availability_bound_pct=composite_bound * 100,
        error_budget_breakdown=breakdown,
        unachievable_warning=warning,
        soft_dependency_risks=[find_service(d.target_service_id, nodes).service_id
                               for d in soft_deps],
        scc_supernodes=relevant_sccs,
        dependency_chain_depth=max_depth_reached(edges),
        total_hard_dependencies=len(hard_sync_deps),
        total_soft_dependencies=len(soft_deps),
        total_external_dependencies=len(external_deps),
        lookback_days=lookback_days,
    )

    RETURN analysis
```

### 6.2 Error Budget Consumption Formula

```
FUNCTION compute_single_dependency_consumption(dep_availability, slo_target_pct):
    """
    dep_availability: ratio (e.g., 0.995 for 99.5%)
    slo_target_pct: percentage (e.g., 99.9)

    Returns: consumption as ratio (0.0 to unbounded)
    """
    slo_target_ratio = slo_target_pct / 100.0
    error_budget = 1.0 - slo_target_ratio     # e.g., 0.001 for 99.9%
    dep_unavailability = 1.0 - dep_availability  # e.g., 0.005 for 99.5%

    IF error_budget == 0.0:
        RETURN float('inf')  # Perfect SLO, any unavailability = infinite consumption

    consumption = dep_unavailability / error_budget

    RETURN consumption

EXAMPLES:
    SLO=99.9%, dep=99.5%: (1-0.995)/(1-0.999) = 0.005/0.001 = 5.0 (500%)
    SLO=99.9%, dep=99.95%: (1-0.9995)/(1-0.999) = 0.0005/0.001 = 0.5 (50%)
    SLO=99.9%, dep=99.99%: (1-0.9999)/(1-0.999) = 0.0001/0.001 = 0.1 (10%)
```

### 6.3 External API Adaptive Buffer Computation

```
FUNCTION compute_effective_availability(profile):
    published = profile.published_sla
    observed = profile.observed_availability

    IF published is not None:
        published_adjusted = published * 0.9   # 10% pessimistic
    ELSE:
        published_adjusted = None

    IF observed is not None AND published_adjusted is not None:
        RETURN min(observed, published_adjusted)
    ELSE IF observed is not None:
        RETURN observed
    ELSE IF published_adjusted is not None:
        RETURN published_adjusted
    ELSE:
        RETURN 0.999  # Conservative default

EXAMPLES:
    published=0.9999, observed=0.9960 → min(0.9960, 0.8999) = 0.8999
    Wait — that's wrong. Published × 0.9 means 99.99% × 0.9 = 89.99%. That's too aggressive.

    CORRECTION: The TRD says "10% pessimistic adjustment" meaning:
    published=0.9999 → use 0.9999 - 0.1*(1-0.9999) = NOT this either.

    Reading TRD 3.3 exactly: "published 99.99% → use 99.89%"
    This means: published_adjusted = published - (1 - published) * 10
    99.99% - (0.01%) * 10 = 99.99% - 0.10% = 99.89%

    In ratio form: 0.9999 → 0.9999 - (1 - 0.9999) * 10 = 0.9999 - 0.001 = 0.9989

    REVISED FORMULA:
    published_adjusted = published - (1 - published) * PESSIMISTIC_MULTIPLIER
    Where PESSIMISTIC_MULTIPLIER = 10 (adds 10x the unavailability as buffer)

    Equivalently: published_adjusted = 1 - (1 - published) * (1 + PESSIMISTIC_MULTIPLIER)
                                     = 1 - (1 - published) * 11

    Examples with multiplier = 10:
        published=0.9999 → 1 - 0.0001 * 11 = 1 - 0.0011 = 0.9989 (99.89%) ✓
        published=0.999  → 1 - 0.001 * 11  = 1 - 0.011  = 0.989  (98.9%)
        published=0.99   → 1 - 0.01 * 11   = 1 - 0.11   = 0.89   (89.0%)

REVISED FUNCTION:
    PESSIMISTIC_MULTIPLIER = 10   # Adds 10x the unavailability margin

    IF published is not None:
        unavailability = 1.0 - published
        published_adjusted = 1.0 - unavailability * (1 + PESSIMISTIC_MULTIPLIER)
        published_adjusted = max(published_adjusted, 0.0)  # Floor at 0%
    ELSE:
        published_adjusted = None

    IF observed is not None AND published_adjusted is not None:
        RETURN min(observed, published_adjusted)
    ELSE IF observed is not None:
        RETURN observed
    ELSE IF published_adjusted is not None:
        RETURN published_adjusted
    ELSE:
        RETURN 0.999  # Conservative default
```

### 6.4 Unachievable SLO Detection & 10x Rule

```
FUNCTION check_achievability(desired_target_pct, composite_bound, n_hard_deps):
    desired_ratio = desired_target_pct / 100.0

    IF composite_bound >= desired_ratio:
        RETURN None  # Achievable

    gap_pct = desired_target_pct - (composite_bound * 100)

    # 10x Rule: what each dep must provide
    # required_per_dep = 1 - (1 - desired_ratio) / (n_hard_deps + 1)
    IF n_hard_deps > 0:
        required = 1.0 - (1.0 - desired_ratio) / (n_hard_deps + 1)
        required_pct = required * 100
    ELSE:
        required_pct = desired_target_pct

    RETURN UnachievableWarning(
        desired_target=desired_target_pct,
        composite_bound=composite_bound * 100,
        gap=gap_pct,
        message=generate_warning_message(desired_target_pct, composite_bound * 100),
        remediation_guidance=generate_remediation(desired_target_pct, required_pct, n_hard_deps),
        required_dep_availability=required_pct,
    )

EXAMPLE:
    desired=99.99%, composite_bound=0.9970, n_hard_deps=3
    gap = 99.99 - 99.70 = 0.29%
    required = 1 - (1 - 0.9999) / 4 = 1 - 0.0001/4 = 1 - 0.000025 = 0.999975 (99.9975%)
```

---

## 7. Error Handling & Edge Cases

### Edge Cases

| Scenario | Handling |
|----------|----------|
| Service not registered | Return 404 |
| Service has no dependencies at all | Return 422: "Service has no dependencies registered." |
| Service has only soft/degraded dependencies | Composite bound = service's own availability. Error budget breakdown shows only self-consumption. Soft deps listed in `soft_dependency_risks`. |
| External dep has no published SLA or observed data | Use conservative default (99.9%). Note in `effective_availability_note`. |
| External dep's `published_sla` is lower than observed | Use published (it's already lower; pessimistic adjustment makes it even lower). |
| Circular dependency in the chain | Detected via FR-1 SCC alerts. Report in `scc_supernodes`. Use weakest-link member's availability for supernode. |
| Dependency has no telemetry data | Assume 99.9% availability with note "No telemetry data; using conservative default." |
| SLO target = 100% (error budget = 0) | Any dependency unavailability = infinite consumption. Return `error_budget_consumption_pct: Infinity` or cap at 999999.99 for JSON safety. Flag as unachievable. |
| Very deep dependency chains (depth > 10) | Truncate at `max_depth` (configurable, max 10). Note in response that analysis is partial. |
| `desired_target_pct` > composite bound but very close (< 0.01% gap) | Still flag as unachievable. Small gaps matter at high nines. |
| Published SLA is absurdly high (100%) | `published_adjusted = 1 - (1 - 1.0) * 11 = 1.0`. Cap at published value. |
| Published SLA is very low (< 90%) | `published_adjusted` may go negative. Floor at 0.0. Flag in note. |

### Retry Strategy

| Operation | Retry Policy |
|-----------|-------------|
| Telemetry query (mock stub) | 3 attempts, exponential backoff (1s, 2s, 4s) — inherited from FR-2 |
| Graph traversal (PostgreSQL CTE) | No retry (single atomic query) |
| Service lookup | No retry (single indexed query) |
| Full constraint analysis pipeline | No retry at pipeline level. Per-dependency failures are caught and the dep uses default availability (99.9%) |

### Fallback Mechanisms

| Failure Mode | Fallback |
|-------------|----------|
| Telemetry service unreachable | Use 99.9% default for all dependencies. Flag `data_quality` as degraded. |
| Single dependency telemetry missing | Use 99.9% default for that dependency. Note in `effective_availability_note`. |
| Graph traversal returns empty | Return 422 "No dependencies registered" |
| Computation takes > 10s | Return 504 Gateway Timeout. Log for investigation. |

---

## 8. Dependencies & Interfaces

### Internal Dependencies (FR-1 → FR-3)

| FR-1 Component | FR-3 Usage | Interface |
|----------------|------------|-----------|
| `ServiceRepositoryInterface` | Lookup service, check service_type | `get_by_service_id(service_id: str)` |
| `DependencyRepositoryInterface` | Traverse dependency subgraph | `traverse_graph(service_id, DOWNSTREAM, max_depth, False)` |
| `GraphTraversalService` | Orchestrate graph traversal | `get_subgraph(...)` |
| `Service` entity | Service metadata, service_type, published_sla | Direct attribute access |
| `ServiceDependency` entity | Edge classification (hard/soft, sync/async) | Direct attribute access |
| `CircularDependencyAlertRepositoryInterface` | Retrieve open SCC alerts | `list_by_status("open")` |

### Internal Dependencies (FR-2 → FR-3)

| FR-2 Component | FR-3 Usage | Interface |
|----------------|------------|-----------|
| `CompositeAvailabilityService` | Compute composite availability bound | `compute_composite_bound(...)` |
| `TelemetryQueryServiceInterface` | Fetch dependency availability data | `get_availability_sli(service_id, window_days)` |
| `DependencyWithAvailability` | Value object for deps with availability | Constructor |
| `CompositeResult` | Output of composite computation | Direct attribute access |
| Mock Prometheus Client | Telemetry data source | Implements `TelemetryQueryServiceInterface` |

### FR-2 Components Required as Phase 0 Prerequisites

Since FR-2 is "Not Started", FR-3 Phase 0 must create minimal stubs for:

| Component | FR-3 Needs | Phase 0 Action |
|-----------|------------|----------------|
| `CompositeAvailabilityService` | `compute_composite_bound()` | Implement fully (FR-3 extends it, so it's a real dep) |
| `CompositeResult` dataclass | Output of composite bound | Implement fully |
| `DependencyWithAvailability` | Input to composite and budget analysis | Implement fully |
| `TelemetryQueryServiceInterface` | `get_availability_sli()` | Define interface + mock stub |
| `AvailabilitySliData` | Return type from telemetry | Implement fully |

These are the *minimal* FR-2 components needed. The full FR-2 recommendation pipeline (tiers, latency, attribution, batch, etc.) is NOT needed for FR-3.

### External Dependencies

| Dependency | Purpose | Interface |
|------------|---------|-----------|
| Mock Prometheus Client | Telemetry data source | `TelemetryQueryServiceInterface` |
| PostgreSQL | Services table, dependency graph | SQLAlchemy 2.0 async |

---

## 9. Security Considerations

- **Input validation:** All query parameters validated via Pydantic (`desired_target_pct` range 90-99.9999, `lookback_days` 7-365, `max_depth` 1-10)
- **Authorization:** Same API key auth as FR-1 endpoints (`X-API-Key` header)
- **Rate limiting:** 30 req/min for constraint analysis (heavier computation), 60 req/min for error budget breakdown (lighter)
- **No user input in computations:** All computations use service IDs from the database, telemetry from the mock stub, and query parameters validated by Pydantic. No raw user input enters math operations.
- **service_type validation:** Enforced by PostgreSQL CHECK constraint (`'internal'` or `'external'`)
- **published_sla validation:** Pydantic validates range (0.0 to 1.0) at API ingestion time
- **No PII:** All data is operational metrics (availability ratios, service identifiers)
- **JSONB safety:** No JSONB fields in FR-3 responses built from user input
- **SQL injection:** All queries via SQLAlchemy ORM or parameterized queries (inherited from FR-1)

---

## 10. Testing Strategy

### Test Distribution

| Layer | Test Type | Coverage Target | Framework |
|-------|-----------|----------------|-----------|
| Domain entities | Unit | >95% | pytest |
| Domain services (ExternalApiBuffer, ErrorBudgetAnalyzer, UnachievableDetector) | Unit | >95% | pytest |
| CompositeAvailabilityService extensions | Unit | >95% | pytest |
| Application use cases | Unit | >90% | pytest + AsyncMock |
| DTOs | Unit | >90% | pytest |
| Infrastructure (API routes) | Integration | >80% | pytest + httpx |
| Infrastructure (migration) | Integration | 100% | pytest + testcontainers |
| E2E (ingest graph → constraint analysis) | E2E | Critical paths | pytest + httpx |

### Test Data Requirements

**Dependency Graph Fixtures:**
- Simple serial chain: A → B → C → D (all hard sync)
- Mixed chain: A → B (hard sync), A → C (soft async), B → D (hard sync)
- External dependency: A → B (internal), B → ExtAPI (external, published SLA=99.99%)
- No dependencies: isolated service
- Circular: A → B → C → A (SCC test)
- Deep chain: 10 levels deep (max depth test)
- Parallel redundant: A → {B, C} where both serve same function

**Telemetry Fixtures (mock):**
- Service with 99.95% availability (typical)
- Service with 99.5% availability (degraded external)
- Service with no telemetry data (cold start)
- Service with 100% availability (edge case)
- Service with 95% availability (highly degraded)

**External Provider Fixtures:**
- Published SLA=99.99%, observed=99.60% (SLA overstated)
- Published SLA=99.99%, observed=99.99% (SLA accurate)
- Published SLA only, no observed data
- Observed data only, no published SLA
- Neither published nor observed (cold start)

### Key Test Cases

| Test | Type | Validates |
|------|------|-----------|
| `min(observed, published×adj)` computes correctly | Unit | ExternalApiBufferService formula |
| TRD example: published 99.99% → effective 99.89% | Unit | Pessimistic adjustment matches spec |
| Error budget: dep at 99.5% consumes 500% of 99.9% budget | Unit | ErrorBudgetAnalyzer formula |
| >30% consumption flags as HIGH risk | Unit | Risk classification |
| Serial composition: 3 deps at 99.9% each → bound ≈ 99.7% | Unit | CompositeAvailabilityService math |
| Unachievable: target 99.99%, bound 99.70% → warning | Unit | UnachievableSloDetector |
| 10x rule: 99.99% target with 3 deps → required ≈ 99.9975% | Unit | Required dep computation |
| Soft deps excluded from composite but listed in risks | Unit | Classification logic |
| Circular dep → SCC supernode with weakest-link | Unit | SCC handling |
| Service not found → 404 | Integration | API error handling |
| No dependencies → 422 | Integration | API error handling |
| Full pipeline: ingest graph → constraint analysis → valid response | E2E | End-to-end workflow |
| External dep with no data → default 99.9% + note | Unit | Cold start fallback |
| SLO target 100% → consumption = infinity → capped | Unit | Edge case handling |
| `published_sla` pessimistic floors at 0.0 | Unit | Low SLA edge case |

---

## 11. Performance Considerations

### Expected Load

| Operation | Expected Volume | Target Latency |
|-----------|----------------|----------------|
| `GET /constraint-analysis` | ~30 req/min | < 2s (p95) |
| `GET /error-budget-breakdown` | ~60 req/min | < 1s (p95) |

### Latency Budget Breakdown (constraint-analysis)

| Step | Expected Latency | Notes |
|------|-----------------|-------|
| Service lookup | ~5ms | Indexed query |
| Graph traversal (depth=3) | ~50-100ms | Recursive CTE, same as FR-1 |
| Telemetry queries (N deps) | ~200-500ms | N parallel mock queries; real Prometheus will be slower |
| Composite computation | ~1ms | Pure math |
| Error budget analysis | ~1ms | Pure math |
| Unachievability check | <1ms | Pure math |
| Response serialization | ~5ms | Pydantic |
| **Total** | **~300-700ms** | Well within 2s target |

### Optimization Strategies

1. **Parallel telemetry queries:** Use `asyncio.gather()` for all dependency availability queries simultaneously
2. **Graph traversal caching:** During high load, cache dependency subgraph results for ~60s (same graph queried by multiple callers)
3. **Short-circuit for no deps:** If service has no hard sync deps, skip composite math and return self_availability as bound
4. **Lazy computation:** Error budget breakdown only computed for hard deps (soft excluded)

### Monitoring Metrics

| Metric | Type | Alert Threshold |
|--------|------|----------------|
| `slo_engine_constraint_analysis_duration_seconds` | Histogram | p95 > 2s |
| `slo_engine_error_budget_breakdown_duration_seconds` | Histogram | p95 > 1s |
| `slo_engine_unachievable_slos_detected_total` | Counter | N/A (observability) |
| `slo_engine_high_risk_dependencies_detected_total` | Counter | N/A (observability) |
| `slo_engine_external_deps_queried_total` | Counter | N/A (observability) |

---

## 12. Implementation Phases

### Phase 0: FR-2 Prerequisites [Week 1, Days 1-3]

**Objective:** Implement the minimal FR-2 components that FR-3 depends on, so FR-3 development is unblocked without waiting for full FR-2 completion.

**Tasks:**

* **Task 0.1: AvailabilitySliData Entity + DependencyWithAvailability Value Object** [Effort: S]
  - **Description:** Create the shared domain entities/value objects that FR-2 and FR-3 both need
  - **Acceptance Criteria:**
    - [ ] `AvailabilitySliData` dataclass with `availability_ratio`, `error_rate` property, window fields
    - [ ] `DependencyWithAvailability` dataclass with edge, availability, external flags
    - [ ] `CompositeResult` dataclass with bound, bottleneck info
    - [ ] >95% unit test coverage
  - **Files to Create:**
    - `src/domain/entities/sli_data.py` — AvailabilitySliData, LatencySliData
    - `src/domain/entities/dependency_with_availability.py` — DependencyWithAvailability, CompositeResult
    - `tests/unit/domain/entities/test_sli_data.py`
    - `tests/unit/domain/entities/test_dependency_with_availability.py`
  - **Dependencies:** None
  - **Testing Requirements:** Unit tests only

* **Task 0.2: TelemetryQueryServiceInterface + Mock Prometheus Stub** [Effort: M]
  - **Description:** Define the telemetry interface and mock implementation for development
  - **Acceptance Criteria:**
    - [ ] `TelemetryQueryServiceInterface` ABC with `get_availability_sli()`, `get_data_completeness()`
    - [ ] `MockPrometheusClient` implementation with configurable seed data per service_id
    - [ ] Seed data: 5 services with 30-day data, 2 with 10-day, 1 external with observed data, 1 with no data
    - [ ] >90% unit test coverage
  - **Files to Create:**
    - `src/domain/repositories/telemetry_query_service.py` — Interface
    - `src/infrastructure/telemetry/mock_prometheus_client.py` — Mock implementation
    - `src/infrastructure/telemetry/seed_data.py` — Default seed data
    - `tests/unit/infrastructure/telemetry/test_mock_prometheus_client.py`
  - **Dependencies:** Task 0.1
  - **Testing Requirements:** Unit tests

* **Task 0.3: CompositeAvailabilityService** [Effort: L]
  - **Description:** Implement the composite availability service that both FR-2 and FR-3 extend
  - **Acceptance Criteria:**
    - [ ] Serial hard deps: `R = R_self × Π(R_hard_dep_i)`
    - [ ] Parallel redundant paths: `R = 1 − Π(1 − R_replica_j)`
    - [ ] Soft deps excluded from composite, counted in metadata
    - [ ] Bottleneck identification (dep contributing most to degradation)
    - [ ] SCC supernode handling: use weakest-link member
    - [ ] Returns `CompositeResult` with bound, bottleneck, per-dep contributions
    - [ ] >95% unit test coverage
  - **Files to Create:**
    - `src/domain/services/composite_availability_service.py`
    - `tests/unit/domain/services/test_composite_availability_service.py`
  - **Dependencies:** Task 0.1
  - **Testing Requirements:** Unit tests with known-answer vectors

**Phase 0 Deliverables:**
- Shared FR-2/FR-3 domain entities and value objects
- Telemetry interface and mock stub
- Composite availability service with full test coverage
- FR-3 development fully unblocked

---

### Phase 1: FR-3 Domain Foundation [Week 1, Days 4-5 + Week 2, Days 1-2]

**Objective:** Implement FR-3's unique domain entities and services.

**Tasks:**

* **Task 1.1: Constraint Analysis Entities** [Effort: M]
  - **Description:** Create `ConstraintAnalysis`, `ErrorBudgetBreakdown`, `DependencyRiskAssessment`, `UnachievableWarning`, `ExternalProviderProfile`, `ServiceType`, `RiskLevel` domain entities
  - **Acceptance Criteria:**
    - [ ] All entities as dataclasses with validation in `__post_init__`
    - [ ] `ExternalProviderProfile.effective_availability` property implements adaptive buffer
    - [ ] `ConstraintAnalysis.is_achievable` and `has_high_risk_dependencies` properties
    - [ ] `DependencyRiskAssessment.error_budget_consumption_pct` validated 0-100
    - [ ] `ServiceType` and `RiskLevel` enums defined
    - [ ] >95% unit test coverage
  - **Files to Create:**
    - `src/domain/entities/constraint_analysis.py` — All FR-3 entities
    - `tests/unit/domain/entities/test_constraint_analysis.py` — Unit tests
  - **Dependencies:** Task 0.1 (AvailabilitySliData, DependencyWithAvailability)
  - **Testing Requirements:** Unit tests

* **Task 1.2: ExternalApiBufferService** [Effort: M]
  - **Description:** Implement external API adaptive buffer computation service
  - **Acceptance Criteria:**
    - [ ] `compute_effective_availability()` implements min(observed, published_adjusted)
    - [ ] Pessimistic adjustment: `published_adjusted = 1 - (1-published) * 11`
    - [ ] TRD example passes: published 99.99% → effective 99.89%
    - [ ] Fallback chain: both → observed-only → published-only → default 99.9%
    - [ ] `generate_availability_note()` produces human-readable explanations
    - [ ] `published_adjusted` floors at 0.0 for very low SLAs
    - [ ] >95% unit test coverage
  - **Files to Create:**
    - `src/domain/services/external_api_buffer_service.py`
    - `tests/unit/domain/services/test_external_api_buffer_service.py`
  - **Dependencies:** Task 1.1
  - **Testing Requirements:** Unit tests with TRD validation vectors

* **Task 1.3: ErrorBudgetAnalyzer** [Effort: L]
  - **Description:** Implement per-dependency error budget consumption analysis and risk classification
  - **Acceptance Criteria:**
    - [ ] `compute_breakdown()` returns full breakdown for all hard deps
    - [ ] Formula: `consumption = (1 - R_dep) / (1 - SLO_target/100)`
    - [ ] Risk classification: LOW (<20%), MODERATE (20-30%), HIGH (>30%)
    - [ ] `high_risk_dependencies` list populated correctly
    - [ ] `total_dependency_consumption_pct` sums all dep consumptions
    - [ ] `self_consumption_pct` computed as service's own error rate contribution
    - [ ] 100% SLO target → consumption capped at 999999.99 for JSON safety
    - [ ] `compute_error_budget_minutes()` matches TRD formula
    - [ ] >95% unit test coverage
  - **Files to Create:**
    - `src/domain/services/error_budget_analyzer.py`
    - `tests/unit/domain/services/test_error_budget_analyzer.py`
  - **Dependencies:** Task 1.1
  - **Testing Requirements:** Unit tests with known-answer vectors

* **Task 1.4: UnachievableSloDetector** [Effort: M]
  - **Description:** Implement unachievable SLO detection with 10x rule guidance
  - **Acceptance Criteria:**
    - [ ] `check()` returns `None` when achievable, `UnachievableWarning` when not
    - [ ] Compares `composite_bound` (ratio) against `desired_target_pct / 100`
    - [ ] 10x rule: `required = 1 - (1-target)/(N+1)` for N hard deps
    - [ ] `generate_warning_message()` matches TRD example string
    - [ ] `generate_remediation_guidance()` includes 3 concrete suggestions
    - [ ] Edge case: 0 hard deps → required = desired target
    - [ ] Edge case: tiny gap (<0.01%) → still flagged
    - [ ] >95% unit test coverage
  - **Files to Create:**
    - `src/domain/services/unachievable_slo_detector.py`
    - `tests/unit/domain/services/test_unachievable_slo_detector.py`
  - **Dependencies:** Task 1.1
  - **Testing Requirements:** Unit tests with TRD validation vectors

**Phase 1 Deliverables:**
- All FR-3 domain entities with validation
- Four domain services with >95% test coverage
- Known-answer test vectors matching TRD examples

---

### Phase 2: Application Layer [Week 2, Days 3-5]

**Objective:** Implement use cases, DTOs, and wire up domain services.

**Tasks:**

* **Task 2.1: Constraint Analysis DTOs** [Effort: M]
  - **Description:** Create all DTOs for request/response in the application layer
  - **Acceptance Criteria:**
    - [ ] All 9 DTO dataclasses created (requests, responses, risk, warning, breakdown)
    - [ ] DTOs use dataclasses (not Pydantic — reserved for API layer)
    - [ ] Percentages use `_pct` suffix convention consistently
    - [ ] >90% unit test coverage
  - **Files to Create:**
    - `src/application/dtos/constraint_analysis_dto.py`
    - `tests/unit/application/dtos/test_constraint_analysis_dto.py`
  - **Dependencies:** Phase 1 complete
  - **Testing Requirements:** Unit tests

* **Task 2.2: RunConstraintAnalysisUseCase** [Effort: XL]
  - **Description:** Implement the full constraint analysis pipeline orchestrating all domain services
  - **Acceptance Criteria:**
    - [ ] Full pipeline: validate → subgraph → classify → resolve availability → composite → budget → achievability → SCC → build response
    - [ ] External deps use adaptive buffer (ExternalApiBufferService)
    - [ ] Internal deps use observed availability from telemetry
    - [ ] Dependencies with no data default to 99.9%
    - [ ] Soft deps excluded from composite, listed in soft_dependency_risks
    - [ ] SCC supernodes reported from FR-1 alert data
    - [ ] Returns None if service not found
    - [ ] Returns error DTO if service has no deps
    - [ ] Parallel telemetry queries via asyncio.gather
    - [ ] >90% unit test coverage with mocked dependencies
  - **Files to Create:**
    - `src/application/use_cases/run_constraint_analysis.py`
    - `tests/unit/application/use_cases/test_run_constraint_analysis.py`
  - **Dependencies:** Task 2.1, Phase 1 complete
  - **Testing Requirements:** Unit tests with AsyncMock for all dependencies

* **Task 2.3: GetErrorBudgetBreakdownUseCase** [Effort: L]
  - **Description:** Implement lighter-weight error budget breakdown (depth=1 only)
  - **Acceptance Criteria:**
    - [ ] Retrieves direct dependencies only (depth=1)
    - [ ] Filters to hard deps only for budget computation
    - [ ] External deps use adaptive buffer
    - [ ] Returns ErrorBudgetBreakdownResponse
    - [ ] Returns None if service not found
    - [ ] >90% unit test coverage
  - **Files to Create:**
    - `src/application/use_cases/get_error_budget_breakdown.py`
    - `tests/unit/application/use_cases/test_get_error_budget_breakdown.py`
  - **Dependencies:** Task 2.1, Phase 1 complete
  - **Testing Requirements:** Unit tests with AsyncMock

**Phase 2 Deliverables:**
- Both use cases with >90% test coverage
- Full pipeline testable with mocks
- Parallel telemetry queries implemented

---

### Phase 3: Infrastructure — Database & API [Week 3]

**Objective:** Implement database migration, API schemas, routes, and wire everything together.

**Tasks:**

* **Task 3.1: Alembic Migration — Add service_type to services** [Effort: S]
  - **Description:** Create migration adding `service_type` and `published_sla` columns to `services` table
  - **Acceptance Criteria:**
    - [ ] `service_type` VARCHAR(20) NOT NULL DEFAULT 'internal' with CHECK constraint
    - [ ] `published_sla` DECIMAL(8,6) DEFAULT NULL
    - [ ] Partial index `idx_services_external` for external service lookups
    - [ ] Migration fully reversible (downgrade drops columns + index)
    - [ ] Tested against real PostgreSQL via testcontainers
    - [ ] Existing data unaffected (all services default to 'internal')
  - **Files to Create:**
    - `alembic/versions/XXX_add_service_type_to_services.py`
  - **Dependencies:** None (additive migration)
  - **Testing Requirements:** Integration test (migration up/down)

* **Task 3.2: Update Service Entity & Repository** [Effort: M]
  - **Description:** Add `service_type` and `published_sla` to Service entity, ServiceModel, and ServiceRepository
  - **Acceptance Criteria:**
    - [ ] `Service` entity: add `service_type: ServiceType = ServiceType.INTERNAL` and `published_sla: float | None = None`
    - [ ] `ServiceModel`: add corresponding columns
    - [ ] `ServiceRepository._to_entity()` and `_to_dict()` handle new fields
    - [ ] `ServiceRepository.get_external_services()` implemented
    - [ ] `ServiceType` enum importable from `src.domain.entities.constraint_analysis`
    - [ ] FR-1 ingestion API accepts optional `service_type` and `published_sla` in node metadata
    - [ ] Existing tests still pass (backward compatible)
  - **Files to Modify:**
    - `src/domain/entities/service.py` — Add service_type, published_sla
    - `src/domain/entities/constraint_analysis.py` — ServiceType enum (already created in Phase 1)
    - `src/domain/repositories/service_repository.py` — Add get_external_services()
    - `src/infrastructure/database/models.py` — Update ServiceModel
    - `src/infrastructure/database/repositories/service_repository.py` — Update mapping + new method
  - **Dependencies:** Task 3.1, Phase 1
  - **Testing Requirements:** Integration tests

* **Task 3.3: Pydantic API Schemas** [Effort: M]
  - **Description:** Create Pydantic v2 models for constraint analysis API
  - **Acceptance Criteria:**
    - [ ] `ConstraintAnalysisQueryParams`: validates `desired_target_pct` (90-99.9999), `lookback_days` (7-365), `max_depth` (1-10)
    - [ ] `ConstraintAnalysisResponse`: matches API spec JSON structure exactly
    - [ ] `ErrorBudgetBreakdownQueryParams`: validates `slo_target_pct` (90-99.9999), `lookback_days`
    - [ ] `ErrorBudgetBreakdownResponse`: matches API spec
    - [ ] Nested models: `DependencyRiskResponse`, `UnachievableWarningResponse`, etc.
    - [ ] RFC 7807 error schema reused from FR-1
  - **Files to Create:**
    - `src/infrastructure/api/schemas/constraint_analysis_schema.py`
    - `tests/unit/infrastructure/api/schemas/test_constraint_analysis_schema.py`
  - **Dependencies:** Phase 2 DTOs
  - **Testing Requirements:** Unit tests for validation rules

* **Task 3.4: API Routes** [Effort: L]
  - **Description:** Implement two FastAPI route handlers with dependency injection
  - **Acceptance Criteria:**
    - [ ] `GET /api/v1/services/{service_id}/constraint-analysis` registered
    - [ ] `GET /api/v1/services/{service_id}/error-budget-breakdown` registered
    - [ ] Auth middleware applied (X-API-Key)
    - [ ] Rate limiting: 30 req/min (constraint) and 60 req/min (budget)
    - [ ] 200: returns computed analysis
    - [ ] 404: service not found
    - [ ] 422: no dependencies registered
    - [ ] 400: invalid query parameters
    - [ ] 429: rate limit exceeded
    - [ ] Integration test with httpx async client
  - **Files to Create:**
    - `src/infrastructure/api/routes/constraint_analysis.py`
    - `tests/integration/infrastructure/api/test_constraint_analysis_endpoint.py`
  - **Dependencies:** Task 3.3, Phase 2 complete
  - **Testing Requirements:** Integration tests with httpx + testcontainers

* **Task 3.5: Dependency Injection Wiring** [Effort: M]
  - **Description:** Wire all FR-3 domain services, use cases via FastAPI dependency injection
  - **Acceptance Criteria:**
    - [ ] FastAPI `Depends()` chain for both route handlers
    - [ ] All services instantiated with correct dependencies
    - [ ] Mock Prometheus client injected via config toggle
    - [ ] Session management preserved from FR-1
    - [ ] New routes registered in main.py
  - **Files to Modify:**
    - `src/infrastructure/api/dependencies.py` — Add FR-3 dependencies
    - `src/infrastructure/api/main.py` — Register new router
  - **Dependencies:** Task 3.4
  - **Testing Requirements:** Verified by integration tests

* **Task 3.6: End-to-End Tests** [Effort: L]
  - **Description:** Full workflow E2E tests: ingest graph (with external service) → constraint analysis → error budget breakdown
  - **Acceptance Criteria:**
    - [ ] E2E: POST /services/dependencies (with external service) → GET /constraint-analysis returns valid response
    - [ ] E2E: External dep uses adaptive buffer correctly in response
    - [ ] E2E: Unachievable SLO detected for high target with low-availability deps
    - [ ] E2E: Error budget breakdown endpoint returns valid response
    - [ ] E2E: Service with no deps → 422
    - [ ] E2E: Service not found → 404
    - [ ] Performance: constraint analysis < 2s
    - [ ] Performance: error budget breakdown < 1s
  - **Files to Create:**
    - `tests/e2e/test_constraint_analysis.py`
  - **Dependencies:** Task 3.4, Task 3.5
  - **Testing Requirements:** E2E with testcontainers + httpx

**Phase 3 Deliverables:**
- Database migration applied and tested
- Service entity updated with service_type
- Two API endpoints with auth and rate limiting
- E2E tests passing
- Full FR-3 feature functional

---

## 13. Pending Decisions & Clarifications

| # | Question | Options | Current Default | Status |
|---|----------|---------|-----------------|--------|
| 1 | **Should constraint analysis results be cached?** | (A) No cache — compute on demand every time. (B) PostgreSQL cache with 1h TTL. (C) Redis cache with configurable TTL. | No cache (compute on demand). Response time target (< 2s) is achievable. Cache adds complexity. | **Decided: No cache (MVP). Revisit if load testing shows issues.** |
| 2 | **Should FR-3 write back to FR-2 recommendations?** | (A) FR-3 is read-only analysis, doesn't modify recommendations. (B) FR-3 enriches FR-2 recommendations with constraint data. | FR-3 is read-only analysis with dedicated endpoints. FR-2 recommendations are separate. | **Decided: Read-only.** |
| 3 | **How should the ingestion API accept `service_type`?** | (A) New field in node metadata during ingestion. (B) Separate `PATCH /api/v1/services/{id}` endpoint. (C) Both. | New field in node metadata (simplest, extends existing ingestion flow). | **Decided: Node metadata field.** |
| 4 | **Pessimistic adjustment interpretation** | (A) Multiply by 0.9 (99.99% → 89.99%). (B) Add 10× unavailability margin (99.99% → 99.89%). | Option B (99.99% → 99.89%) matches TRD example exactly. | **Decided: Option B (10× unavailability margin).** |
| 5 | **Should FR-3 compute latency constraint propagation?** | (A) Availability only (MVP). (B) Both availability and latency. | Availability only. TRD says "percentiles are non-additive" and latency uses end-to-end trace measurement, so constraint propagation doesn't apply to latency the same way. | **Decided: Availability only.** |
| 6 | **What SLO target should be used when none is provided or active?** | (A) 99.9% default (balanced tier). (B) Use FR-2 balanced tier recommendation if available. (C) Require the user to provide one. | 99.9% default. FR-2 recommendation may not exist yet. | **Decided: 99.9% default, with preference for active SLO if available (FR-5 future).** |
| 7 | **Should `published_sla` be stored as ratio or percentage?** | (A) Ratio (0.9999). (B) Percentage (99.99). | Ratio (consistent with availability_ratio throughout the system). API accepts percentage, domain converts to ratio. | **Decided: Ratio internally, percentage in API.** |
