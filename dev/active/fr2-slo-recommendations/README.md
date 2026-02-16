# FR-2: SLO Recommendation Generation

**Feature Status:** 🟢 Phase 1 Complete (46% overall, Phase 1 at 100%)
**Last Updated:** 2026-02-15 (Session 4)

---

## Quick Start

### Run Tests
```bash
source .venv/bin/activate
pytest tests/unit/domain/entities/ -v
pytest tests/unit/domain/services/ -v
```

**Expected:** 167 tests passing, 0 failures, 97-100% coverage

---

## Current State

### Phase 1: Domain Foundation ✅ **COMPLETE**
- **Task 1.1:** SLO Recommendation Entity (32 tests, 100% coverage)
- **Task 1.2:** SLI Data Value Objects (24 tests, 100% coverage)
- **Task 1.3:** Availability Calculator Service (31 tests, 100% coverage)
- **Task 1.4:** Latency Calculator Service (26 tests, 98% coverage)
- **Task 1.5:** Composite Availability Service (26 tests, 97% coverage) ⭐ NEW
- **Task 1.6:** Weighted Attribution Service (28 tests, 100% coverage) ⭐ NEW
- **Task 1.7:** Repository Interfaces

### Phase 2: Application Layer ⏭️ **NEXT**
- **Task 2.1:** SLO Recommendation DTOs (NEXT)
- **Task 2.2:** GenerateSloRecommendation Use Case
- **Task 2.3:** GetSloRecommendation Use Case
- **Task 2.4:** BatchComputeRecommendations Use Case

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

### Latency Calculator
- **Tier Strategy:** Percentile-based with noise margins
  - Conservative: p999 + noise margin
  - Balanced: p99 + noise margin
  - Aggressive: p95 (no margin - achievable potential)
- **Noise Margins:** 5% default, 10% for shared infrastructure
- **Breach Probability:** Historical percentile comparison to threshold
- **Confidence Intervals:** Bootstrap resampling (1000 iterations)

### Composite Availability Service ⭐ NEW
- **Serial Dependencies:** R = R_self × ∏R_dep_i
- **Parallel Redundancy:** R = 1 - ∏(1 - R_replica_j)
- **Bottleneck Identification:** Weakest link in dependency chain
- **Soft Dependencies:** Excluded from composite bound

### Weighted Attribution Service ⭐ NEW
- **Availability Weights:** historical (0.40), dependency risk (0.30), external (0.15), deployment (0.15)
- **Latency Weights:** p99 (0.50), call chain (0.22), noisy neighbor (0.15), seasonality (0.13)
- **Normalization:** Contributions sum to 1.0
- **Sorting:** By absolute contribution descending

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

### New FR-2 Components (Phase 1 Complete)
- `SloRecommendation` entity ✅
- `AvailabilitySliData` / `LatencySliData` ✅
- `AvailabilityCalculator` ✅
- `LatencyCalculator` ✅
- `CompositeAvailabilityService` ✅ ⭐ NEW
- `WeightedAttributionService` ✅ ⭐ NEW
- Repository interfaces ✅

---

## Next Session Actions

1. **Start Phase 2: Application Layer** ⏭️ NEXT
   - Task 2.1: Create SLO Recommendation DTOs (11 dataclasses)
   - Task 2.2: Implement GenerateSloRecommendation Use Case
   - Task 2.3: Implement GetSloRecommendation Use Case
   - Task 2.4: Implement BatchComputeRecommendations Use Case

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

**Last Session:** Session 4 (2026-02-15)
**Progress:** Phase 1 Domain Foundation - ✅ **100% COMPLETE**
**Next Goal:** Start Phase 2 (Application Layer - DTOs and Use Cases)

---

## Handoff Notes (Session 4 → Session 5)

**Just Completed (Session 4):**
- ✅ Task 1.5: Composite Availability Service
  - Files: `src/domain/services/composite_availability_service.py` (73 lines, 97% coverage)
  - Tests: `tests/unit/domain/services/test_composite_availability_service.py` (26 tests)
  - Features: Serial/parallel composition, bottleneck identification, soft dep exclusion

- ✅ Task 1.6: Weighted Attribution Service
  - Files: `src/domain/services/weighted_attribution_service.py` (55 lines, 100% coverage)
  - Tests: `tests/unit/domain/services/test_weighted_attribution_service.py` (28 tests)
  - Features: Heuristic weights, normalization, sorting by contribution

**Current State:**
- ✅ Phase 1 Complete: 167 tests passing, 0 failures
- 97-100% coverage on all FR-2 domain layer components
- All 6 domain tasks complete + repository interfaces

**Next Immediate Task:**
- **Task 2.1: SLO Recommendation DTOs** (Phase 2 start)
- File to create: `src/application/dtos/slo_recommendation_dto.py`
- Test to create: `tests/unit/application/dtos/test_slo_recommendation_dto.py`
- Create 11 DTO dataclasses:
  - Request DTOs: `GenerateSloRequest`, `GetSloRequest`, `BatchComputeRequest`
  - Response DTOs: `SloRecommendationResponse`, `TierResponse`, `ExplanationResponse`, `DependencyImpactResponse`, `DataQualityResponse`, `FeatureAttributionResponse`
  - Result DTOs: `BatchComputeResult`, `FailureDetail`

**Reference:**
- See `fr2-plan.md` section 3.4 for DTO specifications
- Follow FR-1 DTO patterns in `src/application/dtos/dependency_graph_dto.py`

**Verification Command:**
```bash
source .venv/bin/activate
pytest tests/unit/domain/ -v
# Expected: 262 tests passing (167 FR-2 + 95 FR-1), 0 failures
```
