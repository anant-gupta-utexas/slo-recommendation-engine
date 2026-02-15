# FR-2: SLO Recommendation Generation — Technical Requirements Specification

**Created:** 2026-02-15
**Status:** Draft
**Corresponds to:** TRD Section 3 FR-2, PRD F2, F3, F6 (partial), F7

---

## 1. Overview & Scope

### Objective

Implement the SLO Recommendation Generation engine — the core value-producing feature of the system. Given a service registered in the dependency graph (FR-1), this feature computes **availability** and **latency** SLO recommendations across three tiers (Conservative / Balanced / Aggressive) using historical telemetry data and dependency-aware constraint propagation.

### Scope Boundaries

**In scope (FR-2 MVP):**
- Availability SLO computation via composite reliability math (serial/parallel)
- Latency SLO computation via historical percentile analysis
- Three-tier recommendation output (Conservative / Balanced / Aggressive)
- Weighted feature attribution for explainability (MVP heuristic weights)
- Dependency-aware tier adjustment (cap by composite availability bound)
- Pre-computed recommendation storage in PostgreSQL (batch pipeline)
- Mock Prometheus stub for parallel development & testing
- Extended lookback cold-start strategy (no archetype matching)
- `GET /api/v1/services/{service-id}/slo-recommendations` endpoint
- `slo_recommendations` table and `sli_aggregates` table

**Out of scope (deferred):**
- `active_slos` and `slo_audit_log` tables (FR-5)
- Accept/modify/reject workflow (FR-5)
- Impact analysis endpoint (FR-4)
- Redis caching layer (using PostgreSQL pre-computed storage instead)
- SHAP library integration (using weighted attribution)
- Archetype-based cold-start (using extended lookback only)
- Drift detection (FR-9)
- Real Prometheus/Mimir integration (mock stub for MVP)
- Counterfactual analysis (deferred to Phase 5 when ML models are available)
- What-if simulations (deferred to FR-16)

### Key Design Decisions (Confirmed)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Telemetry source | Mock Prometheus stub | Enables parallel development; real integration in FR-6 |
| Explainability | Weighted attribution (fixed domain weights) | Simpler than SHAP; sufficient for rule-based MVP |
| Caching strategy | Pre-compute all, store in PostgreSQL | Simpler ops than Redis lazy-compute; aligns with batch freshness target |
| Cold-start | Extended lookback to 90 days | Simpler than archetype matching; explicit low-confidence flag |
| Tier computation | Percentile + dependency adjustment (hard cap) | Mathematically sound; prevents unachievable SLOs |
| Schema scope | `slo_recommendations` + `sli_aggregates` only | Minimal scope; `active_slos` and `slo_audit_log` deferred to FR-5 |
| SLI coverage | Availability + Latency | Matches TRD FR-2 MVP scope |

---

## 2. Requirements Summary

### Functional Requirements

| ID | Requirement | Source |
|----|-------------|--------|
| FR2-01 | Generate availability SLO recommendations using composite reliability math | TRD 3.2 |
| FR2-02 | Generate latency SLO recommendations using historical percentile analysis | TRD 3.2 |
| FR2-03 | Present three tiers per recommendation: Conservative, Balanced, Aggressive | TRD 3.2, PRD F2 |
| FR2-04 | Include weighted feature attribution in every recommendation | TRD 3.7, PRD F7 |
| FR2-05 | Include dependency impact summary (composite bound, bottleneck service) | TRD 3.3 |
| FR2-06 | Include data quality metadata (completeness, gaps, confidence note) | TRD 3.2 |
| FR2-07 | Handle cold-start via extended lookback (up to 90 days) | TRD 3.2 |
| FR2-08 | Pre-compute recommendations via batch pipeline | Decision |
| FR2-09 | Expose `GET /api/v1/services/{id}/slo-recommendations` API endpoint | TRD 3.8 |
| FR2-10 | Support `force_regenerate` query parameter for on-demand recomputation | TRD 3.2 |
| FR2-11 | Flag unachievable SLOs when composite bound < desired target | TRD 3.3 |

### Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR2-01 | Recommendation retrieval latency (p95) | < 500ms (pre-computed) |
| NFR2-02 | On-demand generation latency (p95) | < 5s |
| NFR2-03 | Batch pipeline throughput | Process 5,000 services within 30 minutes |
| NFR2-04 | Domain layer test coverage | > 90% |
| NFR2-05 | Application layer test coverage | > 85% |
| NFR2-06 | Infrastructure layer test coverage | > 75% |

---

## 3. Detailed Component Design

### 3.1 Architecture Overview (Clean Architecture Layers)

```
┌──────────────────────────────────────────────────────┐
│ Infrastructure Layer                                  │
│ ┌─────────────────┐ ┌──────────────────────────────┐ │
│ │ API Routes       │ │ Database                     │ │
│ │ recommendations  │ │ SloRecommendationRepository  │ │
│ │ .py              │ │ SliAggregateRepository       │ │
│ └────────┬────────┘ └──────────────┬───────────────┘ │
│ ┌────────┴────────┐ ┌──────────────┴───────────────┐ │
│ │ Pydantic        │ │ Telemetry                    │ │
│ │ Schemas         │ │ PrometheusClient (mock stub) │ │
│ └────────┬────────┘ └──────────────┬───────────────┘ │
│ ┌────────┴────────┐ ┌──────────────┴───────────────┐ │
│ │ Background      │ │ SQLAlchemy Models             │ │
│ │ Tasks           │ │ SloRecommendationModel        │ │
│ │ (APScheduler)   │ │ SliAggregateModel             │ │
│ └─────────────────┘ └──────────────────────────────┘ │
├──────────────────────────────────────────────────────┤
│ Application Layer                                     │
│ ┌─────────────────────────────────────────────────┐  │
│ │ Use Cases                                        │  │
│ │ - GenerateSloRecommendationUseCase               │  │
│ │ - GetSloRecommendationUseCase                    │  │
│ │ - BatchComputeRecommendationsUseCase             │  │
│ │ DTOs                                             │  │
│ │ - SloRecommendationDTO, TierDTO, ExplanationDTO  │  │
│ └────────────────────────┬────────────────────────┘  │
├──────────────────────────┼───────────────────────────┤
│ Domain Layer             │                            │
│ ┌────────────────────────┴────────────────────────┐  │
│ │ Entities                                         │  │
│ │ - SloRecommendation, RecommendationTier, SliData │  │
│ │ Services                                         │  │
│ │ - AvailabilityCalculator                         │  │
│ │ - LatencyCalculator                              │  │
│ │ - CompositeAvailabilityService                   │  │
│ │ - WeightedAttributionService                     │  │
│ │ Repositories (Interfaces)                        │  │
│ │ - SloRecommendationRepositoryInterface           │  │
│ │ - TelemetryQueryServiceInterface                 │  │
│ └─────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

### 3.2 Domain Layer

#### Entities

**`src/domain/entities/slo_recommendation.py`**

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4


class SliType(str, Enum):
    AVAILABILITY = "availability"
    LATENCY = "latency"


class RecommendationStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class TierLevel(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


@dataclass
class RecommendationTier:
    """A single tier (Conservative/Balanced/Aggressive) within a recommendation."""
    level: TierLevel
    target: float                      # e.g., 99.9 for availability, 800 for latency ms
    error_budget_monthly_minutes: float | None = None   # availability only
    estimated_breach_probability: float = 0.0
    confidence_interval: tuple[float, float] | None = None
    percentile: str | None = None      # latency only (e.g., "p99")
    target_ms: int | None = None       # latency only

    def __post_init__(self):
        if not (0.0 <= self.estimated_breach_probability <= 1.0):
            raise ValueError("estimated_breach_probability must be between 0.0 and 1.0")


@dataclass
class FeatureAttribution:
    """A single feature's contribution to the recommendation."""
    feature: str
    contribution: float   # 0.0 to 1.0, all contributions sum to 1.0
    description: str = ""


@dataclass
class DependencyImpact:
    """Dependency impact analysis for a recommendation."""
    composite_availability_bound: float
    bottleneck_service: str | None = None
    bottleneck_contribution: str = ""
    hard_dependency_count: int = 0
    soft_dependency_count: int = 0


@dataclass
class DataQuality:
    """Data quality metadata for a recommendation."""
    data_completeness: float        # 0.0 to 1.0
    telemetry_gaps: list[dict] = field(default_factory=list)
    confidence_note: str = ""
    is_cold_start: bool = False
    lookback_days_actual: int = 30


@dataclass
class Explanation:
    """Full explanation for a recommendation."""
    summary: str
    feature_attribution: list[FeatureAttribution] = field(default_factory=list)
    dependency_impact: DependencyImpact | None = None


@dataclass
class SloRecommendation:
    """Represents a single SLO recommendation for one SLI type."""
    service_id: UUID
    sli_type: SliType
    tiers: dict[TierLevel, RecommendationTier]
    explanation: Explanation
    data_quality: DataQuality
    lookback_window_start: datetime
    lookback_window_end: datetime
    metric: str                          # e.g., "error_rate", "p99_response_time_ms"

    # Metadata
    id: UUID = field(default_factory=uuid4)
    status: RecommendationStatus = RecommendationStatus.ACTIVE
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None   # generated_at + 24h

    def __post_init__(self):
        if self.expires_at is None:
            from datetime import timedelta
            self.expires_at = self.generated_at + timedelta(hours=24)

    def supersede(self):
        self.status = RecommendationStatus.SUPERSEDED

    def expire(self):
        self.status = RecommendationStatus.EXPIRED

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at if self.expires_at else False
```

**`src/domain/entities/sli_data.py`**

```python
@dataclass
class AvailabilitySliData:
    """Raw availability SLI data from telemetry source."""
    service_id: str
    good_events: int
    total_events: int
    availability_ratio: float        # good / total
    window_start: datetime
    window_end: datetime
    sample_count: int = 0

    @property
    def error_rate(self) -> float:
        return 1.0 - self.availability_ratio


@dataclass
class LatencySliData:
    """Raw latency SLI data from telemetry source."""
    service_id: str
    p50_ms: float
    p95_ms: float
    p99_ms: float
    p999_ms: float
    window_start: datetime
    window_end: datetime
    sample_count: int = 0
```

#### Domain Services

**`src/domain/services/availability_calculator.py`**

Core computation for availability SLO tiers:

```python
class AvailabilityCalculator:
    """Computes availability SLO recommendation tiers.

    Algorithm:
    1. Compute base availability from historical data
    2. Compute composite availability bound from dependency chain
    3. Compute tier targets = percentile-based + capped by composite bound
    4. Estimate breach probability from historical windows
    """

    def compute_tiers(
        self,
        historical_availability: float,       # e.g., 0.9992
        rolling_availabilities: list[float],  # daily rolling values for breach estimation
        composite_bound: float,               # from CompositeAvailabilityService
    ) -> dict[TierLevel, RecommendationTier]:
        """Compute three-tier availability recommendation.

        Conservative: historical floor (p99.9 of rolling) capped by composite
        Balanced:     historical p99 capped by composite
        Aggressive:   historical p95 (NOT capped — shows achievable without deps)
        """

    def estimate_breach_probability(
        self,
        target: float,
        rolling_availabilities: list[float],
    ) -> float:
        """Count fraction of windows where target would have been breached."""

    @staticmethod
    def compute_error_budget_minutes(target_percentage: float) -> float:
        """Compute monthly error budget in minutes.
        Monthly minutes = 43200 (30 days)
        Budget = (1 - target/100) * 43200
        """
```

**`src/domain/services/latency_calculator.py`**

```python
class LatencyCalculator:
    """Computes latency SLO recommendation tiers.

    Algorithm:
    1. Use historical percentile data from telemetry
    2. Apply noise margin (5-10%) for shared infrastructure
    3. Compute tier targets based on percentile levels
    """

    NOISE_MARGIN: float = 0.05  # 5% buffer

    def compute_tiers(
        self,
        latency_data: LatencySliData,
        has_shared_infrastructure: bool = False,
    ) -> dict[TierLevel, RecommendationTier]:
        """Compute three-tier latency recommendation.

        Conservative: p99.9 + noise margin
        Balanced:     p99 + noise margin
        Aggressive:   p95 (no margin)
        """

    def apply_noise_margin(self, latency_ms: float) -> float:
        """Add noise margin to latency value."""
```

**`src/domain/services/composite_availability_service.py`**

```python
class CompositeAvailabilityService:
    """Computes composite availability bounds from dependency chains.

    Handles:
    - Serial hard dependencies: R_composite = R_self * R_dep1 * R_dep2
    - Parallel redundant paths: R = 1 - (1-R_primary)(1-R_fallback)
    - Soft dependencies: excluded from composite, noted as risk
    - SCCs (circular): weakest-link member used as supernode availability
    """

    def compute_composite_bound(
        self,
        service_availability: float,
        dependencies: list[DependencyWithAvailability],
    ) -> CompositeResult:
        """Compute composite availability bound.

        Returns:
            CompositeResult with bound, bottleneck info, and per-dep contributions
        """

    def identify_bottleneck(
        self,
        dependencies: list[DependencyWithAvailability],
    ) -> tuple[str | None, str]:
        """Identify the dependency contributing most to composite degradation."""
```

**`src/domain/services/weighted_attribution_service.py`**

```python
class WeightedAttributionService:
    """Computes weighted feature attribution for recommendation explainability.

    MVP heuristic weights (to be replaced by ML-derived SHAP values in Phase 5):
    - historical_metric_mean:       0.40  (primary driver)
    - composite_availability_bound: 0.30  (dependency constraint)
    - deployment_frequency:         0.15  (stability signal)
    - external_dependency_risk:     0.15  (external risk)
    """

    AVAILABILITY_WEIGHTS: dict[str, float] = {
        "historical_availability_mean": 0.40,
        "downstream_dependency_risk": 0.30,
        "external_api_reliability": 0.15,
        "deployment_frequency": 0.15,
    }

    LATENCY_WEIGHTS: dict[str, float] = {
        "p99_latency_historical": 0.50,
        "call_chain_depth": 0.22,
        "noisy_neighbor_margin": 0.15,
        "traffic_seasonality": 0.13,
    }

    def compute_attribution(
        self,
        sli_type: SliType,
        feature_values: dict[str, float],
    ) -> list[FeatureAttribution]:
        """Compute weighted feature attributions.

        Normalizes contributions so they sum to 1.0.
        Returns sorted by absolute contribution descending.
        """
```

#### Repository Interfaces

**`src/domain/repositories/slo_recommendation_repository.py`**

```python
class SloRecommendationRepositoryInterface(ABC):

    @abstractmethod
    async def get_active_by_service(
        self, service_id: UUID, sli_type: SliType | None = None
    ) -> list[SloRecommendation]:
        """Get active (non-expired) recommendations for a service."""

    @abstractmethod
    async def save(self, recommendation: SloRecommendation) -> SloRecommendation:
        """Insert or update a recommendation."""

    @abstractmethod
    async def save_batch(self, recommendations: list[SloRecommendation]) -> int:
        """Bulk save recommendations. Returns count saved."""

    @abstractmethod
    async def supersede_existing(self, service_id: UUID, sli_type: SliType) -> int:
        """Mark all active recommendations for service+sli_type as superseded."""

    @abstractmethod
    async def expire_stale(self) -> int:
        """Mark expired recommendations (past expires_at)."""
```

**`src/domain/repositories/telemetry_query_service.py`**

```python
class TelemetryQueryServiceInterface(ABC):
    """Interface for querying telemetry data (abstracted from Prometheus)."""

    @abstractmethod
    async def get_availability_sli(
        self, service_id: str, window_days: int
    ) -> AvailabilitySliData | None:
        """Returns availability SLI data over the given window."""

    @abstractmethod
    async def get_latency_percentiles(
        self, service_id: str, window_days: int
    ) -> LatencySliData | None:
        """Returns latency percentile data over the given window."""

    @abstractmethod
    async def get_rolling_availability(
        self, service_id: str, window_days: int, bucket_hours: int = 24
    ) -> list[float]:
        """Returns rolling availability values (one per bucket) for breach estimation."""

    @abstractmethod
    async def get_data_completeness(
        self, service_id: str, window_days: int
    ) -> float:
        """Returns data completeness score (0.0-1.0) for the window."""
```

### 3.3 Application Layer

#### Use Cases

**`src/application/use_cases/generate_slo_recommendation.py`**

Orchestrates the full recommendation pipeline for a single service:

```python
class GenerateSloRecommendationUseCase:
    """Generate SLO recommendations for a single service.

    Pipeline:
    1. Validate service exists and has sufficient data
    2. Determine lookback window (standard 30d or extended cold-start)
    3. Query telemetry data via TelemetryQueryServiceInterface
    4. Retrieve dependency subgraph (downstream, depth=3)
    5. Compute composite availability bound
    6. Compute availability recommendation tiers
    7. Compute latency recommendation tiers
    8. Generate weighted feature attribution
    9. Build explanation and data quality metadata
    10. Supersede existing recommendations
    11. Save new recommendations
    12. Return response DTO
    """

    def __init__(
        self,
        service_repository: ServiceRepositoryInterface,
        dependency_repository: DependencyRepositoryInterface,
        recommendation_repository: SloRecommendationRepositoryInterface,
        telemetry_service: TelemetryQueryServiceInterface,
        availability_calculator: AvailabilityCalculator,
        latency_calculator: LatencyCalculator,
        composite_service: CompositeAvailabilityService,
        attribution_service: WeightedAttributionService,
        graph_traversal_service: GraphTraversalService,
    ): ...

    async def execute(
        self, request: GenerateRecommendationRequest
    ) -> GenerateRecommendationResponse | None: ...
```

**`src/application/use_cases/get_slo_recommendation.py`**

Simple retrieval of pre-computed recommendations:

```python
class GetSloRecommendationUseCase:
    """Retrieve pre-computed SLO recommendations for a service.

    If force_regenerate=True, delegates to GenerateSloRecommendationUseCase.
    Otherwise, returns stored active recommendations.
    """

    def __init__(
        self,
        service_repository: ServiceRepositoryInterface,
        recommendation_repository: SloRecommendationRepositoryInterface,
        generate_use_case: GenerateSloRecommendationUseCase,
    ): ...

    async def execute(
        self, request: GetRecommendationRequest
    ) -> GetRecommendationResponse | None: ...
```

**`src/application/use_cases/batch_compute_recommendations.py`**

Batch pipeline for pre-computing all recommendations:

```python
class BatchComputeRecommendationsUseCase:
    """Pre-compute SLO recommendations for all registered services.

    Run as a scheduled background task (APScheduler).
    Iterates all non-discovered services, generates recommendations, stores results.
    Emits metrics for monitoring (services processed, failures, duration).
    """

    def __init__(
        self,
        service_repository: ServiceRepositoryInterface,
        generate_use_case: GenerateSloRecommendationUseCase,
    ): ...

    async def execute(self) -> BatchComputeResult: ...
```

#### DTOs

**`src/application/dtos/slo_recommendation_dto.py`**

```python
@dataclass
class GenerateRecommendationRequest:
    service_id: str          # business identifier
    sli_type: str = "all"    # "availability" | "latency" | "all"
    lookback_days: int = 30
    force_regenerate: bool = False

@dataclass
class GetRecommendationRequest:
    service_id: str
    sli_type: str = "all"
    lookback_days: int = 30
    force_regenerate: bool = False

@dataclass
class TierDTO:
    level: str
    target: float
    error_budget_monthly_minutes: float | None = None
    estimated_breach_probability: float = 0.0
    confidence_interval: tuple[float, float] | None = None
    percentile: str | None = None
    target_ms: int | None = None

@dataclass
class FeatureAttributionDTO:
    feature: str
    contribution: float
    description: str = ""

@dataclass
class DependencyImpactDTO:
    composite_availability_bound: float
    bottleneck_service: str | None = None
    bottleneck_contribution: str = ""
    hard_dependency_count: int = 0
    soft_dependency_count: int = 0

@dataclass
class ExplanationDTO:
    summary: str
    feature_attribution: list[FeatureAttributionDTO]
    dependency_impact: DependencyImpactDTO | None = None

@dataclass
class DataQualityDTO:
    data_completeness: float
    telemetry_gaps: list[dict]
    confidence_note: str
    is_cold_start: bool = False
    lookback_days_actual: int = 30

@dataclass
class RecommendationDTO:
    sli_type: str
    metric: str
    tiers: dict[str, TierDTO]
    explanation: ExplanationDTO
    data_quality: DataQualityDTO

@dataclass
class LookbackWindowDTO:
    start: str   # ISO 8601
    end: str     # ISO 8601

@dataclass
class GetRecommendationResponse:
    service_id: str
    generated_at: str
    lookback_window: LookbackWindowDTO
    recommendations: list[RecommendationDTO]

@dataclass
class GenerateRecommendationResponse:
    service_id: str
    generated_at: str
    lookback_window: LookbackWindowDTO
    recommendations: list[RecommendationDTO]

@dataclass
class BatchComputeResult:
    total_services: int
    successful: int
    failed: int
    skipped: int          # discovered-only or insufficient data
    duration_seconds: float
    failures: list[dict]  # [{"service_id": "...", "error": "..."}]
```

### 3.4 Infrastructure Layer

**Mock Prometheus Stub:** `src/infrastructure/telemetry/mock_prometheus_client.py`

Returns hardcoded but realistic metric responses. Configurable per service_id via a seed data file.

**Repository Implementations:**
- `src/infrastructure/database/repositories/slo_recommendation_repository.py`
- SQLAlchemy async implementation of `SloRecommendationRepositoryInterface`

**SQLAlchemy Models:**
- `src/infrastructure/database/models/slo_recommendation.py`
- `src/infrastructure/database/models/sli_aggregate.py`

**Background Task:**
- `src/infrastructure/tasks/batch_recommendations.py`

---

## 4. API Specification

### `GET /api/v1/services/{service_id}/slo-recommendations`

**Description:** Retrieve SLO recommendations for a service.

**Authentication:** API Key (`X-API-Key` header)

**Rate Limit:** 60 req/min

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `service_id` | string | Business identifier (e.g., "checkout-service") |

**Query Parameters:**

| Parameter | Type | Default | Validation | Description |
|-----------|------|---------|------------|-------------|
| `sli_type` | string | `"all"` | `availability \| latency \| all` | Filter by SLI type |
| `lookback_days` | integer | `30` | min: 7, max: 365 | Lookback window for computation |
| `force_regenerate` | boolean | `false` | — | Bypass stored results, recompute fresh |

**Success Response (200 OK):**

```json
{
  "service_id": "checkout-service",
  "generated_at": "2026-02-15T10:30:00Z",
  "lookback_window": {
    "start": "2026-01-16T00:00:00Z",
    "end": "2026-02-15T00:00:00Z"
  },
  "data_quality": {
    "data_completeness": 0.97,
    "telemetry_gaps": [],
    "confidence_note": "Based on 30 days of continuous data with 97% completeness"
  },
  "recommendations": [
    {
      "sli_type": "availability",
      "metric": "error_rate",
      "tiers": {
        "conservative": {
          "target": 99.5,
          "error_budget_monthly_minutes": 219.6,
          "estimated_breach_probability": 0.02,
          "confidence_interval": [99.3, 99.7]
        },
        "balanced": {
          "target": 99.9,
          "error_budget_monthly_minutes": 43.8,
          "estimated_breach_probability": 0.08,
          "confidence_interval": [99.8, 99.95]
        },
        "aggressive": {
          "target": 99.95,
          "error_budget_monthly_minutes": 21.9,
          "estimated_breach_probability": 0.18,
          "confidence_interval": [99.9, 99.99]
        }
      },
      "explanation": {
        "summary": "checkout-service achieved 99.92% availability over 30 days. The Balanced target of 99.9% provides a 0.02% margin. Composite availability bound is 99.70% given 3 hard dependencies.",
        "feature_attribution": [
          {"feature": "historical_availability_mean", "contribution": 0.42},
          {"feature": "downstream_dependency_risk", "contribution": 0.28},
          {"feature": "external_api_reliability", "contribution": 0.18},
          {"feature": "deployment_frequency", "contribution": 0.12}
        ],
        "dependency_impact": {
          "composite_availability_bound": 99.70,
          "bottleneck_service": "external-payment-api",
          "bottleneck_contribution": "Consumes 50% of error budget at 99.9% target",
          "hard_dependency_count": 3,
          "soft_dependency_count": 1
        }
      }
    },
    {
      "sli_type": "latency",
      "metric": "p99_response_time_ms",
      "tiers": {
        "conservative": {
          "target_ms": 1200,
          "percentile": "p99.9",
          "estimated_breach_probability": 0.01
        },
        "balanced": {
          "target_ms": 800,
          "percentile": "p99",
          "estimated_breach_probability": 0.05
        },
        "aggressive": {
          "target_ms": 500,
          "percentile": "p95",
          "estimated_breach_probability": 0.12
        }
      },
      "explanation": {
        "summary": "End-to-end p99 latency measured at 780ms over 30 days. Balanced target of 800ms provides 2.5% headroom.",
        "feature_attribution": [
          {"feature": "p99_latency_historical", "contribution": 0.50},
          {"feature": "call_chain_depth", "contribution": 0.22},
          {"feature": "noisy_neighbor_margin", "contribution": 0.15},
          {"feature": "traffic_seasonality", "contribution": 0.13}
        ]
      }
    }
  ]
}
```

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 404 | Service not registered | RFC 7807: `"Service with ID 'xyz' is not registered."` |
| 400 | Invalid query params | RFC 7807: `"lookback_days must be between 7 and 365"` |
| 422 | Insufficient telemetry data | RFC 7807: `"Service 'xyz' has no telemetry data available."` |
| 429 | Rate limit exceeded | RFC 7807 + `Retry-After` header |
| 500 | Internal error | RFC 7807: generic server error |

---

## 5. Database Design

### 5.1 Schema: `slo_recommendations`

```sql
CREATE TABLE slo_recommendations (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_id                  UUID NOT NULL REFERENCES services(id),
    sli_type                    VARCHAR(20) NOT NULL,
    metric                      VARCHAR(50) NOT NULL,
    tiers                       JSONB NOT NULL,
    explanation                 JSONB NOT NULL,
    data_quality                JSONB NOT NULL,
    lookback_window_start       TIMESTAMPTZ NOT NULL,
    lookback_window_end         TIMESTAMPTZ NOT NULL,
    generated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at                  TIMESTAMPTZ NOT NULL,
    status                      VARCHAR(20) NOT NULL DEFAULT 'active',

    CONSTRAINT ck_slo_rec_sli_type CHECK (sli_type IN ('availability', 'latency')),
    CONSTRAINT ck_slo_rec_status CHECK (status IN ('active', 'superseded', 'expired'))
);

-- Primary lookup: active recommendations by service
CREATE INDEX idx_slo_rec_service_active
    ON slo_recommendations(service_id, status) WHERE status = 'active';

-- Expiry cleanup
CREATE INDEX idx_slo_rec_expires
    ON slo_recommendations(expires_at) WHERE status = 'active';

-- Lookup by sli_type
CREATE INDEX idx_slo_rec_sli_type
    ON slo_recommendations(service_id, sli_type, status);
```

### 5.2 Schema: `sli_aggregates`

```sql
CREATE TABLE sli_aggregates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_id      UUID NOT NULL REFERENCES services(id),
    sli_type        VARCHAR(30) NOT NULL,
    window          VARCHAR(10) NOT NULL,
    value           DECIMAL NOT NULL,
    sample_count    BIGINT NOT NULL DEFAULT 0,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_sli_type CHECK (
        sli_type IN ('availability', 'latency_p50', 'latency_p95', 'latency_p99', 'latency_p999', 'error_rate', 'request_rate')
    ),
    CONSTRAINT ck_sli_window CHECK (
        window IN ('1h', '1d', '7d', '28d', '90d')
    )
);

-- Primary lookup pattern
CREATE INDEX idx_sli_lookup
    ON sli_aggregates(service_id, sli_type, window, computed_at DESC);
```

### 5.3 Data Access Patterns

| Query | Frequency | Index Used |
|-------|-----------|------------|
| Get active recommendations by service_id | ~100 req/min | `idx_slo_rec_service_active` |
| Supersede existing recommendations | Per generation | `idx_slo_rec_service_active` |
| Expire stale recommendations | Hourly batch | `idx_slo_rec_expires` |
| Get SLI aggregates for computation | Per service generation | `idx_sli_lookup` |
| Bulk insert recommendations | Batch (daily) | N/A (write) |

### 5.4 Migration Strategy

Two Alembic migrations:
1. `004_create_slo_recommendations_table.py`
2. `005_create_sli_aggregates_table.py`

Both are additive (no existing table modifications). Foreign keys reference `services.id`.

---

## 6. Algorithm & Logic Design

### 6.1 Availability Recommendation Pipeline

```
Input: service_id, lookback_days

Step 1: DETERMINE LOOKBACK WINDOW
    data_completeness = telemetry.get_data_completeness(service_id, lookback_days)
    IF data_completeness < 0.90 AND lookback_days == 30:
        extended_days = min(90, max_available_data_days)
        data_completeness = telemetry.get_data_completeness(service_id, extended_days)
        lookback_days = extended_days
        is_cold_start = True

Step 2: FETCH TELEMETRY
    avail_sli = telemetry.get_availability_sli(service_id, lookback_days)
    rolling_avail = telemetry.get_rolling_availability(service_id, lookback_days, bucket_hours=24)
    IF avail_sli is None:
        RETURN error: "No telemetry data available"

Step 3: FETCH DEPENDENCY SUBGRAPH
    nodes, edges = graph_traversal.get_subgraph(
        service_id, direction=DOWNSTREAM, max_depth=3
    )
    hard_deps = [e for e in edges where e.criticality == HARD and e.communication_mode == SYNC]
    soft_deps = [e for e in edges where e.criticality == SOFT]

Step 4: FETCH DEPENDENCY AVAILABILITIES
    dep_availabilities = []
    FOR EACH hard_dep IN hard_deps:
        dep_avail = telemetry.get_availability_sli(hard_dep.target_service_id, lookback_days)
        IF dep_avail is None:
            dep_avail = DEFAULT_AVAILABILITY (0.999)  # Assume 99.9% if no data
        dep_availabilities.append(DependencyWithAvailability(dep, dep_avail))

Step 5: COMPUTE COMPOSITE BOUND
    composite_result = composite_service.compute_composite_bound(
        service_availability=avail_sli.availability_ratio,
        dependencies=dep_availabilities
    )
    # composite_result.bound = R_self * R_dep1 * R_dep2 * ...

Step 6: COMPUTE TIER TARGETS
    sorted_rolling = sorted(rolling_avail)
    n = len(sorted_rolling)

    conservative_raw = percentile(sorted_rolling, 0.1)    # p99.9 floor
    balanced_raw     = percentile(sorted_rolling, 1.0)    # p99
    aggressive_raw   = percentile(sorted_rolling, 5.0)    # p95

    # Apply dependency adjustment (hard cap)
    conservative = min(conservative_raw, composite_result.bound) * 100
    balanced     = min(balanced_raw, composite_result.bound) * 100
    aggressive   = aggressive_raw * 100  # NOT capped (shows achievable potential)

Step 7: COMPUTE BREACH PROBABILITIES
    FOR EACH tier_target IN [conservative, balanced, aggressive]:
        breach_prob = count(r < tier_target/100 for r in rolling_avail) / len(rolling_avail)

Step 8: COMPUTE CONFIDENCE INTERVALS (simple bootstrap)
    FOR EACH tier:
        Run 1000 bootstrap resamples of rolling_avail
        confidence_interval = (percentile_2.5, percentile_97.5)

Step 9: COMPUTE WEIGHTED ATTRIBUTION
    feature_values = {
        "historical_availability_mean": avail_sli.availability_ratio,
        "downstream_dependency_risk": 1.0 - composite_result.bound,
        "external_api_reliability": min(dep_avail for external deps) or 1.0,
        "deployment_frequency": 0.5  # placeholder, no deployment data yet
    }
    attributions = attribution_service.compute_attribution("availability", feature_values)

Step 10: BUILD EXPLANATION
    summary = f"{service_id} achieved {avail_sli.availability_ratio*100:.2f}% availability
              over {lookback_days} days. The Balanced target of {balanced:.1f}% provides
              {(avail_sli.availability_ratio*100 - balanced):.2f}% margin.
              Composite availability bound is {composite_result.bound*100:.2f}% given
              {len(hard_deps)} hard dependencies."

Step 11: BUILD AND SAVE RECOMMENDATION
    recommendation = SloRecommendation(
        service_id, SliType.AVAILABILITY, tiers, explanation, data_quality, ...
    )
    supersede_existing(service_id, AVAILABILITY)
    save(recommendation)
    RETURN recommendation
```

### 6.2 Latency Recommendation Pipeline

```
Input: service_id, lookback_days

Step 1: DETERMINE LOOKBACK (same as availability)

Step 2: FETCH TELEMETRY
    latency_sli = telemetry.get_latency_percentiles(service_id, lookback_days)
    IF latency_sli is None:
        RETURN error: "No latency telemetry available"

Step 3: DETERMINE NOISE MARGIN
    has_shared_infra = check_shared_infrastructure(service_id)
    noise_margin = 0.05 if not has_shared_infra else 0.10

Step 4: COMPUTE TIER TARGETS
    conservative_ms = int(latency_sli.p999_ms * (1 + noise_margin))
    balanced_ms     = int(latency_sli.p99_ms  * (1 + noise_margin))
    aggressive_ms   = int(latency_sli.p95_ms)  # No margin

Step 5: ESTIMATE BREACH PROBABILITIES
    # Using the distribution relationship between percentiles
    conservative_breach = 0.001 * (1 + noise_margin)  # ~0.1%
    balanced_breach     = 0.01 * (1 + noise_margin)    # ~1%
    aggressive_breach   = 0.05                          # ~5%

Step 6: COMPUTE WEIGHTED ATTRIBUTION
    feature_values = {
        "p99_latency_historical": latency_sli.p99_ms,
        "call_chain_depth": dependency_chain_depth,
        "noisy_neighbor_margin": noise_margin,
        "traffic_seasonality": 0.5  # placeholder
    }

Step 7: BUILD AND SAVE RECOMMENDATION
```

### 6.3 Composite Availability Formula

```
FUNCTION compute_composite_bound(self_avail, dependencies):
    composite = self_avail

    # Group by classification
    serial_hard = [d for d in dependencies if d.criticality == HARD and d.mode == SYNC]
    parallel_groups = group_parallel_dependencies(dependencies)
    # Soft deps excluded from computation

    # Serial composition
    FOR EACH dep IN serial_hard:
        composite = composite * dep.availability

    # Parallel composition (for redundant paths)
    FOR EACH group IN parallel_groups:
        group_unavail = 1.0
        FOR EACH dep IN group:
            group_unavail = group_unavail * (1.0 - dep.availability)
        composite = composite * (1.0 - group_unavail)

    RETURN composite
```

---

## 7. Error Handling & Edge Cases

### Edge Cases

| Scenario | Handling |
|----------|----------|
| Service not registered | Return 404 |
| No telemetry data at all | Return 422 with explanation |
| Data completeness < 50% even after 90-day extension | Return recommendation with `is_cold_start=True`, `confidence_note="Very low confidence..."` |
| Service has no dependencies | `composite_bound = self_availability` (no adjustment) |
| All dependencies are soft | Same as no dependencies for composite math |
| Circular dependency in chain | Use weakest-link SCC member as supernode |
| Dependency has no telemetry data | Assume 99.9% availability for that dependency |
| `force_regenerate` during batch run | Batch job skips service already being generated (simple lock) |
| Extremely high availability (>99.999%) | Cap display at 99.999%, note in explanation |
| Zero requests in window | Return 422: "No request data available" |

### Retry Strategy

| Operation | Retry Policy |
|-----------|-------------|
| Prometheus query (mock stub) | 3 attempts, exponential backoff (1s, 2s, 4s) |
| Database write | 2 attempts, 500ms delay |
| Batch job overall | Continues on per-service failure, logs error |

---

## 8. Dependencies & Interfaces

### Internal Dependencies (FR-1 → FR-2)

| FR-1 Component | FR-2 Usage | Interface |
|----------------|------------|-----------|
| `ServiceRepositoryInterface` | Lookup service by business ID | `get_by_service_id(service_id: str)` |
| `DependencyRepositoryInterface` | Traverse dependency subgraph | `traverse_graph(service_id, DOWNSTREAM, 3, False)` |
| `GraphTraversalService` | Orchestrate graph traversal | `get_subgraph(...)` |
| `Service` entity | Service metadata (criticality, team) | Direct attribute access |
| `ServiceDependency` entity | Edge classification (hard/soft, sync/async) | Direct attribute access |

### External Dependencies (New)

| Dependency | Purpose | Interface |
|------------|---------|-----------|
| Mock Prometheus Client | Telemetry data source | `TelemetryQueryServiceInterface` |
| APScheduler | Batch computation scheduling | Cron job registration |

---

## 9. Security Considerations

- **Input validation:** All query parameters validated via Pydantic (lookback_days range, sli_type enum)
- **Authorization:** Same API key auth as FR-1 endpoints (X-API-Key header)
- **Rate limiting:** 60 req/min per client for recommendation retrieval
- **PromQL injection prevention:** Mock stub uses parameterized service_id lookup, no raw PromQL construction. When real Prometheus integration is added (FR-6), service_id must be validated against `^[a-z0-9-]+$` pattern before inclusion in PromQL queries
- **No PII in recommendations:** Recommendations contain only service-level operational metrics
- **JSONB content:** Tier and explanation JSONB fields are built programmatically (not from user input), so no injection risk

---

## 10. Testing Strategy

### Test Distribution

| Layer | Test Type | Coverage Target | Framework |
|-------|-----------|----------------|-----------|
| Domain entities | Unit | >95% | pytest |
| Domain services (calculators) | Unit | >95% | pytest |
| Application use cases | Unit | >90% | pytest + AsyncMock |
| DTOs | Unit | >90% | pytest |
| Infrastructure (repository) | Integration | >80% | pytest + testcontainers |
| Infrastructure (mock client) | Unit | >90% | pytest |
| API endpoint | Integration | >80% | pytest + httpx |
| Batch pipeline | Integration | >75% | pytest + testcontainers |

### Test Data Requirements

**Mock Prometheus Stub Data:**
- 5 services with full 30-day data (high confidence)
- 2 services with 10-day data (cold-start trigger)
- 1 service with 0 data (error case)
- 1 service with highly variable availability (breach probability testing)
- 1 service with external dependency consuming >50% error budget

**Synthetic Dependency Graphs:**
- Simple chain: A → B → C (serial hard)
- Fan-out: A → {B, C, D} (parallel soft)
- Mixed: A → B (hard sync), A → C (soft async), B → D (hard sync)
- Circular: A → B → C → A (SCC supernode test)

### Key Test Cases

| Test | Type | Validates |
|------|------|-----------|
| Availability tier computation with known inputs | Unit | AvailabilityCalculator math correctness |
| Composite bound for 3 serial deps | Unit | CompositeAvailabilityService formula |
| Cold-start triggers extended lookback | Unit | GenerateUseCase lookback logic |
| Service with no telemetry returns 422 | Integration | Error handling |
| Pre-computed recommendation retrieval < 500ms | Integration | NFR2-01 |
| Batch processes 100 services without failure | Integration | BatchComputeUseCase robustness |
| Weighted attribution sums to 1.0 | Unit | WeightedAttributionService normalization |
| Tier capped by composite bound | Unit | Dependency adjustment logic |
| Aggressive tier NOT capped | Unit | Design decision verification |

---

## 11. Performance Considerations

### Expected Load

| Operation | Expected Volume | Target Latency |
|-----------|----------------|----------------|
| `GET /slo-recommendations` (pre-computed) | ~100 req/min | < 500ms (p95) |
| `GET /slo-recommendations?force_regenerate=true` | ~5 req/min | < 5s (p95) |
| Batch computation (daily) | 5000 services | < 30 minutes total |

### Optimization Strategies

1. **Pre-computed storage:** Recommendations stored in PostgreSQL, retrieval is a simple indexed SELECT
2. **Batch parallelism:** Batch job processes services concurrently (asyncio.gather with semaphore, max 20 concurrent)
3. **Dependency caching:** During batch run, cache dependency subgraph results in memory (same graph queried for multiple services)
4. **Indexed queries:** `idx_slo_rec_service_active` covers the primary lookup path
5. **Lazy loading:** Explanation JSONB only deserialized when explicitly requested (API always returns it, but DB stores as JSONB blob)

### Monitoring Metrics

| Metric | Type | Alert Threshold |
|--------|------|----------------|
| `slo_engine_recommendation_generation_duration_seconds` | Histogram | p95 > 5s |
| `slo_engine_recommendations_generated_total` | Counter | N/A |
| `slo_engine_batch_duration_seconds` | Histogram | > 30 min |
| `slo_engine_batch_failures_total` | Counter | > 5% of services |
| `slo_engine_recommendation_retrieval_duration_seconds` | Histogram | p95 > 500ms |

---

## 12. Implementation Phases

### Phase 1: Domain Foundation [Week 1]

**Objective:** Implement domain entities, value objects, and pure computation services with comprehensive unit tests.

**Tasks:**

* **Task 1.1: SLO Recommendation Entity** [Effort: M]
  - **Description:** Create `SloRecommendation`, `RecommendationTier`, `FeatureAttribution`, `DependencyImpact`, `DataQuality`, `Explanation` domain entities
  - **Acceptance Criteria:**
    - [ ] All entities created as frozen or mutable dataclasses with validation
    - [ ] `SloRecommendation.__post_init__` auto-computes `expires_at = generated_at + 24h`
    - [ ] `SliType`, `RecommendationStatus`, `TierLevel` enums defined
    - [ ] `supersede()` and `expire()` methods work correctly
    - [ ] `is_expired` property returns correct boolean
    - [ ] All validation constraints enforced (breach probability 0-1, etc.)
    - [ ] >95% unit test coverage
  - **Files to Create:**
    - `src/domain/entities/slo_recommendation.py` - Entity definitions
    - `tests/unit/domain/entities/test_slo_recommendation.py` - Unit tests
  - **Dependencies:** None
  - **Testing Requirements:** Unit tests only

* **Task 1.2: SLI Data Value Objects** [Effort: S]
  - **Description:** Create `AvailabilitySliData` and `LatencySliData` value objects
  - **Acceptance Criteria:**
    - [ ] `AvailabilitySliData` has `error_rate` computed property
    - [ ] `LatencySliData` stores p50, p95, p99, p999 percentiles
    - [ ] Both include window_start, window_end, sample_count
    - [ ] >95% unit test coverage
  - **Files to Create:**
    - `src/domain/entities/sli_data.py` - Value objects
    - `tests/unit/domain/entities/test_sli_data.py` - Unit tests
  - **Dependencies:** None
  - **Testing Requirements:** Unit tests only

* **Task 1.3: Availability Calculator Service** [Effort: L]
  - **Description:** Implement `AvailabilityCalculator` with tier computation, breach probability estimation, error budget calculation, and confidence interval bootstrapping
  - **Acceptance Criteria:**
    - [ ] `compute_tiers()` returns Conservative (p99.9 capped), Balanced (p99 capped), Aggressive (p95 uncapped)
    - [ ] Tiers correctly capped by `composite_bound` for Conservative and Balanced
    - [ ] Aggressive tier NOT capped by composite bound
    - [ ] `estimate_breach_probability()` returns correct fraction of breaching windows
    - [ ] `compute_error_budget_minutes()` returns correct monthly budget
    - [ ] Bootstrap confidence intervals computed from 1000 resamples
    - [ ] Edge cases: 100% availability, 0% availability, single data point
    - [ ] >95% unit test coverage
  - **Files to Create:**
    - `src/domain/services/availability_calculator.py` - Calculator
    - `tests/unit/domain/services/test_availability_calculator.py` - Unit tests
  - **Dependencies:** Task 1.1
  - **Testing Requirements:** Unit tests with known-answer test vectors

* **Task 1.4: Latency Calculator Service** [Effort: M]
  - **Description:** Implement `LatencyCalculator` with tier computation and noise margin
  - **Acceptance Criteria:**
    - [ ] `compute_tiers()` returns Conservative (p999+noise), Balanced (p99+noise), Aggressive (p95)
    - [ ] Noise margin applied correctly (5% default, 10% shared infra)
    - [ ] Breach probabilities estimated from percentile positions
    - [ ] >95% unit test coverage
  - **Files to Create:**
    - `src/domain/services/latency_calculator.py` - Calculator
    - `tests/unit/domain/services/test_latency_calculator.py` - Unit tests
  - **Dependencies:** Task 1.2
  - **Testing Requirements:** Unit tests with known-answer test vectors

* **Task 1.5: Composite Availability Service** [Effort: L]
  - **Description:** Implement `CompositeAvailabilityService` for serial/parallel dependency composition and bottleneck identification
  - **Acceptance Criteria:**
    - [ ] Serial hard deps: `R = R_self * product(R_dep_i)`
    - [ ] Parallel paths: `R = 1 - product(1 - R_replica_j)`
    - [ ] Soft deps excluded from composite, counted in metadata
    - [ ] Bottleneck correctly identified as dep contributing most to degradation
    - [ ] Edge cases: no dependencies, all soft, single dep, very low dep availability
    - [ ] >95% unit test coverage
  - **Files to Create:**
    - `src/domain/services/composite_availability_service.py` - Service
    - `tests/unit/domain/services/test_composite_availability_service.py` - Unit tests
  - **Dependencies:** Task 1.1, Task 1.2
  - **Testing Requirements:** Unit tests with known-answer test vectors

* **Task 1.6: Weighted Attribution Service** [Effort: M]
  - **Description:** Implement `WeightedAttributionService` with fixed MVP weights for availability and latency
  - **Acceptance Criteria:**
    - [ ] Availability weights: historical=0.40, deps=0.30, external=0.15, deploy=0.15
    - [ ] Latency weights: p99=0.50, call_chain=0.22, noise=0.15, seasonality=0.13
    - [ ] Contributions normalized to sum to 1.0
    - [ ] Results sorted by absolute contribution descending
    - [ ] >95% unit test coverage
  - **Files to Create:**
    - `src/domain/services/weighted_attribution_service.py` - Service
    - `tests/unit/domain/services/test_weighted_attribution_service.py` - Unit tests
  - **Dependencies:** Task 1.1
  - **Testing Requirements:** Unit tests

* **Task 1.7: Repository Interfaces** [Effort: S]
  - **Description:** Define `SloRecommendationRepositoryInterface` and `TelemetryQueryServiceInterface` abstract base classes
  - **Acceptance Criteria:**
    - [ ] `SloRecommendationRepositoryInterface` with all 5 methods defined
    - [ ] `TelemetryQueryServiceInterface` with all 4 methods defined
    - [ ] Type hints use domain entities and value objects
    - [ ] Docstrings for all methods
  - **Files to Create:**
    - `src/domain/repositories/slo_recommendation_repository.py` - Interface
    - `src/domain/repositories/telemetry_query_service.py` - Interface
  - **Dependencies:** Task 1.1, Task 1.2
  - **Testing Requirements:** None (interfaces only)

**Phase 1 Deliverables:**
- All domain entities with validation
- Four computation services with >95% unit test coverage
- Two repository interfaces
- Known-answer test vectors for all computation algorithms

---

### Phase 2: Application Layer [Week 2]

**Objective:** Implement use cases (orchestration), DTOs, and wire up domain services.

**Tasks:**

* **Task 2.1: SLO Recommendation DTOs** [Effort: M]
  - **Description:** Create all DTOs for request/response in the application layer
  - **Acceptance Criteria:**
    - [ ] All 11 DTO dataclasses created (request, response, tier, attribution, etc.)
    - [ ] DTOs use dataclasses (not Pydantic — reserved for API layer)
    - [ ] `BatchComputeResult` includes failure details
    - [ ] >90% unit test coverage
  - **Files to Create:**
    - `src/application/dtos/slo_recommendation_dto.py` - DTOs
    - `tests/unit/application/dtos/test_slo_recommendation_dto.py` - Tests
  - **Dependencies:** Phase 1 complete
  - **Testing Requirements:** Unit tests

* **Task 2.2: GenerateSloRecommendation Use Case** [Effort: XL]
  - **Description:** Implement the core recommendation generation pipeline orchestrating all domain services
  - **Acceptance Criteria:**
    - [ ] Full pipeline: validate → lookback → telemetry → deps → composite → tiers → attribution → save
    - [ ] Cold-start: data_completeness < 0.90 triggers extended lookback up to 90 days
    - [ ] Supersedes existing active recommendations before saving new ones
    - [ ] Returns None if service not found
    - [ ] Handles missing telemetry data gracefully (422-equivalent)
    - [ ] Handles missing dependency data (assumes 99.9% default)
    - [ ] Builds correct explanation summary string
    - [ ] >90% unit test coverage with mocked dependencies
  - **Files to Create:**
    - `src/application/use_cases/generate_slo_recommendation.py` - Use case
    - `tests/unit/application/use_cases/test_generate_slo_recommendation.py` - Tests
  - **Dependencies:** Task 2.1, Phase 1 complete
  - **Testing Requirements:** Unit tests with AsyncMock for all dependencies

* **Task 2.3: GetSloRecommendation Use Case** [Effort: M]
  - **Description:** Implement retrieval of pre-computed recommendations with force_regenerate support
  - **Acceptance Criteria:**
    - [ ] Returns stored active recommendations when available
    - [ ] Delegates to GenerateUseCase when force_regenerate=True
    - [ ] Returns None if service not found
    - [ ] Filters by sli_type if specified
    - [ ] >90% unit test coverage
  - **Files to Create:**
    - `src/application/use_cases/get_slo_recommendation.py` - Use case
    - `tests/unit/application/use_cases/test_get_slo_recommendation.py` - Tests
  - **Dependencies:** Task 2.2
  - **Testing Requirements:** Unit tests with AsyncMock

* **Task 2.4: BatchComputeRecommendations Use Case** [Effort: L]
  - **Description:** Implement batch pipeline that generates recommendations for all registered services
  - **Acceptance Criteria:**
    - [ ] Iterates all non-discovered services from ServiceRepository
    - [ ] Calls GenerateUseCase for each service
    - [ ] Continues on per-service failure, collects errors
    - [ ] Returns BatchComputeResult with stats
    - [ ] Supports concurrency via asyncio.gather with semaphore (max 20)
    - [ ] >85% unit test coverage
  - **Files to Create:**
    - `src/application/use_cases/batch_compute_recommendations.py` - Use case
    - `tests/unit/application/use_cases/test_batch_compute_recommendations.py` - Tests
  - **Dependencies:** Task 2.2
  - **Testing Requirements:** Unit tests with AsyncMock

**Phase 2 Deliverables:**
- All use cases with >90% test coverage
- Full recommendation pipeline testable with mocks
- Batch pipeline ready for scheduling

---

### Phase 3: Infrastructure — Persistence & Telemetry [Week 3]

**Objective:** Implement database models, repositories, mock Prometheus client, and Alembic migrations.

**Tasks:**

* **Task 3.1: SQLAlchemy Models** [Effort: M]
  - **Description:** Create `SloRecommendationModel` and `SliAggregateModel` SQLAlchemy models
  - **Acceptance Criteria:**
    - [ ] `SloRecommendationModel` maps to `slo_recommendations` table with all columns
    - [ ] `SliAggregateModel` maps to `sli_aggregates` table with all columns
    - [ ] Check constraints for enums (sli_type, status, window)
    - [ ] JSONB columns for tiers, explanation, data_quality
    - [ ] Models follow same patterns as FR-1 models (Base class, Mapped[], etc.)
  - **Files to Create:**
    - `src/infrastructure/database/models/slo_recommendation.py` - Model
    - `src/infrastructure/database/models/sli_aggregate.py` - Model
  - **Dependencies:** Phase 2 complete
  - **Testing Requirements:** Verified by integration tests

* **Task 3.2: Alembic Migrations** [Effort: S]
  - **Description:** Create migration scripts for the two new tables
  - **Acceptance Criteria:**
    - [ ] Migration 004: create `slo_recommendations` table with indexes
    - [ ] Migration 005: create `sli_aggregates` table with indexes
    - [ ] Both migrations are reversible (downgrade drops tables)
    - [ ] Foreign key to `services.id` validated
    - [ ] Migrations tested against real PostgreSQL via testcontainers
  - **Files to Create:**
    - `alembic/versions/004_create_slo_recommendations_table.py`
    - `alembic/versions/005_create_sli_aggregates_table.py`
  - **Dependencies:** Task 3.1
  - **Testing Requirements:** Integration test (migration up/down)

* **Task 3.3: SloRecommendation Repository Implementation** [Effort: L]
  - **Description:** Implement `SloRecommendationRepositoryInterface` with SQLAlchemy async
  - **Acceptance Criteria:**
    - [ ] `get_active_by_service()` returns active recommendations, optionally filtered by sli_type
    - [ ] `save()` inserts new recommendation
    - [ ] `save_batch()` bulk inserts recommendations
    - [ ] `supersede_existing()` marks active recs as superseded
    - [ ] `expire_stale()` marks expired recs
    - [ ] Domain ↔ model mapping in both directions
    - [ ] >80% integration test coverage with testcontainers
  - **Files to Create:**
    - `src/infrastructure/database/repositories/slo_recommendation_repository.py`
    - `tests/integration/infrastructure/database/test_slo_recommendation_repository.py`
  - **Dependencies:** Task 3.1, Task 3.2
  - **Testing Requirements:** Integration tests with testcontainers PostgreSQL

* **Task 3.4: Mock Prometheus Client** [Effort: L]
  - **Description:** Implement `TelemetryQueryServiceInterface` as a mock stub returning realistic hardcoded data per service_id
  - **Acceptance Criteria:**
    - [ ] Implements all 4 interface methods
    - [ ] Returns different data per service_id (configurable via seed data dict)
    - [ ] Default seed data includes: 5 services with 30-day data, 2 with 10-day, 1 with no data
    - [ ] `get_data_completeness()` returns realistic values (0.97 for 30-day, 0.3 for 10-day)
    - [ ] `get_rolling_availability()` returns daily values with realistic variance
    - [ ] Seed data is injectable for tests
    - [ ] >90% unit test coverage
  - **Files to Create:**
    - `src/infrastructure/telemetry/mock_prometheus_client.py` - Mock implementation
    - `src/infrastructure/telemetry/seed_data.py` - Default seed data
    - `tests/unit/infrastructure/telemetry/test_mock_prometheus_client.py` - Tests
  - **Dependencies:** Phase 1 Task 1.7 (interface)
  - **Testing Requirements:** Unit tests

**Phase 3 Deliverables:**
- Database tables created and migrated
- Repository with full CRUD operations tested
- Mock Prometheus client with realistic seed data
- All infrastructure components ready for wiring

---

### Phase 4: Infrastructure — API & Background Tasks [Week 4]

**Objective:** Implement API endpoint, Pydantic schemas, background batch task, and wire everything together.

**Tasks:**

* **Task 4.1: Pydantic API Schemas** [Effort: M]
  - **Description:** Create Pydantic v2 models for API request validation and response serialization
  - **Acceptance Criteria:**
    - [ ] `SloRecommendationQueryParams` validates sli_type enum, lookback_days range (7-365), force_regenerate bool
    - [ ] `SloRecommendationResponse` matches TRD JSON schema exactly
    - [ ] Nested models: `TierResponse`, `ExplanationResponse`, `DependencyImpactResponse`, etc.
    - [ ] RFC 7807 error schema reused from FR-1
  - **Files to Create:**
    - `src/infrastructure/api/schemas/slo_recommendation_schema.py` - Schemas
    - `tests/unit/infrastructure/api/schemas/test_slo_recommendation_schema.py` - Tests
  - **Dependencies:** Phase 2 DTOs
  - **Testing Requirements:** Unit tests for validation rules

* **Task 4.2: API Route — GET /slo-recommendations** [Effort: L]
  - **Description:** Implement FastAPI route handler with dependency injection
  - **Acceptance Criteria:**
    - [ ] Route registered at `GET /api/v1/services/{service_id}/slo-recommendations`
    - [ ] Query params: sli_type, lookback_days, force_regenerate
    - [ ] Auth middleware applied (X-API-Key)
    - [ ] Rate limiting applied (60 req/min)
    - [ ] 200: returns pre-computed or freshly generated recommendation
    - [ ] 404: service not found
    - [ ] 422: insufficient telemetry data
    - [ ] 400: invalid query parameters
    - [ ] 429: rate limit exceeded
    - [ ] Response matches Pydantic schema
    - [ ] Integration test with httpx async client
  - **Files to Create:**
    - `src/infrastructure/api/routes/recommendations.py` - Route
    - `tests/integration/infrastructure/api/test_recommendations_endpoint.py` - Tests
  - **Dependencies:** Task 4.1, Phase 3 complete
  - **Testing Requirements:** Integration tests with httpx + testcontainers

* **Task 4.3: Dependency Injection Wiring** [Effort: M]
  - **Description:** Wire all domain services, repositories, and use cases via FastAPI dependency injection
  - **Acceptance Criteria:**
    - [ ] FastAPI `Depends()` chain for route handler
    - [ ] All services instantiated with correct dependencies
    - [ ] Mock Prometheus client injected via config toggle
    - [ ] Session management (auto-commit/rollback) preserved from FR-1
  - **Files to Modify:**
    - `src/infrastructure/api/dependencies.py` - Add FR-2 dependencies
    - `src/infrastructure/api/main.py` - Register new route
  - **Dependencies:** Task 4.2
  - **Testing Requirements:** Verified by integration tests

* **Task 4.4: Batch Computation Background Task** [Effort: M]
  - **Description:** Schedule batch recommendation computation via APScheduler
  - **Acceptance Criteria:**
    - [ ] APScheduler cron job runs every 24 hours (configurable via `BATCH_RECOMMENDATION_INTERVAL_HOURS`)
    - [ ] Calls `BatchComputeRecommendationsUseCase.execute()`
    - [ ] Logs results (services processed, failures, duration)
    - [ ] Emits Prometheus metrics for monitoring
    - [ ] Does not block API serving
  - **Files to Create:**
    - `src/infrastructure/tasks/batch_recommendations.py` - Task
    - `tests/integration/infrastructure/tasks/test_batch_recommendations.py` - Tests
  - **Dependencies:** Phase 2 Task 2.4, Phase 3 complete
  - **Testing Requirements:** Integration test with mock services

* **Task 4.5: End-to-End Tests** [Effort: L]
  - **Description:** Full workflow E2E tests: ingest graph → generate recommendations → retrieve via API
  - **Acceptance Criteria:**
    - [ ] E2E: POST /services/dependencies → GET /slo-recommendations returns valid response
    - [ ] E2E: force_regenerate=true recomputes and returns fresh data
    - [ ] E2E: service with no data returns 422
    - [ ] E2E: response matches TRD JSON schema structure
    - [ ] Performance: pre-computed retrieval < 500ms
  - **Files to Create:**
    - `tests/e2e/test_slo_recommendations.py` - E2E tests
  - **Dependencies:** Task 4.2, Task 4.3
  - **Testing Requirements:** E2E with testcontainers + httpx

**Phase 4 Deliverables:**
- Working API endpoint with auth and rate limiting
- Background batch task scheduled
- E2E tests passing
- Full FR-2 feature functional

---

## 13. Pending Decisions & Clarifications

| # | Question | Options | Current Default | Status |
|---|----------|---------|-----------------|--------|
| 1 | **Batch schedule frequency** | 6h / 12h / 24h | 24h (matches TRD cache TTL) | **Decided: 24h** |
| 2 | **Concurrent batch workers** | 10 / 20 / 50 | 20 (asyncio semaphore) | **Decided: 20** |
| 3 | **Bootstrap resample count** | 100 / 500 / 1000 | 1000 (TRD says bootstrap) | **Decided: 1000** |
| 4 | **Default availability for deps with no data** | 99.0% / 99.5% / 99.9% | 99.9% | **Decided: 99.9%** |
| 5 | **Should `sli_aggregates` table be populated in FR-2 or deferred to FR-6?** | FR-2 (mock data) / FR-6 (real data) | Deferred to FR-6. FR-2 computes on-the-fly from mock stub. | **Decided: FR-6** |
| 6 | **How to handle graph snapshots** (`dependency_graph_snapshot_id` from TRD) | Create snapshots / Use timestamp | Use `generated_at` timestamp for provenance (no separate snapshot table for MVP) | **Decided: Timestamp** |
| 7 | **FR-1 Phase 4 (API layer) dependency** | Block on FR-1 P4 / Proceed independently | Proceed independently — FR-2 uses domain/application interfaces directly. API layer shares FastAPI app. | **Decided: Independent** |
