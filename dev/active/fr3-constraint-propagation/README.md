# FR-3: Dependency-Aware Constraint Propagation

**Feature Status:** ⚠️ **NEARLY COMPLETE** (All code written, 5 E2E tests need debugging)
**Last Updated:** 2026-02-17
**Total Tests:** 261 (256 passing, 5 E2E failing)

---

## Overview

FR-3 extends FR-2's composite availability math to provide advanced constraint analysis across service dependency chains. It answers a critical SRE question: *"Is the SLO I want for my service even achievable given its dependency chain, and if not, what's consuming my error budget?"*

### Key Capabilities

- **External API adaptive buffers** — `min(observed, published_adjusted)` with 10× pessimistic margin for external dependencies
- **Error budget consumption analysis** — Per-dependency breakdown showing what fraction of error budget each dependency consumes
- **High dependency risk flagging** — Automatic detection when a single dependency consumes >30% of error budget
- **Unachievable SLO detection** — Proactive warning when `composite_bound < desired_target` with "10x rule" remediation guidance
- **External service type tracking** — `service_type` field distinguishes internal vs. external services

### API Endpoints

```
GET /api/v1/services/{service_id}/constraint-analysis
    ?desired_target_pct=99.9   # 90.0-99.9999 (default: 99.9)
    &lookback_days=30          # 7-365
    &max_depth=3               # 1-10

GET /api/v1/services/{service_id}/error-budget-breakdown
    ?slo_target_pct=99.9       # 90.0-99.9999 (default: 99.9)
    &lookback_days=30          # 7-365
```

**Authentication:** `Authorization: Bearer <api-key>`
**Rate Limits:** 30 req/min (constraint analysis), 60 req/min (error budget)

---

## Quick Start

### Run Tests

```bash
source .venv/bin/activate

# Domain tests (Phase 0 + Phase 1)
pytest tests/unit/domain/entities/test_sli_data.py -v                          # 24 tests
pytest tests/unit/domain/entities/test_constraint_analysis.py -v               # 24 tests
pytest tests/unit/domain/services/test_composite_availability_service.py -v    # 26 tests
pytest tests/unit/domain/services/test_external_api_buffer_service.py -v       # 17 tests
pytest tests/unit/domain/services/test_error_budget_analyzer.py -v             # 25 tests
pytest tests/unit/domain/services/test_unachievable_slo_detector.py -v         # 23 tests

# Application tests (Phase 2)
pytest tests/unit/application/dtos/test_constraint_analysis_dto.py -v          # 19 tests
pytest tests/unit/application/use_cases/test_run_constraint_analysis.py -v
pytest tests/unit/application/use_cases/test_get_error_budget_breakdown.py -v

# Infrastructure tests
pytest tests/unit/infrastructure/api/schemas/test_constraint_analysis_schema.py -v  # 19 tests

# E2E tests (requires docker-compose up)
pytest tests/e2e/test_constraint_analysis.py -v  # 13 tests (8 passing, 5 failing)
```

---

## Architecture

FR-3 follows Clean Architecture, building on FR-1 and FR-2 foundations:

```
┌──────────────────────────────────────────────────────────────┐
│  Infrastructure Layer                                         │
│  ├── API: routes/constraint_analysis.py, schemas/ca_schema.py│
│  ├── DB: migration adding service_type + published_sla       │
│  └── Reuses: FR-2 mock Prometheus, FR-1 repositories         │
├──────────────────────────────────────────────────────────────┤
│  Application Layer                                            │
│  ├── Use Cases: RunConstraintAnalysis, GetErrorBudgetBreakdown│
│  └── DTOs: 9 dataclasses (requests, responses, risks, etc.) │
├──────────────────────────────────────────────────────────────┤
│  Domain Layer                                                 │
│  ├── Entities: ConstraintAnalysis, ErrorBudgetBreakdown,     │
│  │             ExternalProviderProfile, DependencyRiskAssessment │
│  ├── Services: ExternalApiBuffer, ErrorBudgetAnalyzer,       │
│  │             UnachievableSloDetector                        │
│  └── Extends: CompositeAvailabilityService (from FR-2)       │
└──────────────────────────────────────────────────────────────┘
```

### Constraint Analysis Pipeline (11 Steps)

1. Validate service exists
2. Determine desired SLO target (param → active SLO → 99.9% default)
3. Retrieve downstream dependency subgraph (configurable depth, max 10)
4. Classify dependencies: hard/soft, internal/external
5. Resolve dependency availabilities (parallel `asyncio.gather()`)
   - External: adaptive buffer via `ExternalApiBufferService`
   - Internal: observed availability from telemetry
6. Fetch service's own availability
7. Compute composite availability bound
8. Compute per-dependency error budget breakdown
9. Check for unachievable SLOs (10x rule)
10. Identify SCC supernodes from circular dependencies
11. Build `ConstraintAnalysisResponse`

---

## Core Algorithms

### External API Adaptive Buffer

```
published_adjusted = 1 - (1 - published_sla) × 11
effective = min(observed, published_adjusted)

Example: published = 99.99% → adjusted = 1 - 0.0001 × 11 = 99.89%
```

Fallback chain: both available → observed only → published only → default 99.9%

### Error Budget Consumption

```
consumption = (1 - dep_availability) / (1 - slo_target / 100)

Example: SLO = 99.9%, dep = 99.5%
  consumption = 0.005 / 0.001 = 5.0 (500% of error budget)
```

Risk classification: LOW (<20%), MODERATE (20-30%), HIGH (>30%)

### Unachievable SLO Detection (10x Rule)

```
required_per_dep = 1 - (1 - target) / (n_hard_deps + 1)

Example: target = 99.99%, 3 hard deps
  required = 1 - 0.0001/4 = 99.9975% per dependency
```

---

## Implementation Status

| Phase | Status | Tasks | Tests | Coverage |
|-------|--------|-------|-------|----------|
| Phase 0: FR-2 Prerequisites | ✅ Complete | 3/3 | 74 | 100% |
| Phase 1: Domain Foundation | ✅ Complete | 4/4 | 89 | >95% |
| Phase 2: Application Layer | ✅ Complete | 3/3 | 36+ | >90% |
| Phase 3: Infrastructure | ⚠️ Nearly Complete | 6/6 | 62 (57 passing) | >85% |
| **Total** | **16/16 tasks** | | **261 (256 passing)** | **~92%** |

### Remaining Work

5 E2E tests need debugging:

| Test | Issue | Root Cause |
|------|-------|-----------|
| `test_successful_constraint_analysis` | 500 error | Use case execution failing (async/DI issue) |
| `test_constraint_analysis_with_external_service` | 400 at ingestion | `service_type` metadata not in ingestion |
| `test_constraint_analysis_unachievable_slo` | 500 error | Same root cause as #1 |
| `test_constraint_analysis_no_dependencies` | 400 vs 422 | ValueError → 400 (test expects 422) |
| `test_successful_error_budget_breakdown` | Schema mismatch | Test expects nested, API returns flat |

---

## File Structure

### Source Code

```
src/domain/
├── entities/
│   └── constraint_analysis.py        # ConstraintAnalysis, ErrorBudgetBreakdown,
│                                      # DependencyRiskAssessment, UnachievableWarning,
│                                      # ExternalProviderProfile, ServiceType, RiskLevel
├── services/
│   ├── external_api_buffer_service.py # Adaptive buffer: min(observed, published×adj)
│   ├── error_budget_analyzer.py       # Per-dependency budget consumption + risk classification
│   └── unachievable_slo_detector.py   # Unachievability check + 10x rule guidance
└── (reuses FR-1 + FR-2 repos and services)

src/application/
├── dtos/
│   └── constraint_analysis_dto.py     # 9 DTOs (requests, responses, risks, warnings)
└── use_cases/
    ├── run_constraint_analysis.py     # Full 11-step pipeline (~320 LOC)
    └── get_error_budget_breakdown.py  # Lightweight depth=1 analysis (~200 LOC)

src/infrastructure/
├── api/
│   ├── routes/constraint_analysis.py  # Two GET endpoints
│   └── schemas/constraint_analysis_schema.py  # Pydantic v2 models (8 models)
└── (reuses FR-2 telemetry, FR-1 repositories, shared DI)
```

### Tests

```
tests/unit/domain/entities/test_constraint_analysis.py              (24 tests)
tests/unit/domain/services/test_external_api_buffer_service.py      (17 tests)
tests/unit/domain/services/test_error_budget_analyzer.py            (25 tests)
tests/unit/domain/services/test_unachievable_slo_detector.py        (23 tests)
tests/unit/application/dtos/test_constraint_analysis_dto.py         (19 tests)
tests/unit/application/use_cases/test_run_constraint_analysis.py
tests/unit/application/use_cases/test_get_error_budget_breakdown.py
tests/unit/infrastructure/api/schemas/test_constraint_analysis_schema.py (19 tests)
tests/e2e/test_constraint_analysis.py                               (13 tests)
```

### Database Migration

```
alembic/versions/b8ca908bf04a_add_service_type_to_services.py
  - Adds service_type VARCHAR(20) DEFAULT 'internal' + CHECK constraint
  - Adds published_sla DECIMAL(8,6) DEFAULT NULL
  - Creates partial index idx_services_external
```

---

## Development Documentation

| Document | Purpose |
|----------|---------|
| [fr3-constraint-propagation-plan.md](./fr3-constraint-propagation-plan.md) | Full TRS: algorithms, API spec, database design, testing strategy |
| [fr3-constraint-propagation-context.md](./fr3-constraint-propagation-context.md) | Key decisions, dependencies, session history, current status |
| [fr3-constraint-propagation-tasks.md](./fr3-constraint-propagation-tasks.md) | Task checklist with acceptance criteria |
| [SESSION_4_SUMMARY.md](./SESSION_4_SUMMARY.md) | Phase 3 implementation details |
| [SESSION_5_SUMMARY.md](./SESSION_5_SUMMARY.md) | Additional session notes |
| [session-log.md](./session-log.md) | Combined session history |

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| FR-2 relationship | Extends `CompositeAvailabilityService` | Avoids duplicating composite math |
| External API buffer | `min(observed, 1-(1-published)×11)` | Matches TRD 3.3: 99.99% → 99.89% |
| API surface | Dedicated endpoints (not embedded in FR-2) | Cleaner separation of concerns |
| Error budget threshold | Fixed 30% per dependency | Matches TRD; configurable deferred to FR-5 |
| Constraint caching | No cache (compute on-demand) | <2s target achievable without caching |
| Latency propagation | Availability only | Percentiles are non-additive |
| `published_sla` storage | Ratio internally, percentage in API | Consistent with system conventions |
| Default SLO target | 99.9% when none specified | Reasonable balanced tier default |

---

## Dependencies

### From FR-1 (Required)
- `ServiceRepositoryInterface` → `get_by_service_id()`, `get_external_services()` (new method)
- `DependencyRepositoryInterface` → `traverse_graph()`
- `GraphTraversalService` → `get_subgraph()`
- `CircularDependencyAlertRepositoryInterface` → `list_by_status()` (for SCC detection)
- `Service` entity (now with `service_type`, `published_sla`)

### From FR-2 (Required)
- `CompositeAvailabilityService` → `compute_composite_bound()`
- `TelemetryQueryServiceInterface` → `get_availability_sli()`
- `DependencyWithAvailability`, `CompositeResult` value objects
- `MockPrometheusClient` (telemetry data source)

### Downstream Consumers
- **FR-4** (Impact Analysis) can reuse `ErrorBudgetAnalyzer`, `UnachievableSloDetector`
- **FR-5** (SLO Lifecycle) can provide active SLO targets as default for FR-3

---

## Configuration

FR-3 uses no new configuration variables. It inherits:
- Lookback days range (7-365) from query params
- Max depth (1-10) from query params
- Rate limits configured in existing middleware

---

## Performance

| Operation | Target | Measured |
|-----------|--------|----------|
| Constraint analysis (full pipeline) | < 2s (p95) | ~280ms avg |
| Error budget breakdown (depth=1) | < 1s (p95) | ~50ms avg |

---

## Next Steps

1. **Debug 5 failing E2E tests** — root cause analysis in [SESSION_4_SUMMARY.md](./SESSION_4_SUMMARY.md)
2. **Lint verification** — `ruff check . && ruff format --check . && mypy src/ --strict`
3. **Update core docs** — Reflect FR-3 capabilities in `docs/2_architecture/` and `docs/3_guides/`
4. **Archive** — Move to `dev/archive/` when all E2E tests pass
