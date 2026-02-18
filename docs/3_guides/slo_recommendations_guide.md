# SLO Recommendations Developer Guide

> **Last Updated:** 2026-02-17
> **Feature:** FR-2 — SLO Recommendation Generation
> **Status:** Complete (All 4 Phases)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [API Reference](#api-reference)
- [Data Model](#data-model)
- [Algorithms](#algorithms)
- [Background Tasks](#background-tasks)
- [Configuration](#configuration)
- [Observability](#observability)
- [Testing](#testing)
- [Extending the System](#extending-the-system)
- [Troubleshooting](#troubleshooting)

---

## Overview

The SLO Recommendation Generation engine is the core value-producing feature of the system. Given a service registered in the dependency graph (FR-1), it computes **availability** and **latency** SLO recommendations across three tiers:

| Tier | Availability Basis | Latency Basis | Dependency Cap |
|------|-------------------|---------------|----------------|
| **Conservative** | p99.9 of rolling windows | p99.9 + noise margin | Capped by composite bound |
| **Balanced** | p99 of rolling windows | p99 + noise margin | Capped by composite bound |
| **Aggressive** | p95 of rolling windows | p95 (no margin) | **NOT capped** (shows potential) |

Each recommendation includes:
- **Tier targets** with confidence intervals and breach probability estimates
- **Error budget** in monthly minutes (availability only)
- **Weighted feature attribution** explaining what factors drove the recommendation
- **Dependency impact** showing composite bounds and bottleneck services
- **Data quality metadata** including completeness, gaps, and cold-start flags

### How It Works (High Level)

```
Service registered in graph (FR-1)
        │
        ▼
┌─────────────────────────┐
│ Telemetry Query         │  Query historical availability/latency
│ (Mock Prometheus)       │  from Prometheus (mock stub in MVP)
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ Dependency Traversal    │  Walk downstream graph (depth=3)
│ (FR-1 GraphTraversal)   │  to find hard/soft dependencies
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ Composite Bound         │  R_composite = R_self × Π(R_hard_dep_i)
│ Computation             │  Identify bottleneck service
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ Tier Computation        │  Percentile-based + dependency cap
│ + Attribution           │  Weighted feature contribution
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ Store in PostgreSQL     │  Pre-computed, 24h TTL
│ (slo_recommendations)   │  Supersedes previous active recs
└─────────────────────────┘
```

---

## Architecture

### Clean Architecture Layers

FR-2 follows the same three-layer Clean Architecture pattern as FR-1:

```
┌──────────────────────────────────────────────────────────────┐
│  Infrastructure Layer                                         │
│  ├── routes/recommendations.py     GET /slo-recommendations  │
│  ├── schemas/slo_recommendation_schema.py    Pydantic v2     │
│  ├── models.py          SloRecommendationModel + SliAggregate│
│  ├── repositories/slo_recommendation_repository.py           │
│  ├── telemetry/mock_prometheus_client.py                     │
│  └── tasks/batch_recommendations.py    APScheduler (24h)     │
├──────────────────────────────────────────────────────────────┤
│  Application Layer                                            │
│  ├── dtos/slo_recommendation_dto.py     11 dataclasses       │
│  ├── use_cases/generate_slo_recommendation.py   12-step pipe │
│  ├── use_cases/get_slo_recommendation.py        retrieval    │
│  └── use_cases/batch_compute_recommendations.py  batch all   │
├──────────────────────────────────────────────────────────────┤
│  Domain Layer                                                 │
│  ├── entities/slo_recommendation.py   SloRecommendation etc. │
│  ├── entities/sli_data.py             AvailabilitySliData etc.│
│  ├── services/availability_calculator.py                     │
│  ├── services/latency_calculator.py                          │
│  ├── services/composite_availability_service.py              │
│  ├── services/weighted_attribution_service.py                │
│  └── repositories/  (interfaces only)                        │
└──────────────────────────────────────────────────────────────┘
```

### Dependency Injection Chain

```
GET /slo-recommendations
  └─> GetSloRecommendationUseCase
       ├─> ServiceRepository
       ├─> SloRecommendationRepository
       └─> GenerateSloRecommendationUseCase
            ├─> ServiceRepository
            ├─> DependencyRepository
            ├─> SloRecommendationRepository
            ├─> MockPrometheusClient
            ├─> AvailabilityCalculator
            ├─> LatencyCalculator
            ├─> CompositeAvailabilityService
            ├─> WeightedAttributionService
            └─> GraphTraversalService
```

---

## API Reference

### `GET /api/v1/services/{service_id}/slo-recommendations`

Retrieve pre-computed or freshly generated SLO recommendations for a service.

**Authentication:** `Authorization: Bearer <api-key>`
**Rate Limit:** 60 req/min

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `service_id` | string | Business identifier (e.g., `payment-service`) |

#### Query Parameters

| Parameter | Type | Default | Validation | Description |
|-----------|------|---------|------------|-------------|
| `sli_type` | string | `all` | `availability`, `latency`, `all` | Filter by SLI type |
| `lookback_days` | integer | `30` | 7-365 | Historical data window |
| `force_regenerate` | boolean | `false` | — | Bypass cache, recompute fresh |

#### Example Request

```bash
curl -H "Authorization: Bearer your-api-key" \
  "http://localhost:8000/api/v1/services/checkout-service/slo-recommendations?sli_type=availability&lookback_days=30"
```

#### Example Response (200 OK)

```json
{
  "service_id": "checkout-service",
  "generated_at": "2026-02-15T10:30:00Z",
  "lookback_window": {
    "start": "2026-01-16T00:00:00Z",
    "end": "2026-02-15T00:00:00Z"
  },
  "recommendations": [
    {
      "sli_type": "availability",
      "metric": "error_rate",
      "tiers": {
        "conservative": {
          "target": 99.5,
          "error_budget_monthly_minutes": 219.6,
          "estimated_breach_probability": 0.02,
          "confidence_interval": [99.3, 99.7]
        },
        "balanced": {
          "target": 99.9,
          "error_budget_monthly_minutes": 43.8,
          "estimated_breach_probability": 0.08,
          "confidence_interval": [99.8, 99.95]
        },
        "aggressive": {
          "target": 99.95,
          "error_budget_monthly_minutes": 21.9,
          "estimated_breach_probability": 0.18,
          "confidence_interval": [99.9, 99.99]
        }
      },
      "explanation": {
        "summary": "checkout-service achieved 99.92% availability over 30 days...",
        "feature_attribution": [
          {"feature": "historical_availability_mean", "contribution": 0.42},
          {"feature": "downstream_dependency_risk", "contribution": 0.28},
          {"feature": "external_api_reliability", "contribution": 0.18},
          {"feature": "deployment_frequency", "contribution": 0.12}
        ],
        "dependency_impact": {
          "composite_availability_bound": 99.70,
          "bottleneck_service": "external-payment-api",
          "bottleneck_contribution": "Consumes 50% of error budget at 99.9% target",
          "hard_dependency_count": 3,
          "soft_dependency_count": 1
        }
      },
      "data_quality": {
        "data_completeness": 0.97,
        "telemetry_gaps": [],
        "confidence_note": "Based on 30 days of continuous data with 97% completeness",
        "is_cold_start": false,
        "lookback_days_actual": 30
      }
    }
  ]
}
```

#### Error Responses

| Status | Condition |
|--------|-----------|
| 404 | Service not registered |
| 400 | Invalid query parameters |
| 401 | Missing or invalid API key |
| 422 | Insufficient telemetry data |
| 429 | Rate limit exceeded |

---

## Data Model

### Database Tables

#### `slo_recommendations`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `service_id` | UUID (FK → services) | Target service |
| `sli_type` | VARCHAR(20) | `availability` or `latency` |
| `metric` | VARCHAR(50) | e.g., `error_rate`, `p99_response_time_ms` |
| `tiers` | JSONB | Three-tier recommendation data |
| `explanation` | JSONB | Attribution + dependency impact |
| `data_quality` | JSONB | Completeness, gaps, confidence |
| `lookback_window_start` | TIMESTAMPTZ | Window start |
| `lookback_window_end` | TIMESTAMPTZ | Window end |
| `generated_at` | TIMESTAMPTZ | Creation timestamp |
| `expires_at` | TIMESTAMPTZ | TTL (generated_at + 24h) |
| `status` | VARCHAR(20) | `active`, `superseded`, `expired` |

**Indexes:**
- `idx_slo_rec_service_active` — primary lookup (service_id, status) WHERE active
- `idx_slo_rec_expires` — expiry cleanup (expires_at) WHERE active
- `idx_slo_rec_sli_type` — type filter (service_id, sli_type, status)

#### `sli_aggregates`

Pre-aggregated SLI metrics (populated by FR-6 when real Prometheus integration is added):

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `service_id` | UUID (FK → services) | Target service |
| `sli_type` | VARCHAR(30) | SLI type (availability, latency_p50, etc.) |
| `time_window` | VARCHAR(10) | `1h`, `1d`, `7d`, `28d`, `90d` |
| `value` | DECIMAL | Metric value |
| `sample_count` | BIGINT | Number of samples |
| `computed_at` | TIMESTAMPTZ | Computation time |

### Domain Entities

Key entities in `src/domain/entities/slo_recommendation.py`:

- **`SloRecommendation`** — Top-level entity with service_id, tiers, explanation, data quality, status lifecycle
- **`RecommendationTier`** — Single tier (target, breach probability, confidence interval, error budget)
- **`FeatureAttribution`** — Feature name + contribution weight (sums to 1.0)
- **`DependencyImpact`** — Composite bound, bottleneck service, dep counts
- **`DataQuality`** — Completeness, gaps, cold-start flag
- **`Explanation`** — Summary string + attribution list + dependency impact

---

## Algorithms

### Availability Tier Computation

```python
sorted_rolling = sorted(rolling_availability_values)

conservative_raw = percentile(sorted_rolling, 0.1)   # p99.9 floor
balanced_raw     = percentile(sorted_rolling, 1.0)    # p99
aggressive_raw   = percentile(sorted_rolling, 5.0)    # p95

conservative = min(conservative_raw, composite_bound) * 100
balanced     = min(balanced_raw, composite_bound) * 100
aggressive   = aggressive_raw * 100  # NOT capped
```

### Composite Availability Bound

For serial hard dependencies:
```
R_composite = R_self × R_dep1 × R_dep2 × ... × R_depN
```

For parallel redundant paths:
```
R_group = 1 - (1 - R_primary)(1 - R_fallback)
```

### Bootstrap Confidence Intervals

1000 bootstrap resamples of rolling availability values, reporting 2.5th and 97.5th percentiles.

### Breach Probability

```python
breach_prob = count(r < target for r in rolling_values) / len(rolling_values)
```

### Error Budget

```
monthly_budget_minutes = (1 - target/100) × 43200
# 99.9% → 43.2 minutes/month
```

### Weighted Feature Attribution

Fixed MVP weights normalized to sum to 1.0:

| Availability Feature | Weight |
|---------------------|--------|
| historical_availability_mean | 0.40 |
| downstream_dependency_risk | 0.30 |
| external_api_reliability | 0.15 |
| deployment_frequency | 0.15 |

| Latency Feature | Weight |
|----------------|--------|
| p99_latency_historical | 0.50 |
| call_chain_depth | 0.22 |
| noisy_neighbor_margin | 0.15 |
| traffic_seasonality | 0.13 |

### Cold-Start Detection

When data completeness < 90% for the standard 30-day window, the system extends lookback to up to 90 days. The response includes `is_cold_start: true` and an adjusted `confidence_note`.

---

## Background Tasks

### Batch Recommendation Computation

An APScheduler job runs every 24 hours (configurable via `slo_batch_interval_hours`) to pre-compute recommendations for all registered services.

**Behavior:**
- Fetches all non-discovered services via `ServiceRepository.list_all()`
- Processes concurrently with `asyncio.gather()` + semaphore(20)
- Continues on per-service failure; collects errors
- Emits Prometheus metrics: `slo_batch_recommendations_total`, `slo_batch_recommendations_duration_seconds`
- Never raises exceptions (prevents scheduler from stopping)

**Manual Trigger:**
```bash
# Force regeneration for a specific service via API
curl -H "Authorization: Bearer your-key" \
  "http://localhost:8000/api/v1/services/payment-service/slo-recommendations?force_regenerate=true"
```

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `slo_batch_interval_hours` | `24` | Batch job frequency |
| Semaphore limit | `20` | Max concurrent batch computations |
| Lookback window | `30` days | Standard analysis window |
| Extended lookback | `90` days | Cold-start fallback window |
| Completeness threshold | `0.90` | Triggers extended lookback |
| Default dep availability | `0.999` | For dependencies without telemetry |
| Recommendation expiry | `24` hours | TTL before auto-expiration |

---

## Observability

### Prometheus Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `slo_engine_recommendation_generation_duration_seconds` | Histogram | Single recommendation generation time |
| `slo_engine_recommendations_generated_total` | Counter | Total recommendations generated |
| `slo_engine_slo_batch_recommendations_total` | Counter | Batch runs by status (success/failure) |
| `slo_engine_slo_batch_recommendations_duration_seconds` | Histogram | Batch execution duration |
| `slo_engine_recommendation_retrieval_duration_seconds` | Histogram | Pre-computed retrieval time |

### Performance Targets

| Operation | Target | Typical |
|-----------|--------|---------|
| Pre-computed retrieval (p95) | < 500ms | ~100ms |
| On-demand generation (p95) | < 5s | ~300-500ms |
| Batch (5000 services) | < 30 minutes | Varies |

---

## Testing

### Test Distribution

| Layer | Test File | Count | Type |
|-------|-----------|-------|------|
| Domain entities | `test_slo_recommendation.py`, `test_sli_data.py` | 56 | Unit |
| Domain services | `test_availability_calculator.py`, etc. | 111 | Unit |
| Application DTOs | `test_slo_recommendation_dto.py` | 25 | Unit |
| Application use cases | `test_generate_*.py`, `test_get_*.py`, `test_batch_*.py` | 38 | Unit |
| Infrastructure schemas | `test_slo_recommendation_schema.py` | 37 | Unit |
| Infrastructure telemetry | `test_mock_prometheus_client.py` | 24 | Unit |
| Infrastructure DB | `test_slo_recommendation_repository.py` | 12 | Integration |
| Infrastructure API | `test_recommendations_endpoint.py` | 12 | Integration |
| Infrastructure tasks | `test_batch_recommendations.py` | 11 | Integration |
| E2E | `test_slo_recommendations.py` | 16 | E2E |

### Running Tests

```bash
# Fast: unit tests only (no docker needed)
pytest tests/unit/domain/ tests/unit/application/ -v

# Integration (requires docker-compose up -d db redis)
pytest tests/integration/ -v

# E2E (requires docker-compose up)
pytest tests/e2e/test_slo_recommendations.py -v
```

---

## Extending the System

### Adding a New SLI Type

1. Add enum value to `SliType` in `src/domain/entities/slo_recommendation.py`
2. Create a new calculator service in `src/domain/services/` (follow `availability_calculator.py` pattern)
3. Add weights to `WeightedAttributionService` for the new type
4. Update `GenerateSloRecommendationUseCase` to call the new calculator
5. Update Pydantic schemas and migration CHECK constraints

### Replacing Mock Prometheus

When FR-6 (real Prometheus integration) is implemented:
1. Create `src/infrastructure/telemetry/prometheus_client.py` implementing `TelemetryQueryServiceInterface`
2. Update `dependencies.py` to inject the real client based on a config toggle
3. No domain or application code changes required (dependency inversion)

### Adding Redis Caching

If retrieval latency needs improvement:
1. Add a caching layer in `GetSloRecommendationUseCase` before DB lookup
2. Cache key: `slo_rec:{service_id}:{sli_type}`
3. TTL: match recommendation expiry (24h)
4. Invalidate on `force_regenerate` or batch recomputation

---

## Troubleshooting

### Common Issues

**"Service with ID 'xyz' is not registered" (404)**
- Verify the service exists: `GET /api/v1/services/{service_id}`
- Services must be ingested via FR-1's dependency graph endpoint first

**"No telemetry data available" (422)**
- Check that the service ID exists in the mock Prometheus seed data
- Default seed data covers: `payment-service`, `auth-service`, `notification-service`, `analytics-service`, `legacy-report-service`, `new-checkout-service`, `experimental-ml-service`
- Service `uninstrumented-service` returns no data (by design, for testing)

**Stale recommendations**
- Recommendations expire after 24 hours. The batch job should recompute daily.
- Use `force_regenerate=true` to get fresh results immediately.

**Cold-start: low confidence**
- If a service has < 90% data completeness for the 30-day window, the system extends to 90 days.
- Response will include `is_cold_start: true` with a confidence note.

**High breach probability**
- Breach probability > 0.1 indicates the SLO target may be too aggressive for the service's current performance.
- Consider using the Conservative tier as a starting point.
