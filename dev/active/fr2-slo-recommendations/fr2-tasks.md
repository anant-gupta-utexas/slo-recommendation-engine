# FR-2: SLO Recommendation Generation — Task Tracker

**Created:** 2026-02-15
**Last Updated:** 2026-02-15

---

## Phase 1: Domain Foundation [Week 1]

**Objective:** Domain entities, value objects, and pure computation services with comprehensive unit tests.

### Tasks

- [ ] **Task 1.1: SLO Recommendation Entity** [Effort: M]
  - Files: `src/domain/entities/slo_recommendation.py`, `tests/unit/domain/entities/test_slo_recommendation.py`
  - Acceptance:
    - [ ] `SloRecommendation`, `RecommendationTier`, `FeatureAttribution`, `DependencyImpact`, `DataQuality`, `Explanation` entities created
    - [ ] `SliType`, `RecommendationStatus`, `TierLevel` enums defined
    - [ ] `__post_init__` auto-computes `expires_at = generated_at + 24h`
    - [ ] `supersede()`, `expire()`, `is_expired` work correctly
    - [ ] Validation: breach_probability 0-1, required fields
    - [ ] >95% unit test coverage

- [ ] **Task 1.2: SLI Data Value Objects** [Effort: S]
  - Files: `src/domain/entities/sli_data.py`, `tests/unit/domain/entities/test_sli_data.py`
  - Acceptance:
    - [ ] `AvailabilitySliData` with `error_rate` property
    - [ ] `LatencySliData` with p50/p95/p99/p999
    - [ ] >95% unit test coverage

- [ ] **Task 1.3: Availability Calculator Service** [Effort: L]
  - Files: `src/domain/services/availability_calculator.py`, `tests/unit/domain/services/test_availability_calculator.py`
  - Dependencies: Task 1.1
  - Acceptance:
    - [ ] `compute_tiers()` returns 3 tiers with correct percentile-based values
    - [ ] Conservative + Balanced capped by composite_bound
    - [ ] Aggressive NOT capped
    - [ ] `estimate_breach_probability()` correct fraction
    - [ ] `compute_error_budget_minutes()` correct calculation
    - [ ] Bootstrap confidence intervals (1000 resamples)
    - [ ] Edge cases: 100% avail, 0% avail, single data point
    - [ ] >95% unit test coverage

- [ ] **Task 1.4: Latency Calculator Service** [Effort: M]
  - Files: `src/domain/services/latency_calculator.py`, `tests/unit/domain/services/test_latency_calculator.py`
  - Dependencies: Task 1.2
  - Acceptance:
    - [ ] Conservative = p999 + noise, Balanced = p99 + noise, Aggressive = p95
    - [ ] Noise margin: 5% default, 10% shared infra
    - [ ] Breach probabilities estimated from percentile positions
    - [ ] >95% unit test coverage

- [ ] **Task 1.5: Composite Availability Service** [Effort: L]
  - Files: `src/domain/services/composite_availability_service.py`, `tests/unit/domain/services/test_composite_availability_service.py`
  - Dependencies: Task 1.1, Task 1.2
  - Acceptance:
    - [ ] Serial hard: `R = R_self * product(R_dep_i)`
    - [ ] Parallel: `R = 1 - product(1 - R_replica_j)`
    - [ ] Soft deps excluded, counted in metadata
    - [ ] Bottleneck identification correct
    - [ ] Edge cases: no deps, all soft, single dep, very low availability
    - [ ] >95% unit test coverage

- [ ] **Task 1.6: Weighted Attribution Service** [Effort: M]
  - Files: `src/domain/services/weighted_attribution_service.py`, `tests/unit/domain/services/test_weighted_attribution_service.py`
  - Dependencies: Task 1.1
  - Acceptance:
    - [ ] Availability weights: 0.40 / 0.30 / 0.15 / 0.15
    - [ ] Latency weights: 0.50 / 0.22 / 0.15 / 0.13
    - [ ] Normalized to sum = 1.0
    - [ ] Sorted by absolute contribution descending
    - [ ] >95% unit test coverage

- [ ] **Task 1.7: Repository Interfaces** [Effort: S]
  - Files: `src/domain/repositories/slo_recommendation_repository.py`, `src/domain/repositories/telemetry_query_service.py`
  - Dependencies: Task 1.1, Task 1.2
  - Acceptance:
    - [ ] `SloRecommendationRepositoryInterface` with 5 abstract methods
    - [ ] `TelemetryQueryServiceInterface` with 4 abstract methods
    - [ ] Type hints using domain entities
    - [ ] Docstrings for all methods

### Phase 1 Checklist
- [ ] All entities created with validation
- [ ] 4 computation services with >95% test coverage
- [ ] 2 repository interfaces defined
- [ ] All unit tests passing
- [ ] Total Phase 1 tests: ~XX passing

---

## Phase 2: Application Layer [Week 2]

**Objective:** Use cases (orchestration), DTOs, and domain service wiring.

### Tasks

- [ ] **Task 2.1: SLO Recommendation DTOs** [Effort: M]
  - Files: `src/application/dtos/slo_recommendation_dto.py`, `tests/unit/application/dtos/test_slo_recommendation_dto.py`
  - Dependencies: Phase 1 complete
  - Acceptance:
    - [ ] 11 DTO dataclasses created
    - [ ] Request DTOs with sensible defaults
    - [ ] `BatchComputeResult` with failure details list
    - [ ] >90% unit test coverage

- [ ] **Task 2.2: GenerateSloRecommendation Use Case** [Effort: XL]
  - Files: `src/application/use_cases/generate_slo_recommendation.py`, `tests/unit/application/use_cases/test_generate_slo_recommendation.py`
  - Dependencies: Task 2.1
  - Acceptance:
    - [ ] Full pipeline: validate → lookback → telemetry → deps → composite → tiers → attribution → save
    - [ ] Cold-start: data_completeness < 0.90 → extended lookback
    - [ ] Supersedes existing recommendations
    - [ ] Returns None if service not found
    - [ ] Handles missing telemetry (returns error DTO)
    - [ ] Defaults 99.9% for deps without data
    - [ ] Builds correct explanation summary string
    - [ ] >90% unit test coverage (AsyncMock)

- [ ] **Task 2.3: GetSloRecommendation Use Case** [Effort: M]
  - Files: `src/application/use_cases/get_slo_recommendation.py`, `tests/unit/application/use_cases/test_get_slo_recommendation.py`
  - Dependencies: Task 2.2
  - Acceptance:
    - [ ] Returns stored active recommendations
    - [ ] Delegates to GenerateUseCase when force_regenerate=True
    - [ ] Returns None if service not found
    - [ ] Filters by sli_type
    - [ ] >90% unit test coverage

- [ ] **Task 2.4: BatchComputeRecommendations Use Case** [Effort: L]
  - Files: `src/application/use_cases/batch_compute_recommendations.py`, `tests/unit/application/use_cases/test_batch_compute_recommendations.py`
  - Dependencies: Task 2.2
  - Acceptance:
    - [ ] Iterates non-discovered services
    - [ ] Calls GenerateUseCase per service
    - [ ] Continues on failure, collects errors
    - [ ] asyncio.gather with semaphore(20)
    - [ ] Returns BatchComputeResult
    - [ ] >85% unit test coverage

### Phase 2 Checklist
- [ ] All DTOs created and tested
- [ ] All 3 use cases implemented
- [ ] >90% test coverage on use cases
- [ ] All unit tests passing
- [ ] Total Phase 2 tests: ~XX passing

---

## Phase 3: Infrastructure — Persistence & Telemetry [Week 3]

**Objective:** Database models, repositories, mock Prometheus client, and Alembic migrations.

### Tasks

- [ ] **Task 3.1: SQLAlchemy Models** [Effort: M]
  - Files: `src/infrastructure/database/models/slo_recommendation.py`, `src/infrastructure/database/models/sli_aggregate.py`
  - Dependencies: Phase 2 complete
  - Acceptance:
    - [ ] `SloRecommendationModel` with all columns and constraints
    - [ ] `SliAggregateModel` with all columns and constraints
    - [ ] JSONB for tiers, explanation, data_quality
    - [ ] Check constraints for enums
    - [ ] Follows FR-1 model patterns (Base class, Mapped[])

- [ ] **Task 3.2: Alembic Migrations** [Effort: S]
  - Files: `alembic/versions/004_create_slo_recommendations_table.py`, `alembic/versions/005_create_sli_aggregates_table.py`
  - Dependencies: Task 3.1
  - Acceptance:
    - [ ] Migration 004: slo_recommendations table + indexes
    - [ ] Migration 005: sli_aggregates table + indexes
    - [ ] Both reversible
    - [ ] FK to services.id validated
    - [ ] Tested against real PostgreSQL

- [ ] **Task 3.3: SloRecommendation Repository Implementation** [Effort: L]
  - Files: `src/infrastructure/database/repositories/slo_recommendation_repository.py`, `tests/integration/infrastructure/database/test_slo_recommendation_repository.py`
  - Dependencies: Task 3.1, Task 3.2
  - Acceptance:
    - [ ] `get_active_by_service()` with optional sli_type filter
    - [ ] `save()` inserts new recommendation
    - [ ] `save_batch()` bulk inserts
    - [ ] `supersede_existing()` marks active → superseded
    - [ ] `expire_stale()` marks expired
    - [ ] Domain ↔ model mapping
    - [ ] >80% integration test coverage (testcontainers)

- [ ] **Task 3.4: Mock Prometheus Client** [Effort: L]
  - Files: `src/infrastructure/telemetry/mock_prometheus_client.py`, `src/infrastructure/telemetry/seed_data.py`, `tests/unit/infrastructure/telemetry/test_mock_prometheus_client.py`
  - Dependencies: Phase 1 Task 1.7
  - Acceptance:
    - [ ] Implements all 4 TelemetryQueryServiceInterface methods
    - [ ] Different data per service_id via seed data dict
    - [ ] Seed: 5 services (30d), 2 services (10d), 1 service (no data)
    - [ ] Realistic variance in rolling availability
    - [ ] Injectable seed data for tests
    - [ ] >90% unit test coverage

### Phase 3 Checklist
- [ ] 2 SQLAlchemy models created
- [ ] 2 Alembic migrations created and tested
- [ ] Repository with full CRUD tested
- [ ] Mock Prometheus client with seed data
- [ ] All tests passing
- [ ] Total Phase 3 tests: ~XX passing

---

## Phase 4: Infrastructure — API & Background Tasks [Week 4]

**Objective:** API endpoint, Pydantic schemas, batch task, full integration.

### Tasks

- [ ] **Task 4.1: Pydantic API Schemas** [Effort: M]
  - Files: `src/infrastructure/api/schemas/slo_recommendation_schema.py`, `tests/unit/infrastructure/api/schemas/test_slo_recommendation_schema.py`
  - Dependencies: Phase 2 DTOs
  - Acceptance:
    - [ ] Query param validation (sli_type enum, lookback_days 7-365, force_regenerate bool)
    - [ ] Response matches TRD JSON schema
    - [ ] Nested models: Tier, Explanation, DependencyImpact, DataQuality
    - [ ] RFC 7807 error schema reused from FR-1

- [ ] **Task 4.2: API Route — GET /slo-recommendations** [Effort: L]
  - Files: `src/infrastructure/api/routes/recommendations.py`, `tests/integration/infrastructure/api/test_recommendations_endpoint.py`
  - Dependencies: Task 4.1, Phase 3 complete
  - Acceptance:
    - [ ] Route: `GET /api/v1/services/{service_id}/slo-recommendations`
    - [ ] Query params: sli_type, lookback_days, force_regenerate
    - [ ] Auth middleware (X-API-Key)
    - [ ] Rate limiting (60 req/min)
    - [ ] 200: recommendation response
    - [ ] 404: service not found
    - [ ] 422: insufficient data
    - [ ] 400: invalid params
    - [ ] 429: rate limited
    - [ ] Integration test with httpx

- [ ] **Task 4.3: Dependency Injection Wiring** [Effort: M]
  - Files: `src/infrastructure/api/dependencies.py` (modify), `src/infrastructure/api/main.py` (modify)
  - Dependencies: Task 4.2
  - Acceptance:
    - [ ] FastAPI Depends() chain for all FR-2 services
    - [ ] Mock Prometheus client injected via config
    - [ ] Session management preserved

- [ ] **Task 4.4: Batch Computation Background Task** [Effort: M]
  - Files: `src/infrastructure/tasks/batch_recommendations.py`, `tests/integration/infrastructure/tasks/test_batch_recommendations.py`
  - Dependencies: Phase 2 Task 2.4, Phase 3
  - Acceptance:
    - [ ] APScheduler cron: every 24h (configurable)
    - [ ] Calls BatchComputeRecommendationsUseCase
    - [ ] Logs results
    - [ ] Prometheus metrics emitted
    - [ ] Non-blocking to API

- [ ] **Task 4.5: End-to-End Tests** [Effort: L]
  - Files: `tests/e2e/test_slo_recommendations.py`
  - Dependencies: Task 4.2, Task 4.3
  - Acceptance:
    - [ ] E2E: ingest graph → get recommendations → valid response
    - [ ] E2E: force_regenerate recomputes
    - [ ] E2E: no-data service returns 422
    - [ ] E2E: response matches TRD schema
    - [ ] Performance: pre-computed retrieval < 500ms

### Phase 4 Checklist
- [ ] Pydantic schemas created and tested
- [ ] API endpoint live with auth + rate limiting
- [ ] DI wiring complete
- [ ] Batch task scheduled
- [ ] E2E tests passing
- [ ] Total Phase 4 tests: ~XX passing

---

## Overall Progress Summary

| Phase | Status | Tests Passing | Coverage |
|-------|--------|--------------|----------|
| Phase 1: Domain | ⬜ Not Started | 0/0 | — |
| Phase 2: Application | ⬜ Not Started | 0/0 | — |
| Phase 3: Infrastructure (DB + Telemetry) | ⬜ Not Started | 0/0 | — |
| Phase 4: Infrastructure (API + Tasks) | ⬜ Not Started | 0/0 | — |
| **Total** | **⬜ Not Started** | **0/0** | **—** |

---

## Session Log

### Session 1 (2026-02-15): Planning
- Created FR-2 plan, context, and task documents
- Key decisions documented: mock Prometheus, weighted attribution, pre-compute, extended lookback, percentile + cap
- No blockers identified

---

**Document Version:** 1.0
**Last Updated:** 2026-02-15
