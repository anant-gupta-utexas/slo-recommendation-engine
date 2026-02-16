# FR-2: SLO Recommendation Generation

**Feature Status:** ✅ Phase 2 Complete (62% overall)
**Last Updated:** 2026-02-15 (Session 6)

---

## Quick Start

### Run Tests
```bash
source .venv/bin/activate
pytest tests/unit/domain/ -v        # Phase 1: 167 tests
pytest tests/unit/application/ -v   # Phase 2: 63 tests (FR-2 only)
```

**Expected:** 230 total tests passing (167 Phase 1 + 63 Phase 2), 0 failures, 97-100% coverage

---

## Current State

### Phase 1: Domain Foundation ✅ **COMPLETE**
- **Task 1.1:** SLO Recommendation Entity (32 tests, 100% coverage)
- **Task 1.2:** SLI Data Value Objects (24 tests, 100% coverage)
- **Task 1.3:** Availability Calculator Service (31 tests, 100% coverage)
- **Task 1.4:** Latency Calculator Service (26 tests, 98% coverage)
- **Task 1.5:** Composite Availability Service (26 tests, 97% coverage)
- **Task 1.6:** Weighted Attribution Service (28 tests, 100% coverage)
- **Task 1.7:** Repository Interfaces

### Phase 2: Application Layer ✅ **COMPLETE**
- **Task 2.1:** SLO Recommendation DTOs (25 tests, 100% coverage) ✅
- **Task 2.2:** GenerateSloRecommendation Use Case (20 tests, 98% coverage) ✅
- **Task 2.3:** GetSloRecommendation Use Case (7 tests, 97% coverage) ✅
- **Task 2.4:** BatchComputeRecommendations Use Case (11 tests, 100% coverage) ✅

### Phase 3: Infrastructure — Persistence & Telemetry ⏭️ **NEXT**
- **Task 3.1:** SQLAlchemy Models (NEXT)
- **Task 3.2:** Alembic Migrations
- **Task 3.3:** Repository Implementation
- **Task 3.4:** Mock Prometheus Client

### Phase 4: Infrastructure — API & Tasks ⬜ **NOT STARTED**

---

## File Structure

```
dev/active/fr2-slo-recommendations/
├── README.md                    # This file - quick handoff notes
├── fr2-plan.md                  # Technical requirements specification
├── fr2-context.md               # Key decisions, dependencies, current status
├── fr2-tasks.md                 # Task checklist with acceptance criteria
└── phase-logs/
    ├── fr2-phase1.md           # Phase 1 session log
    └── fr2-phase2.md           # Phase 2 session log
```

---

## Implementation Highlights

### Phase 1: Domain Foundation
- Three-tier availability/latency recommendations
- Bootstrap confidence intervals (1000 resamples)
- Composite bound capping (Conservative/Balanced capped, Aggressive NOT capped)
- Breach probability estimation
- Serial/parallel dependency composition
- Weighted feature attribution

### Phase 2: Application Layer
- Full 12-step recommendation generation pipeline
- Cold-start detection (30d → 90d when completeness < 90%)
- Dependency traversal + composite bounds
- Batch processing with concurrency control (semaphore 20)
- Robust error handling and detailed metrics
- Force regeneration capability

---

## Dependencies

### From FR-1 (Available)
- `Service` entity
- `ServiceDependency` entity
- `ServiceRepositoryInterface` → `get_by_service_id()`, `list_all()`
- `DependencyRepositoryInterface` → `traverse_graph()`
- `GraphTraversalService` → `get_subgraph()`

### FR-2 Components (Phase 1 + 2 Complete)
**Domain Layer:**
- `SloRecommendation` entity ✅
- `AvailabilitySliData` / `LatencySliData` ✅
- `AvailabilityCalculator` ✅
- `LatencyCalculator` ✅
- `CompositeAvailabilityService` ✅
- `WeightedAttributionService` ✅
- Repository interfaces ✅

**Application Layer:**
- SLO Recommendation DTOs (11 DTOs) ✅
- `GenerateSloRecommendationUseCase` ✅
- `GetSloRecommendationUseCase` ✅
- `BatchComputeRecommendationsUseCase` ✅

---

## Next Session Actions

1. **Start Phase 3: Infrastructure — Persistence** ⏭️ NEXT
   - Task 3.1: Create SQLAlchemy models
     - `src/infrastructure/database/models/slo_recommendation.py`
     - `src/infrastructure/database/models/sli_aggregate.py`
   - Follow FR-1 patterns: `Base`, `Mapped[]`, JSONB for complex types

---

## Blockers

**None.** FR-2 Phase 3 ready to proceed.

---

## Documentation

- **Plan:** [fr2-plan.md](./fr2-plan.md) - Full TRS with algorithms, schemas, migrations
- **Context:** [fr2-context.md](./fr2-context.md) - Decisions, dependencies, current status
- **Tasks:** [fr2-tasks.md](./fr2-tasks.md) - Checklist with acceptance criteria
- **Phase Logs:**
  - [phase-logs/fr2-phase1.md](./phase-logs/fr2-phase1.md) - Phase 1 session notes
  - [phase-logs/fr2-phase2.md](./phase-logs/fr2-phase2.md) - Phase 2 session notes

---

## Test Commands

```bash
# Run all FR-2 tests (Phase 1 + 2)
pytest tests/unit/domain/ tests/unit/application/ -v

# Run with coverage
pytest tests/unit/domain/ tests/unit/application/ --cov=src/domain --cov=src/application --cov-report=html

# Run Phase 2 tests only
pytest tests/unit/application/use_cases/test_generate_slo_recommendation.py -v
pytest tests/unit/application/use_cases/test_get_slo_recommendation.py -v
pytest tests/unit/application/use_cases/test_batch_compute_recommendations.py -v
```

---

**Last Session:** Session 6 (2026-02-15)
**Progress:** Phase 2 Application Layer - ✅ **100% COMPLETE**
**Next Goal:** Start Phase 3 (Infrastructure - SQLAlchemy models + migrations)

---

## Handoff Notes (Session 6 → Session 7)

**Just Completed (Session 6):**
- ✅ Task 2.3: GetSloRecommendation Use Case
  - Files: `src/application/use_cases/get_slo_recommendation.py` (30 lines, 97% coverage)
  - Tests: `tests/unit/application/use_cases/test_get_slo_recommendation.py` (7 tests)
  - Features: Retrieval + force_regenerate delegation, sli_type filtering

- ✅ Task 2.4: BatchComputeRecommendations Use Case
  - Files: `src/application/use_cases/batch_compute_recommendations.py` (54 lines, 100% coverage)
  - Tests: `tests/unit/application/use_cases/test_batch_compute_recommendations.py` (11 tests)
  - Features: Batch processing, semaphore(20), error collection, detailed metrics

**Current State:**
- ✅ Phase 1 Complete: 167 tests passing
- ✅ Phase 2 Complete: 63 tests passing
- ✅ Total: 230 tests passing, 0 failures
- Coverage: 62% overall, 97-100% on FR-2 code

**Next Immediate Task:**
- **Task 3.1: SQLAlchemy Models** (Phase 3 start)
- Files to create:
  - `src/infrastructure/database/models/slo_recommendation.py`
  - `src/infrastructure/database/models/sli_aggregate.py`
- Follow FR-1 model patterns:
  - Extend `Base` from `src/infrastructure/database/models.py`
  - Use `Mapped[]` type annotations
  - JSONB columns for complex types (tiers, explanation, data_quality)
  - Check constraints for enums
  - Indexes for common queries

**Reference:**
- See `fr2-plan.md` section 3.5 for schema specifications
- Follow FR-1 model patterns in `src/infrastructure/database/models.py`
- Check `alembic/versions/` for migration patterns

**Verification Command:**
```bash
source .venv/bin/activate
pytest tests/unit/ -v
# Expected: 230 tests passing (167 Phase 1 + 63 Phase 2), 0 failures
```

**Technical Notes:**
- GetSloRecommendation falls back to generation in Phase 2 MVP
- Phase 3 will add actual repository retrieval
- BatchComputeRecommendations uses `list_all(skip=0, limit=10000)` to fetch all services
- Semaphore limits to 20 concurrent generations to avoid DB pressure
