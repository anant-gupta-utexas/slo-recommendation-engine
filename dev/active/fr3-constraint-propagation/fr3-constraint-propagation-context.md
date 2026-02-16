# FR-3: Dependency-Aware Constraint Propagation — Context Document

**Created:** 2026-02-15
**Status:** Not Started
**Last Updated:** 2026-02-15

---

## Current State

FR-3 plan is complete and ready for implementation. FR-2 is "Not Started", so FR-3 Phase 0 includes minimal FR-2 prerequisites to unblock development.

### Session Log

- **2026-02-15:** TRS created. All clarifying questions answered. Plan reviewed against PRD F3, TRD 3.3, and existing FR-1 patterns. Phase 0 prerequisites identified from FR-2.

---

## Key Decisions Made

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| 1 | FR-2 relationship | Extend FR-2's CompositeAvailabilityService with advanced features | Avoids duplicating composite math; FR-3 adds external buffers, budget analysis, unachievability on top | 2026-02-15 |
| 2 | External API buffer strategy | `min(observed, published_adjusted)` where `published_adjusted = 1 - (1-published)*11` | Matches TRD 3.3 example (99.99% → 99.89%); conservative and simple | 2026-02-15 |
| 3 | API surface | Dedicated endpoints (`/constraint-analysis`, `/error-budget-breakdown`) | Cleaner separation; FR-2 response stays focused on recommendations | 2026-02-15 |
| 4 | Error budget threshold | Fixed 30% per single dependency | Matches TRD; keeps MVP simple | 2026-02-15 |
| 5 | External service tracking | `service_type` field on `services` table | Minimal schema change; clean data model | 2026-02-15 |
| 6 | FR-2 dependency | Phase 0 includes minimal FR-2 prerequisites | Self-contained plan; no blocking on FR-2 completion | 2026-02-15 |
| 7 | Constraint analysis caching | No cache (compute on demand) | < 2s target is achievable; cache adds complexity | 2026-02-15 |
| 8 | FR-3 scope on latency | Availability only | Percentiles are non-additive; latency uses e2e trace measurement, not propagation | 2026-02-15 |
| 9 | `published_sla` storage format | Ratio internally (0.9999), percentage in API (99.99%) | Consistent with `availability_ratio` throughout the system | 2026-02-15 |
| 10 | Pessimistic adjustment formula | `1 - (1-published) * 11` (adds 10× unavailability margin) | Matches TRD example: 99.99% → 99.89% | 2026-02-15 |
| 11 | Default SLO target when none specified | 99.9% (balanced tier default) | FR-2 recommendation may not exist; 99.9% is a reasonable default | 2026-02-15 |
| 12 | SLO target 100% handling | Cap consumption at 999999.99 | Prevents JSON serialization issues with infinity | 2026-02-15 |

---

## Dependencies

### Internal Dependencies (FR-1 → FR-3)

| Component | Status | Import Path | Usage |
|-----------|--------|-------------|-------|
| `Service` entity | Production Ready | `src.domain.entities.service.Service` | Service lookup, metadata |
| `ServiceDependency` entity | Production Ready | `src.domain.entities.service_dependency.ServiceDependency` | Edge classification |
| `ServiceRepositoryInterface` | Production Ready | `src.domain.repositories.service_repository.ServiceRepositoryInterface` | Service queries |
| `DependencyRepositoryInterface` | Production Ready | `src.domain.repositories.dependency_repository.DependencyRepositoryInterface` | Graph traversal |
| `GraphTraversalService` | Production Ready | `src.domain.services.graph_traversal_service.GraphTraversalService` | Subgraph extraction |
| `CircularDependencyAlertRepositoryInterface` | Production Ready | `src.domain.repositories.circular_dependency_alert_repository` | SCC data |
| Auth middleware | Production Ready | `src.infrastructure.api.middleware.auth.verify_api_key` | API authentication |
| Rate limiting middleware | Production Ready | `src.infrastructure.api.middleware` | API rate limiting |
| RFC 7807 error schemas | Production Ready | `src.infrastructure.api.schemas.error_schema` | Error responses |
| FastAPI dependency injection | Production Ready | `src.infrastructure.api.dependencies` | DI wiring |

### Internal Dependencies (FR-2 → FR-3, Phase 0 Prerequisites)

| Component | FR-2 Status | FR-3 Phase 0 Action | Shared With |
|-----------|-------------|---------------------|-------------|
| `AvailabilitySliData` | Not Started | Create in Phase 0 Task 0.1 | FR-2 |
| `LatencySliData` | Not Started | Create in Phase 0 Task 0.1 | FR-2 |
| `DependencyWithAvailability` | Not Started | Create in Phase 0 Task 0.1 | FR-2 |
| `CompositeResult` | Not Started | Create in Phase 0 Task 0.1 | FR-2 |
| `CompositeAvailabilityService` | Not Started | Create in Phase 0 Task 0.3 | FR-2 |
| `TelemetryQueryServiceInterface` | Not Started | Create in Phase 0 Task 0.2 | FR-2 |
| Mock Prometheus Client | Not Started | Create in Phase 0 Task 0.2 | FR-2 |

### External Dependencies

| Dependency | Version | Purpose | Status |
|------------|---------|---------|--------|
| PostgreSQL | 16+ | Services table extension, dependency graph | Available (FR-1) |
| FastAPI | 0.115+ | API endpoints | Available (FR-1) |
| SQLAlchemy | 2.0+ | Database operations | Available (FR-1) |
| Alembic | Latest | Schema migration | Available (FR-1) |
| Pydantic | 2.0+ | API validation | Available (FR-1) |
| pytest | Latest | Testing | Available (FR-1) |
| httpx | Latest | API integration testing | Available (FR-1) |

---

## Integration Points

### Upstream (Components that FR-3 depends on)

| Component | Integration | Notes |
|-----------|-------------|-------|
| FR-1 dependency graph | Graph traversal via `DependencyRepositoryInterface.traverse_graph()` | Critical path; graph must be ingested before constraint analysis works |
| FR-1 service registry | Service lookup via `ServiceRepositoryInterface.get_by_service_id()` | Must include `service_type` and `published_sla` after migration |
| FR-1 circular dependency alerts | SCC data via `CircularDependencyAlertRepositoryInterface.list_by_status()` | Used for supernode reporting |
| FR-2 telemetry interface | Availability data via `TelemetryQueryServiceInterface` | Phase 0 creates the interface; real Prometheus in FR-6 |

### Downstream (Components that will depend on FR-3)

| Component | Integration | Notes |
|-----------|-------------|-------|
| FR-2 recommendations | FR-2 may use FR-3's enhanced composite math (external buffers) | FR-2 can import `CompositeAvailabilityService` and `ExternalApiBufferService` |
| FR-4 impact analysis | Impact analysis needs composite bounds and error budget data | FR-4 can reuse FR-3's `ErrorBudgetAnalyzer` and `UnachievableSloDetector` |
| FR-5 recommendation lifecycle | Active SLO target feeds into FR-3's default target selection | FR-3 currently defaults to 99.9%; FR-5 provides the preferred source |

---

## Files to Create/Modify

### Phase 0: FR-2 Prerequisites

| File | Action | Purpose |
|------|--------|---------|
| `src/domain/entities/sli_data.py` | CREATE | AvailabilitySliData, LatencySliData |
| `src/domain/entities/dependency_with_availability.py` | CREATE | DependencyWithAvailability, CompositeResult |
| `src/domain/repositories/telemetry_query_service.py` | CREATE | TelemetryQueryServiceInterface |
| `src/domain/services/composite_availability_service.py` | CREATE | CompositeAvailabilityService |
| `src/infrastructure/telemetry/mock_prometheus_client.py` | CREATE | MockPrometheusClient |
| `src/infrastructure/telemetry/seed_data.py` | CREATE | Default seed data |
| `src/infrastructure/telemetry/__init__.py` | CREATE | Package init |
| `tests/unit/domain/entities/test_sli_data.py` | CREATE | Unit tests |
| `tests/unit/domain/entities/test_dependency_with_availability.py` | CREATE | Unit tests |
| `tests/unit/domain/services/test_composite_availability_service.py` | CREATE | Unit tests |
| `tests/unit/infrastructure/telemetry/test_mock_prometheus_client.py` | CREATE | Unit tests |

### Phase 1: Domain Foundation

| File | Action | Purpose |
|------|--------|---------|
| `src/domain/entities/constraint_analysis.py` | CREATE | FR-3 entities (ConstraintAnalysis, ErrorBudgetBreakdown, etc.) |
| `src/domain/services/external_api_buffer_service.py` | CREATE | External API adaptive buffer |
| `src/domain/services/error_budget_analyzer.py` | CREATE | Error budget consumption analysis |
| `src/domain/services/unachievable_slo_detector.py` | CREATE | Unachievable SLO detection |
| `tests/unit/domain/entities/test_constraint_analysis.py` | CREATE | Unit tests |
| `tests/unit/domain/services/test_external_api_buffer_service.py` | CREATE | Unit tests |
| `tests/unit/domain/services/test_error_budget_analyzer.py` | CREATE | Unit tests |
| `tests/unit/domain/services/test_unachievable_slo_detector.py` | CREATE | Unit tests |

### Phase 2: Application Layer

| File | Action | Purpose |
|------|--------|---------|
| `src/application/dtos/constraint_analysis_dto.py` | CREATE | DTOs |
| `src/application/use_cases/run_constraint_analysis.py` | CREATE | Constraint analysis use case |
| `src/application/use_cases/get_error_budget_breakdown.py` | CREATE | Error budget use case |
| `tests/unit/application/dtos/test_constraint_analysis_dto.py` | CREATE | Unit tests |
| `tests/unit/application/use_cases/test_run_constraint_analysis.py` | CREATE | Unit tests |
| `tests/unit/application/use_cases/test_get_error_budget_breakdown.py` | CREATE | Unit tests |

### Phase 3: Infrastructure

| File | Action | Purpose |
|------|--------|---------|
| `alembic/versions/XXX_add_service_type_to_services.py` | CREATE | Migration |
| `src/domain/entities/service.py` | MODIFY | Add service_type, published_sla |
| `src/domain/repositories/service_repository.py` | MODIFY | Add get_external_services() |
| `src/infrastructure/database/models.py` | MODIFY | Update ServiceModel |
| `src/infrastructure/database/repositories/service_repository.py` | MODIFY | Update mapping + new method |
| `src/infrastructure/api/schemas/constraint_analysis_schema.py` | CREATE | Pydantic schemas |
| `src/infrastructure/api/routes/constraint_analysis.py` | CREATE | API routes |
| `src/infrastructure/api/dependencies.py` | MODIFY | Add FR-3 DI factories |
| `src/infrastructure/api/main.py` | MODIFY | Register FR-3 router |
| `tests/unit/infrastructure/api/schemas/test_constraint_analysis_schema.py` | CREATE | Schema tests |
| `tests/integration/infrastructure/api/test_constraint_analysis_endpoint.py` | CREATE | Integration tests |
| `tests/e2e/test_constraint_analysis.py` | CREATE | E2E tests |

**Total: 28 files to create, 6 files to modify**

---

## Configuration Management

### New Environment Variables

None required. FR-3 uses the same configuration as FR-1 (database, Redis, auth).

### New Config Settings (via Pydantic Settings)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `EXTERNAL_API_PESSIMISTIC_MULTIPLIER` | int | 10 | Multiplier for pessimistic SLA adjustment |
| `ERROR_BUDGET_HIGH_RISK_THRESHOLD` | float | 0.30 | Threshold for high risk flagging |
| `DEFAULT_SLO_TARGET_PCT` | float | 99.9 | Default SLO target when none specified |
| `DEFAULT_EXTERNAL_AVAILABILITY` | float | 0.999 | Default availability for external deps with no data |

---

## Testing Strategy Summary

| Test Type | Count (est.) | Framework | Target |
|-----------|-------------|-----------|--------|
| Unit (entities) | ~25 | pytest | >95% coverage |
| Unit (services) | ~50 | pytest | >95% coverage |
| Unit (use cases) | ~20 | pytest + AsyncMock | >90% coverage |
| Unit (DTOs) | ~10 | pytest | >90% coverage |
| Unit (schemas) | ~10 | pytest | >90% coverage |
| Integration (API) | ~15 | pytest + httpx | >80% coverage |
| Integration (migration) | ~3 | pytest + testcontainers | 100% |
| E2E | ~8 | pytest + httpx | Critical paths |
| **Total** | **~141** | | |

---

## Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| FR-2 development overlaps with Phase 0 prerequisites | Low | Medium | Phase 0 creates minimal shared components; FR-2 can adopt them directly. No duplication. |
| Graph traversal latency for deep chains (>5 hops) | Medium | Low | Cap `max_depth` at 10. Recursive CTE performance tested at 5,000 nodes in FR-1 (< 100ms). |
| External service data not available (no published_sla set) | Low | High | Graceful fallback to 99.9% default. Clear note in response. |
| Pessimistic adjustment too aggressive for some SLAs | Low | Medium | Formula is well-defined and consistent. Users can override by providing `desired_target_pct`. |
| Error budget consumption >100% confuses users | Medium | Medium | API response includes `total_error_budget_minutes` for context. Consumption >100% means "dep alone exceeds your budget." |

---

## Technical Debt Accepted

| Debt Item | Reason | Remediation Plan |
|-----------|--------|-----------------|
| No caching for constraint analysis | MVP simplicity; < 2s response is achievable | Add PostgreSQL or Redis cache if load testing shows issues |
| Fixed 30% threshold (not configurable) | MVP simplicity | Make configurable per-service in FR-5 or config table |
| Mock Prometheus instead of real telemetry | Parallel development enablement | Replace with real Prometheus client in FR-6 |
| No latency constraint propagation | Percentiles are non-additive (not a debt — a design decision) | If needed, add Monte Carlo simulation in FR-15 |
| `published_sla` stored in services.metadata | Could be a separate table for richer modeling | Migrate to `external_providers` table if external provider management grows complex |
| Phase 0 components may need adjustment when FR-2 implements | Shared components may evolve | FR-2 should adopt Phase 0 components; any changes are additive |
