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
- **Total: 230 tests passing** (167 Phase 1 + 63 Phase 2)
- Phase 2: 63 tests (25 DTOs + 20 Generate + 7 Get + 11 Batch)
- 0 failures
- Coverage: 62% overall, 97-100% on Phase 2 code

### Phase 3: Infrastructure (DB + Telemetry) ⬜ **NOT STARTED**
**Next Steps:**
- Task 3.1: SQLAlchemy models (`SloRecommendationModel`, `SliAggregateModel`)
- Task 3.2: Alembic migrations (004, 005)
- Task 3.3: Repository implementation with domain↔model mapping
- Task 3.4: Mock Prometheus client with seed data

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

**Current State:** Phase 2 COMPLETE ✅

**Commands to Verify:**
```bash
source .venv/bin/activate
pytest tests/unit/application/ -v  # Should show 116 tests passing
pytest tests/unit/domain/ -v       # Should show 167 tests passing
```

**Next Task:** Phase 3 - Task 3.1: SQLAlchemy Models
- Create `src/infrastructure/database/models/slo_recommendation.py`
- Create `src/infrastructure/database/models/sli_aggregate.py`
- Follow FR-1 patterns: `Base`, `Mapped[]`, JSONB for complex types

**Reference Files:**
- `dev/active/fr2-slo-recommendations/fr2-plan.md` - Full technical spec
- `dev/active/fr2-slo-recommendations/fr2-tasks.md` - Task checklist
- `dev/active/fr2-slo-recommendations/phase-logs/fr2-phase2.md` - Phase 2 log

---

**Document Version:** 1.3
**Last Updated:** 2026-02-15 (Session 6 - Phase 2 COMPLETE)
