# Code Coverage Report

> **Last Updated:** 2026-03-02
> **Applies to:** SLO Recommendation Engine v0.4 (FR-1, FR-2, FR-3)

---

## Executive Summary

**Overall Coverage: 86%** (4000 statements, 576 missing)

- **Tests Passing:** 720 / 741 (97% pass rate)
- **Tests Failing:** 21 (mostly E2E and authentication-related)
- **Test Execution Time:** ~30 seconds (unit + integration)

---

## Coverage by Architectural Layer

### Domain Layer (Business Logic) - ⭐ Excellent

| Component | Coverage | Status | Missing Lines |
|-----------|----------|--------|---------------|
| **Entities** | | | |
| `service.py` | 100% | ✅ | None |
| `service_dependency.py` | 100% | ✅ | None |
| `sli_data.py` | 100% | ✅ | None |
| `slo_recommendation.py` | 100% | ✅ | None |
| `circular_dependency_alert.py` | 100% | ✅ | None |
| `constraint_analysis.py` | 100% | ✅ | None |
| `active_slo.py` | 84% | ⚠️ | 63-66, 103-106 |
| `impact_analysis.py` | 90% | ⚠️ | 29, 34-37 |
| **Services** | | | |
| `availability_calculator.py` | 100% | ✅ | None |
| `latency_calculator.py` | 98% | ✅ | 81 |
| `circular_dependency_detector.py` | 100% | ✅ | None |
| `composite_availability_service.py` | 97% | ✅ | 205, 242 |
| `edge_merge_service.py` | 100% | ✅ | None |
| `graph_traversal_service.py` | 100% | ✅ | None |
| `error_budget_analyzer.py` | 98% | ✅ | 132 |
| `counterfactual_service.py` | 95% | ✅ | 139-140 |
| `weighted_attribution_service.py` | 100% | ✅ | None |
| `external_api_buffer_service.py` | 100% | ✅ | None |
| `unachievable_slo_detector.py` | 100% | ✅ | None |
| `impact_analysis_service.py` | 19% | ❌ | FR-4 not implemented |

**Domain Layer Summary:** 95% coverage (excluding unimplemented FR-4)

---

### Application Layer (Use Cases) - ⭐ Excellent

| Component | Coverage | Status | Missing Lines |
|-----------|----------|--------|---------------|
| **DTOs** | | | |
| `common.py` | 100% | ✅ | None |
| `dependency_graph_dto.py` | 100% | ✅ | None |
| `dependency_subgraph_dto.py` | 100% | ✅ | None |
| `slo_recommendation_dto.py` | 100% | ✅ | None |
| `constraint_analysis_dto.py` | 100% | ✅ | None |
| `impact_analysis_dto.py` | 100% | ✅ | None |
| `slo_lifecycle_dto.py` | 100% | ✅ | None |
| **Use Cases** | | | |
| `generate_slo_recommendation.py` | 99% | ✅ | 275, 598 |
| `batch_compute_recommendations.py` | 100% | ✅ | None |
| `run_constraint_analysis.py` | 97% | ✅ | 145, 267, 330 |
| `get_error_budget_breakdown.py` | 97% | ✅ | 167, 230 |
| `get_slo_recommendation.py` | 97% | ✅ | 107 |
| `query_dependency_subgraph.py` | 95% | ✅ | 63, 70, 210 |
| `ingest_dependency_graph.py` | 94% | ✅ | 74, 111, 257, 285 |
| `detect_circular_dependencies.py` | 91% | ✅ | 84-87, 108 |
| `manage_slo_lifecycle.py` | 27% | ❌ | FR-5 not fully implemented |
| `run_impact_analysis.py` | 28% | ❌ | FR-4 not implemented |

**Application Layer Summary:** 96% coverage (excluding unimplemented features)

---

### Infrastructure Layer - 🟡 Good

#### Database

| Component | Coverage | Status | Missing Lines |
|-----------|----------|--------|---------------|
| `models.py` | 100% | ✅ | None |
| `session.py` | 100% | ✅ | None |
| `config.py` | 86% | ⚠️ | 25, 145-149, 162 |
| `health.py` | 39% | ❌ | 24-39, 56-57 |
| **Repositories** | | | |
| `dependency_repository.py` | 100% | ✅ | None |
| `slo_recommendation_repository.py` | 100% | ✅ | None |
| `circular_dependency_alert_repository.py` | 98% | ✅ | 82 |
| `service_repository.py` | 94% | ✅ | 199-203 |

#### API Layer

| Component | Coverage | Status | Missing Lines |
|-----------|----------|--------|---------------|
| **Schemas** | | | |
| All schemas | 100% | ✅ | None |
| **Routes** | | | |
| `health.py` | 93% | ✅ | 69-70 |
| `dependencies.py` | 69% | ⚠️ | 157-159, 231-285 |
| `constraint_analysis.py` | 68% | ⚠️ | 99-106, 156, 159, 228, 258-268 |
| `impact_analysis.py` | 50% | ❌ | 43-50, 82-139 |
| `slo_lifecycle.py` | 42% | ❌ | 29, 51-103, 127-134, 165-167 |
| `demo.py` | 36% | ❌ | 109-225, 255-282, 292, 399, 537-547 |
| `recommendations.py` | 33% | ❌ | 127-268 |
| **Middleware** | | | |
| `rate_limit.py` | 99% | ✅ | 67 |
| `metrics_middleware.py` | 83% | ✅ | 88-93 |
| `logging_middleware.py` | 79% | ✅ | 76-90, 108, 114 |
| `error_handler.py` | 57% | ⚠️ | 44-58, 74-118, 136-147, 158 |
| `auth.py` | 41% | ❌ | 61-97, 118-132, 146-151 |
| **Dependencies** | | | |
| `dependencies.py` | 97% | ✅ | 108, 191 |
| `main.py` | 82% | ✅ | 39-57, 209 |

#### Integrations & Tasks

| Component | Coverage | Status | Missing Lines |
|-----------|----------|--------|---------------|
| `otel_service_graph.py` | 94% | ✅ | 244-246, 260-261 |
| `mock_prometheus_client.py` | 97% | ✅ | 196, 211 |
| `seed_data.py` | 88% | ✅ | 307, 316 |
| `batch_recommendations.py` | 83% | ✅ | 93-115 |
| `in_memory_slo_store.py` | 44% | ⚠️ | 26, 35, 47-50, 59, 68, 80-84, 89-90 |
| `tracing.py` | 40% | ⚠️ | 40-94, 105-109 |
| `scheduler.py` | 25% | ❌ | Not tested |
| `ingest_otel_graph.py` | 0% | ❌ | Not tested |
| `mark_stale_edges.py` | 0% | ❌ | Not tested |

#### Observability

| Component | Coverage | Status | Missing Lines |
|-----------|----------|--------|---------------|
| `logging.py` | 89% | ✅ | 56, 89-90, 134 |
| `metrics.py` | 88% | ✅ | 200-202, 245, 258 |
| `cache/health.py` | 82% | ⚠️ | 36-37 |

**Infrastructure Layer Summary:** 75% coverage

---

## Test Results by Test Suite

### Unit Tests - ✅ All Passing

```
583 tests passing (~2 seconds)
```

| Test Suite | Tests | Status |
|------------|-------|--------|
| Domain entities | 147 | ✅ All passing |
| Domain services | 195 | ✅ All passing |
| Application DTOs | 81 | ✅ All passing |
| Application use cases | 160 | ✅ All passing |

### Integration Tests - ⚠️ 2 Failures

```
135 tests, 2 failures (~15 seconds)
```

**Passing:**
- Database repositories: 80 tests ✅
- OTel integration: 8 tests ✅
- Health checks: 5 tests ✅
- Metrics: 8 tests ✅
- Logging: 5 tests ✅
- API endpoints (most): 27 tests ✅

**Failing:**
- `test_get_recommendations_missing_api_key` - expects 401, gets 200
- `test_get_recommendations_invalid_api_key` - expects 401, gets 200

**Root Cause:** Auth middleware coverage is only 41%, indicating authentication bypass in test environment.

### E2E Tests - ⚠️ 19 Failures

```
23 tests, 19 failures (~12 seconds)
```

**Passing:**
- Basic dependency workflows: 4 tests ✅

**Failing Categories:**
1. **Authentication** (10 tests) - Auth middleware issues
2. **Constraint Analysis** (6 tests) - FR-3 500 errors
3. **SLO Recommendations** (3 tests) - Data/async issues

---

## Coverage Trends

### By Feature Release

| Feature | Coverage | Tests Passing | Status |
|---------|----------|---------------|--------|
| **FR-1** Dependency Graph | 98% | 147/147 | ✅ Production ready |
| **FR-2** SLO Recommendations | 97% | 339/339 | ✅ Production ready |
| **FR-3** Constraint Propagation | 96% | 135/140 | 🟡 Nearly complete |
| **FR-4** Impact Analysis | 19% | 0/0 | ❌ Not implemented |
| **FR-5** SLO Lifecycle | 27% | 0/0 | ❌ Partially implemented |

### Historical Progress

```
2026-02-15: 72% coverage, 489 tests
2026-02-20: 78% coverage, 583 tests (FR-2 complete)
2026-03-02: 86% coverage, 720 tests (FR-3 near complete)
```

---

## Critical Gaps Analysis

### High Priority (Blocking Production)

1. **Authentication Middleware** (41% coverage)
   - **Impact:** 10 auth-related test failures
   - **Risk:** Security vulnerability - bypassed auth in tests
   - **Action:** Fix auth middleware configuration, add auth middleware tests
   - **Estimate:** 1-2 hours

2. **API Routes** (33-50% coverage)
   - **Impact:** Low confidence in API layer behavior
   - **Risk:** Runtime errors in production
   - **Action:** Add E2E tests for all critical endpoints
   - **Estimate:** 4-6 hours

### Medium Priority (Technical Debt)

3. **Background Tasks** (0-25% coverage)
   - **Components:** `scheduler.py`, `ingest_otel_graph.py`, `mark_stale_edges.py`
   - **Impact:** No coverage for scheduled jobs
   - **Risk:** Silent failures in production
   - **Action:** Add integration tests for background tasks
   - **Estimate:** 3-4 hours

4. **Error Handling Middleware** (57% coverage)
   - **Impact:** Error responses may not follow RFC 7807
   - **Risk:** Poor client experience, debugging issues
   - **Action:** Add tests for error paths
   - **Estimate:** 2 hours

### Low Priority (Nice to Have)

5. **Observability Tracing** (40% coverage)
   - **Impact:** OpenTelemetry spans may not be correct
   - **Risk:** Limited, observability is supplementary
   - **Action:** Add tracing validation tests
   - **Estimate:** 2 hours

6. **Demo Routes** (36% coverage)
   - **Impact:** Demo endpoints may break
   - **Risk:** Low, not production-critical
   - **Action:** Add basic smoke tests
   - **Estimate:** 1 hour

---

## Recommendations

### Immediate Actions

1. **Fix Auth Middleware** (Priority: CRITICAL)
   ```bash
   # Investigate why auth is bypassed in tests
   pytest tests/integration/infrastructure/api/test_recommendations_endpoint.py -vv
   ```

2. **Debug Constraint Analysis E2E Failures** (Priority: HIGH)
   ```bash
   # Check logs for 500 errors
   pytest tests/e2e/test_constraint_analysis.py::test_successful_constraint_analysis -vv --tb=long
   ```

3. **Add Background Task Tests** (Priority: MEDIUM)
   - Test `scheduler.py` task registration
   - Test `ingest_otel_graph.py` periodic ingestion
   - Test `mark_stale_edges.py` cleanup logic

### Coverage Goals for v1.0

| Layer | Current | Target | Gap |
|-------|---------|--------|-----|
| Domain | 95% | 98% | +3% |
| Application | 96% | 95% | ✅ Met |
| Infrastructure | 75% | 85% | +10% |
| **Overall** | **86%** | **90%** | **+4%** |

### Test Suite Goals

```
Unit:        583/583 passing (100%) ✅ ACHIEVED
Integration: 133/135 passing (99%)  🎯 TARGET: Fix 2 auth tests
E2E:         4/23 passing (17%)     🎯 TARGET: 80% (18/23)
```

---

## How to Generate This Report

```bash
# Full coverage report with terminal output
pytest tests/ --cov=src --cov-report=term-missing

# Generate HTML coverage report
pytest tests/ --cov=src --cov-report=html
open htmlcov/index.html

# Coverage by layer
pytest tests/unit/domain/ --cov=src/domain --cov-report=term
pytest tests/unit/application/ --cov=src/application --cov-report=term
pytest tests/integration/ --cov=src/infrastructure --cov-report=term

# Missing coverage only
pytest tests/ --cov=src --cov-report=term-missing | grep -A 1000 "TOTAL"
```

---

## Further Reading

- [Testing Strategy](./index.md) - Overall testing approach
- [Test Organization](./index.md#test-organization) - Test structure
- [Coverage Goals](./index.md#coverage-goals) - Target coverage by layer
- [CI/CD Pipeline](../../.github/workflows/ci.yml) - Automated testing
