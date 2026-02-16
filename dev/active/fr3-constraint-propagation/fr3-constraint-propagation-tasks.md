# FR-3: Dependency-Aware Constraint Propagation — Task Tracker

**Created:** 2026-02-15
**Status:** Not Started
**Estimated Duration:** 3 weeks (15 working days)

---

## Progress Summary

| Phase | Status | Tasks | Completed | Notes |
|-------|--------|-------|-----------|-------|
| Phase 0: FR-2 Prerequisites | Not Started | 3 | 0/3 | Unblocks FR-3 without waiting for FR-2 |
| Phase 1: Domain Foundation | Not Started | 4 | 0/4 | FR-3 unique entities and services |
| Phase 2: Application Layer | Not Started | 3 | 0/3 | Use cases and DTOs |
| Phase 3: Infrastructure | Not Started | 6 | 0/6 | Migration, API, DI, E2E |
| **Total** | | **16** | **0/16** | |

---

## Phase 0: FR-2 Prerequisites [Week 1, Days 1-3]

**Objective:** Create the minimal FR-2 shared components that FR-3 depends on.

### Task 0.1: AvailabilitySliData Entity + DependencyWithAvailability [Effort: S]

- [ ] Create `src/domain/entities/sli_data.py`
  - [ ] `AvailabilitySliData` dataclass (service_id, good_events, total_events, availability_ratio, window_start, window_end, sample_count)
  - [ ] `AvailabilitySliData.error_rate` computed property = `1.0 - availability_ratio`
  - [ ] `LatencySliData` dataclass (service_id, p50_ms, p95_ms, p99_ms, p999_ms, window fields, sample_count)
  - [ ] Validation: availability_ratio 0.0-1.0, sample_count >= 0
- [ ] Create `src/domain/entities/dependency_with_availability.py`
  - [ ] `DependencyWithAvailability` dataclass (dependency, service_id, service_uuid, availability, is_external, published_sla, observed_availability, effective_availability_note)
  - [ ] `CompositeResult` dataclass (bound: float, bottleneck_service: str | None, bottleneck_contribution: str, per_dep_contributions: list)
  - [ ] Validation: availability 0.0-1.0, bound 0.0-1.0
- [ ] Create `tests/unit/domain/entities/test_sli_data.py` (>95% coverage)
- [ ] Create `tests/unit/domain/entities/test_dependency_with_availability.py` (>95% coverage)

**Files to Create:** 4
**Dependencies:** None
**Testing:** Unit tests only

---

### Task 0.2: TelemetryQueryServiceInterface + Mock Stub [Effort: M]

- [ ] Create `src/domain/repositories/telemetry_query_service.py`
  - [ ] `TelemetryQueryServiceInterface` ABC
  - [ ] `get_availability_sli(service_id: str, window_days: int) -> AvailabilitySliData | None`
  - [ ] `get_latency_percentiles(service_id: str, window_days: int) -> LatencySliData | None`
  - [ ] `get_rolling_availability(service_id: str, window_days: int, bucket_hours: int = 24) -> list[float]`
  - [ ] `get_data_completeness(service_id: str, window_days: int) -> float`
  - [ ] Type hints use domain entities
  - [ ] Docstrings for all methods
- [ ] Create `src/infrastructure/telemetry/__init__.py`
- [ ] Create `src/infrastructure/telemetry/seed_data.py`
  - [ ] Default seed data dict: 5 services with 30-day data (high confidence)
  - [ ] 2 services with 10-day data (cold-start trigger)
  - [ ] 1 external service with observed availability data
  - [ ] 1 service with no data (error case)
  - [ ] 1 service with highly variable availability
- [ ] Create `src/infrastructure/telemetry/mock_prometheus_client.py`
  - [ ] Implements `TelemetryQueryServiceInterface`
  - [ ] Configurable seed data per service_id (injectable via constructor)
  - [ ] `get_availability_sli()` returns AvailabilitySliData from seed
  - [ ] `get_latency_percentiles()` returns LatencySliData from seed
  - [ ] `get_rolling_availability()` returns daily values with realistic variance
  - [ ] `get_data_completeness()` returns completeness from seed (0.97 for 30-day, 0.3 for 10-day)
  - [ ] Returns None for services not in seed data
- [ ] Create `tests/unit/infrastructure/telemetry/test_mock_prometheus_client.py` (>90% coverage)

**Files to Create:** 5
**Dependencies:** Task 0.1
**Testing:** Unit tests

---

### Task 0.3: CompositeAvailabilityService [Effort: L]

- [ ] Create `src/domain/services/composite_availability_service.py`
  - [ ] `compute_composite_bound(service_availability, dependencies) -> CompositeResult`
  - [ ] Serial hard deps: `R = R_self × Π(R_hard_dep_i)`
  - [ ] Parallel redundant paths: `R = 1 − Π(1 − R_replica_j)`
  - [ ] Soft deps excluded from composite, counted in metadata
  - [ ] `identify_bottleneck(dependencies) -> tuple[str | None, str]`
  - [ ] Bottleneck = dep contributing most to composite degradation (highest unavailability share)
  - [ ] SCC supernode handling: use weakest-link member's availability
  - [ ] Edge cases: no dependencies (bound = self_availability), all soft (bound = self_availability), single dep
- [ ] Create `tests/unit/domain/services/test_composite_availability_service.py` (>95% coverage)
  - [ ] Test serial: 3 deps at 0.999 → bound ≈ 0.997
  - [ ] Test parallel: 2 deps at 0.99 → bound ≈ 0.9999
  - [ ] Test mixed: serial + parallel combination
  - [ ] Test no deps: bound = self
  - [ ] Test all soft: bound = self
  - [ ] Test bottleneck identification
  - [ ] Test single dep at 0.95 → bound = self × 0.95

**Files to Create:** 2
**Dependencies:** Task 0.1
**Testing:** Unit tests with known-answer test vectors

---

## Phase 1: FR-3 Domain Foundation [Week 1 Day 4 - Week 2 Day 2]

**Objective:** Implement FR-3's unique domain entities and services.

### Task 1.1: Constraint Analysis Entities [Effort: M]

- [ ] Create `src/domain/entities/constraint_analysis.py`
  - [ ] `ServiceType` enum: INTERNAL, EXTERNAL
  - [ ] `RiskLevel` enum: LOW, MODERATE, HIGH
  - [ ] `ExternalProviderProfile` dataclass
    - [ ] `effective_availability` property implements adaptive buffer
    - [ ] Fallback chain: both → observed-only → published-only → default 99.9%
  - [ ] `DependencyRiskAssessment` dataclass
    - [ ] Validation: `error_budget_consumption_pct` 0.0-100.0
  - [ ] `UnachievableWarning` dataclass
  - [ ] `ErrorBudgetBreakdown` dataclass
    - [ ] `high_risk_dependencies` list
    - [ ] `total_dependency_consumption_pct` sum
  - [ ] `ConstraintAnalysis` dataclass
    - [ ] `is_achievable` property
    - [ ] `has_high_risk_dependencies` property
    - [ ] UUID id, analyzed_at timestamp
- [ ] Create `tests/unit/domain/entities/test_constraint_analysis.py` (>95% coverage)
  - [ ] ExternalProviderProfile.effective_availability: all 4 fallback paths
  - [ ] DependencyRiskAssessment validation: out-of-range consumption
  - [ ] ConstraintAnalysis properties: achievable vs unachievable
  - [ ] ErrorBudgetBreakdown: high_risk_dependencies populated correctly

**Files to Create:** 2
**Dependencies:** Task 0.1
**Testing:** Unit tests

---

### Task 1.2: ExternalApiBufferService [Effort: M]

- [ ] Create `src/domain/services/external_api_buffer_service.py`
  - [ ] `PESSIMISTIC_MULTIPLIER = 10`
  - [ ] `DEFAULT_EXTERNAL_AVAILABILITY = 0.999`
  - [ ] `compute_effective_availability(profile) -> float`
    - [ ] Formula: `published_adjusted = 1 - (1-published) * (1 + PESSIMISTIC_MULTIPLIER)`
    - [ ] `min(observed, published_adjusted)` when both available
    - [ ] Observed-only, published-only, and default fallback paths
    - [ ] Floor published_adjusted at 0.0
  - [ ] `build_profile(service_id, service_uuid, published_sla, observed_availability, observation_window_days) -> ExternalProviderProfile`
  - [ ] `generate_availability_note(profile, effective) -> str`
    - [ ] "Using min(observed X%, published×adj Y%) = Z%"
    - [ ] "No monitoring data; using published SLA X% adjusted to Y%"
    - [ ] "No published SLA or monitoring data; using conservative default 99.9%"
- [ ] Create `tests/unit/domain/services/test_external_api_buffer_service.py` (>95% coverage)
  - [ ] TRD validation: published 99.99% → effective 99.89% ✓
  - [ ] Both available: min(observed, adjusted) selected correctly
  - [ ] Observed-only: returns observed
  - [ ] Published-only: returns adjusted
  - [ ] Neither: returns 0.999
  - [ ] Low SLA: published_adjusted floors at 0.0
  - [ ] Note generation: all 3 paths produce correct strings

**Files to Create:** 2
**Dependencies:** Task 1.1
**Testing:** Unit tests with TRD validation vectors

---

### Task 1.3: ErrorBudgetAnalyzer [Effort: L]

- [ ] Create `src/domain/services/error_budget_analyzer.py`
  - [ ] `HIGH_RISK_THRESHOLD = 0.30`
  - [ ] `MODERATE_RISK_THRESHOLD = 0.20`
  - [ ] `MONTHLY_MINUTES = 43200.0`
  - [ ] `compute_breakdown(service_id, slo_target, service_availability, dependencies) -> ErrorBudgetBreakdown`
    - [ ] Iterates hard sync deps
    - [ ] Computes per-dep consumption
    - [ ] Classifies risk levels
    - [ ] Populates high_risk_dependencies list
    - [ ] Computes self_consumption_pct
    - [ ] Computes total_dependency_consumption_pct
  - [ ] `compute_single_dependency_consumption(dep_availability, slo_target_pct) -> float`
    - [ ] Formula: `(1 - dep_availability) / (1 - slo_target/100)`
    - [ ] Returns infinity cap (999999.99) when slo_target = 100%
  - [ ] `classify_risk(consumption_pct) -> RiskLevel`
    - [ ] < 20% → LOW
    - [ ] 20-30% → MODERATE
    - [ ] > 30% → HIGH
  - [ ] `compute_error_budget_minutes(slo_target_pct) -> float`
    - [ ] Formula: `(1 - target/100) × 43200`
    - [ ] 99.9% → 43.2 minutes
- [ ] Create `tests/unit/domain/services/test_error_budget_analyzer.py` (>95% coverage)
  - [ ] SLO=99.9%, dep=99.5% → consumption = 500%
  - [ ] SLO=99.9%, dep=99.95% → consumption = 50%
  - [ ] SLO=99.9%, dep=99.99% → consumption = 10%
  - [ ] SLO=100%, dep=99.99% → consumption capped at 999999.99
  - [ ] Risk classification: LOW, MODERATE, HIGH thresholds
  - [ ] Full breakdown: multiple deps, high_risk list populated
  - [ ] Error budget minutes: 99.9% → 43.2, 99% → 432
  - [ ] Self consumption computed correctly

**Files to Create:** 2
**Dependencies:** Task 1.1
**Testing:** Unit tests with known-answer vectors

---

### Task 1.4: UnachievableSloDetector [Effort: M]

- [ ] Create `src/domain/services/unachievable_slo_detector.py`
  - [ ] `check(desired_target_pct, composite_bound, hard_dependency_count) -> UnachievableWarning | None`
    - [ ] Returns None when `composite_bound >= desired_target_pct / 100`
    - [ ] Returns UnachievableWarning when unachievable
    - [ ] Computes gap as `desired - composite * 100`
  - [ ] `compute_required_dep_availability(desired_target_pct, hard_dependency_count) -> float`
    - [ ] Formula: `1 - (1 - target/100) / (N + 1)`
    - [ ] Edge case: 0 deps → required = target itself
    - [ ] 99.99% with 3 deps → 99.9975%
  - [ ] `generate_warning_message(desired_target_pct, composite_bound_pct) -> str`
    - [ ] Matches TRD: "The desired target of X% is unachievable. Composite availability bound is Y% given current dependency chain."
  - [ ] `generate_remediation_guidance(desired_target_pct, required_pct, n_hard_deps) -> str`
    - [ ] 3 concrete suggestions: redundant paths, async conversion, target relaxation
- [ ] Create `tests/unit/domain/services/test_unachievable_slo_detector.py` (>95% coverage)
  - [ ] Achievable: target=99.9%, bound=0.998 → None
  - [ ] Unachievable: target=99.99%, bound=0.997 → warning
  - [ ] 10x rule: 99.99% with 3 deps → 99.9975%
  - [ ] 0 deps: required = target
  - [ ] Tiny gap (< 0.01%): still flagged
  - [ ] Warning message matches TRD format
  - [ ] Remediation guidance contains 3 suggestions

**Files to Create:** 2
**Dependencies:** Task 1.1
**Testing:** Unit tests with TRD validation vectors

---

## Phase 2: Application Layer [Week 2, Days 3-5]

**Objective:** Implement use cases, DTOs, and wire up domain services.

### Task 2.1: Constraint Analysis DTOs [Effort: M]

- [ ] Create `src/application/dtos/constraint_analysis_dto.py`
  - [ ] `ConstraintAnalysisRequest` (service_id, desired_target_pct, lookback_days, max_depth)
  - [ ] `ErrorBudgetBreakdownRequest` (service_id, slo_target_pct, lookback_days)
  - [ ] `DependencyRiskDTO` (service_id, availability_pct, error_budget_consumption_pct, risk_level, is_external, etc.)
  - [ ] `UnachievableWarningDTO` (desired_target_pct, composite_bound_pct, gap_pct, message, guidance, required_pct)
  - [ ] `ErrorBudgetBreakdownDTO` (service_id, slo_target_pct, total_budget_minutes, self_consumption, risks, high_risk list)
  - [ ] `ConstraintAnalysisResponse` (full response DTO with all fields)
  - [ ] `ErrorBudgetBreakdownResponse` (budget-only response DTO)
  - [ ] All DTOs use dataclasses (not Pydantic)
  - [ ] Percentages use `_pct` suffix convention
- [ ] Create `tests/unit/application/dtos/test_constraint_analysis_dto.py` (>90% coverage)

**Files to Create:** 2
**Dependencies:** Phase 1 complete
**Testing:** Unit tests

---

### Task 2.2: RunConstraintAnalysisUseCase [Effort: XL]

- [ ] Create `src/application/use_cases/run_constraint_analysis.py`
  - [ ] Constructor with 8 injected dependencies
  - [ ] `async execute(request: ConstraintAnalysisRequest) -> ConstraintAnalysisResponse | None`
  - [ ] Step 1: Validate service exists (return None if not found)
  - [ ] Step 2: Determine desired target (param > active SLO > 99.9% default)
  - [ ] Step 3: Retrieve dependency subgraph (downstream, max_depth)
  - [ ] Step 4: Classify deps (hard_sync, soft, external)
  - [ ] Step 5: Resolve dependency availabilities (parallel via asyncio.gather)
    - [ ] External deps: use ExternalApiBufferService
    - [ ] Internal deps: use telemetry service
    - [ ] Missing data: default to 99.9%
  - [ ] Step 6: Fetch service's own availability
  - [ ] Step 7: Compute composite bound via CompositeAvailabilityService
  - [ ] Step 8: Compute error budget breakdown via ErrorBudgetAnalyzer
  - [ ] Step 9: Check unachievability via UnachievableSloDetector
  - [ ] Step 10: Identify SCC supernodes
  - [ ] Step 11: Build ConstraintAnalysisResponse
  - [ ] Error: no deps → return error response (422 equivalent)
- [ ] Create `tests/unit/application/use_cases/test_run_constraint_analysis.py` (>90% coverage)
  - [ ] Happy path: service with 3 hard deps → full analysis
  - [ ] External dep: adaptive buffer applied correctly
  - [ ] No deps: returns error
  - [ ] Service not found: returns None
  - [ ] Missing telemetry: defaults to 99.9%
  - [ ] Unachievable SLO: warning included
  - [ ] All soft deps: composite = self
  - [ ] SCC reported from alerts

**Files to Create:** 2
**Dependencies:** Task 2.1, Phase 1 complete
**Testing:** Unit tests with AsyncMock

---

### Task 2.3: GetErrorBudgetBreakdownUseCase [Effort: L]

- [ ] Create `src/application/use_cases/get_error_budget_breakdown.py`
  - [ ] Constructor with 5 injected dependencies
  - [ ] `async execute(request: ErrorBudgetBreakdownRequest) -> ErrorBudgetBreakdownResponse | None`
  - [ ] Retrieves direct dependencies only (depth=1)
  - [ ] Filters to hard sync deps for budget computation
  - [ ] External deps use adaptive buffer
  - [ ] Returns ErrorBudgetBreakdownResponse
  - [ ] Returns None if service not found
- [ ] Create `tests/unit/application/use_cases/test_get_error_budget_breakdown.py` (>90% coverage)
  - [ ] Happy path: service with 2 hard deps
  - [ ] External dep handled correctly
  - [ ] Service not found: returns None
  - [ ] No hard deps: only self consumption

**Files to Create:** 2
**Dependencies:** Task 2.1, Phase 1 complete
**Testing:** Unit tests with AsyncMock

---

## Phase 3: Infrastructure — Database, API, E2E [Week 3]

**Objective:** Database migration, API endpoints, dependency injection, and E2E tests.

### Task 3.1: Alembic Migration — Add service_type [Effort: S]

- [ ] Create `alembic/versions/XXX_add_service_type_to_services.py`
  - [ ] `service_type` VARCHAR(20) NOT NULL DEFAULT 'internal'
  - [ ] CHECK constraint: `service_type IN ('internal', 'external')`
  - [ ] `published_sla` DECIMAL(8,6) DEFAULT NULL
  - [ ] Partial index `idx_services_external` WHERE `service_type = 'external'`
  - [ ] Reversible downgrade (drop columns + index)
- [ ] Test migration up/down on real PostgreSQL (testcontainers)
- [ ] Verify existing data unaffected

**Files to Create:** 1
**Dependencies:** None
**Testing:** Integration (migration up/down)

---

### Task 3.2: Update Service Entity & Repository [Effort: M]

- [ ] Modify `src/domain/entities/service.py`
  - [ ] Add `service_type: ServiceType = ServiceType.INTERNAL`
  - [ ] Add `published_sla: float | None = None`
  - [ ] Import `ServiceType` from constraint_analysis entities
- [ ] Modify `src/domain/repositories/service_repository.py`
  - [ ] Add `get_external_services() -> list[Service]` abstract method
- [ ] Modify `src/infrastructure/database/models.py`
  - [ ] Add `service_type` column to `ServiceModel`
  - [ ] Add `published_sla` column to `ServiceModel`
- [ ] Modify `src/infrastructure/database/repositories/service_repository.py`
  - [ ] Update `_to_entity()` to map service_type and published_sla
  - [ ] Update `_to_dict()` to include new fields
  - [ ] Implement `get_external_services()` with filtered query
- [ ] Verify all existing FR-1 tests still pass (backward compatible)
- [ ] Add integration tests for new fields and method

**Files to Modify:** 4
**Dependencies:** Task 3.1, Task 1.1
**Testing:** Integration tests

---

### Task 3.3: Pydantic API Schemas [Effort: M]

- [ ] Create `src/infrastructure/api/schemas/constraint_analysis_schema.py`
  - [ ] `ConstraintAnalysisQueryParams`: desired_target_pct (90-99.9999, optional), lookback_days (7-365), max_depth (1-10)
  - [ ] `ConstraintAnalysisApiResponse`: matches API spec JSON exactly
  - [ ] `ErrorBudgetBreakdownQueryParams`: slo_target_pct (90-99.9999, default 99.9), lookback_days (7-365)
  - [ ] `ErrorBudgetBreakdownApiResponse`: matches API spec JSON exactly
  - [ ] `DependencyRiskApiModel`: nested model for each dep risk
  - [ ] `UnachievableWarningApiModel`: nested model for warning
  - [ ] Reuse RFC 7807 error schema from FR-1
- [ ] Create `tests/unit/infrastructure/api/schemas/test_constraint_analysis_schema.py` (>90% coverage)
  - [ ] Validation: desired_target_pct range
  - [ ] Validation: lookback_days range
  - [ ] Validation: max_depth range
  - [ ] Default values applied correctly
  - [ ] Response model serialization

**Files to Create:** 2
**Dependencies:** Phase 2 DTOs
**Testing:** Unit tests

---

### Task 3.4: API Routes [Effort: L]

- [ ] Create `src/infrastructure/api/routes/constraint_analysis.py`
  - [ ] `GET /api/v1/services/{service_id}/constraint-analysis`
    - [ ] Auth: `verify_api_key` dependency
    - [ ] Rate limit: 30 req/min
    - [ ] Query params: desired_target_pct, lookback_days, max_depth
    - [ ] 200: returns ConstraintAnalysisApiResponse
    - [ ] 404: service not found (RFC 7807)
    - [ ] 422: no dependencies (RFC 7807)
    - [ ] 400: invalid params (RFC 7807)
    - [ ] 429: rate limit (RFC 7807 + Retry-After)
  - [ ] `GET /api/v1/services/{service_id}/error-budget-breakdown`
    - [ ] Auth: `verify_api_key` dependency
    - [ ] Rate limit: 60 req/min
    - [ ] Query params: slo_target_pct, lookback_days
    - [ ] Same error handling pattern
  - [ ] Convert API schemas ↔ Application DTOs in route handlers
- [ ] Create `tests/integration/infrastructure/api/test_constraint_analysis_endpoint.py` (>80% coverage)
  - [ ] 200 response structure matches schema
  - [ ] 404 for unknown service
  - [ ] 400 for invalid params
  - [ ] Auth required (401 without key)

**Files to Create:** 2
**Dependencies:** Task 3.3, Phase 2 complete
**Testing:** Integration tests with httpx

---

### Task 3.5: Dependency Injection Wiring [Effort: M]

- [ ] Modify `src/infrastructure/api/dependencies.py`
  - [ ] Factory for `ExternalApiBufferService`
  - [ ] Factory for `ErrorBudgetAnalyzer`
  - [ ] Factory for `UnachievableSloDetector`
  - [ ] Factory for `RunConstraintAnalysisUseCase` (8 deps)
  - [ ] Factory for `GetErrorBudgetBreakdownUseCase` (5 deps)
  - [ ] Factory for `MockPrometheusClient` (conditional on config)
- [ ] Modify `src/infrastructure/api/main.py`
  - [ ] Register constraint analysis router
- [ ] Verify DI chain works end-to-end (verified by integration tests)

**Files to Modify:** 2
**Dependencies:** Task 3.4
**Testing:** Verified by integration + E2E tests

---

### Task 3.6: End-to-End Tests [Effort: L]

- [ ] Create `tests/e2e/test_constraint_analysis.py`
  - [ ] E2E: Ingest graph with internal + external services → GET /constraint-analysis → valid response
  - [ ] E2E: External dep uses adaptive buffer (published_sla vs observed)
  - [ ] E2E: Unachievable SLO detected (desired_target_pct=99.99, low-availability deps)
  - [ ] E2E: GET /error-budget-breakdown → valid response with per-dep risks
  - [ ] E2E: Service with no deps → 422
  - [ ] E2E: Unknown service → 404
  - [ ] E2E: Invalid params → 400
  - [ ] Performance: constraint analysis response < 2s
  - [ ] Performance: error budget breakdown response < 1s

**Files to Create:** 1
**Dependencies:** Task 3.4, Task 3.5
**Testing:** E2E with testcontainers + httpx

---

## Definition of Done

- [ ] All 16 tasks completed
- [ ] All unit tests passing (>90% domain coverage, >85% application coverage)
- [ ] All integration tests passing (>75% infrastructure coverage)
- [ ] All E2E tests passing
- [ ] `ruff check .` passes (no lint errors)
- [ ] `ruff format --check .` passes (formatted)
- [ ] `mypy src/ --strict` passes (no type errors)
- [ ] Database migration applied and reversible
- [ ] API endpoints documented in Swagger UI
- [ ] FR-3 context document updated with final status
- [ ] Core docs (`docs/`) updated to reflect FR-3 capabilities
