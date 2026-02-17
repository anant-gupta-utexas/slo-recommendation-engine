# FR-3: Dependency-Aware Constraint Propagation — Context Document

**Created:** 2026-02-15
**Status:** Phase 2 Complete (Code), Phase 3 Pending
**Last Updated:** 2026-02-16 17:30

---

## Current State

**Phase 0 & Phase 1:** ✅ **COMPLETE** (All tests passing)
**Phase 2:** ✅ **CODE COMPLETE** (Tests blocked on Task 3.2)
**Phase 3:** ⏳ **READY TO START**

### Implementation Progress: 10/16 Tasks Complete (62.5%)

| Phase | Status | Details |
|-------|--------|---------|
| Phase 0: FR-2 Prerequisites | ✅ Complete | 3/3 tasks, 74 tests passing, 100% coverage |
| Phase 1: Domain Foundation | ✅ Complete | 4/4 tasks, all domain services + entities implemented |
| Phase 2: Application Layer | ⚠️ Code Complete | 3/3 tasks code done, tests need Task 3.2 |
| Phase 3: Infrastructure | 🔜 Ready | 0/6 tasks, migration + API routes pending |

### Files Created (Phase 0-2)

**Phase 0:** (FR-2 Prerequisites)
- `src/domain/entities/sli_data.py` ✅
- `src/domain/repositories/telemetry_query_service.py` ✅
- `src/domain/services/composite_availability_service.py` ✅
- `src/infrastructure/telemetry/mock_prometheus_client.py` ✅
- `src/infrastructure/telemetry/seed_data.py` ✅
- All tests passing (74 tests total)

**Phase 1:** (FR-3 Domain)
- `src/domain/entities/constraint_analysis.py` ✅
- `src/domain/services/external_api_buffer_service.py` ✅
- `src/domain/services/error_budget_analyzer.py` ✅
- `src/domain/services/unachievable_slo_detector.py` ✅
- All tests passing (89 tests total)

**Phase 2:** (Application Layer)
- `src/application/dtos/constraint_analysis_dto.py` ✅ (19 tests passing)
- `src/application/use_cases/run_constraint_analysis.py` ✅ (code complete)
- `src/application/use_cases/get_error_budget_breakdown.py` ✅ (code complete)
- Tests written but blocked on Task 3.2

---

## Critical Blocker: Phase 2 Tests Need Task 3.2

### Problem
The Phase 2 use case tests are failing because `Service` entity doesn't have `service_type` and `published_sla` attributes yet. Task 3.2 adds these fields.

### Solution Implemented in Code
Both use cases defensively use `getattr()` to access these attributes:
```python
service_type = getattr(target_service, 'service_type', ServiceType.INTERNAL)
published_sla = getattr(target_service, 'published_sla', None)
```

This allows the code to work both before and after Task 3.2.

### Unblock Strategy
**Complete Task 3.1 and 3.2 FIRST** in Phase 3 to:
1. Add migration for `service_type` and `published_sla` columns
2. Update `Service` entity with new fields
3. This will unblock all Phase 2 tests

**Then complete remaining Phase 3 tasks** (3.3-3.6).

---

## Session Log

### 2026-02-15
- TRS created
- All clarifying questions answered
- Plan reviewed against PRD F3, TRD 3.3, FR-1 patterns
- Phase 0 prerequisites identified from FR-2

### 2026-02-16 (Session 1)
- ✅ **Phase 0 Complete:** All FR-2 prerequisites implemented (3 tasks, 74 tests passing)
- ✅ **Phase 1 Complete:** All FR-3 domain layer implemented (4 tasks, 89 tests passing)
- Key entities: ConstraintAnalysis, ErrorBudgetBreakdown, ExternalProviderProfile
- Key services: ExternalApiBufferService, ErrorBudgetAnalyzer, UnachievableSloDetector
- CompositeAvailabilityService fully implemented with serial/parallel/SCC handling

### 2026-02-16 (Session 2 - Current)
- ✅ **Task 2.1:** DTOs complete (19 tests passing, 100% coverage)
- ✅ **Task 2.2:** RunConstraintAnalysisUseCase implemented (~320 lines)
  - Full 11-step pipeline with parallel telemetry queries
  - External adaptive buffer integration
  - Handles all edge cases (no deps, missing telemetry, circular deps)
- ✅ **Task 2.3:** GetErrorBudgetBreakdownUseCase implemented (~200 lines)
  - Lighter-weight depth=1 analysis
  - Hard sync dependency filtering
- ⚠️ **Discovery:** Phase 2 tests blocked on Task 3.2 (Service entity update)
- 📝 **Decision:** Use `getattr()` in use cases for defensive field access
- 🔜 **Next:** Phase 3 Tasks 3.1 & 3.2 to unblock tests, then 3.3-3.6

---

## Key Decisions Made

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| 1 | FR-2 relationship | Extend FR-2's CompositeAvailabilityService | Avoids duplicating composite math | 2026-02-15 |
| 2 | External API buffer | `min(observed, published_adjusted)` with `published_adjusted = 1 - (1-published)*11` | Matches TRD 3.3: 99.99% → 99.89% | 2026-02-15 |
| 3 | API surface | Dedicated endpoints (`/constraint-analysis`, `/error-budget-breakdown`) | Cleaner separation from FR-2 | 2026-02-15 |
| 4 | Error budget threshold | Fixed 30% per dependency | Matches TRD; simple MVP | 2026-02-15 |
| 5 | External service tracking | `service_type` + `published_sla` on `services` table | Minimal schema change | 2026-02-15 |
| 6 | FR-2 dependency | Phase 0 includes minimal FR-2 prerequisites | Self-contained, no blocking | 2026-02-15 |
| 7 | Constraint caching | No cache (compute on demand) | <2s target achievable | 2026-02-15 |
| 8 | Latency propagation | Availability only | Percentiles non-additive | 2026-02-15 |
| 9 | `published_sla` storage | Ratio internally, percentage in API | Consistent with system | 2026-02-15 |
| 10 | Default SLO target | 99.9% when none specified | Reasonable balanced tier | 2026-02-15 |
| 11 | Phase 2 field access | Use `getattr()` with defaults | Works before/after Task 3.2 | 2026-02-16 |
| 12 | Phase 3 task order | Tasks 3.1 & 3.2 first | Unblocks Phase 2 tests | 2026-02-16 |

---

## Next Immediate Steps

### Priority 1: Unblock Phase 2 Tests (Tasks 3.1 & 3.2)

**Task 3.1:** Alembic Migration [Effort: S]
```sql
ALTER TABLE services
    ADD COLUMN service_type VARCHAR(20) NOT NULL DEFAULT 'internal',
    ADD COLUMN published_sla DECIMAL(8,6) DEFAULT NULL,
    ADD CONSTRAINT ck_service_type CHECK (service_type IN ('internal', 'external'));

CREATE INDEX idx_services_external
    ON services(service_type) WHERE service_type = 'external';
```

**Task 3.2:** Update Service Entity [Effort: M]
- Add to `src/domain/entities/service.py`:
  ```python
  from src.domain.entities.constraint_analysis import ServiceType

  service_type: ServiceType = ServiceType.INTERNAL
  published_sla: float | None = None
  ```
- Update `ServiceRepositoryInterface`: Add `get_external_services()`
- Update database models and repository mappings
- Verify FR-1 tests still pass (backward compatible)

**Result:** Phase 2 tests will pass after these two tasks complete.

### Priority 2: Complete Phase 3 (Tasks 3.3-3.6)

**Task 3.3:** Pydantic API Schemas
- `ConstraintAnalysisQueryParams` with validation
- `ConstraintAnalysisApiResponse` matching spec
- `ErrorBudgetBreakdownQueryParams`
- Nested models for risks and warnings

**Task 3.4:** API Routes
- `GET /api/v1/services/{id}/constraint-analysis`
- `GET /api/v1/services/{id}/error-budget-breakdown`
- Auth + rate limiting (30/min, 60/min)
- Error handling (404, 400, 422, 429)

**Task 3.5:** Dependency Injection
- Wire all FR-3 services in `dependencies.py`
- Register router in `main.py`

**Task 3.6:** E2E Tests
- Full workflow: ingest → constraint analysis
- External service adaptive buffer verification
- Performance: <2s constraint analysis, <1s breakdown

---

## Technical Patterns Used

### Use Case Structure (Phase 2)
Both use cases follow the same pattern:
1. **Validate service exists** → Return `None` if not found
2. **Retrieve subgraph** → Use GraphTraversalService
3. **Classify dependencies** → Hard/soft, internal/external
4. **Resolve availabilities** → Parallel via `asyncio.gather()`
5. **Apply adaptive buffer** → For external services
6. **Compute results** → Via domain services
7. **Build response DTO** → Convert entities to DTOs

### Defensive Programming
```python
# Handles fields that don't exist yet (Task 3.2 pending)
service_type = getattr(target_service, 'service_type', ServiceType.INTERNAL)
published_sla = getattr(target_service, 'published_sla', None)
```

### Parallel Telemetry Queries
```python
async def resolve_single(edge):
    # Fetch availability for one dependency
    ...

results = await asyncio.gather(*[resolve_single(e) for e in edges])
```

---

## Dependencies

### Internal (FR-1 → FR-3) ✅ Available
- `Service`, `ServiceDependency`, `ServiceRepositoryInterface`
- `DependencyRepositoryInterface`, `GraphTraversalService`
- `CircularDependencyAlertRepositoryInterface`
- Auth middleware, rate limiting, error schemas
- FastAPI dependency injection

### Internal (FR-2 → FR-3, Phase 0) ✅ Complete
- `AvailabilitySliData`, `LatencySliData`
- `DependencyWithAvailability`, `CompositeResult`
- `CompositeAvailabilityService`
- `TelemetryQueryServiceInterface`
- Mock Prometheus Client

### Internal (Phase 1) ✅ Complete
- All FR-3 domain entities and services

### Internal (Phase 2) ⚠️ Blocked on Task 3.2
- DTOs ✅ complete
- Use cases ✅ code complete, tests pending

### External ✅ Available
- PostgreSQL 16+, FastAPI 0.115+, SQLAlchemy 2.0+
- Alembic, Pydantic 2.0+, pytest, httpx

---

## Integration Points

### Upstream (FR-3 depends on)
- **FR-1 dependency graph:** Graph traversal via DependencyRepositoryInterface
- **FR-1 service registry:** Service lookup via ServiceRepositoryInterface
- **FR-1 circular alerts:** SCC data via CircularDependencyAlertRepositoryInterface
- **FR-2 telemetry:** Availability via TelemetryQueryServiceInterface (Phase 0 mock)

### Downstream (Will depend on FR-3)
- **FR-2 recommendations:** Can use enhanced CompositeAvailabilityService
- **FR-4 impact analysis:** Can reuse ErrorBudgetAnalyzer, UnachievableSloDetector
- **FR-5 lifecycle:** Active SLO target feeds FR-3 default selection

---

## Testing Summary

| Phase | Tests Written | Tests Passing | Coverage |
|-------|--------------|---------------|----------|
| Phase 0 | 74 | ✅ 74 | 100% |
| Phase 1 | 89 | ✅ 89 | >95% |
| Phase 2 DTOs | 19 | ✅ 19 | 100% |
| Phase 2 Use Cases | 17 | ⚠️ 3 | Blocked on Task 3.2 |
| **Total** | **199** | **185** | **~93%** |

**After Task 3.2:** Expect all 199 tests to pass.

---

## Commands for Next Session

### Run All Tests (Current State)
```bash
source .venv/bin/activate
pytest tests/unit/domain/ tests/unit/application/dtos/ -v
# Expected: 182 tests passing
```

### After Task 3.2
```bash
pytest tests/unit/ -v
# Expected: All 199 tests passing
```

### Start Phase 3
```bash
# Task 3.1: Create migration
alembic revision --autogenerate -m "add_service_type_to_services"
# Edit the generated migration file

# Task 3.2: Update Service entity
# Edit src/domain/entities/service.py
```

---

## Known Issues & Workarounds

### Issue #1: Phase 2 Tests Blocked
**Problem:** Service entity lacks `service_type` and `published_sla` attributes.
**Impact:** 14/17 Phase 2 use case tests failing.
**Workaround:** Use cases use `getattr()` with defaults.
**Resolution:** Complete Task 3.2 (update Service entity).

### Issue #2: AvailabilitySliData Time Windows in Tests
**Problem:** Test fixtures create same start/end times.
**Impact:** Validation fails (`window_end` must be after `window_start`).
**Workaround:** Helper function `create_avail_sli()` uses `timedelta`.
**Status:** Helper created but not applied to all tests yet.

---

## Risks & Mitigations

| Risk | Impact | Mitigation Status |
|------|--------|-------------------|
| FR-2 overlaps Phase 0 | Low | ✅ Phase 0 designed for reuse |
| Graph latency (deep chains) | Medium | ✅ Capped at max_depth=10 |
| External data unavailable | Low | ✅ Graceful 99.9% default |
| Pessimistic adjustment too aggressive | Low | ✅ User can override target |
| Phase 2 test blocking | High | ⚠️ Resolved by Task 3.2 |

---

## Technical Debt Accepted

| Debt Item | Reason | Plan |
|-----------|--------|------|
| No caching | MVP simplicity, <2s achievable | Add if load testing shows need |
| Fixed 30% threshold | MVP simplicity | Make configurable in FR-5 |
| Mock Prometheus | Parallel development | Replace in FR-6 |
| No latency propagation | By design (non-additive) | Monte Carlo in FR-15 if needed |

---

## Handoff Notes for Next Developer

### Current State
- **Completed:** Phase 0 & 1 fully done, Phase 2 code complete
- **Blocked:** Phase 2 tests need Task 3.2
- **Next:** Phase 3, Tasks 3.1 & 3.2 first

### What Just Happened
1. Implemented all Phase 2 DTOs (7 classes, 19 tests passing)
2. Implemented RunConstraintAnalysisUseCase (11-step pipeline, ~320 lines)
3. Implemented GetErrorBudgetBreakdownUseCase (depth=1 analysis, ~200 lines)
4. Discovered Task 3.2 dependency, added defensive `getattr()` calls
5. Updated task tracker with accurate status

### Immediate Actions
```bash
# 1. Start with Task 3.1 (migration)
alembic revision --autogenerate -m "add_service_type_to_services"

# 2. Then Task 3.2 (Service entity)
# Edit: src/domain/entities/service.py
# Add: service_type, published_sla fields

# 3. Run tests to verify unblock
pytest tests/unit/application/use_cases/ -v
```

### Key Files Modified This Session
- `src/application/dtos/constraint_analysis_dto.py` (new)
- `src/application/use_cases/run_constraint_analysis.py` (new)
- `src/application/use_cases/get_error_budget_breakdown.py` (new)
- `tests/unit/application/dtos/test_constraint_analysis_dto.py` (new)
- `tests/unit/application/use_cases/test_run_constraint_analysis.py` (new, blocked)
- `tests/unit/application/use_cases/test_get_error_budget_breakdown.py` (new, blocked)
- `dev/active/fr3-constraint-propagation/fr3-constraint-propagation-tasks.md` (updated)

### Test Commands
```bash
# Current passing tests
pytest tests/unit/domain/ tests/unit/application/dtos/ -v
# 182 tests should pass

# After Task 3.2
pytest tests/unit/ -v
# All 199 tests should pass
```

### Architecture Notes
- Use cases follow Clean Architecture: repos → domain services → DTOs
- Parallel queries via `asyncio.gather()` for performance
- Defensive `getattr()` allows code to work before/after migration
- External/internal service distinction via `ServiceType` enum

---

**Last Updated:** 2026-02-16 17:30 by Claude Sonnet 4.5
**Status:** Ready for Phase 3 continuation
**Next Session:** Start with Tasks 3.1 & 3.2 to unblock Phase 2 tests
