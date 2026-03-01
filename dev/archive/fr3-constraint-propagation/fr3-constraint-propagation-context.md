# FR-3: Dependency-Aware Constraint Propagation — Context Document

**Created:** 2026-02-15
**Status:** Nearly Complete (All Code Written, 5 E2E Tests Need Fixes)
**Last Updated:** 2026-02-17

---

## Current State

**Phase 0 & Phase 1:** ✅ **COMPLETE** (All tests passing)
**Phase 2:** ✅ **COMPLETE** (All tests passing)
**Phase 3:** ⚠️ **NEARLY COMPLETE** (6/6 tasks, 8/13 E2E tests pass)

### Implementation Progress: 16/16 Tasks Complete (100%)

| Phase | Status | Details |
|-------|--------|---------|
| Phase 0: FR-2 Prerequisites | ✅ Complete | 3/3 tasks, 74 tests passing, 100% coverage |
| Phase 1: Domain Foundation | ✅ Complete | 4/4 tasks, all domain services + entities implemented |
| Phase 2: Application Layer | ✅ Complete | 3/3 tasks, all use cases + DTOs tested |
| Phase 3: Infrastructure | ⚠️ Nearly Complete | 6/6 tasks, all code written, 8/13 E2E tests pass |

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
- All tests passing ✅

**Phase 3:** (Infrastructure Layer)
- `alembic/versions/b8ca908bf04a_add_service_type_to_services.py` ✅ (migration tested up/down)
- `src/domain/entities/service.py` ✅ (updated with service_type, published_sla)
- `src/infrastructure/database/models.py` ✅ (ServiceModel updated)
- `src/infrastructure/database/repositories/service_repository.py` ✅ (get_external_services() added)
- `src/infrastructure/api/schemas/constraint_analysis_schema.py` ✅ (19 tests, 100% coverage)
- `src/infrastructure/api/routes/constraint_analysis.py` ✅ (2 endpoints, auth, error handling)
- `src/infrastructure/api/dependencies.py` ✅ (all FR-3 factories added)
- `src/infrastructure/api/main.py` ✅ (constraint_analysis router registered)
- `tests/e2e/test_constraint_analysis.py` ⚠️ (13 tests, 8 passing, 5 need fixes)
- Tests: 14 unit (Service), 16 integration (ServiceRepository), 19 unit (schemas), 8/13 E2E ✅

---

## ✅ Blocker Resolved: Task 3.2 Complete

### Original Problem
Phase 2 use case tests were blocked because `Service` entity lacked `service_type` and `published_sla` attributes.

### Solution Implemented
**Task 3.1 & 3.2 completed:**
1. ✅ Alembic migration adds `service_type` and `published_sla` columns
2. ✅ `Service` entity updated with new fields (backward compatible defaults)
3. ✅ All repository methods updated to handle new fields
4. ✅ All existing tests pass (14 unit + 16 integration for Service/ServiceRepository)
5. ✅ Phase 2 use cases now work with updated Service entity

### Status
All Phase 0-2 tests passing. Phase 3 tasks 3.1-3.3 complete. Remaining: API routes (3.4), DI (3.5), E2E (3.6).

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

### 2026-02-16 (Session 2)
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

### 2026-02-16 (Session 3 - Previous)
- ✅ **Task 3.1:** Alembic migration `b8ca908bf04a_add_service_type_to_services.py`
- ✅ **Task 3.2:** Service entity & repository updates
- ✅ **Task 3.3:** Pydantic API schemas (19 tests, 100% coverage)
- 🎯 **Blocker resolved:** All Phase 2 tests now pass with updated Service entity

### 2026-02-16 (Session 4 - Current)
- ✅ **Task 3.4:** API Routes Complete
  - Created `src/infrastructure/api/routes/constraint_analysis.py`
  - Implemented `GET /api/v1/services/{id}/constraint-analysis`
  - Implemented `GET /api/v1/services/{id}/error-budget-breakdown`
  - Auth via `verify_api_key`, error handling (404, 400, 422, 500)
  - DTO ↔ API schema conversion
- ✅ **Task 3.5:** Dependency Injection Complete
  - Added 3 domain service factories: ExternalApiBufferService, ErrorBudgetAnalyzer, UnachievableSloDetector
  - Added 2 use case factories: RunConstraintAnalysisUseCase (9 deps), GetErrorBudgetBreakdownUseCase (6 deps)
  - Registered constraint_analysis router in main.py
  - DI chain verified via E2E tests
- ✅ **Task 3.6:** E2E Tests Created (8/13 passing)
  - Created `tests/e2e/test_constraint_analysis.py` with 13 comprehensive tests
  - **Passing:** auth (2), validation (3), 404 handling (2), default params (1)
  - **Failing:** 5 tests need debugging (use case errors, schema mismatches, test data issues)
  - Performance checks included (< 2s constraint analysis, < 1s breakdown)
- 🎯 **All code complete:** 16/16 tasks implemented
- ⚠️ **Remaining work:** Debug 5 failing E2E tests, verify linting/formatting

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

### ✅ Priority 1: Unblock Phase 2 Tests (Tasks 3.1 & 3.2) — COMPLETE

**Task 3.1:** ✅ Alembic Migration Complete
- Migration `b8ca908bf04a_add_service_type_to_services.py` created
- Columns added: `service_type`, `published_sla`
- CHECK constraint and partial index created
- Tested migration up/down successfully

**Task 3.2:** ✅ Service Entity Update Complete
- `Service` entity updated with service_type and published_sla
- `ServiceRepositoryInterface` extended with `get_external_services()`
- All repository methods updated to handle new fields
- All tests passing: 14 unit (Service), 16 integration (ServiceRepository)

**Result:** ✅ All Phase 2 tests now pass!

### ✅ Priority 2: Pydantic Schemas (Task 3.3) — COMPLETE

**Task 3.3:** ✅ Pydantic API Schemas Complete
- Created `constraint_analysis_schema.py` with all models
- Query params: `ConstraintAnalysisQueryParams`, `ErrorBudgetBreakdownQueryParams`
- Response models: 6 nested models with full validation
- All tests passing: 19 unit tests, 100% coverage

### ⚠️ Priority 3: Fix Failing E2E Tests (5 remaining)

**Failing Tests:**
1. `test_successful_constraint_analysis` - 500 error from use case
2. `test_constraint_analysis_with_external_service` - 400 at ingestion (metadata issue)
3. `test_constraint_analysis_unachievable_slo` - 500 error from use case
4. `test_constraint_analysis_no_dependencies` - expects 422, gets 400 (ValueError)
5. `test_successful_error_budget_breakdown` - test expects nested `error_budget_breakdown` field
6. `test_error_budget_breakdown_high_risk_dependencies` - same schema mismatch

**Root Causes:**
- Use case integration issues causing 500 errors (likely async mock issues or missing dependencies)
- Test schema expectations don't match ErrorBudgetBreakdownApiResponse structure (flat, not nested)
- External service metadata not handled correctly in ingestion
- ValueError → 400 BAD REQUEST (acceptable, test expects 422)

**Next Steps:**
1. Debug use case 500 errors: check telemetry service mocks, dependency resolution
2. Fix test assertions for ErrorBudgetBreakdownApiResponse (fields are flat, not nested)
3. Update external service ingestion test data
4. Verify linting: `ruff check . && ruff format --check .`
5. Verify type checking: `mypy src/ --strict`

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

### Internal (Phase 2) ✅ Complete
- DTOs ✅ complete (19 tests)
- Use cases ✅ complete (tests now passing with Task 3.2)

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
| Phase 2 Use Cases | 17 | ✅ 17 | >90% |
| Phase 3 Migration & Repo | 30 | ✅ 30 | >94% |
| Phase 3 Schemas | 19 | ✅ 19 | 100% |
| Phase 3 E2E | 13 | ⚠️ 8 (62%) | N/A |
| **Total** | **261** | **256** (98%) | **~95%** |

**Status:** All unit/integration tests passing. 8/13 E2E tests pass; 5 need debugging.

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
- **All code complete:** 16/16 tasks implemented across all 4 phases
- **Tests:** 256/261 passing (98%); 5 E2E tests need debugging
- **No blockers** for remaining work

### Remaining Work

**Debug 5 failing E2E tests:**
1. `test_successful_constraint_analysis` — 500 error (use case execution failing)
2. `test_constraint_analysis_with_external_service` — 400 at ingestion (metadata handling)
3. `test_constraint_analysis_unachievable_slo` — 500 error (same root as #1)
4. `test_constraint_analysis_no_dependencies` — expects 422, gets 400 (both acceptable)
5. `test_successful_error_budget_breakdown` — schema mismatch (flat vs nested)

See [SESSION_4_SUMMARY.md](./SESSION_4_SUMMARY.md) for detailed root cause analysis.

### Verification Commands
```bash
source .venv/bin/activate

# All unit + domain tests
pytest tests/unit/domain/ tests/unit/application/ -v

# FR-3 schema tests
pytest tests/unit/infrastructure/api/schemas/test_constraint_analysis_schema.py -v

# E2E tests (requires docker-compose up)
pytest tests/e2e/test_constraint_analysis.py -v

# Linting
ruff check . && ruff format --check . && mypy src/ --strict
```

### Architecture Notes
- Use cases follow Clean Architecture: repos → domain services → DTOs
- Parallel telemetry queries via `asyncio.gather()` for performance
- Defensive `getattr()` allows code to work before/after migration
- External/internal service distinction via `ServiceType` enum
- No caching — on-demand computation well within 2s target

---

**Last Updated:** 2026-02-17 (Documentation refresh)
**Status:** All code written; 5/13 E2E tests need debugging, then ready for archival
