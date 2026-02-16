# FR-2: SLO Recommendation Generation — Task Tracker

**Created:** 2026-02-15
**Last Updated:** 2026-02-15 (Session 7 - Phase 3: 50%)

---

## Phase 1: Domain Foundation [Week 1]

**Objective:** Domain entities, value objects, and pure computation services with comprehensive unit tests.

### Tasks

- [x] **Task 1.1: SLO Recommendation Entity** [Effort: M] ✅ **COMPLETE**
  - Files: `src/domain/entities/slo_recommendation.py`, `tests/unit/domain/entities/test_slo_recommendation.py`
  - Acceptance:
    - [x] `SloRecommendation`, `RecommendationTier`, `FeatureAttribution`, `DependencyImpact`, `DataQuality`, `Explanation` entities created
    - [x] `SliType`, `RecommendationStatus`, `TierLevel` enums defined
    - [x] `__post_init__` auto-computes `expires_at = generated_at + 24h`
    - [x] `supersede()`, `expire()`, `is_expired` work correctly
    - [x] Validation: breach_probability 0-1, required fields
    - [x] >95% unit test coverage (32 tests, 100% coverage)

- [x] **Task 1.2: SLI Data Value Objects** [Effort: S] ✅ **COMPLETE**
  - Files: `src/domain/entities/sli_data.py`, `tests/unit/domain/entities/test_sli_data.py`
  - Acceptance:
    - [x] `AvailabilitySliData` with `error_rate` property
    - [x] `LatencySliData` with p50/p95/p99/p999
    - [x] >95% unit test coverage (24 tests, 100% coverage)

- [x] **Task 1.3: Availability Calculator Service** [Effort: L] ✅ **COMPLETE**
  - Files: `src/domain/services/availability_calculator.py`, `tests/unit/domain/services/test_availability_calculator.py`
  - Dependencies: Task 1.1
  - Acceptance:
    - [x] `compute_tiers()` returns 3 tiers with correct percentile-based values
    - [x] Conservative + Balanced capped by composite_bound
    - [x] Aggressive NOT capped
    - [x] `estimate_breach_probability()` correct fraction
    - [x] `compute_error_budget_minutes()` correct calculation
    - [x] Bootstrap confidence intervals (1000 resamples)
    - [x] Edge cases: 100% avail, 0% avail, single data point
    - [x] >95% unit test coverage (31 tests, 100% coverage)

- [x] **Task 1.4: Latency Calculator Service** [Effort: M] ✅ **COMPLETE**
  - Files: `src/domain/services/latency_calculator.py`, `tests/unit/domain/services/test_latency_calculator.py`
  - Dependencies: Task 1.2
  - Acceptance:
    - [x] Conservative = p999 + noise, Balanced = p99 + noise, Aggressive = p95
    - [x] Noise margin: 5% default, 10% shared infra
    - [x] Breach probabilities estimated from percentile positions
    - [x] >95% unit test coverage (26 tests, 98% coverage)

- [x] **Task 1.5: Composite Availability Service** [Effort: L] ✅ **COMPLETE**
  - Files: `src/domain/services/composite_availability_service.py`, `tests/unit/domain/services/test_composite_availability_service.py`
  - Dependencies: Task 1.1, Task 1.2
  - Acceptance:
    - [x] Serial hard: `R = R_self * product(R_dep_i)`
    - [x] Parallel: `R = 1 - product(1 - R_replica_j)`
    - [x] Soft deps excluded, counted in metadata
    - [x] Bottleneck identification correct
    - [x] Edge cases: no deps, all soft, single dep, very low availability
    - [x] >95% unit test coverage (26 tests, 97% coverage)

- [x] **Task 1.6: Weighted Attribution Service** [Effort: M] ✅ **COMPLETE**
  - Files: `src/domain/services/weighted_attribution_service.py`, `tests/unit/domain/services/test_weighted_attribution_service.py`
  - Dependencies: Task 1.1
  - Acceptance:
    - [x] Availability weights: 0.40 / 0.30 / 0.15 / 0.15
    - [x] Latency weights: 0.50 / 0.22 / 0.15 / 0.13
    - [x] Normalized to sum = 1.0
    - [x] Sorted by absolute contribution descending
    - [x] >95% unit test coverage (28 tests, 100% coverage)

- [x] **Task 1.7: Repository Interfaces** [Effort: S] ✅ **COMPLETE**
  - Files: `src/domain/repositories/slo_recommendation_repository.py`, `src/domain/repositories/telemetry_query_service.py`
  - Dependencies: Task 1.1, Task 1.2
  - Acceptance:
    - [x] `SloRecommendationRepositoryInterface` with 5 abstract methods
    - [x] `TelemetryQueryServiceInterface` with 4 abstract methods
    - [x] Type hints using domain entities
    - [x] Docstrings for all methods

### Phase 1 Checklist
- [x] All entities created with validation ✅
- [x] 4 computation services with >95% test coverage (4/4 complete) ✅
- [x] 2 repository interfaces defined ✅
- [x] All unit tests passing (167/167 tests) ✅
- **Total Phase 1 tests: 167 passing (100% complete)** ✅

---

## Phase 2: Application Layer [Week 2]

**Objective:** Use cases (orchestration), DTOs, and domain service wiring.

### Tasks

- [x] **Task 2.1: SLO Recommendation DTOs** [Effort: M] ✅ **COMPLETE**
  - Files: `src/application/dtos/slo_recommendation_dto.py`, `tests/unit/application/dtos/test_slo_recommendation_dto.py`
  - Dependencies: Phase 1 complete
  - Acceptance:
    - [x] 11 DTO dataclasses created
    - [x] Request DTOs with sensible defaults
    - [x] `BatchComputeResult` with failure details list
    - [x] >90% unit test coverage (25 tests, 100% coverage)

- [x] **Task 2.2: GenerateSloRecommendation Use Case** [Effort: XL] ✅ **COMPLETE**
  - Files: `src/application/use_cases/generate_slo_recommendation.py`, `tests/unit/application/use_cases/test_generate_slo_recommendation.py`
  - Dependencies: Task 2.1
  - Acceptance:
    - [x] Full pipeline: validate → lookback → telemetry → deps → composite → tiers → attribution → save
    - [x] Cold-start: data_completeness < 0.90 → extended lookback
    - [x] Supersedes existing recommendations
    - [x] Returns None if service not found
    - [x] Handles missing telemetry (skips that SLI type)
    - [x] Defaults 99.9% for deps without data
    - [x] Builds correct explanation summary string
    - [x] >90% unit test coverage (20 tests, 100% coverage on use case logic)

- [x] **Task 2.3: GetSloRecommendation Use Case** [Effort: M] ✅ **COMPLETE**
  - Files: `src/application/use_cases/get_slo_recommendation.py`, `tests/unit/application/use_cases/test_get_slo_recommendation.py`
  - Dependencies: Task 2.2
  - Acceptance:
    - [x] Returns stored active recommendations (falls back to generation in Phase 2)
    - [x] Delegates to GenerateUseCase when force_regenerate=True
    - [x] Returns None if service not found
    - [x] Filters by sli_type
    - [x] >90% unit test coverage (7 tests, 97% coverage)

- [x] **Task 2.4: BatchComputeRecommendations Use Case** [Effort: L] ✅ **COMPLETE**
  - Files: `src/application/use_cases/batch_compute_recommendations.py`, `tests/unit/application/use_cases/test_batch_compute_recommendations.py`
  - Dependencies: Task 2.2
  - Acceptance:
    - [x] Iterates non-discovered services
    - [x] Calls GenerateUseCase per service
    - [x] Continues on failure, collects errors
    - [x] asyncio.gather with semaphore(20)
    - [x] Returns BatchComputeResult
    - [x] >85% unit test coverage (11 tests, 100% coverage)

### Phase 2 Checklist
- [x] All DTOs created and tested ✅
- [x] All 3 use cases implemented (3/3 complete: Generate ✅, Get ✅, Batch ✅) ✅
- [x] >90% test coverage on use cases (97-100% coverage) ✅
- [x] All unit tests passing (63 Phase 2 tests) ✅
- **Total Phase 2 tests: 63/63 passing (100% complete)** ✅

---

## Phase 3: Infrastructure — Persistence & Telemetry [Week 3]

**Objective:** Database models, repositories, mock Prometheus client, and Alembic migrations.

### Tasks

- [x] **Task 3.1: SQLAlchemy Models** [Effort: M] ✅ **COMPLETE**
  - Files: `src/infrastructure/database/models.py` (added to existing file)
  - Dependencies: Phase 2 complete
  - Acceptance:
    - [x] `SloRecommendationModel` with all columns and constraints
    - [x] `SliAggregateModel` with all columns and constraints
    - [x] JSONB for tiers, explanation, data_quality
    - [x] Check constraints for enums
    - [x] Follows FR-1 model patterns (Base class, Mapped[])
    - [x] Fixed SQL reserved keyword issue: renamed "window" → "time_window"

- [x] **Task 3.2: Alembic Migrations** [Effort: S] ✅ **COMPLETE**
  - Files: `alembic/versions/ecd649c39043_create_slo_recommendations_table.py`, `alembic/versions/0493364c9562_create_sli_aggregates_table.py`
  - Dependencies: Task 3.1
  - Acceptance:
    - [x] Migration ecd649c39043: slo_recommendations table + 3 indexes
    - [x] Migration 0493364c9562: sli_aggregates table + 1 index
    - [x] Both reversible (tested upgrade/downgrade)
    - [x] FK to services.id validated with CASCADE delete
    - [x] Tested against real PostgreSQL (docker-compose)

- [x] **Task 3.3: SloRecommendation Repository Implementation** [Effort: L] ✅ **COMPLETE**
  - Files: `src/infrastructure/database/repositories/slo_recommendation_repository.py`, `tests/integration/infrastructure/database/test_slo_recommendation_repository.py`
  - Dependencies: Task 3.1, Task 3.2
  - Acceptance:
    - [x] `get_active_by_service()` with optional sli_type filter
    - [x] `save()` inserts new recommendation
    - [x] `save_batch()` bulk inserts
    - [x] `supersede_existing()` marks active → superseded
    - [x] `expire_stale()` marks expired
    - [x] Domain ↔ model mapping
    - [x] 100% integration test coverage (12 tests passing, testcontainers)

- [x] **Task 3.4: Mock Prometheus Client** [Effort: L] ✅ **COMPLETE**
  - Files: `src/infrastructure/telemetry/mock_prometheus_client.py`, `src/infrastructure/telemetry/seed_data.py`, `tests/unit/infrastructure/telemetry/test_mock_prometheus_client.py`
  - Dependencies: Phase 1 Task 1.7
  - Acceptance:
    - [x] Implements all 4 TelemetryQueryServiceInterface methods
    - [x] Different data per service_id via seed data dict (8 services)
    - [x] Seed: 5 services (30d), 2 services (7-10d cold-start), 1 service (no data)
    - [x] Realistic variance in rolling availability (reproducible randomness)
    - [x] Injectable seed data for tests (constructor parameter)
    - [x] 95% unit test coverage (24 tests passing)

### Phase 3 Checklist
- [x] 2 SQLAlchemy models created ✅
- [x] 2 Alembic migrations created and tested ✅
- [x] Repository with full CRUD tested (12 integration tests, 100% coverage) ✅
- [x] Mock Prometheus client with seed data (24 unit tests, 95% coverage) ✅
- [x] All tests passing (414 total: 402 unit + 12 integration) ✅
- [x] **Phase 3: 100% COMPLETE** ✅

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
| Phase 1: Domain | ✅ Complete (100%) | 167/167 | 97-100% |
| Phase 2: Application | ✅ Complete (100%) | 63/63 | 97-100% |
| Phase 3: Infrastructure (DB + Telemetry) | ✅ Complete (100%) | 36/36 | 95-100% |
| Phase 4: Infrastructure (API + Tasks) | ⬜ Not Started | 0/~60 | — |
| **Total** | **✅ Phase 3 Complete → Phase 4 Next** | **266/~330** | **81%** |

**Phase 3 Progress:**
- ✅ Task 3.1: SQLAlchemy Models (COMPLETE)
- ✅ Task 3.2: Alembic Migrations (COMPLETE)
- ✅ Task 3.3: Repository Implementation (COMPLETE)
- ✅ Task 3.4: Mock Prometheus Client (COMPLETE)

---

**Document Version:** 1.6
**Last Updated:** 2026-02-15 (Session 8 - Phase 3: 100% COMPLETE ✅)
