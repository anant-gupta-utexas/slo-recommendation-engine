# Constraint Propagation Developer Guide

> **Last Updated:** 2026-02-17
> **Feature:** FR-3 — Dependency-Aware Constraint Propagation
> **Status:** Nearly Complete (5 E2E tests need debugging)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [API Reference](#api-reference)
- [Data Model](#data-model)
- [Algorithms](#algorithms)
- [Configuration](#configuration)
- [Observability](#observability)
- [Testing](#testing)
- [Extending the System](#extending-the-system)
- [Troubleshooting](#troubleshooting)

---

## Overview

FR-3 extends FR-2's composite availability math to provide advanced constraint analysis across service dependency chains. While FR-2 **generates** SLO recommendations, FR-3 **validates** whether those targets are achievable and explains **why or why not**.

### Key Questions FR-3 Answers

1. **"Is my desired SLO achievable?"** — Compares the composite availability bound against the target
2. **"What's consuming my error budget?"** — Per-dependency breakdown of error budget consumption
3. **"Which dependencies are risky?"** — Flags dependencies consuming >30% of the error budget
4. **"What should I do about it?"** — Provides actionable remediation guidance (10x rule, redundancy, async conversion)

### Example Scenario

A `checkout-service` targets 99.9% availability (43.2 minutes of error budget per month). It has three hard sync dependencies:

| Dependency | Availability | Budget Consumed | Risk |
|-----------|-------------|-----------------|------|
| payment-service | 99.95% | 50% | HIGH |
| external-payment-api | 99.60% | 400% | HIGH |
| inventory-service | 99.90% | 100% | HIGH |

The composite bound is 99.45% — the target of 99.9% is **unachievable**. FR-3 detects this and suggests remediation.

---

## Architecture

FR-3 builds on FR-1 (dependency graph) and FR-2 (composite math, telemetry) without duplicating functionality:

```
┌──────────────────────────────────────────────────────────────┐
│  Infrastructure Layer                                         │
│  ├── routes/constraint_analysis.py   2 GET endpoints         │
│  ├── schemas/constraint_analysis_schema.py  Pydantic v2      │
│  └── migration: service_type + published_sla on services     │
├──────────────────────────────────────────────────────────────┤
│  Application Layer                                            │
│  ├── dtos/constraint_analysis_dto.py     9 dataclasses       │
│  ├── use_cases/run_constraint_analysis.py   11-step pipeline │
│  └── use_cases/get_error_budget_breakdown.py  depth=1 only   │
├──────────────────────────────────────────────────────────────┤
│  Domain Layer (FR-3 unique)                                   │
│  ├── entities/constraint_analysis.py  ConstraintAnalysis etc.│
│  ├── services/external_api_buffer_service.py                 │
│  ├── services/error_budget_analyzer.py                       │
│  └── services/unachievable_slo_detector.py                   │
│                                                               │
│  Domain Layer (reused from FR-1/FR-2)                        │
│  ├── CompositeAvailabilityService (FR-2)                     │
│  ├── GraphTraversalService (FR-1)                            │
│  ├── TelemetryQueryServiceInterface (FR-2)                   │
│  └── ServiceRepository, DependencyRepository (FR-1)          │
└──────────────────────────────────────────────────────────────┘
```

### How FR-3 Extends FR-2

FR-3 does **not** modify FR-2 code. It consumes FR-2's `CompositeAvailabilityService` output and adds three new analysis layers:

1. **External API Buffer** — Adjusts external dependency availability using pessimistic buffers
2. **Error Budget Analysis** — Breaks down the composite bound into per-dependency budget consumption
3. **Unachievability Detection** — Compares composite bound against desired target with guidance

---

## API Reference

### `GET /api/v1/services/{service_id}/constraint-analysis`

Full dependency-aware constraint analysis including composite bounds, error budget breakdown, and unachievable SLO warnings.

**Authentication:** `Authorization: Bearer <api-key>`
**Rate Limit:** 30 req/min

#### Query Parameters

| Parameter | Type | Default | Validation | Description |
|-----------|------|---------|------------|-------------|
| `desired_target_pct` | float | `99.9` | 90.0-99.9999 | Desired SLO target (%) |
| `lookback_days` | integer | `30` | 7-365 | Telemetry data window |
| `max_depth` | integer | `3` | 1-10 | Dependency chain depth |

#### Example Request

```bash
curl -H "Authorization: Bearer your-api-key" \
  "http://localhost:8000/api/v1/services/checkout-service/constraint-analysis?desired_target_pct=99.99&lookback_days=30"
```

#### Example Response — Achievable SLO (200 OK)

```json
{
  "service_id": "checkout-service",
  "analyzed_at": "2026-02-15T14:00:00Z",
  "composite_availability_bound_pct": 99.70,
  "is_achievable": true,
  "has_high_risk_dependencies": true,
  "dependency_chain_depth": 3,
  "total_hard_dependencies": 3,
  "total_soft_dependencies": 1,
  "total_external_dependencies": 1,
  "lookback_days": 30,
  "error_budget_breakdown": {
    "service_id": "checkout-service",
    "slo_target_pct": 99.9,
    "total_error_budget_minutes": 43.2,
    "self_consumption_pct": 8.0,
    "dependency_risks": [
      {
        "service_id": "payment-service",
        "availability_pct": 99.95,
        "error_budget_consumption_pct": 50.0,
        "risk_level": "high",
        "is_external": false,
        "communication_mode": "sync",
        "criticality": "hard"
      },
      {
        "service_id": "external-payment-api",
        "availability_pct": 99.50,
        "error_budget_consumption_pct": 500.0,
        "risk_level": "high",
        "is_external": true,
        "communication_mode": "sync",
        "criticality": "hard",
        "published_sla_pct": 99.99,
        "observed_availability_pct": 99.60,
        "effective_availability_note": "Using min(observed 99.60%, published×adj 99.89%) = 99.60%"
      }
    ],
    "high_risk_dependencies": ["payment-service", "external-payment-api"],
    "total_dependency_consumption_pct": 650.0
  },
  "unachievable_warning": null,
  "soft_dependency_risks": ["recommendation-service"],
  "scc_supernodes": []
}
```

#### Example Response — Unachievable SLO (200 OK with warning)

```json
{
  "service_id": "checkout-service",
  "composite_availability_bound_pct": 99.70,
  "is_achievable": false,
  "unachievable_warning": {
    "desired_target_pct": 99.99,
    "composite_bound_pct": 99.70,
    "gap_pct": 0.29,
    "message": "The desired target of 99.99% is unachievable. Composite availability bound is 99.70% given current dependency chain.",
    "remediation_guidance": "To achieve 99.99%, each of the 3 critical dependencies must provide at least 99.9975% availability. Consider: (1) Adding redundant paths for critical deps, (2) Converting hard sync deps to async soft deps, (3) Relaxing the target to ≤99.70%.",
    "required_dep_availability_pct": 99.9975
  }
}
```

#### Error Responses

| Status | Condition |
|--------|-----------|
| 404 | Service not registered |
| 400 | Invalid query parameters or ValueError |
| 422 | No dependency data available |
| 429 | Rate limit exceeded |

---

### `GET /api/v1/services/{service_id}/error-budget-breakdown`

Lightweight error budget analysis (direct dependencies only, depth=1).

**Authentication:** `Authorization: Bearer <api-key>`
**Rate Limit:** 60 req/min

#### Query Parameters

| Parameter | Type | Default | Validation | Description |
|-----------|------|---------|------------|-------------|
| `slo_target_pct` | float | `99.9` | 90.0-99.9999 | SLO target for budget calculation |
| `lookback_days` | integer | `30` | 7-365 | Telemetry data window |

#### Example Request

```bash
curl -H "Authorization: Bearer your-api-key" \
  "http://localhost:8000/api/v1/services/checkout-service/error-budget-breakdown?slo_target_pct=99.9"
```

#### Example Response (200 OK)

```json
{
  "service_id": "checkout-service",
  "analyzed_at": "2026-02-15T14:00:00Z",
  "slo_target_pct": 99.9,
  "total_error_budget_minutes": 43.2,
  "self_consumption_pct": 8.0,
  "dependency_risks": [...],
  "high_risk_dependencies": ["external-payment-api"],
  "total_dependency_consumption_pct": 500.0
}
```

---

## Data Model

### Schema Changes to `services` Table

FR-3 adds two columns via Alembic migration (`b8ca908bf04a`):

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `service_type` | VARCHAR(20) | `'internal'` | `'internal'` or `'external'` |
| `published_sla` | DECIMAL(8,6) | NULL | Published SLA ratio for external services |

A partial index `idx_services_external` is created for external service lookups.

**Backward Compatibility:** All existing services default to `internal` with NULL published_sla.

### Domain Entities

Key entities in `src/domain/entities/constraint_analysis.py`:

- **`ConstraintAnalysis`** — Complete analysis result (composite bound, budget breakdown, warnings)
- **`ErrorBudgetBreakdown`** — Per-dependency budget consumption with risk classification
- **`DependencyRiskAssessment`** — Single dependency's availability, consumption, and risk level
- **`UnachievableWarning`** — Warning when target exceeds composite bound, with remediation
- **`ExternalProviderProfile`** — Published SLA + observed data for adaptive buffer
- **`ServiceType`** enum — INTERNAL, EXTERNAL
- **`RiskLevel`** enum — LOW, MODERATE, HIGH

---

## Algorithms

### External API Adaptive Buffer

External services often publish optimistic SLAs. FR-3 applies a pessimistic adjustment:

```
published_adjusted = 1 - (1 - published_sla) × 11

effective = min(observed_availability, published_adjusted)
```

**Fallback chain:**
1. Both observed and published → `min(observed, published_adjusted)`
2. Observed only → `observed`
3. Published only → `published_adjusted`
4. Neither → `0.999` (conservative default)

**Example:** Published SLA of 99.99%
```
published_adjusted = 1 - (1 - 0.9999) × 11 = 1 - 0.0011 = 0.9989 (99.89%)
```

### Error Budget Consumption

For each hard sync dependency:

```
consumption = (1 - dep_availability) / (1 - slo_target / 100)
```

| SLO Target | Dep Availability | Budget Consumed |
|-----------|-----------------|-----------------|
| 99.9% | 99.5% | 500% |
| 99.9% | 99.95% | 50% |
| 99.9% | 99.99% | 10% |
| 100% | any | ∞ (capped at 999999.99) |

### Risk Classification

| Risk Level | Consumption Threshold |
|-----------|----------------------|
| LOW | < 20% |
| MODERATE | 20-30% |
| HIGH | > 30% |

### Unachievable SLO Detection

A target is **unachievable** when `composite_bound < desired_target / 100`.

The **10x Rule** computes what each dependency needs:
```
required_per_dep = 1 - (1 - target) / (n_hard_deps + 1)
```

**Example:** 99.99% target with 3 hard deps → each needs 99.9975%

### Composite Availability (from FR-2)

Serial hard dependencies:
```
R_composite = R_self × R_dep1 × R_dep2 × ... × R_depN
```

Parallel redundant:
```
R_group = 1 - (1 - R_primary)(1 - R_fallback)
```

---

## Configuration

FR-3 introduces no new configuration variables. Query parameters control all behavior:
- `desired_target_pct` / `slo_target_pct` — SLO target for analysis
- `lookback_days` — Telemetry window
- `max_depth` — Dependency chain traversal depth

Fixed constants:
- Error budget risk threshold: 30% (HIGH)
- Moderate risk threshold: 20%
- Pessimistic multiplier for external SLAs: 10× unavailability
- Default external availability: 99.9%
- Monthly minutes for budget calculation: 43,200 (30 days)

---

## Observability

### Prometheus Metrics

| Metric | Type | Alert Threshold |
|--------|------|----------------|
| `slo_engine_constraint_analysis_duration_seconds` | Histogram | p95 > 2s |
| `slo_engine_error_budget_breakdown_duration_seconds` | Histogram | p95 > 1s |
| `slo_engine_unachievable_slos_detected_total` | Counter | N/A |
| `slo_engine_high_risk_dependencies_detected_total` | Counter | N/A |

### Performance Targets

| Operation | Target | Measured |
|-----------|--------|----------|
| Constraint analysis | < 2s (p95) | ~280ms |
| Error budget breakdown | < 1s (p95) | ~50ms |

---

## Testing

### Test Distribution

| Layer | Tests | Coverage |
|-------|-------|----------|
| Domain entities (constraint_analysis) | 24 | >95% |
| Domain services (buffer, budget, detector) | 65 | >95% |
| Domain shared (Phase 0: SLI data, composite) | 74 | 100% |
| Application DTOs | 19 | 100% |
| Application use cases | 17+ | >90% |
| Infrastructure schemas | 19 | 100% |
| E2E | 8/13 passing | — |

### Running Tests

```bash
# All FR-3 domain tests
pytest tests/unit/domain/entities/test_constraint_analysis.py \
       tests/unit/domain/services/test_external_api_buffer_service.py \
       tests/unit/domain/services/test_error_budget_analyzer.py \
       tests/unit/domain/services/test_unachievable_slo_detector.py -v

# Application layer
pytest tests/unit/application/dtos/test_constraint_analysis_dto.py -v

# Schemas
pytest tests/unit/infrastructure/api/schemas/test_constraint_analysis_schema.py -v

# E2E (requires docker-compose up)
pytest tests/e2e/test_constraint_analysis.py -v
```

---

## Extending the System

### Adding Configurable Risk Thresholds

Currently the 30% HIGH threshold is a fixed constant. To make it configurable per-service:

1. Add a `risk_threshold` field to the `services` table
2. Pass the threshold through the use case to `ErrorBudgetAnalyzer`
3. Update `classify_risk()` to accept an optional threshold parameter

### Adding Latency Constraint Propagation

Currently FR-3 only propagates availability constraints. Latency is excluded because percentiles are non-additive. If needed:
1. Consider Monte Carlo simulation (FR-15) for mixed topologies
2. Or use end-to-end trace-based measurement from Tempo (FR-6)

### Supporting Active SLO Targets (FR-5)

When FR-5 adds active SLO storage:
1. Update `RunConstraintAnalysisUseCase` Step 2 to query active SLOs
2. Use the active SLO target as the default `desired_target_pct` when not provided

---

## Troubleshooting

### Common Issues

**"Service has no dependencies registered" (422)**
- The service exists but has no downstream edges in the dependency graph
- Ingest dependencies via FR-1: `POST /api/v1/services/{service_id}/dependencies`

**External service not using adaptive buffer**
- Verify the service has `service_type: "external"` in the database
- Check that `published_sla` is set (as a ratio, e.g., 0.9999 for 99.99%)
- The ingestion API accepts `service_type` in node metadata

**Budget consumption > 100%**
- This is expected. A single dependency can consume more than 100% of error budget if its unavailability exceeds the total budget. For example, at SLO 99.9% (budget = 0.1%), a dependency at 99.5% (unavailability = 0.5%) consumes 500%.

**"Unachievable" but seems close**
- Even small gaps matter at high nines. A gap of 0.01% between 99.99% target and 99.98% bound means 4.3 more minutes of downtime per month.
- The 10x rule remediation gives concrete per-dependency targets.

**SCC supernodes in response**
- Circular dependencies are detected by FR-1. FR-3 reports them in `scc_supernodes` and uses the weakest-link member's availability for the supernode in composite math.
