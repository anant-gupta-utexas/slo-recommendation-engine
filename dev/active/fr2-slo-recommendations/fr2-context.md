# FR-2 Context Document
## SLO Recommendation Generation

**Created:** 2026-02-15
**Last Updated:** 2026-02-15 (Session 6 - Phase 2 COMPLETE)

---

## Current Implementation Status

### Phase 1: Domain Foundation ✅ **COMPLETE**
**Status:** 100% complete (167 tests passing, 97-100% coverage)

**Components:**
- ✅ Entities: `SloRecommendation`, `AvailabilitySliData`, `LatencySliData`
- ✅ Services: `AvailabilityCalculator`, `LatencyCalculator`, `CompositeAvailabilityService`, `WeightedAttributionService`
- ✅ Repository Interfaces: `SloRecommendationRepositoryInterface`, `TelemetryQueryServiceInterface`

**Key Features:**
- Three-tier availability/latency recommendations
- Bootstrap confidence intervals (1000 resamples)
- Composite bound capping (Conservative/Balanced capped, Aggressive NOT capped)
- Breach probability estimation
- Error budget calculation

### Phase 2: Application Layer ✅ **COMPLETE**
**Status:** 100% complete (63 tests passing, 97-100% coverage)

**Completed Components:**
1. ✅ **DTOs (Task 2.1):**
   - 11 DTOs with full validation
   - 25 tests, 100% coverage
   - File: `src/application/dtos/slo_recommendation_dto.py`

2. ✅ **GenerateSloRecommendation Use Case (Task 2.2):**
   - Full 12-step recommendation pipeline
   - Cold-start logic (30d → 90d when completeness < 90%)
   - Dependency traversal + composite bounds
   - Weighted attribution + explanation generation
   - 20 tests, 98% coverage
   - File: `src/application/use_cases/generate_slo_recommendation.py`

3. ✅ **GetSloRecommendation Use Case (Task 2.3):**
   - Retrieves recommendations (falls back to generation in Phase 2 MVP)
   - Delegates to GenerateUseCase when `force_regenerate=True`
   - Returns None if service not found
   - Filters by `sli_type`
   - 7 tests, 97% coverage
   - File: `src/application/use_cases/get_slo_recommendation.py`

4. ✅ **BatchComputeRecommendations Use Case (Task 2.4):**
   - Batch computes for all eligible services
   - Excludes discovered-only services by default
   - Concurrent execution with semaphore(20)
   - Robust error handling + detailed metrics
   - 11 tests, 100% coverage
   - File: `src/application/use_cases/batch_compute_recommendations.py`

**Test Summary:**
- **Total: 266 tests passing** (167 Phase 1 + 63 Phase 2 + 36 Phase 3)
- Phase 2: 63 tests (25 DTOs + 20 Generate + 7 Get + 11 Batch)
- Phase 3: 36 tests (12 integration repository + 24 unit telemetry)
- 0 failures
- Coverage: 81% overall, 95-100% on Phase 3 components

### Phase 3: Infrastructure (DB + Telemetry) ✅ **COMPLETE (100%)**
**Status:** All 4 tasks complete

**Completed Components:**
1. ✅ **SQLAlchemy Models (Task 3.1):**
   - `SloRecommendationModel` with JSONB fields, constraints, FK
   - `SliAggregateModel` with renamed column `time_window` (SQL keyword fix)
   - File: `src/infrastructure/database/models.py`

2. ✅ **Alembic Migrations (Task 3.2):**
   - Migration `ecd649c39043_create_slo_recommendations_table.py`
   - Migration `0493364c9562_create_sli_aggregates_table.py`
   - Both tested: upgrade ✅, downgrade ✅, re-upgrade ✅
   - Tables created with all indexes and constraints

3. ✅ **SloRecommendationRepository (Task 3.3):**
   - Full CRUD implementation with domain↔model mapping
   - 5 methods: `get_active_by_service`, `save`, `save_batch`, `supersede_existing`, `expire_stale`
   - JSONB serialization for nested structures (tiers, explanation, data_quality)
   - 12 integration tests, 100% coverage
   - File: `src/infrastructure/database/repositories/slo_recommendation_repository.py`
   - Tests: `tests/integration/infrastructure/database/test_slo_recommendation_repository.py`

4. ✅ **Mock Prometheus Client (Task 3.4):**
   - Implements all 4 `TelemetryQueryServiceInterface` methods
   - 8 seed scenarios: 5 stable (30d), 2 cold-start (7-10d), 1 no-data
   - Realistic variance with reproducible randomness
   - Injectable seed data for custom tests
   - 24 unit tests, 95% coverage
   - Files: `src/infrastructure/telemetry/mock_prometheus_client.py`, `src/infrastructure/telemetry/seed_data.py`
   - Tests: `tests/unit/infrastructure/telemetry/test_mock_prometheus_client.py`

### Phase 4: Infrastructure (API + Tasks) ⬜ **NOT STARTED**

---

## Key Decisions Made

### Architecture Decisions

| Decision | Choice Made | Rationale |
|----------|-------------|-----------|
| **Telemetry Source** | Mock Prometheus stub | Enables parallel development; faster iteration |
| **Explainability** | Weighted attribution (fixed weights) | Simpler than SHAP; sufficient for MVP |
| **Caching Strategy** | Pre-compute in PostgreSQL | Simpler ops; aligns with 24h freshness |
| **Cold-Start** | Extended lookback (up to 90 days) | Simpler; no archetype baselines needed |
| **Tier Computation** | Percentile + dependency hard cap | Prevents unachievable SLOs |
| **Aggressive Tier Cap** | NOT capped | Shows achievable potential |
| **Batch Concurrency** | asyncio.gather with semaphore(20) | Balance throughput and DB pressure |

---

## Dependencies

### FR-1 Integration Points

FR-2 depends on these FR-1 components:
- `ServiceRepositoryInterface` → `get_by_service_id()`, `list_all()`
- `DependencyRepositoryInterface` → `traverse_graph()`
- `GraphTraversalService` → `get_subgraph()`
- `Service` entity (criticality, team, service_id)
- `ServiceDependency` entity (criticality, communication_mode)

### External Service Dependencies

| Service | Purpose | Criticality |
|---------|---------|-------------|
| **PostgreSQL** | Recommendation storage | Critical |
| **Redis** | Rate limiting (shared) | High |
| **Mock Prometheus** | Telemetry data (FR-2 only) | Critical |

---

## Files Created (Phase 1 + Phase 2)

### Domain Layer (Phase 1)
```
src/domain/entities/slo_recommendation.py          (~200 LOC)
src/domain/entities/sli_data.py                    (~80 LOC)
src/domain/services/availability_calculator.py     (~200 LOC)
src/domain/services/latency_calculator.py          (~120 LOC)
src/domain/services/composite_availability_service.py (~150 LOC)
src/domain/services/weighted_attribution_service.py (~100 LOC)
src/domain/repositories/slo_recommendation_repository.py (~80 LOC)
src/domain/repositories/telemetry_query_service.py (~40 LOC)
```

### Application Layer (Phase 2)
```
src/application/dtos/slo_recommendation_dto.py                     (~140 LOC)
src/application/use_cases/generate_slo_recommendation.py           (~580 LOC)
src/application/use_cases/get_slo_recommendation.py                (~30 LOC)
src/application/use_cases/batch_compute_recommendations.py         (~54 LOC)
```

### Tests
```
tests/unit/domain/entities/test_slo_recommendation.py              (~450 LOC)
tests/unit/domain/entities/test_sli_data.py                        (~300 LOC)
tests/unit/domain/services/test_availability_calculator.py         (~450 LOC)
tests/unit/domain/services/test_latency_calculator.py              (~350 LOC)
tests/unit/domain/services/test_composite_availability_service.py  (~400 LOC)
tests/unit/domain/services/test_weighted_attribution_service.py    (~350 LOC)
tests/unit/application/dtos/test_slo_recommendation_dto.py         (~380 LOC)
tests/unit/application/use_cases/test_generate_slo_recommendation.py (~530 LOC)
tests/unit/application/use_cases/test_get_slo_recommendation.py    (~320 LOC)
tests/unit/application/use_cases/test_batch_compute_recommendations.py (~400 LOC)
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BATCH_RECOMMENDATION_INTERVAL_HOURS` | `24` | Batch job frequency |
| `BATCH_RECOMMENDATION_CONCURRENCY` | `20` | Max concurrent computations |
| `DEFAULT_LOOKBACK_DAYS` | `30` | Standard lookback window |
| `EXTENDED_LOOKBACK_DAYS` | `90` | Cold-start extended window |
| `DATA_COMPLETENESS_THRESHOLD` | `0.90` | Threshold for extended lookback |
| `DEFAULT_DEPENDENCY_AVAILABILITY` | `0.999` | Assumed availability for deps |
| `RECOMMENDATION_EXPIRY_HOURS` | `24` | TTL for recommendations |

---

## Patterns & Lessons from FR-1

### Code Patterns
- Domain entities: `dataclass` with `__post_init__` validation
- DTOs: `dataclass` (not Pydantic)
- API schemas: Pydantic `BaseModel`
- Repository interfaces: `ABC` with `@abstractmethod`
- Use cases: Constructor injection, `async execute()` method

### Key Lessons Applied
1. Use `MagicMock` for sync services, `AsyncMock` for async repos
2. Fixture pattern: one fixture per dependency
3. `metadata_` attribute naming for SQLAlchemy reserved names
4. Parameterized CTEs: use `array()` + `bindparam()`, never `literal_column()` with f-strings
5. E2E test isolation: dispose DB pool per test function
6. HTTPException re-raise before generic `except Exception`
7. Correlation ID consistency in exception handlers

---

## Blockers & Risks

**Current Blockers:** None

**Risks:**
- Mock Prometheus unrealistic data → Mitigated by seed data design
- Batch job performance for 5000+ services → Semaphore limits concurrency
- JSONB schema drift → Pydantic validates on read, tests verify round-trip

---

## Next Session Handoff

**Current State:** Phase 3 - 100% COMPLETE ✅ → Phase 4 Ready to Start

**Commands to Verify:**
```bash
# Run all tests (414 total: 402 unit + 12 integration)
uv run python -m pytest tests/unit/domain/ tests/unit/application/ tests/unit/infrastructure/telemetry/ -v  # 402 tests
uv run python -m pytest tests/integration/infrastructure/database/test_slo_recommendation_repository.py -v  # 12 tests

# Verify migrations applied
export DATABASE_URL="postgresql+asyncpg://slo_user:slo_password_dev@localhost:5432/slo_engine"
alembic current  # Should show: 0493364c9562 (head)

# Test mock Prometheus client
uv run python -m pytest tests/unit/infrastructure/telemetry/ -v  # 24 tests
```

**Next Task:** Phase 4 - Task 4.1: Pydantic API Schemas
- Files:
  - `src/infrastructure/api/schemas/slo_recommendation_schema.py` (~150 LOC)
  - `tests/unit/infrastructure/api/schemas/test_slo_recommendation_schema.py` (~200 LOC)
- Create Pydantic schemas for API request/response
- Query param validation (sli_type enum, lookback_days 7-365, force_regenerate bool)
- Response schema matching TRD JSON format
- Nested models: Tier, Explanation, DependencyImpact, DataQuality

**Key Files:**
- DTOs: `src/application/dtos/slo_recommendation_dto.py` (convert to Pydantic)
- Entity: `src/domain/entities/slo_recommendation.py` (reference for structure)
- Reference: `src/infrastructure/api/schemas/dependency_schema.py` (FR-1 patterns)

**Important Notes:**
- Pydantic for API layer, dataclasses for application/domain
- Reuse RFC 7807 error schema from FR-1
- Use Field() for validation (lookback_days: int = Field(ge=7, le=365))
- CamelCase field names via alias for API (snake_case internally)

**Reference Files:**
- `dev/active/fr2-slo-recommendations/fr2-plan.md` - Full technical spec
- `dev/active/fr2-slo-recommendations/fr2-tasks.md` - Task checklist
- `dev/active/fr2-slo-recommendations/phase-logs/fr2-phase3.md` - Phase 3 log

---

**Document Version:** 1.6
**Last Updated:** 2026-02-15 (Session 8 - Phase 3: 100% COMPLETE ✅)
