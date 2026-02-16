# FR-2: SLO Recommendation Generation

**Feature Status:** 🟡 In Progress (30% overall, Phase 1 at 67%)
**Last Updated:** 2026-02-15 (Session 3)

---

## Quick Start

### Run Tests
```bash
source .venv/bin/activate
pytest tests/unit/domain/entities/ -v
pytest tests/unit/domain/services/ -v
```

**Expected:** 113 tests passing, 0 failures, 100% coverage

---

## Current State

### Completed ✅
- **Task 1.1:** SLO Recommendation Entity (32 tests, 100% coverage)
- **Task 1.2:** SLI Data Value Objects (24 tests, 100% coverage)
- **Task 1.3:** Availability Calculator Service (31 tests, 100% coverage)
- **Task 1.4:** Latency Calculator Service (26 tests, 98% coverage) ⭐ NEW
- **Task 1.7:** Repository Interfaces

### Next Up ⏭️
- **Task 1.5:** Composite Availability Service (NEXT)
- **Task 1.6:** Weighted Attribution Service

---

## File Structure

```
dev/active/fr2-slo-recommendations/
├── README.md                    # This file - quick handoff notes
├── fr2-plan.md                  # Technical requirements specification
├── fr2-context.md               # Key decisions, dependencies, current status
├── fr2-tasks.md                 # Task checklist with acceptance criteria
└── phase-logs/
    └── fr2-phase1.md           # Detailed Phase 1 session log
```

---

## Implementation Highlights

### Availability Calculator
- **Tier Strategy:** Percentile-based (p99.9, p99, p95)
- **Composite Bound Capping:** Conservative/Balanced capped, Aggressive NOT capped
- **Breach Probability:** Historical window counting
- **Error Budget:** Monthly minutes calculation
- **Confidence Intervals:** Bootstrap resampling (1000 iterations)

### Latency Calculator ⭐ NEW
- **Tier Strategy:** Percentile-based with noise margins
  - Conservative: p999 + noise margin
  - Balanced: p99 + noise margin
  - Aggressive: p95 (no margin - achievable potential)
- **Noise Margins:** 5% default, 10% for shared infrastructure
- **Breach Probability:** Historical percentile comparison to threshold
- **Confidence Intervals:** Bootstrap resampling (1000 iterations)

### Key Design Decisions
- Mock Prometheus for parallel development (real integration in FR-6)
- Weighted attribution with fixed MVP weights (SHAP in Phase 5)
- Pre-compute recommendations in PostgreSQL (no Redis)
- Extended lookback (up to 90 days) for cold-start

---

## Dependencies

### From FR-1 (Available)
- `Service` entity
- `ServiceDependency` entity
- `ServiceRepository` interface
- `DependencyRepository` interface
- `GraphTraversalService`

### New FR-2 Components
- `SloRecommendation` entity ✅
- `AvailabilitySliData` / `LatencySliData` ✅
- `AvailabilityCalculator` ✅
- `LatencyCalculator` ✅ ⭐ NEW
- Repository interfaces ✅

---

## Next Session Actions

1. **Implement Composite Availability Service** (Task 1.5) ⏭️ NEXT
   - Serial composition: R = R_self * ∏R_dep
   - Parallel composition: R = 1 - ∏(1 - R_replica)
   - Bottleneck identification

3. **Implement Weighted Attribution** (Task 1.6)
   - Fixed weights for availability/latency
   - Normalization to sum = 1.0

---

## Blockers

**None.** FR-2 is independent of FR-1 Phase 4 (API layer).

---

## Documentation

- **Plan:** [fr2-plan.md](./fr2-plan.md) - Full TRS with algorithms, schemas, migrations
- **Context:** [fr2-context.md](./fr2-context.md) - Decisions, dependencies, status
- **Tasks:** [fr2-tasks.md](./fr2-tasks.md) - Checklist with acceptance criteria
- **Phase 1 Log:** [phase-logs/fr2-phase1.md](./phase-logs/fr2-phase1.md) - Detailed session notes

---

## Test Commands

```bash
# Run all Phase 1 tests
pytest tests/unit/domain/ -v

# Run with coverage
pytest tests/unit/domain/ --cov=src/domain --cov-report=html

# Run specific test file
pytest tests/unit/domain/services/test_availability_calculator.py -v
```

---

**Last Session:** Session 3 (2026-02-15)
**Progress:** Phase 1 Domain Foundation - 67% complete
**Next Goal:** Complete remaining domain services (Tasks 1.5, 1.6)

---

## Handoff Notes (Session 3 → Session 4)

**Just Completed:**
- ✅ Task 1.4: Latency Calculator Service
- Files: `src/domain/services/latency_calculator.py` (57 lines, 98% coverage)
- Tests: `tests/unit/domain/services/test_latency_calculator.py` (26 tests, all passing)

**Current State:**
- 113 tests passing, 0 failures
- 100% coverage on all implemented FR-2 domain code
- Phase 1 is 67% complete (5/7 tasks done)

**Next Immediate Task:**
- **Task 1.5: Composite Availability Service**
- File to create: `src/domain/services/composite_availability_service.py`
- Test to create: `tests/unit/domain/services/test_composite_availability_service.py`
- Algorithm: Serial hard deps: `R = R_self * product(R_dep_i)`
- Algorithm: Parallel replicas: `R = 1 - product(1 - R_replica_j)`
- Must identify bottlenecks (lowest availability dependency)
- Soft dependencies excluded from calculation

**Verification Command:**
```bash
source .venv/bin/activate
pytest tests/unit/domain/ -v
# Expected: 113 tests passing, 0 failures, 100% coverage
```
