# Technical Requirements Document (TRD)

## 1. Executive Summary

The SLO Recommendation Engine is an AI-assisted backend system built with **Python/FastAPI** following **Clean Architecture** principles. It analyzes telemetry data and structural dependencies across 500-5,000+ interconnected microservices to recommend achievable **availability and latency SLOs** for each service.

The system integrates with an existing **OpenTelemetry + Prometheus + Grafana** observability stack, queries historical metrics from Prometheus/Mimir, models service dependency graphs (stored in PostgreSQL), and exposes a RESTful API (OpenAPI 3.0) for integration into a Backstage-based internal developer platform.

**Automation model:** Semi-automated (human-on-the-loop) at launch. All SLO recommendations require explicit SRE or service-owner approval. An auto-approval rules engine enables graduation toward full automation for low-criticality services as the system builds a track record.

**MVP scope:** Availability SLOs (composite reliability math) and latency SLOs (p95/p99 via end-to-end trace analysis). Throughput and correctness SLOs are deferred post-MVP.

**Key technical decisions:**
- Query existing metric stores rather than duplicating telemetry data
- PostgreSQL with recursive CTEs for dependency graph storage (sufficient for 10,000+ edges; Neo4j deferred unless graph analytics require it)
- Phased ML approach: rule-based composite math (MVP) graduating to GNN + Temporal Fusion Transformer (Phase 5)
- SHAP-based explainability for every recommendation from day one

---

## 2. Business Context & Objectives

This section references the PRD (`docs/1_product/PRD.md`) and maps business goals to technical decisions.

### Business Goals → Technical Implications

| Business Goal | Key Metric | Technical Implication |
|---------------|------------|----------------------|
| Dependency-aware SLOs | 100% of recommendations include dependency analysis | Dependency graph must be complete, queryable, and annotated with criticality/mode. Graph traversal must execute within API latency targets. |
| Reduce SLO violations to <5% breach rate | <5% of SLO windows breach | Composite reliability math must be correct. Latency SLOs must use end-to-end measurement, not mathematical composition. Historical data windows must be sufficient (30+ days). |
| Error budget utilization 50-80% | Average across services | Recommendation algorithm must produce three tiers (Conservative/Balanced/Aggressive) calibrated against historical budget burn rates. |
| SLO adoption >80% within 90 days | Time to first SLO < 1 hour (6mo), <15 min (12mo) | API must support bulk recommendation generation. Cold-start strategy needed for services with <30 days of data. |
| Build trust for automation | Acceptance rate >70% at 12 months | Explainability is mandatory for every recommendation. Audit trail must be immutable. Feedback loop must capture accept/modify/reject rationale. |

### Success KPIs (Technical)

| KPI | Target | Measurement Method |
|-----|--------|-------------------|
| Recommendation retrieval latency (p95) | < 500ms | Application Performance Monitoring (APM) on `GET /slo-recommendations` |
| On-demand generation latency (p95) | < 5s | APM on recommendation computation pipeline |
| Dependency graph ingestion (1000 services) | < 30s | Benchmark test in CI/CD |
| System availability | 99.9% (43 min/month downtime) | Prometheus uptime monitoring |
| Data pipeline freshness | < 24 hours from telemetry to recommendation | Pipeline lag metric |

---

## 3. Functional Requirements

This section provides the detailed technical translation of each PRD functional requirement into implementable specifications.

### FR-1: Service Dependency Graph Ingestion & Management

**Corresponds to:** PRD F1

#### API Specification

**`POST /api/v1/services/dependencies`** — Bulk upsert of dependency graph

Request body:
```json
{
  "source": "manual | otel_service_graph | kubernetes | service_mesh",
  "timestamp": "2026-02-14T10:00:00Z",
  "nodes": [
    {
      "service_id": "checkout-service",
      "metadata": {
        "team": "payments",
        "criticality": "high",
        "tier": 1,
        "namespace": "production",
        "runtime": "python3.12"
      }
    }
  ],
  "edges": [
    {
      "source": "checkout-service",
      "target": "payment-service",
      "attributes": {
        "communication_mode": "sync | async",
        "criticality": "hard | soft | degraded",
        "protocol": "grpc | http | kafka",
        "timeout_ms": 5000,
        "retry_config": {
          "max_retries": 3,
          "backoff_strategy": "exponential"
        }
      }
    }
  ]
}
```

Response (202 Accepted for async processing):
```json
{
  "ingestion_id": "uuid",
  "status": "processing",
  "nodes_received": 150,
  "edges_received": 420,
  "estimated_completion_seconds": 15
}
```

**`GET /api/v1/services/{service-id}/dependencies`** — Get dependency subgraph

Query parameters:
- `direction`: `upstream | downstream | both` (default: `both`)
- `depth`: integer, max hops (default: 3, max: 10)
- `include_external`: boolean (default: `true`)

Response includes the subgraph with edge annotations and per-edge confidence scores.

#### System Behaviors

**Happy Path:**
1. Client submits dependency graph via API
2. System validates schema (JSON Schema validation)
3. System upserts nodes and edges into PostgreSQL, merging with existing data from other sources
4. System runs Tarjan's algorithm for SCC detection on the updated graph
5. System compares runtime-observed graph against declared configuration
6. System returns ingestion confirmation with any detected issues (circular deps, divergences)

**Edge Cases:**
- **Circular dependency detected:** System contracts the strongly connected component (SCC) into a logical "supernode" for SLO computation. Returns a warning with the cycle path (e.g., `["service-a", "service-b", "service-c", "service-a"]`) and a recommendation to refactor using async boundaries.
- **Partial graph submission:** System merges partial updates with existing graph. Each edge retains its discovery source and timestamp. Edges not refreshed within a configurable staleness window (default: 7 days) are marked `stale` but not deleted.
- **Conflicting edge attributes from multiple sources:** System applies a priority hierarchy: manual > service_mesh > otel_service_graph > kubernetes. Conflicts are logged and surfaced in the API response.
- **Unknown service_id in edges:** System auto-creates a placeholder node with `discovered: true` flag. Service remains in `unregistered` state until metadata is provided.
- **Graph exceeds depth limit:** When the graph contains dependency chains deeper than 10 hops, the system truncates traversal and logs a warning. Composite SLO computation uses the truncated subgraph with a reduced confidence score.

#### Data Model (PostgreSQL)

```
Table: services
  - id: UUID (PK)
  - service_id: VARCHAR(255) UNIQUE NOT NULL (business identifier)
  - metadata: JSONB NOT NULL DEFAULT '{}'
  - criticality: ENUM('critical', 'high', 'medium', 'low') DEFAULT 'medium'
  - team: VARCHAR(255)
  - discovered: BOOLEAN DEFAULT false
  - created_at: TIMESTAMPTZ NOT NULL DEFAULT NOW()
  - updated_at: TIMESTAMPTZ NOT NULL DEFAULT NOW()

Table: service_dependencies
  - id: UUID (PK)
  - source_service_id: UUID FK -> services.id
  - target_service_id: UUID FK -> services.id
  - communication_mode: ENUM('sync', 'async') NOT NULL
  - criticality: ENUM('hard', 'soft', 'degraded') NOT NULL DEFAULT 'hard'
  - protocol: VARCHAR(50)
  - timeout_ms: INTEGER
  - retry_config: JSONB
  - discovery_source: ENUM('manual', 'otel_service_graph', 'kubernetes', 'service_mesh') NOT NULL
  - confidence_score: FLOAT DEFAULT 1.0 (0.0-1.0)
  - last_observed_at: TIMESTAMPTZ NOT NULL DEFAULT NOW()
  - is_stale: BOOLEAN DEFAULT false
  - created_at: TIMESTAMPTZ NOT NULL DEFAULT NOW()
  - updated_at: TIMESTAMPTZ NOT NULL DEFAULT NOW()
  - UNIQUE(source_service_id, target_service_id, discovery_source)

Table: circular_dependency_alerts
  - id: UUID (PK)
  - cycle_path: JSONB NOT NULL (array of service_ids forming the cycle)
  - detected_at: TIMESTAMPTZ NOT NULL DEFAULT NOW()
  - status: ENUM('open', 'acknowledged', 'resolved') DEFAULT 'open'
  - acknowledged_by: VARCHAR(255)
  - resolution_notes: TEXT
```

#### Graph Traversal

Dependency subgraph queries use **PostgreSQL recursive CTEs**:

```sql
WITH RECURSIVE dependency_tree AS (
  -- Base case: direct dependencies
  SELECT target_service_id, source_service_id, 1 AS depth,
         ARRAY[source_service_id] AS path
  FROM service_dependencies
  WHERE source_service_id = :service_id AND is_stale = false

  UNION ALL

  -- Recursive case: transitive dependencies
  SELECT sd.target_service_id, sd.source_service_id, dt.depth + 1,
         dt.path || sd.source_service_id
  FROM service_dependencies sd
  JOIN dependency_tree dt ON sd.source_service_id = dt.target_service_id
  WHERE dt.depth < :max_depth
    AND sd.is_stale = false
    AND NOT sd.target_service_id = ANY(dt.path)  -- cycle prevention
)
SELECT * FROM dependency_tree;
```

Performance target: < 100ms for a 3-hop traversal on a graph of 5,000 services.

#### Circular Dependency Detection

Tarjan's algorithm runs as an **async background task** triggered after each graph ingestion:
1. Build in-memory adjacency list from `service_dependencies` table
2. Execute Tarjan's SCC algorithm (O(V + E))
3. For each SCC with |V| > 1, insert into `circular_dependency_alerts` if not already recorded
4. Mark SCCs in the graph for supernode contraction during SLO computation

---

### FR-2: SLO Recommendation Generation

**Corresponds to:** PRD F2

#### API Specification

**`GET /api/v1/services/{service-id}/slo-recommendations`**

Query parameters:
- `sli_type`: `availability | latency | all` (default: `all`)
- `lookback_days`: integer (default: 30, min: 7, max: 365)
- `force_regenerate`: boolean (default: `false`) — bypass cache and compute fresh

Response:
```json
{
  "service_id": "checkout-service",
  "generated_at": "2026-02-14T10:30:00Z",
  "lookback_window": {
    "start": "2026-01-15T00:00:00Z",
    "end": "2026-02-14T00:00:00Z"
  },
  "data_quality": {
    "data_completeness": 0.97,
    "telemetry_gaps": [],
    "confidence_note": "Based on 30 days of continuous data with 97% completeness"
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
        "summary": "checkout-service achieved 99.92% availability over 30 days. The Balanced target of 99.9% provides a 0.02% margin.",
        "feature_attribution": [
          {"feature": "historical_availability_mean", "contribution": 0.42},
          {"feature": "downstream_dependency_risk", "contribution": 0.28},
          {"feature": "external_api_reliability", "contribution": 0.18},
          {"feature": "deployment_frequency", "contribution": 0.12}
        ],
        "dependency_impact": {
          "composite_availability_bound": 99.70,
          "bottleneck_service": "external-payment-api",
          "bottleneck_contribution": "Consumes 50% of error budget at 99.9% target"
        },
        "counterfactuals": [
          {
            "condition": "If external-payment-api improved to 99.99%",
            "result": "Recommended target would increase to 99.95%"
          }
        ]
      }
    },
    {
      "sli_type": "latency",
      "metric": "p99_response_time_ms",
      "tiers": {
        "conservative": {
          "target_ms": 1200,
          "percentile": "p99.9",
          "estimated_breach_probability": 0.01
        },
        "balanced": {
          "target_ms": 800,
          "percentile": "p99",
          "estimated_breach_probability": 0.05
        },
        "aggressive": {
          "target_ms": 500,
          "percentile": "p95",
          "estimated_breach_probability": 0.12
        }
      },
      "explanation": {
        "summary": "End-to-end p99 latency measured at 780ms over 30 days via distributed tracing. Balanced target of 800ms provides 2.5% headroom.",
        "feature_attribution": [
          {"feature": "p99_latency_historical", "contribution": 0.50},
          {"feature": "call_chain_depth", "contribution": 0.22},
          {"feature": "noisy_neighbor_margin", "contribution": 0.15},
          {"feature": "traffic_seasonality", "contribution": 0.13}
        ],
        "note": "Latency SLO derived from end-to-end trace measurement, not mathematical composition (percentiles are non-additive)."
      }
    }
  ]
}
```

#### Computation Pipeline

**Availability SLO computation:**

1. **Query historical SLI data** from Prometheus/Mimir:
   - `sum(rate(http_requests_total{service="X", status!~"5.."}[30d])) / sum(rate(http_requests_total{service="X"}[30d]))` — availability ratio
   - Compute rolling availability over 1h, 1d, 7d, 28d windows
2. **Retrieve dependency subgraph** for the service (downstream, depth=3)
3. **Compute composite availability bounds:**
   - For serial hard dependencies: `R_composite = R_self × R_dep1 × R_dep2 × ...`
   - For parallel (redundant) dependencies: `R = 1 - (1-R_primary)(1-R_fallback)`
   - For soft dependencies: exclude from composite calculation, note as degraded-mode risk
4. **Calculate tier targets:**
   - Conservative: historical p99.9 availability (floor of observed performance)
   - Balanced: historical p99 availability, capped by composite availability bound
   - Aggressive: historical p95 availability
5. **Compute confidence intervals** using bootstrap resampling on the 30-day window
6. **Generate SHAP feature attributions** from the scoring model inputs
7. **Run what-if simulations** by varying dependency availability ±1 nine

**Latency SLO computation:**

1. **Query end-to-end latency distribution** from trace data:
   - Query Mimir/Tempo for latency histogram buckets: `histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{service="X"}[30d])) by (le))`
   - For journey-level: use distributed trace spans to measure actual end-to-end latency (not sum of component latencies)
2. **Apply noise margin:** Add 5-10% buffer for shared infrastructure (read `container_cpu_cfs_throttled_seconds_total` as signal)
3. **Calculate tier targets:**
   - Conservative: observed p99.9 + noise margin
   - Balanced: observed p99 + noise margin
   - Aggressive: observed p95
4. **Compute breach probability** by counting historical windows where the target would have been breached

**Caching strategy:**
- Pre-computed recommendations cached in PostgreSQL with `generated_at` timestamp
- Cache TTL: 24 hours (aligned with batch pipeline freshness target)
- `force_regenerate=true` bypasses cache, recomputes, and updates the stored recommendation
- Cache invalidated when: dependency graph changes, drift detected, or new SLO accepted

#### Cold-Start Strategy (services with <30 days of data)

1. **Extend lookback window** to maximum available data (up to 90 days)
2. **Archetype matching:** Classify the service by type (API gateway, backend service, data pipeline, external integration) using metadata and auto-assign archetype baselines:
   - API Gateway: 99.95% availability, p99 < 200ms
   - Backend Service: 99.9% availability, p99 < 500ms
   - External Integration: 99.5% availability, p99 < 2000ms
3. **Flag as low confidence:** Set `confidence_note` to indicate insufficient data and archetype-based inference
4. **Re-evaluate trigger:** Schedule automatic re-evaluation when 30 days of data accumulates

---

### FR-3: Dependency-Aware Constraint Propagation

**Corresponds to:** PRD F3

#### System Behaviors

**Composite availability computation** runs as part of FR-2 recommendation generation:

1. Retrieve full downstream dependency DAG for the target service
2. Handle circular dependencies: replace SCCs with supernodes, compute internal SCC availability using the weakest-link member
3. Classify each edge as serial-hard, serial-soft, or parallel-redundant
4. Apply serial formula for hard dependencies: `R = R_self × Π(R_hard_dep_i)`
5. Apply parallel formula for redundant paths: `R = 1 - Π(1 - R_replica_j)`
6. Soft dependencies excluded from composite but noted in risk analysis

**External dependency handling:**

1. For edges where `target.service_type = 'external'`:
   - Use **observed historical availability** (from monitoring the external endpoint), NOT the published SLA
   - If no monitoring data: use published SLA with a 10% pessimistic adjustment (e.g., published 99.99% → use 99.89%)
   - Calculate error budget consumption: `(1 - R_external) / (1 - SLO_target)`
2. If external dependency consumes >30% of error budget, flag as "high dependency risk" in the recommendation

**Unachievable SLO detection:**

When `R_composite_bound < desired_SLO_target`:
- Return an explicit warning: "The desired target of 99.99% is unachievable. Composite availability bound is 99.70% given current dependency chain."
- Suggest: "To achieve 99.99%, each critical dependency must be at least 99.999% (Google's 10x rule)"

---

### FR-4: Impact Analysis

**Corresponds to:** PRD F4

#### API Specification

**`POST /api/v1/slos/impact-analysis`**

Request body:
```json
{
  "service_id": "payment-service",
  "proposed_change": {
    "sli_type": "availability",
    "current_target": 99.9,
    "proposed_target": 99.5
  }
}
```

Response:
```json
{
  "analysis_id": "uuid",
  "proposed_change": { "..." },
  "impacted_services": [
    {
      "service_id": "checkout-service",
      "relationship": "upstream",
      "current_composite_availability": 99.70,
      "projected_composite_availability": 99.35,
      "delta": -0.35,
      "current_slo_target": 99.9,
      "slo_at_risk": true,
      "risk_detail": "Composite drops below SLO target (99.9% > 99.35%)"
    },
    {
      "service_id": "api-gateway",
      "relationship": "upstream (transitive)",
      "current_composite_availability": 99.65,
      "projected_composite_availability": 99.30,
      "delta": -0.35,
      "current_slo_target": 99.9,
      "slo_at_risk": true
    }
  ],
  "summary": {
    "total_impacted": 2,
    "slos_at_risk": 2,
    "recommendation": "Reducing payment-service to 99.5% puts 2 upstream services at risk of SLO breach."
  }
}
```

#### System Behavior

1. Identify all **upstream** services (services that depend on the changed service) via reverse graph traversal
2. For each upstream service with an active SLO:
   - Recalculate composite availability using the proposed target
   - Compare against the upstream service's current SLO target
   - Flag if `projected_composite < current_slo_target`
3. Return sorted by impact magnitude (largest delta first)

**Edge cases:**
- Service has no active SLO: include in response but mark as `slo_at_risk: null` (no target to compare against)
- Circular dependency in path: use supernode availability, note the cycle in response
- External dependency changed: trace impact through all internal services that depend on it

---

### FR-5: Recommendation Lifecycle

**Corresponds to:** PRD F5

#### API Specification

**`POST /api/v1/services/{service-id}/slos`** — Accept, modify, or reject a recommendation

Request body:
```json
{
  "recommendation_id": "uuid",
  "action": "accept | modify | reject",
  "selected_tier": "conservative | balanced | aggressive",
  "modifications": {
    "availability_target": 99.95,
    "latency_p99_target_ms": 600
  },
  "rationale": "Adjusting availability up because we are adding a payment fallback provider next sprint",
  "actor": "jane.doe@company.com"
}
```

Response:
```json
{
  "slo_id": "uuid",
  "service_id": "checkout-service",
  "status": "active",
  "targets": {
    "availability": 99.95,
    "latency_p99_ms": 600
  },
  "source": "recommendation_modified",
  "recommendation_id": "uuid",
  "modification_delta": {
    "availability": "+0.05 from recommended 99.9"
  },
  "activated_at": "2026-02-14T11:00:00Z",
  "activated_by": "jane.doe@company.com"
}
```

#### Data Model

```
Table: slo_recommendations
  - id: UUID (PK)
  - service_id: UUID FK -> services.id
  - sli_type: ENUM('availability', 'latency')
  - tiers: JSONB NOT NULL (conservative/balanced/aggressive targets)
  - explanation: JSONB NOT NULL (feature attribution, counterfactuals, dependency impact)
  - data_quality: JSONB NOT NULL (completeness, gaps, confidence note)
  - lookback_window_start: TIMESTAMPTZ
  - lookback_window_end: TIMESTAMPTZ
  - dependency_graph_snapshot_id: UUID FK -> graph_snapshots.id
  - generated_at: TIMESTAMPTZ NOT NULL DEFAULT NOW()
  - expires_at: TIMESTAMPTZ NOT NULL (generated_at + 24h)
  - status: ENUM('active', 'superseded', 'expired') DEFAULT 'active'

Table: active_slos
  - id: UUID (PK)
  - service_id: UUID FK -> services.id UNIQUE
  - availability_target: DECIMAL(6,4)
  - latency_p95_target_ms: INTEGER
  - latency_p99_target_ms: INTEGER
  - source: ENUM('recommendation_accepted', 'recommendation_modified', 'manual')
  - recommendation_id: UUID FK -> slo_recommendations.id (nullable)
  - activated_at: TIMESTAMPTZ NOT NULL
  - activated_by: VARCHAR(255) NOT NULL
  - created_at: TIMESTAMPTZ NOT NULL DEFAULT NOW()
  - updated_at: TIMESTAMPTZ NOT NULL DEFAULT NOW()

Table: slo_audit_log
  - id: UUID (PK)
  - service_id: UUID FK -> services.id
  - action: ENUM('accept', 'modify', 'reject', 'auto_approve', 'expire', 'drift_triggered')
  - actor: VARCHAR(255) NOT NULL
  - recommendation_id: UUID FK -> slo_recommendations.id
  - previous_slo: JSONB (snapshot of active_slos before change, nullable)
  - new_slo: JSONB (snapshot after change, nullable)
  - selected_tier: VARCHAR(20)
  - rationale: TEXT
  - modification_delta: JSONB
  - timestamp: TIMESTAMPTZ NOT NULL DEFAULT NOW()
  - INDEX(service_id, timestamp)
  - INDEX(actor, timestamp)
```

**Audit log is append-only.** No UPDATE or DELETE operations are permitted on `slo_audit_log`.

---

### FR-6: Telemetry Ingestion Pipeline

**Corresponds to:** PRD F6

#### Architecture Decision: Query, Don't Store

The SLO Recommendation Engine **queries existing Prometheus/Mimir metric stores** rather than ingesting and storing raw telemetry. This is a deliberate design choice:

- **Advantages:** No data duplication, leverages existing infrastructure investment, reduces operational footprint
- **Trade-off:** Dependent on Prometheus/Mimir availability and query performance

#### Data Access Patterns

| Data Need | Source | Query Method | Frequency |
|-----------|--------|-------------|-----------|
| Availability SLI (error rate) | Prometheus/Mimir | PromQL remote read API | Batch: every 1 hour for rolling aggregates |
| Latency percentiles (p50/p95/p99) | Prometheus/Mimir | PromQL histogram_quantile | Batch: every 1 hour |
| Infrastructure metrics (CPU, memory, CFS throttling) | Prometheus | PromQL | On-demand during recommendation generation |
| End-to-end trace latency | Grafana Tempo | TraceQL / Tempo API | On-demand for latency SLO computation |
| Dependency topology | OTel Service Graph Connector | Metrics published to Prometheus | Batch: every 15 minutes |

#### Prometheus Query Abstraction Layer

The system implements a **PromQL query builder** as a domain service:

```python
class TelemetryQueryService:
    """Domain service for querying telemetry from Prometheus/Mimir."""

    async def get_availability_sli(
        self, service_id: str, window_days: int
    ) -> AvailabilitySLI:
        """Returns good_events / total_events ratio over window."""

    async def get_latency_percentiles(
        self, service_id: str, percentiles: list[float], window_days: int
    ) -> dict[float, float]:
        """Returns latency values at requested percentiles."""

    async def get_error_budget_burn_rate(
        self, service_id: str, slo_target: float, window_hours: int
    ) -> float:
        """Returns current burn rate relative to SLO target."""

    async def get_infrastructure_metrics(
        self, service_id: str, window_hours: int
    ) -> InfrastructureMetrics:
        """Returns CPU, memory, CFS throttling for noise margin."""
```

#### Pre-Computed Aggregates

For performance, the system maintains **pre-computed SLI aggregates** in PostgreSQL:

```
Table: sli_aggregates
  - id: UUID (PK)
  - service_id: UUID FK -> services.id
  - sli_type: ENUM('availability', 'latency_p50', 'latency_p95', 'latency_p99', 'error_rate', 'request_rate')
  - window: ENUM('1h', '1d', '7d', '28d', '90d')
  - value: DECIMAL
  - sample_count: BIGINT
  - computed_at: TIMESTAMPTZ NOT NULL
  - INDEX(service_id, sli_type, window)
```

A **batch aggregation job** (scheduled via APScheduler or Celery Beat) runs hourly:
1. Queries Prometheus/Mimir for each registered service
2. Computes rolling aggregates across configured windows
3. Upserts into `sli_aggregates`
4. Marks recommendations as stale if aggregates changed significantly (>5% delta)

**Data Retention:**
- `sli_aggregates` at 1h granularity: 90 days
- `sli_aggregates` at 1d granularity: 1 year
- `slo_audit_log`: indefinite (append-only, compliance requirement)
- `slo_recommendations`: 90 days (superseded/expired purged after 90d)

---

### FR-7: Explainability

**Corresponds to:** PRD F7

#### Technical Implementation

Every recommendation response includes an `explanation` object with:

1. **Summary (natural language):** Template-based string generation from computed values:
   ```
   "{service} achieved {observed}% availability over {window} days.
    The Balanced target of {target}% provides {margin}% margin.
    Composite availability bound is {bound}% given {dep_count} hard dependencies."
   ```

2. **Feature Attribution (SHAP values):** Using the `shap` Python library:
   - For MVP (rule-based model): compute feature contributions as weighted input factors
   - For Phase 5 (ML model): use `shap.TreeExplainer` or `shap.KernelExplainer` depending on model type
   - Return top-N features sorted by absolute contribution

3. **Counterfactual Analysis:**
   - For each top-3 feature, compute: "What target would we recommend if this feature were X% better/worse?"
   - Implementation: re-run recommendation logic with perturbed input, return delta

4. **Dependency Impact:**
   - Composite availability bound from FR-3
   - Bottleneck service identification (the dependency contributing most to composite degradation)
   - Error budget consumption breakdown per external dependency

5. **Data Provenance:**
   - `dependency_graph_snapshot_id` linking to the exact graph version used
   - `lookback_window_start/end` specifying the telemetry window
   - `data_completeness` score (0.0-1.0)

---

### FR-8: REST API for Developer Platform Integration

**Corresponds to:** PRD F8

#### API Design Standards

- **Framework:** FastAPI (Python 3.12+)
- **Specification:** OpenAPI 3.0, auto-generated from Pydantic models via FastAPI
- **Versioning:** URL path versioning (`/api/v1/`)
- **Serialization:** JSON (application/json)
- **Pagination:** Cursor-based for list endpoints (e.g., `GET /api/v1/services`)
- **Error format:** RFC 7807 Problem Details

```json
{
  "type": "https://slo-engine.internal/errors/service-not-found",
  "title": "Service Not Found",
  "status": 404,
  "detail": "Service with ID 'nonexistent-service' is not registered.",
  "instance": "/api/v1/services/nonexistent-service/slo-recommendations"
}
```

#### Complete Endpoint Inventory

| Method | Endpoint | Description | Auth | Rate Limit |
|--------|----------|-------------|------|------------|
| POST | `/api/v1/services/dependencies` | Bulk upsert dependency graph | API Key / OAuth2 | 10 req/min |
| GET | `/api/v1/services/{id}/dependencies` | Get dependency subgraph | API Key / OAuth2 | 60 req/min |
| GET | `/api/v1/services/{id}/slo-recommendations` | Get SLO recommendations | API Key / OAuth2 | 60 req/min |
| POST | `/api/v1/services/{id}/slos` | Accept/modify/reject recommendation | OAuth2 (user identity required) | 30 req/min |
| GET | `/api/v1/services/{id}/slos` | Get active SLO for service | API Key / OAuth2 | 120 req/min |
| GET | `/api/v1/services/{id}/slo-history` | Get SLO audit history | OAuth2 | 30 req/min |
| POST | `/api/v1/slos/impact-analysis` | Run impact analysis | API Key / OAuth2 | 10 req/min |
| GET | `/api/v1/services` | List registered services | API Key / OAuth2 | 30 req/min |
| GET | `/api/v1/health` | Health check | None | Unlimited |
| GET | `/api/v1/health/ready` | Readiness check | None | Unlimited |

#### Authentication & Authorization

**Authentication:**
- **API Keys:** For service-to-service calls (Backstage backend → SLO Engine). Keys stored as bcrypt hashes in the database. Passed via `X-API-Key` header.
- **OAuth2/OIDC:** For user-facing operations (accept/modify/reject). JWT tokens validated against the organization's identity provider (e.g., Keycloak, Okta). Token passed via `Authorization: Bearer <token>` header.

**Authorization (RBAC):**

| Role | Permissions |
|------|------------|
| `sre_admin` | All operations on all services. Configure auto-approval rules. |
| `service_owner` | View recommendations, accept/modify/reject for owned services only. View dependencies. |
| `viewer` | Read-only access to recommendations, SLOs, and dependencies. |

Role-to-service ownership mapping is resolved via the service catalog metadata (`team` field on `services` table, cross-referenced with the JWT `groups` or `team` claim).

#### Rate Limiting

Implemented via **FastAPI middleware** using a token bucket algorithm (backed by Redis for distributed deployments):
- Limits are per API key or per OAuth2 subject
- Rate limit headers returned: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`
- Exceeded: HTTP 429 with `Retry-After` header

---

### FR-9 through FR-12: Should Have Features

These are specified at a level sufficient for Phase 3 planning.

#### FR-9: Drift Detection

**Implementation:** A background worker (Celery task) runs every 15 minutes per service:
1. Fetch latest 1h of SLI data from `sli_aggregates`
2. Run three drift detectors against the stored baseline:
   - **Page-Hinkley:** Monitors cumulative sum of deviations; detects abrupt shifts (post-deployment)
   - **ADWIN:** Variable-length windowing with Hoeffding bound; handles gradual and abrupt drift
   - **KS-test (KSWIN):** Kolmogorov-Smirnov distributional comparison; rigorous but expensive
3. **Majority voting:** Drift confirmed only when ≥2 of 3 detectors agree
4. On confirmed drift: mark current recommendation as `stale`, enqueue re-evaluation, notify service owner via webhook

**Libraries:** `river` (Python streaming ML library) provides Page-Hinkley, ADWIN implementations. `scipy.stats.ks_2samp` for KS-test.

#### FR-10: Burn-Rate Alert Configuration

For each accepted SLO, generate Prometheus recording rules:

```yaml
# Generated by SLO Recommendation Engine for checkout-service
groups:
  - name: checkout-service-slo-alerts
    rules:
      - record: slo:checkout_service:availability:burn_rate_1h
        expr: |
          1 - (
            sum(rate(http_requests_total{service="checkout-service", status!~"5.."}[1h]))
            /
            sum(rate(http_requests_total{service="checkout-service"}[1h]))
          ) / (1 - 0.999)
      # ... additional rules for 6h, 3d windows
```

Export via `GET /api/v1/services/{id}/slos/alerts?format=prometheus`.

#### FR-11: Auto-Approval Rules

```
Table: auto_approval_rules
  - id: UUID (PK)
  - name: VARCHAR(255)
  - conditions: JSONB NOT NULL
    -- Example: {"criticality": ["low", "medium"], "confidence_min": 0.85, "tier": "balanced"}
  - enabled: BOOLEAN DEFAULT false
  - created_by: VARCHAR(255) NOT NULL
  - created_at: TIMESTAMPTZ NOT NULL
```

The rules engine evaluates conditions against recommendation metadata. Matching recommendations are auto-accepted with `action: 'auto_approve'` in the audit log.

#### FR-12: Organizational Dashboard

Expose aggregate endpoints:
- `GET /api/v1/dashboard/coverage` — SLO coverage stats by team/criticality
- `GET /api/v1/dashboard/error-budget-health` — budget utilization distribution
- `GET /api/v1/dashboard/recommendation-quality` — acceptance rates, breach rates

Data served from pre-computed materialized views refreshed every hour.

---

## 4. Non-Functional Requirements (NFRs)

### 4.1 Performance Requirements

| Requirement ID | Requirement | Measurement | Target |
|----------------|-------------|-------------|--------|
| PERF-001 | `GET /api/v1/services/{id}/slo-recommendations` response time | APM p95 latency | < 500ms (cached), < 5s (force_regenerate) |
| PERF-002 | `POST /api/v1/slos/impact-analysis` response time | APM p95 latency | < 10s for graphs up to 5,000 services |
| PERF-003 | `POST /api/v1/services/dependencies` ingestion time | APM p95 latency | < 30s for 1,000 service graph |
| PERF-004 | Dependency graph traversal (3-hop) | Query execution time | < 100ms on 5,000-node graph |
| PERF-005 | Concurrent API connections | Load test (k6/Locust) | 200+ concurrent users, no degradation |
| PERF-006 | Batch aggregation job throughput | Job completion time | Process 5,000 services within 30 minutes |
| PERF-007 | Database connection pool | PostgreSQL connections | Max 50 connections per application instance |
| PERF-008 | Memory usage per instance | Container metrics | < 2GB RSS under normal load |

### 4.2 Security Requirements

| Requirement ID | Requirement | Implementation |
|----------------|-------------|----------------|
| SEC-001 | All API communication encrypted in transit | TLS 1.3 mandatory. HTTP requests redirected to HTTPS. HSTS header enabled. |
| SEC-002 | API key storage | API keys hashed with `bcrypt` (cost factor 12). Raw keys never stored or logged. |
| SEC-003 | JWT validation | Validate signature against IdP JWKS endpoint. Verify `exp`, `iss`, `aud` claims. Token cache TTL: 5 minutes. |
| SEC-004 | RBAC enforcement | Middleware validates role claims on every request. Service ownership checked against `services.team` ↔ JWT `groups`. |
| SEC-005 | Audit log immutability | `slo_audit_log` table: no UPDATE/DELETE grants. Application ORM models enforce append-only. |
| SEC-006 | Input validation | All API inputs validated via Pydantic models with strict type coercion. Max request body size: 10MB. |
| SEC-007 | SQL injection prevention | All database queries via SQLAlchemy ORM or parameterized queries. No raw SQL string interpolation. |
| SEC-008 | Metric label sanitization | Validate all metric labels before use in PromQL queries. Reject labels matching PII patterns (email, IP, UUID-like user identifiers). |
| SEC-009 | Rate limiting | Token bucket per client (API key / OAuth2 subject). Backed by Redis for distributed consistency. |
| SEC-010 | Dependency: no secret in config | All secrets (DB passwords, API keys, IdP secrets) via environment variables or Kubernetes Secrets. Never in source code or config files. |

### 4.3 Reliability & Availability

| Requirement ID | Requirement | Target |
|----------------|-------------|--------|
| REL-001 | System uptime | 99.9% (≈43 min/month downtime) |
| REL-002 | Recovery Time Objective (RTO) | < 15 minutes (container restart + health check) |
| REL-003 | Recovery Point Objective (RPO) | < 1 hour (PostgreSQL WAL replication) |
| REL-004 | Database failover | PostgreSQL streaming replication with automatic failover (Patroni or cloud-managed) |
| REL-005 | Graceful degradation | If Prometheus/Mimir is unreachable, serve cached recommendations with `stale: true` flag. Do not return 500. |
| REL-006 | Circuit breaker on external dependencies | Prometheus client wrapped with circuit breaker (10 failures → 30s open → half-open). |
| REL-007 | Health checks | `/health` (liveness): process is running. `/health/ready` (readiness): DB connected, Prometheus reachable, Redis connected. |
| REL-008 | Zero-downtime deployments | Rolling deployment via Kubernetes. Readiness probe gates traffic. Graceful shutdown with in-flight request drain (30s). |

### 4.4 Usability Requirements

| Requirement ID | Requirement | Target |
|----------------|-------------|--------|
| USA-001 | API documentation | Auto-generated OpenAPI 3.0 spec served at `/docs` (Swagger UI) and `/redoc` |
| USA-002 | Error messages | All error responses follow RFC 7807 Problem Details with actionable `detail` field |
| USA-003 | API consistency | All timestamps in ISO 8601 / UTC. All IDs are UUIDs. Enum values are lowercase snake_case. |

> **Note:** The SLO Recommendation Engine is an API-only backend. The user-facing UI is provided by Backstage plugins consuming this API. WCAG and browser compatibility requirements apply to the Backstage frontend, not this service.

---

## 5. System Constraints & Assumptions

### Technology Stack

| Layer | Technology | Version | Rationale |
|-------|-----------|---------|-----------|
| Language | Python | 3.12+ | Team expertise. Rich ML/data ecosystem. Async support via asyncio. |
| API Framework | FastAPI | 0.115+ | Async-native, auto-generated OpenAPI docs, Pydantic validation. |
| ORM | SQLAlchemy | 2.0+ | Async support, mature PostgreSQL integration, type-safe queries. |
| Database | PostgreSQL | 16+ | Recursive CTEs for graph traversal, JSONB for flexible metadata, proven at scale. |
| Cache / Rate Limiting | Redis | 7+ | Token bucket rate limiting, recommendation cache, distributed locking. |
| Task Queue | Celery + Redis broker | 5.3+ | Background jobs: batch aggregation, drift detection, graph analysis. |
| ML / Explainability | scikit-learn, shap, scipy, river | Latest stable | MVP models (rule-based + statistical). SHAP for explainability. river for drift detection. |
| Telemetry Client | prometheus-api-client | Latest | PromQL queries against Prometheus/Mimir. |
| Containerization | Docker | Latest | Consistent builds across dev/staging/prod. |
| Orchestration | Kubernetes | 1.28+ | Deployment, scaling, health checks. |
| CI/CD | GitHub Actions | N/A | Build, test, lint, deploy pipeline. |

### Constraints

1. **No raw telemetry storage.** The system queries Prometheus/Mimir and Tempo. It does not operate its own time-series database.
2. **Single-region deployment** for MVP. Multi-region is a post-MVP concern.
3. **No UI.** API-only backend. All user-facing interactions go through Backstage.
4. **Python ecosystem.** All components must be implementable in Python. No polyglot services for MVP.
5. **Clean Architecture.** Domain logic must be framework-independent. FastAPI and SQLAlchemy are infrastructure concerns.

### Assumptions

1. Prometheus/Mimir retains at least 90 days of metric history at 15-30s scrape interval.
2. OpenTelemetry traces are available with at least 10% sampling rate and 100% error/slow trace retention.
3. Kubernetes RBAC allows the SLO Engine service account to read pod/service/deployment resources.
4. A Redis instance is available (or can be provisioned) for rate limiting and caching.
5. The organization's IdP supports OIDC with group/team claims in JWT tokens.

---

## 6. Integration Requirements

### 6.1 Prometheus / Grafana Mimir

**Protocol:** HTTP, PromQL remote read API
**Authentication:** Bearer token or basic auth (configurable)
**Data Exchange:** JSON (Prometheus API response format)

**Queries executed by the system:**

| Query Purpose | Example PromQL | Frequency |
|---------------|---------------|-----------|
| Availability SLI | `sum(rate(http_requests_total{service=~"$svc",status!~"5.."}[$window])) / sum(rate(http_requests_total{service=~"$svc"}[$window]))` | Hourly batch |
| Latency percentile | `histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{service=~"$svc"}[$window])) by (le))` | Hourly batch |
| Error budget burn rate | `1 - (availability_sli / (1 - (1 - $slo_target)))` | On-demand |
| CFS throttling | `rate(container_cpu_cfs_throttled_seconds_total{pod=~"$svc.*"}[$window])` | On-demand |
| Service graph edges | `traces_service_graph_request_total` | Every 15 min |

**Error handling:** If Prometheus returns 503 or times out, the system retries with exponential backoff (3 attempts, 1s/2s/4s) and circuit-breaks after 10 consecutive failures.

### 6.2 OpenTelemetry Collector

**Protocol:** The system does NOT receive OTLP directly. Instead, it reads the outputs of the OTel Collector that are already published to Prometheus (Span Metrics Connector → Prometheus, Service Graph Connector → Prometheus).

**Dependency:** The OTel Collector must be configured with:
- `spanmetrics` connector: derives RED metrics from spans, publishes to Prometheus
- `servicegraph` connector: derives service-to-service edges from trace parent-child relationships

### 6.3 Backstage Developer Platform

**Protocol:** REST API (this system serves; Backstage consumes)
**Authentication:** API key issued per Backstage backend instance
**Data exchange:** JSON
**Integration pattern:** Backstage backend plugin makes HTTP calls to the SLO Engine API. The plugin renders recommendations, dependency graphs, and SLO status in the Backstage catalog entity page.

### 6.4 Kubernetes API

**Protocol:** Kubernetes client-go (via `kubernetes` Python library)
**Authentication:** Service account token (in-cluster) or kubeconfig (out-of-cluster dev)
**Data read:**
- `v1/Services` — service discovery
- `apps/v1/Deployments` — deployment metadata, replica count
- `v1/Namespaces` — organizational grouping
- `v1/ConfigMaps` — static dependency declarations (optional)

**Permissions required (RBAC):**
```yaml
rules:
  - apiGroups: [""]
    resources: ["services", "namespaces", "configmaps"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "watch"]
```

---

## 7. Data Requirements

### 7.1 Entity-Relationship Summary

```
services (1) ---< (N) service_dependencies (N) >--- (1) services
services (1) ---< (N) slo_recommendations
services (1) ---< (1) active_slos
services (1) ---< (N) sli_aggregates
services (1) ---< (N) slo_audit_log
slo_recommendations (1) ---< (N) slo_audit_log
auto_approval_rules (standalone)
circular_dependency_alerts (standalone)
api_keys (standalone)
```

### 7.2 Storage Estimates

| Table | Row Estimate (1 year, 5000 services) | Avg Row Size | Total Size |
|-------|--------------------------------------|-------------|------------|
| services | 5,000 | 500B | ~2.5 MB |
| service_dependencies | 50,000 (10 edges avg) | 300B | ~15 MB |
| sli_aggregates | 5,000 × 6 SLI types × 5 windows × 8760 hourly records = ~1.3B | 50B | ~65 GB |
| slo_recommendations | 5,000 × 365 daily = 1.8M | 2KB | ~3.6 GB |
| slo_audit_log | ~100K actions/year | 500B | ~50 MB |
| **Total** | | | **~70 GB** |

> **Note:** `sli_aggregates` dominates storage. Consider partitioning by `computed_at` (monthly partitions) and dropping hourly granularity after 90 days (retain daily aggregates only).

### 7.3 Backup & Recovery

| Aspect | Strategy |
|--------|----------|
| Database backup | PostgreSQL continuous archiving (WAL) to object storage. Point-in-time recovery capability. |
| Backup frequency | Continuous WAL shipping + daily base backup |
| Backup retention | 30 days |
| Restore test | Monthly automated restore to staging environment |
| Data migration | Alembic (SQLAlchemy migration tool) for schema versioning. All migrations are reversible. |

### 7.4 Database Indexing Strategy

```sql
-- High-frequency query: get dependencies for a service
CREATE INDEX idx_deps_source ON service_dependencies(source_service_id) WHERE NOT is_stale;
CREATE INDEX idx_deps_target ON service_dependencies(target_service_id) WHERE NOT is_stale;

-- Recommendation lookup by service
CREATE INDEX idx_recs_service_active ON slo_recommendations(service_id, status) WHERE status = 'active';

-- SLI aggregate lookup
CREATE INDEX idx_sli_lookup ON sli_aggregates(service_id, sli_type, window, computed_at DESC);

-- Audit log queries
CREATE INDEX idx_audit_service_time ON slo_audit_log(service_id, timestamp DESC);
CREATE INDEX idx_audit_actor_time ON slo_audit_log(actor, timestamp DESC);

-- Partition sli_aggregates by month
-- PARTITION BY RANGE (computed_at)
```

---

## 8. Infrastructure & Environment Requirements

### 8.1 Environment Topology

| Environment | Purpose | Infrastructure | Data |
|-------------|---------|---------------|------|
| **Development** | Local development | Docker Compose (FastAPI + PostgreSQL + Redis) | Seed data, mock Prometheus |
| **Staging** | Integration testing, pre-prod validation | Kubernetes (same namespace, smaller replicas) | Copy of production graph, synthetic metrics |
| **Production** | Live service | Kubernetes (dedicated namespace) | Live data from Prometheus/Mimir |

### 8.2 Production Kubernetes Resources

```yaml
# Application deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: slo-engine-api
spec:
  replicas: 3  # Minimum for HA
  template:
    spec:
      containers:
        - name: slo-engine-api
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              cpu: "2"
              memory: "2Gi"
          readinessProbe:
            httpGet:
              path: /api/v1/health/ready
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /api/v1/health
              port: 8000
            initialDelaySeconds: 15
            periodSeconds: 10

---
# Background worker deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: slo-engine-worker
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: slo-engine-worker
          command: ["celery", "-A", "src.infrastructure.tasks", "worker", "--loglevel=info"]
          resources:
            requests:
              cpu: "1"
              memory: "2Gi"
            limits:
              cpu: "4"
              memory: "4Gi"
```

### 8.3 Network Requirements

| Port | Service | Protocol | Exposure |
|------|---------|----------|----------|
| 8000 | FastAPI application | HTTP/HTTPS | Internal (Kubernetes Service, Ingress) |
| 5432 | PostgreSQL | TCP | Internal only |
| 6379 | Redis | TCP | Internal only |
| 9090 | Prometheus (outbound) | HTTP | Egress to monitoring stack |
| 443 | IdP (outbound) | HTTPS | Egress for JWKS/token validation |

### 8.4 Resource Scaling Strategy

| Component | Scaling Trigger | Scaling Action |
|-----------|----------------|----------------|
| API pods | CPU > 70% or p95 latency > 400ms | HPA: scale 3 → 10 pods |
| Worker pods | Celery queue depth > 100 tasks | HPA: scale 2 → 8 pods |
| PostgreSQL | Connection count > 80% of max | Vertical scaling (increase instance size) or PgBouncer connection pooling |
| Redis | Memory > 80% | Vertical scaling or Redis Cluster |

---

## 9. Compliance & Regulatory Requirements

### 9.1 EU AI Act Alignment

The SLO Recommendation Engine is classified as a **limited-risk AI system** (automated recommendations that influence operational decisions, not directly affecting individuals' rights).

| Requirement | Implementation |
|-------------|----------------|
| Human oversight | Semi-automated model: all recommendations require human approval. Auto-approval is opt-in and logged. |
| Transparency | Every recommendation includes explainability data (SHAP, counterfactuals, data provenance). |
| Record-keeping | Immutable audit trail (`slo_audit_log`) with full recommendation lifecycle. |
| Risk management | Confidence scores, low-confidence flags, fallback to archetype baselines. |

### 9.2 SOC 2 Trust Principles

| Principle | Implementation |
|-----------|----------------|
| Security | TLS 1.3, RBAC, API key hashing, input validation (SEC-001 through SEC-010) |
| Availability | 99.9% uptime target, health checks, graceful degradation (REL-001 through REL-008) |
| Confidentiality | No PII processing. Metric label sanitization. Audit log access restricted to `sre_admin` role. |
| Processing Integrity | Immutable audit trail. Recommendation provenance (data window, graph snapshot). |

### 9.3 Data Protection

- The system processes **operational metrics only** (request rates, error rates, latency). No user PII.
- Metric label validation rejects labels matching PII patterns before they enter the system (SEC-008).
- Audit logs contain actor identifiers (email addresses) — these are classified as employee operational data, not customer PII.

> **Assumption:** The organization does not require HIPAA or PCI-DSS compliance for this system specifically, as it processes infrastructure metrics, not protected health information or cardholder data.

---

## 10. Quality Assurance Requirements

### 10.1 Testing Strategy

| Test Type | Scope | Coverage Target | Framework |
|-----------|-------|----------------|-----------|
| **Unit Tests** | Domain entities, use cases, computation logic | 90% line coverage | pytest |
| **Integration Tests** | Repository implementations, Prometheus client, API endpoints | 80% coverage | pytest + testcontainers (PostgreSQL, Redis) |
| **End-to-End Tests** | Full API workflows (ingest → recommend → accept → impact analysis) | Critical paths covered | pytest + httpx (async client) |
| **Load Tests** | API performance under concurrent load | PERF-001 through PERF-008 targets | Locust or k6 |
| **Contract Tests** | API response schema validation | 100% of endpoints | schemathesis (property-based API testing from OpenAPI spec) |

### 10.2 Code Quality Gates

| Gate | Threshold | Enforcement |
|------|-----------|-------------|
| Unit test pass rate | 100% | CI blocks merge on failure |
| Integration test pass rate | 100% | CI blocks merge on failure |
| Line coverage (domain + application layers) | 90% | CI blocks merge if below |
| Line coverage (infrastructure layer) | 75% | CI warns if below |
| Type checking | Zero errors | `mypy --strict` in CI |
| Linting | Zero errors | `ruff` in CI |
| Security scan | Zero high/critical findings | `bandit` + `safety` in CI |
| Dependency vulnerability scan | Zero critical CVEs | `pip-audit` in CI |

### 10.3 Recommendation Quality Validation

Beyond code testing, recommendation accuracy must be validated:

| Validation | Method | Frequency |
|------------|--------|-----------|
| Backtesting | Apply recommendations to historical data, measure simulated breach rate | Pre-release, monthly |
| Shadow mode | Generate recommendations without applying, compare to manual SLOs | Phase 2-3 (continuous) |
| Acceptance rate tracking | Monitor accept/modify/reject ratios per team and service criticality | Continuous (dashboard FR-12) |
| Breach rate tracking | For accepted SLOs, measure actual breach frequency | Monthly, automated report |

---

## 11. Deployment & Operations Requirements

### 11.1 CI/CD Pipeline

```
Trigger: Push to main branch or PR

Stage 1: Validate
  ├── ruff (linting)
  ├── mypy --strict (type checking)
  └── bandit + pip-audit (security)

Stage 2: Test
  ├── pytest (unit tests, coverage report)
  ├── pytest (integration tests via testcontainers)
  └── schemathesis (API contract tests)

Stage 3: Build
  ├── Docker build (multi-stage: builder + runtime)
  └── Push to container registry (tagged: git SHA + semver)

Stage 4: Deploy (staging)
  ├── Helm upgrade --install (staging namespace)
  ├── Run smoke tests against staging
  └── Run load tests (Locust, 5-minute burst)

Stage 5: Deploy (production) [manual approval gate]
  ├── Helm upgrade --install (production namespace)
  ├── Rolling update (maxUnavailable: 0, maxSurge: 1)
  ├── Readiness probe gates traffic
  └── Post-deploy smoke test

Stage 6: Post-deploy validation
  ├── Monitor error rate for 15 minutes
  └── Auto-rollback if 5xx rate > 1%
```

### 11.2 Monitoring & Alerting

**Application metrics** (exported via Prometheus client in FastAPI middleware):

| Metric | Type | Labels | Alert Threshold |
|--------|------|--------|----------------|
| `slo_engine_http_requests_total` | Counter | method, endpoint, status_code | 5xx rate > 1% for 5 min |
| `slo_engine_http_request_duration_seconds` | Histogram | method, endpoint | p95 > 500ms for 5 min |
| `slo_engine_recommendations_generated_total` | Counter | service_id, sli_type, tier | N/A (observability) |
| `slo_engine_recommendations_accepted_total` | Counter | service_id, action | N/A (business metric) |
| `slo_engine_dependency_graph_nodes` | Gauge | | Drop > 10% in 1 hour |
| `slo_engine_batch_aggregation_duration_seconds` | Histogram | | p95 > 30 min |
| `slo_engine_drift_detections_total` | Counter | service_id, detector | N/A (observability) |
| `slo_engine_prometheus_query_duration_seconds` | Histogram | query_type | p95 > 10s |
| `slo_engine_prometheus_query_errors_total` | Counter | query_type, error_type | > 10 errors in 5 min |

**Infrastructure metrics** (from Kubernetes / cAdvisor):
- CPU/memory usage per pod
- PostgreSQL connection count, query duration, replication lag
- Redis memory usage, connection count, command latency
- Celery queue depth, task execution time, failure rate

### 11.3 Logging Strategy

**Format:** Structured JSON logs

```json
{
  "timestamp": "2026-02-14T10:30:00.123Z",
  "level": "INFO",
  "logger": "slo_engine.api.recommendations",
  "message": "Recommendation generated",
  "service_id": "checkout-service",
  "sli_type": "availability",
  "balanced_target": 99.9,
  "confidence": 0.87,
  "duration_ms": 1234,
  "trace_id": "abc123",
  "span_id": "def456",
  "request_id": "req-789"
}
```

**Log levels:**
- `ERROR`: Unhandled exceptions, Prometheus query failures, database errors
- `WARNING`: Stale data served, low confidence recommendations, drift detected, rate limit exceeded
- `INFO`: Recommendation generated, SLO accepted/modified/rejected, graph ingested
- `DEBUG`: PromQL queries executed, graph traversal details, SHAP computation details

**Log shipping:** stdout → collected by Kubernetes log agent → Loki/Elasticsearch

**Retention:** 30 days in searchable storage, 90 days in cold archive.

### 11.4 Operational Runbook (Key Procedures)

| Scenario | Procedure |
|----------|-----------|
| Prometheus unreachable | Circuit breaker opens. Cached recommendations served with `stale: true`. Alert fires. Investigate Prometheus/Mimir health. |
| Recommendation generation takes >5s | Check Prometheus query latency. Check graph size for the service. Consider pre-computing complex subgraph traversals. |
| Database disk >80% | Check `sli_aggregates` partition sizes. Drop hourly partitions older than 90 days. Verify daily aggregation is running. |
| Drift detection false positives | Adjust detector thresholds (increase Page-Hinkley delta, widen ADWIN window). Review the service's traffic pattern for expected seasonality. |
| API 429 (rate limit) from Backstage | Increase rate limit for the Backstage API key. Consider implementing request coalescing in Backstage plugin. |

---

## 12. Dependencies & Risks

### 12.1 Technical Dependencies

| Dependency | Version | Purpose | Fallback |
|------------|---------|---------|----------|
| Python | 3.12+ | Runtime | None (hard requirement) |
| FastAPI | 0.115+ | API framework | None (hard requirement) |
| SQLAlchemy | 2.0+ | ORM | None (hard requirement) |
| PostgreSQL | 16+ | Primary database | Cloud-managed (RDS, Cloud SQL) or self-hosted with Patroni |
| Redis | 7+ | Cache, rate limiting, Celery broker | In-memory fallback for rate limiting (single-instance only) |
| Prometheus/Mimir | 2.x / latest | Metric source | None — this is the primary data source. System cannot function without it. |
| Grafana Tempo | latest | Trace source | Latency SLOs degrade to Prometheus histogram-based only (less accurate) |
| shap | latest | Explainability | Feature attribution falls back to weighted input factor list (rule-based) |
| river | latest | Drift detection | scipy.stats-based detectors only |
| Celery | 5.3+ | Task queue | APScheduler as lightweight alternative (loses distributed execution) |

### 12.2 Risk Register

| Risk ID | Risk | Impact | Probability | Mitigation |
|---------|------|--------|-------------|------------|
| RISK-001 | Prometheus query latency spikes during high-traffic periods degrade recommendation generation | Medium | High | Pre-compute aggregates in batch. Circuit breaker. Query Mimir (long-term store) instead of Prometheus for historical queries. |
| RISK-002 | PostgreSQL recursive CTE performance degrades at >10,000 edges | Medium | Medium | Benchmark early. If proven insufficient, migrate graph queries to Neo4j or materialized adjacency tables. |
| RISK-003 | SHAP computation is slow for complex models | Low (MVP) | Low (MVP) | MVP uses rule-based model (SHAP is fast). Phase 5 GNN models may need KernelExplainer with background sampling. |
| RISK-004 | Celery worker memory leak from long-running batch jobs | Medium | Medium | Set `worker_max_tasks_per_child=100` (recycle workers). Monitor RSS. Use `--pool=prefork`. |
| RISK-005 | Schema migrations on large `sli_aggregates` table take too long | High | Medium | Use `pg_repack` for zero-lock table rewrites. Partition table from day one. Test migrations on staging with production-scale data. |
| RISK-006 | OpenTelemetry Service Graph Connector produces incomplete topology | High | High | Multi-source graph discovery (FR-1). Confidence scores per edge. Divergence alerting. |
| RISK-007 | Redis failure takes down rate limiting and caching | Medium | Low | Rate limiting falls back to in-process token bucket (per-instance, not distributed). Cache falls back to direct Prometheus queries (higher latency). |

---

## 13. Success Criteria & Acceptance Criteria

### 13.1 MVP Acceptance Criteria (Phase 1-2 Complete)

| ID | Criterion | Verification Method |
|----|-----------|-------------------|
| AC-001 | **Given** a dependency graph of 500 services is submitted via API, **When** ingestion completes, **Then** all nodes and edges are stored with correct annotations, and circular dependencies are detected and reported. | Integration test with 500-node synthetic graph |
| AC-002 | **Given** a registered service with 30 days of Prometheus data, **When** `GET /slo-recommendations` is called, **Then** the response includes availability and latency recommendations with three tiers, confidence scores, and SHAP feature attribution within 5s. | Integration test against staging Prometheus |
| AC-003 | **Given** a service with 3 serial hard dependencies, **When** recommendations are generated, **Then** composite availability is correctly computed as the product of individual availabilities and the bound is reflected in the recommendation. | Unit test + integration test |
| AC-004 | **Given** a proposed SLO change for payment-service, **When** impact analysis is run, **Then** all upstream services are identified with projected composite availability changes and SLO-at-risk flags. | Integration test with known topology |
| AC-005 | **Given** an SRE accepts a recommendation, **When** the action is submitted, **Then** the active SLO is updated, the audit log records the action with actor and rationale, and previous SLO state is preserved. | Integration test |
| AC-006 | **Given** an SRE rejects a recommendation with rationale "target too aggressive for upcoming holiday traffic", **When** submitted, **Then** the rationale is stored in the audit log and the recommendation status is updated. | Integration test |
| AC-007 | **Given** 200 concurrent users hitting the API, **When** load test runs for 10 minutes, **Then** p95 latency for cached recommendation retrieval is < 500ms and error rate is < 0.1%. | Load test (k6/Locust) |
| AC-008 | **Given** Prometheus is unreachable, **When** recommendation retrieval is requested, **Then** cached recommendations are served with `stale: true` and no 500 errors are returned. | Integration test with Prometheus mock returning 503 |

### 13.2 Post-MVP Acceptance Criteria (Phase 3-4)

| ID | Criterion | Verification Method |
|----|-----------|-------------------|
| AC-009 | **Given** a deployment causes p99 latency to increase by 20%, **When** drift detection runs, **Then** at least 2 of 3 detectors confirm drift, the recommendation is marked stale, and the service owner is notified within 30 minutes. | Integration test with injected latency shift |
| AC-010 | **Given** an accepted SLO, **When** burn-rate alert config is requested, **Then** valid Prometheus recording rules are generated following Google SRE multi-window format with correct burn rate thresholds. | Unit test + Prometheus rule validation |
| AC-011 | **Given** an auto-approval rule for low-criticality services, **When** a recommendation matching the rule is generated, **Then** it is auto-accepted with `action: auto_approve` in the audit log. | Integration test |

### 13.3 Operational Acceptance Criteria

| ID | Criterion | Verification Method |
|----|-----------|-------------------|
| AC-012 | System achieves 99.9% uptime over first 30 days of production | Prometheus uptime monitoring |
| AC-013 | Batch aggregation job completes within 30 minutes for 5,000 services | Job duration metric |
| AC-014 | Database storage growth matches estimates (±20%) | PostgreSQL `pg_stat_user_tables` |
| AC-015 | All API endpoints return correct OpenAPI-documented response schemas | schemathesis contract tests in CI |
