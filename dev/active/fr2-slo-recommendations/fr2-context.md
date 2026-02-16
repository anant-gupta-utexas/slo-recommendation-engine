# FR-2 Context Document
## SLO Recommendation Generation

**Created:** 2026-02-15
**Last Updated:** 2026-02-15

---

## Key Decisions Made

### Architecture Decisions

| Decision | Options Considered | Choice Made | Rationale | Date |
|----------|-------------------|-------------|-----------|------|
| **Telemetry Source** | Real Prometheus / Mock stub / In-memory TSDB | Mock Prometheus stub | Enables parallel development with FR-6; faster iteration | 2026-02-15 |
| **Explainability** | SHAP library / Weighted attribution / Equal weights | Weighted attribution (fixed domain weights) | Simpler than SHAP; sufficient for rule-based MVP; documented as future ML replacement | 2026-02-15 |
| **Caching Strategy** | Redis lazy-compute / Pre-compute PostgreSQL / Hybrid | Pre-compute in PostgreSQL | Simpler ops; aligns with 24h freshness target; no Redis dependency for this feature | 2026-02-15 |
| **Cold-Start** | Archetype matching / Extended lookback / Both | Extended lookback only (up to 90 days) | Simpler; no need to define/maintain archetype baselines for MVP | 2026-02-15 |
| **Tier Computation** | Percentile only / Percentile + cap / Composite-aware scaling | Percentile + dependency hard cap | Mathematically sound; prevents unachievable SLOs while showing achievable potential | 2026-02-15 |
| **Schema Scope** | All 3 TRD tables / Only slo_recommendations / Recommendations + aggregates | `slo_recommendations` + `sli_aggregates` schema (aggregates populated in FR-6) | Minimal scope for FR-2; active_slos and audit_log deferred to FR-5 | 2026-02-15 |
| **Graph Snapshots** | Separate snapshot table / Timestamp reference | Timestamp (`generated_at`) for provenance | Simpler; snapshot table adds complexity without clear MVP benefit | 2026-02-15 |
| **FR-1 Coupling** | Block on FR-1 Phase 4 / Independent development | Independent — use domain interfaces directly | FR-2 shares the same FastAPI app but doesn't need FR-1 API routes done | 2026-02-15 |
| **Batch Concurrency** | Sequential / asyncio.gather(10) / asyncio.gather(20) | asyncio.gather with semaphore(20) | Balance throughput and DB connection pressure; 20 << pool_size(50) | 2026-02-15 |
| **Aggressive Tier Cap** | Cap all tiers / Cap Conservative+Balanced only | Aggressive tier NOT capped | Shows achievable potential; useful contrast for user decision-making | 2026-02-15 |

---

## Dependencies

### Internal Module Dependencies (FR-1 → FR-2)

```
FR-2 Use Cases
    ├── src/domain/repositories/service_repository.py (FR-1)
    │   └── get_by_service_id(), list_all()
    ├── src/domain/repositories/dependency_repository.py (FR-1)
    │   └── traverse_graph()
    ├── src/domain/services/graph_traversal_service.py (FR-1)
    │   └── get_subgraph()
    ├── src/domain/entities/service.py (FR-1)
    │   └── Service entity (criticality, team, service_id)
    ├── src/domain/entities/service_dependency.py (FR-1)
    │   └── ServiceDependency entity (criticality, communication_mode)
    │
    ├── NEW: src/domain/entities/slo_recommendation.py
    ├── NEW: src/domain/entities/sli_data.py
    ├── NEW: src/domain/services/availability_calculator.py
    ├── NEW: src/domain/services/latency_calculator.py
    ├── NEW: src/domain/services/composite_availability_service.py
    ├── NEW: src/domain/services/weighted_attribution_service.py
    ├── NEW: src/domain/repositories/slo_recommendation_repository.py
    └── NEW: src/domain/repositories/telemetry_query_service.py
```

### FR-2 Internal Dependency Graph

```
Task 1.1 (Entities) ─────────┬─> Task 1.3 (AvailCalc)
                              ├─> Task 1.5 (CompositeAvail)
                              ├─> Task 1.6 (Attribution)
                              └─> Task 1.7 (Interfaces)
Task 1.2 (SLI Data) ─────────┬─> Task 1.4 (LatencyCalc)
                              ├─> Task 1.5 (CompositeAvail)
                              └─> Task 1.7 (Interfaces)

Phase 1 ──────────────────────> Task 2.1 (DTOs)
                                Task 2.2 (GenerateUseCase) ──> Task 2.3 (GetUseCase)
                                                           ──> Task 2.4 (BatchUseCase)

Phase 2 + Phase 1.7 ─────────> Task 3.1 (Models)
                                Task 3.2 (Migrations)
                                Task 3.3 (Repository)
                                Task 3.4 (Mock Prometheus)

Phase 3 ──────────────────────> Task 4.1 (Schemas)
                                Task 4.2 (API Route)
                                Task 4.3 (DI Wiring)
                                Task 4.4 (Batch Task)
                                Task 4.5 (E2E Tests)
```

### External Service Dependencies

| Service | Purpose | Criticality | Fallback |
|---------|---------|-------------|----------|
| **PostgreSQL** | Recommendation storage | Critical | None |
| **Redis** | Rate limiting (shared with FR-1) | High | In-memory fallback |
| **Mock Prometheus Stub** | Telemetry data source | Critical (for FR-2) | Hardcoded defaults |

### Library Dependencies (New for FR-2)

No new library dependencies required. FR-2 uses:
- `dataclasses` (stdlib) — domain entities
- `math`, `random`, `statistics` (stdlib) — computation and bootstrap
- Existing: `sqlalchemy`, `fastapi`, `pydantic`, `asyncpg`, `apscheduler`

---

## Integration Points

### Upstream Consumers (Who calls FR-2)

| Consumer | Endpoint/Interface | Frequency | Purpose |
|----------|-------------------|-----------|---------|
| **Backstage Plugin** | GET /services/{id}/slo-recommendations | ~100 req/min | Display recommendations in catalog |
| **FR-4 (Impact Analysis)** | GenerateSloRecommendationUseCase (internal) | On-demand | Recompute after proposed SLO change |
| **FR-5 (Lifecycle)** | GetSloRecommendationUseCase (internal) | On-demand | Retrieve recommendation for accept/reject |
| **Batch Scheduler** | BatchComputeRecommendationsUseCase | Every 24h | Pre-compute all recommendations |

### Downstream Dependencies (What FR-2 calls)

| Component | Purpose | Interface |
|-----------|---------|-----------|
| **ServiceRepository** (FR-1) | Lookup services | `get_by_service_id()`, `list_all()` |
| **DependencyRepository** (FR-1) | Graph traversal | `traverse_graph()` |
| **GraphTraversalService** (FR-1) | Subgraph retrieval | `get_subgraph()` |
| **SloRecommendationRepository** (FR-2) | Store/retrieve recommendations | `get_active_by_service()`, `save()`, etc. |
| **TelemetryQueryService** (FR-2) | Mock Prometheus data | `get_availability_sli()`, etc. |

---

## Files to Create

### Phase 1: Domain Foundation

**Code:**
- `src/domain/entities/slo_recommendation.py` (~120 LOC)
- `src/domain/entities/sli_data.py` (~60 LOC)
- `src/domain/services/availability_calculator.py` (~150 LOC)
- `src/domain/services/latency_calculator.py` (~80 LOC)
- `src/domain/services/composite_availability_service.py` (~120 LOC)
- `src/domain/services/weighted_attribution_service.py` (~80 LOC)
- `src/domain/repositories/slo_recommendation_repository.py` (~50 LOC)
- `src/domain/repositories/telemetry_query_service.py` (~50 LOC)

**Tests:**
- `tests/unit/domain/entities/test_slo_recommendation.py` (~200 LOC)
- `tests/unit/domain/entities/test_sli_data.py` (~80 LOC)
- `tests/unit/domain/services/test_availability_calculator.py` (~300 LOC)
- `tests/unit/domain/services/test_latency_calculator.py` (~150 LOC)
- `tests/unit/domain/services/test_composite_availability_service.py` (~250 LOC)
- `tests/unit/domain/services/test_weighted_attribution_service.py` (~150 LOC)

### Phase 2: Application Layer

**Code:**
- `src/application/dtos/slo_recommendation_dto.py` (~130 LOC)
- `src/application/use_cases/generate_slo_recommendation.py` (~300 LOC)
- `src/application/use_cases/get_slo_recommendation.py` (~80 LOC)
- `src/application/use_cases/batch_compute_recommendations.py` (~100 LOC)

**Tests:**
- `tests/unit/application/dtos/test_slo_recommendation_dto.py` (~150 LOC)
- `tests/unit/application/use_cases/test_generate_slo_recommendation.py` (~400 LOC)
- `tests/unit/application/use_cases/test_get_slo_recommendation.py` (~150 LOC)
- `tests/unit/application/use_cases/test_batch_compute_recommendations.py` (~200 LOC)

### Phase 3: Infrastructure — Persistence & Telemetry

**Code:**
- `src/infrastructure/database/models/slo_recommendation.py` (~80 LOC)
- `src/infrastructure/database/models/sli_aggregate.py` (~50 LOC)
- `alembic/versions/004_create_slo_recommendations_table.py` (~60 LOC)
- `alembic/versions/005_create_sli_aggregates_table.py` (~50 LOC)
- `src/infrastructure/database/repositories/slo_recommendation_repository.py` (~200 LOC)
- `src/infrastructure/telemetry/mock_prometheus_client.py` (~180 LOC)
- `src/infrastructure/telemetry/seed_data.py` (~100 LOC)

**Tests:**
- `tests/integration/infrastructure/database/test_slo_recommendation_repository.py` (~300 LOC)
- `tests/unit/infrastructure/telemetry/test_mock_prometheus_client.py` (~200 LOC)

### Phase 4: Infrastructure — API & Tasks

**Code:**
- `src/infrastructure/api/schemas/slo_recommendation_schema.py` (~120 LOC)
- `src/infrastructure/api/routes/recommendations.py` (~100 LOC)
- `src/infrastructure/tasks/batch_recommendations.py` (~60 LOC)

**Modified:**
- `src/infrastructure/api/dependencies.py` — Add FR-2 dependency factories
- `src/infrastructure/api/main.py` — Register recommendations router

**Tests:**
- `tests/unit/infrastructure/api/schemas/test_slo_recommendation_schema.py` (~100 LOC)
- `tests/integration/infrastructure/api/test_recommendations_endpoint.py` (~250 LOC)
- `tests/integration/infrastructure/tasks/test_batch_recommendations.py` (~150 LOC)
- `tests/e2e/test_slo_recommendations.py` (~200 LOC)

### Estimated Totals

| Category | Files | LOC |
|----------|-------|-----|
| Domain code | 8 | ~710 |
| Application code | 4 | ~610 |
| Infrastructure code | 9 | ~1,000 |
| Tests | 16 | ~3,230 |
| **Total** | **37** | **~5,550** |

---

## Configuration Management

### New Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BATCH_RECOMMENDATION_INTERVAL_HOURS` | `24` | Batch job frequency |
| `BATCH_RECOMMENDATION_CONCURRENCY` | `20` | Max concurrent service computations |
| `DEFAULT_LOOKBACK_DAYS` | `30` | Standard lookback window |
| `EXTENDED_LOOKBACK_DAYS` | `90` | Cold-start extended window |
| `DATA_COMPLETENESS_THRESHOLD` | `0.90` | Threshold for triggering extended lookback |
| `DEFAULT_DEPENDENCY_AVAILABILITY` | `0.999` | Assumed availability for deps with no data |
| `RECOMMENDATION_EXPIRY_HOURS` | `24` | TTL for recommendations |
| `NOISE_MARGIN_DEFAULT` | `0.05` | Default latency noise margin (5%) |
| `NOISE_MARGIN_SHARED_INFRA` | `0.10` | Shared infra noise margin (10%) |
| `BOOTSTRAP_RESAMPLE_COUNT` | `1000` | Number of bootstrap resamples |

---

## Patterns & Conventions (Aligned with FR-1)

### Code Patterns

| Pattern | Convention | Example |
|---------|-----------|---------|
| **Domain entities** | `dataclass` with `__post_init__` validation | `SloRecommendation.__post_init__` |
| **DTOs** | `dataclass` (not Pydantic) | `GenerateRecommendationRequest` |
| **API schemas** | Pydantic `BaseModel` | `SloRecommendationResponse` |
| **Repository interfaces** | `ABC` with `@abstractmethod` | `SloRecommendationRepositoryInterface` |
| **Use cases** | Constructor injection, `async execute()` method | `GenerateSloRecommendationUseCase` |
| **Enums** | `str, Enum` for serializable enums | `SliType(str, Enum)` |
| **Imports** | `TYPE_CHECKING` for circular deps | Standard FR-1 pattern |
| **Testing** | `AsyncMock` for async deps, `MagicMock` for sync | From FR-1 Phase 3 lessons |
| **Naming** | `test_<scenario>_<expected_outcome>` | `test_compute_tiers_caps_by_composite_bound` |

### Lessons from FR-1 (Apply to FR-2)

1. **Use `MagicMock` (not `AsyncMock`) for synchronous services** — e.g., AvailabilityCalculator is sync
2. **Use `AsyncMock` for all repository methods** — they're async
3. **UUID→string conversion helpers** — may need similar patterns for service lookups
4. **`metadata_` attribute naming** — reuse FR-1 pattern for SQLAlchemy reserved names
5. **Fixture pattern: one fixture per dependency** — maintain isolation
6. **Statistics bugs** — double-check len() boundaries in list operations

---

## Current Status

**Phase Completion:**
- 🟡 **Phase 1 (Week 1)**: Domain layer — IN PROGRESS (67% complete)
  - ✅ Task 1.1: SLO Recommendation Entity (COMPLETE)
  - ✅ Task 1.2: SLI Data Value Objects (COMPLETE)
  - ✅ Task 1.3: Availability Calculator Service (COMPLETE)
  - ✅ Task 1.4: Latency Calculator Service (COMPLETE)
  - ⏭️ Task 1.5: Composite Availability Service (NEXT)
  - ⬜ Task 1.6: Weighted Attribution Service (PENDING)
  - ✅ Task 1.7: Repository Interfaces (COMPLETE)
- ⬜ **Phase 2 (Week 2)**: Application layer — NOT STARTED
- ⬜ **Phase 3 (Week 3)**: Infrastructure persistence & telemetry — NOT STARTED
- ⬜ **Phase 4 (Week 4)**: API & background tasks — NOT STARTED

**Test Summary:**
- 113 tests passing, 0 failures
- 100% coverage on all implemented code
- Domain entities: 32 + 24 = 56 tests
- Domain services: 31 (availability) + 26 (latency) = 57 tests
- Repository interfaces: 0 tests (pure interfaces)

**Implementation Highlights:**
- Sophisticated availability tier computation with percentile analysis
- Latency tier computation with configurable noise margins (5% default, 10% shared infra)
- Bootstrap confidence intervals for uncertainty quantification (1000 resamples)
- Composite bound capping logic (Conservative/Balanced capped, Aggressive NOT capped)
- Breach probability estimation from historical percentile data
- Comprehensive validation in all entities
- Error budget calculation aligned with SRE best practices

**Blockers:**
- None. FR-2 can proceed independently of FR-1 Phase 4 (API layer).

**FR-1 Status (for reference):**
- Phase 1-3: Complete (domain, infrastructure, application)
- Phase 4: In progress (API layer)
- Phases 5-6: Not started

---

## Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Mock Prometheus returns unrealistic data | Medium | Medium | Seed data based on real-world distributions; document assumptions |
| Bootstrap confidence intervals slow for large datasets | Low | Low | Cap at 1000 resamples; profile during Phase 1 testing |
| FR-1 API layer changes affect shared FastAPI app | Low | Medium | FR-2 registers its own router; minimal coupling to FR-1 routes |
| Batch job takes > 30 min for 5000 services | Medium | Medium | Semaphore limits concurrency; can increase if DB handles load |
| JSONB schema drift between entity and API response | Medium | Low | Pydantic schema validates on read; unit tests verify round-trip |

---

## Technical Debt Accepted

| Item | Rationale | Repayment Plan |
|------|-----------|---------------|
| Mock Prometheus instead of real integration | Parallel development speed | Replace with real PrometheusClient in FR-6 |
| Fixed attribution weights | Sufficient for rule-based MVP | Replace with SHAP values in Phase 5 ML integration |
| No counterfactual analysis | Requires re-running pipeline with perturbed inputs | Add in Phase 5 alongside ML models |
| No graph snapshot versioning | Timestamp sufficient for provenance tracking | Add snapshot table if audit requirements demand it |
| sli_aggregates table created but not populated | Populated by FR-6 batch job | FR-6 implements hourly aggregation pipeline |
| Deployment frequency feature = 0.5 placeholder | No deployment data source yet | Integrate with CI/CD pipeline or K8s deployment events |
| Bootstrap with stdlib random (not numpy) | No numpy dependency for MVP | Switch to numpy if performance requires vectorized bootstrap |

---

---

## Current Implementation Status

### Phase 1: Domain Foundation ✅ **COMPLETE**
**Status:** 100% complete (167 tests passing)

**Completed Components:**
1. ✅ **Entities:**
   - `SloRecommendation` - Main entity with auto-expiry, supersede, expire methods
   - `AvailabilitySliData` - Availability telemetry value object
   - `LatencySliData` - Latency telemetry value object

2. ✅ **Domain Services:**
   - `AvailabilityCalculator` - Three-tier availability recommendations with composite capping
   - `LatencyCalculator` - Three-tier latency recommendations with noise margins
   - `CompositeAvailabilityService` - Dependency-aware availability bounds (serial/parallel)
   - `WeightedAttributionService` - Heuristic feature attribution for explainability

3. ✅ **Repository Interfaces:**
   - `SloRecommendationRepositoryInterface` - CRUD operations
   - `TelemetryQueryServiceInterface` - Telemetry query abstraction

**Test Coverage:**
- 167 unit tests, 0 failures
- 97-100% code coverage on all components
- Comprehensive edge case testing
- Known-answer test vectors for mathematical correctness

**Key Files:**
```
src/domain/entities/slo_recommendation.py
src/domain/entities/sli_data.py
src/domain/services/availability_calculator.py
src/domain/services/latency_calculator.py
src/domain/services/composite_availability_service.py
src/domain/services/weighted_attribution_service.py
src/domain/repositories/slo_recommendation_repository.py
src/domain/repositories/telemetry_query_service.py
```

### Phase 2: Application Layer ⬜ **NOT STARTED**
**Next Steps:**
- Task 2.1: Create 11 DTO dataclasses
- Task 2.2: GenerateSloRecommendation Use Case
- Task 2.3: GetSloRecommendation Use Case
- Task 2.4: BatchComputeRecommendations Use Case

### Phase 3: Infrastructure (DB + Telemetry) ⬜ **NOT STARTED**
### Phase 4: Infrastructure (API + Tasks) ⬜ **NOT STARTED**

---

## Session 4 Additions (2026-02-15)

**Completed:**
- ✅ Task 1.5: Composite Availability Service (26 tests, 97% coverage)
- ✅ Task 1.6: Weighted Attribution Service (28 tests, 100% coverage)
- ✅ Phase 1 Domain Foundation Complete

**Technical Highlights:**
- Serial dependency composition: R = R_self × ∏R_dep
- Parallel redundancy: R = 1 - ∏(1 - R_replica)
- Bottleneck identification (weakest link)
- Heuristic feature weights for availability and latency

**Tests Added:** 54 (from 113 to 167)

---

## Next Session Handoff

**Ready to Start:** Phase 2 - Application Layer (DTOs and Use Cases)

**Commands to Verify:**
```bash
source .venv/bin/activate
pytest tests/unit/domain/ -v  # Should show 262 tests passing (167 FR-2 + 95 FR-1)
```

**First Task:** Create `src/application/dtos/slo_recommendation_dto.py` with 11 DTOs

**Reference Files:**
- `dev/active/fr2-slo-recommendations/fr2-plan.md` - Full technical spec
- `dev/active/fr2-slo-recommendations/fr2-tasks.md` - Task checklist
- `dev/active/fr2-slo-recommendations/phase-logs/fr2-phase1.md` - Phase 1 session log

---

**Document Version:** 1.1
**Last Updated:** 2026-02-15 (Session 4)
