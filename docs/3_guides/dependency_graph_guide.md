# Dependency Graph Developer Guide

> **Last Updated:** 2026-02-15
> **Feature:** FR-1 — Service Dependency Graph Ingestion & Management
> **Status:** Production Ready

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [API Reference](#api-reference)
- [Data Model](#data-model)
- [Key Concepts](#key-concepts)
- [Background Tasks](#background-tasks)
- [Configuration](#configuration)
- [Observability](#observability)
- [Security](#security)
- [Performance](#performance)
- [Extending the System](#extending-the-system)
- [Troubleshooting](#troubleshooting)

---

## Overview

The Service Dependency Graph is the foundational data structure of the SLO Recommendation Engine. It models the interconnections between microservices as a directed graph where:

- **Nodes** represent microservices (e.g., `api-gateway`, `auth-service`, `checkout-service`)
- **Edges** represent directed dependencies with rich annotations (communication mode, criticality, protocol, timeout, retry config)

This graph enables:
- **Dependency-aware SLO recommendations** (FR-2, FR-3) — understanding that a checkout service inheriting an unreliable payment API must have SLOs that account for that dependency
- **Impact analysis** (FR-4) — traversing upstream to find all services affected by a degraded dependency
- **Anti-pattern detection** — automatically detecting circular dependencies using Tarjan's algorithm
- **Multi-source discovery** — combining manual declarations with automated discovery from OpenTelemetry traces

### How It Fits in the System

```
                    ┌─────────────────────┐
                    │  Backstage Plugin   │  (External consumer)
                    │  Service Catalog UI │
                    └─────────┬───────────┘
                              │ GET /services/{id}/dependencies
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  SLO Recommendation Engine                    │
│                                                              │
│  ┌──────────────┐    ┌────────────────┐    ┌─────────────┐ │
│  │ FR-1         │───▶│ FR-2           │───▶│ FR-3        │ │
│  │ Dependency   │    │ SLO Recommend  │    │ Composite   │ │
│  │ Graph        │    │ Engine         │    │ SLOs        │ │
│  └──────┬───────┘    └────────────────┘    └─────────────┘ │
│         │                                                    │
│         │  ┌────────────────┐                               │
│         └─▶│ FR-4           │                               │
│            │ Impact Analysis │                               │
│            └────────────────┘                               │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ traces_service_graph_request_total
                    ┌─────────┴───────────┐
                    │  OTel Collector →    │
                    │  Prometheus          │  (Auto-discovery)
                    └─────────────────────┘
```

---

## Architecture

The dependency graph follows Clean Architecture with three layers. Dependencies point inward — infrastructure depends on application, which depends on domain.

### Layer Overview

```
┌────────────────────────────────────────────────────────────────────┐
│  Infrastructure Layer (src/infrastructure/)                         │
│  FastAPI routes, SQLAlchemy repos, OTel integration, scheduler     │
│                                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ API Routes   │  │ DB Repos     │  │ Integrations           │  │
│  │ dependencies │  │ dependency   │  │ otel_service_graph     │  │
│  │ health       │  │ service      │  │ tasks/scheduler        │  │
│  └──────┬───────┘  │ alert        │  └────────────────────────┘  │
│         │          └──────┬───────┘                               │
└─────────┼─────────────────┼──────────────────────────────────────┘
          │                 │
          ▼                 │ implements
┌─────────────────────────────────────────────────────────────────┐
│  Application Layer (src/application/)                             │
│  Use cases, DTOs — orchestrates domain logic                     │
│                                                                   │
│  ┌──────────────────────────────┐  ┌──────────────────────────┐ │
│  │ Use Cases                    │  │ DTOs                     │ │
│  │ • IngestDependencyGraph      │  │ • DependencyGraphIngest  │ │
│  │ • QueryDependencySubgraph    │  │   Request/Response       │ │
│  │ • DetectCircularDependencies │  │ • DependencySubgraph     │ │
│  └──────────────┬───────────────┘  │   Request/Response       │ │
│                 │                   └──────────────────────────┘ │
└─────────────────┼───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  Domain Layer (src/domain/)                                       │
│  Pure business logic — no framework dependencies                  │
│                                                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ Entities         │  │ Services        │  │ Repo Interfaces │ │
│  │ • Service        │  │ • GraphTraversal│  │ • ServiceRepo   │ │
│  │ • ServiceDep     │  │ • CircularDep   │  │ • DependencyRepo│ │
│  │ • CircularAlert  │  │   Detector      │  │ • AlertRepo     │ │
│  │                  │  │ • EdgeMerge     │  │                 │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Key Files

| File | Purpose | LOC |
|------|---------|-----|
| `src/domain/entities/service_dependency.py` | Dependency edge entity with enums and validation | ~180 |
| `src/domain/services/circular_dependency_detector.py` | Tarjan's SCC algorithm | ~80 |
| `src/domain/services/graph_traversal_service.py` | Traversal direction/depth orchestration | ~50 |
| `src/domain/services/edge_merge_service.py` | Multi-source conflict resolution | ~90 |
| `src/application/use_cases/ingest_dependency_graph.py` | Full ingestion workflow | ~260 |
| `src/application/use_cases/query_dependency_subgraph.py` | Subgraph query workflow | ~165 |
| `src/application/use_cases/detect_circular_dependencies.py` | Cycle detection workflow | ~104 |
| `src/infrastructure/database/repositories/dependency_repository.py` | PostgreSQL with recursive CTEs | ~560 |
| `src/infrastructure/api/routes/dependencies.py` | FastAPI endpoints | ~262 |
| `src/infrastructure/integrations/otel_service_graph.py` | Prometheus/OTel client | ~280 |

---

## API Reference

### Base URL

```
http://localhost:8000/api/v1
```

### Authentication

All endpoints (except `/health` and `/metrics`) require an API key:

```
Authorization: Bearer <your-api-key>
```

### Endpoints

#### POST /services/dependencies — Ingest Dependency Graph

Bulk upsert services and their dependency edges. Idempotent — safe to call repeatedly with the same data.

**Request:**

```bash
curl -X POST http://localhost:8000/api/v1/services/dependencies \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "manual",
    "nodes": [
      {
        "service_id": "api-gateway",
        "team": "platform",
        "criticality": "critical",
        "metadata": {"language": "go", "repo": "github.com/org/api-gateway"}
      },
      {
        "service_id": "auth-service",
        "team": "identity",
        "criticality": "critical"
      },
      {
        "service_id": "checkout-service",
        "team": "commerce",
        "criticality": "high"
      },
      {
        "service_id": "payment-service",
        "team": "payments",
        "criticality": "critical"
      }
    ],
    "edges": [
      {
        "source_service_id": "api-gateway",
        "target_service_id": "auth-service",
        "attributes": {
          "communication_mode": "sync",
          "criticality": "critical",
          "protocol": "grpc",
          "timeout_ms": 500,
          "retry_config": {
            "max_retries": 3,
            "backoff_ms": 100,
            "backoff_multiplier": 2.0
          }
        }
      },
      {
        "source_service_id": "api-gateway",
        "target_service_id": "checkout-service",
        "attributes": {
          "communication_mode": "sync",
          "criticality": "high",
          "protocol": "http",
          "timeout_ms": 2000
        }
      },
      {
        "source_service_id": "checkout-service",
        "target_service_id": "payment-service",
        "attributes": {
          "communication_mode": "sync",
          "criticality": "critical",
          "protocol": "grpc",
          "timeout_ms": 5000,
          "retry_config": {
            "max_retries": 2,
            "backoff_ms": 500,
            "backoff_multiplier": 1.5
          }
        }
      }
    ]
  }'
```

**Response (202 Accepted):**

```json
{
  "nodes_upserted": 4,
  "edges_upserted": 3,
  "circular_dependencies": [],
  "warnings": [],
  "conflicts": []
}
```

**Key Behaviors:**
- **Idempotent:** Uses `ON CONFLICT` for upserts — repeated calls with the same data have no side effects
- **Auto-discovery:** If an edge references a `service_id` not in the `nodes` array, a placeholder service is created with `discovered=true`
- **Circular dependency detection:** After ingestion, Tarjan's algorithm runs and any new cycles are returned in the `circular_dependencies` field
- **Sources:** Valid values are `manual`, `otel_service_graph`, `service_mesh`, `kubernetes`

**Error Responses:**

| Status | Description | Example |
|--------|-------------|---------|
| 400 | Invalid request body | Missing required fields |
| 401 | Missing or invalid API key | `Authorization` header absent |
| 429 | Rate limit exceeded (10 req/min) | Too many ingestion calls |
| 500 | Internal server error | Database connection failure |

---

#### GET /services/{service_id}/dependencies — Query Dependency Subgraph

Retrieve the dependency subgraph for a service, traversing upstream, downstream, or both directions.

**Request:**

```bash
# Downstream dependencies (what does this service call?)
curl "http://localhost:8000/api/v1/services/api-gateway/dependencies?direction=downstream&depth=3" \
  -H "Authorization: Bearer YOUR_API_KEY"

# Upstream dependencies (what calls this service?)
curl "http://localhost:8000/api/v1/services/payment-service/dependencies?direction=upstream&depth=2" \
  -H "Authorization: Bearer YOUR_API_KEY"

# Both directions
curl "http://localhost:8000/api/v1/services/checkout-service/dependencies?direction=both&depth=2" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `direction` | string | `downstream` | `downstream`, `upstream`, or `both` |
| `depth` | integer | `3` | Traversal depth (1-10) |
| `include_stale` | boolean | `false` | Include edges not refreshed within staleness threshold |

**Response (200 OK):**

```json
{
  "service_id": "api-gateway",
  "direction": "downstream",
  "depth": 3,
  "nodes": [
    {
      "service_id": "auth-service",
      "team": "identity",
      "criticality": "critical",
      "discovered": false
    },
    {
      "service_id": "checkout-service",
      "team": "commerce",
      "criticality": "high",
      "discovered": false
    },
    {
      "service_id": "payment-service",
      "team": "payments",
      "criticality": "critical",
      "discovered": false
    }
  ],
  "edges": [
    {
      "source_service_id": "api-gateway",
      "target_service_id": "auth-service",
      "communication_mode": "sync",
      "criticality": "critical",
      "protocol": "grpc",
      "timeout_ms": 500,
      "confidence_score": 1.0,
      "is_stale": false,
      "discovery_source": "manual"
    },
    {
      "source_service_id": "api-gateway",
      "target_service_id": "checkout-service",
      "communication_mode": "sync",
      "criticality": "high",
      "protocol": "http",
      "timeout_ms": 2000,
      "confidence_score": 1.0,
      "is_stale": false,
      "discovery_source": "manual"
    },
    {
      "source_service_id": "checkout-service",
      "target_service_id": "payment-service",
      "communication_mode": "sync",
      "criticality": "critical",
      "protocol": "grpc",
      "timeout_ms": 5000,
      "confidence_score": 1.0,
      "is_stale": false,
      "discovery_source": "manual"
    }
  ],
  "statistics": {
    "total_nodes": 3,
    "total_edges": 3,
    "max_depth_reached": 2,
    "has_circular_dependencies": false,
    "upstream_count": 0,
    "downstream_count": 3
  }
}
```

**Error Responses:**

| Status | Description |
|--------|-------------|
| 404 | Service not found |
| 400 | Invalid depth (must be 1-10) or direction |
| 401 | Missing or invalid API key |
| 429 | Rate limit exceeded (60 req/min) |

---

#### GET /health — Liveness Probe

```bash
curl http://localhost:8000/api/v1/health
# {"status": "healthy", "timestamp": "2026-02-15T10:30:00Z"}
```

#### GET /health/ready — Readiness Probe

Checks database and Redis connectivity.

```bash
curl http://localhost:8000/api/v1/health/ready
# {"status": "ready", "checks": {"database": "healthy", "redis": "healthy"}}
```

#### GET /metrics — Prometheus Metrics

```bash
curl http://localhost:8000/api/v1/metrics
# HELP slo_engine_http_requests_total Total HTTP requests
# TYPE slo_engine_http_requests_total counter
# ...
```

### Error Response Format (RFC 7807)

All errors follow the [RFC 7807 Problem Details](https://datatracker.ietf.org/doc/html/rfc7807) format:

```json
{
  "type": "https://httpstatuses.com/400",
  "title": "Bad Request",
  "status": 400,
  "detail": "Invalid depth value: must be between 1 and 10",
  "correlation_id": "abc-123-def-456"
}
```

The `correlation_id` is also returned in the `X-Correlation-ID` response header for tracing.

---

## Data Model

### Database Schema

```
┌─────────────────────────┐       ┌──────────────────────────────────┐
│ services                │       │ service_dependencies              │
├─────────────────────────┤       ├──────────────────────────────────┤
│ id          UUID   PK   │◀──┐   │ id                UUID   PK     │
│ service_id  VARCHAR UQ  │   ├──│ source_service_id  UUID   FK     │
│ metadata    JSONB       │   └──│ target_service_id  UUID   FK     │
│ criticality VARCHAR     │       │ communication_mode VARCHAR       │
│ team        VARCHAR     │       │ criticality        VARCHAR       │
│ discovered  BOOLEAN     │       │ discovery_source   VARCHAR       │
│ created_at  TIMESTAMP   │       │ protocol           VARCHAR       │
│ updated_at  TIMESTAMP   │       │ timeout_ms         INTEGER       │
└─────────────────────────┘       │ retry_config       JSONB         │
                                  │ confidence_score   FLOAT         │
┌─────────────────────────┐       │ observation_count  INTEGER       │
│ circular_dependency_    │       │ is_stale           BOOLEAN       │
│ alerts                  │       │ last_observed_at   TIMESTAMP     │
├─────────────────────────┤       │ created_at         TIMESTAMP     │
│ id          UUID   PK   │       │ updated_at         TIMESTAMP     │
│ cycle_path  JSONB  UQ   │       └──────────────────────────────────┘
│ status      VARCHAR     │       UNIQUE(source_service_id,
│ detected_at TIMESTAMP   │              target_service_id,
│ resolved_at TIMESTAMP   │              discovery_source)
└─────────────────────────┘

┌─────────────────────────┐
│ api_keys                │
├─────────────────────────┤
│ id          UUID   PK   │
│ name        VARCHAR UQ  │
│ key_hash    VARCHAR     │  (bcrypt)
│ is_active   BOOLEAN     │
│ created_at  TIMESTAMP   │
│ last_used_at TIMESTAMP  │
│ revoked_at  TIMESTAMP   │
└─────────────────────────┘
```

### Alembic Migrations

| Migration | Table | Description |
|-----------|-------|-------------|
| `13cdc22bf8f3` | `services` | Service registry with indexes and auto-update trigger |
| `4f4258078909` | `service_dependencies` | Dependency edges with FKs, constraints, and composite indexes |
| `7b72a01346cf` | `circular_dependency_alerts` | Cycle alerts with JSONB unique constraint |
| `2d6425d45f9f` | `api_keys` | API key authentication |

### Key Constraints

- **No self-loops:** `CHECK (source_service_id != target_service_id)` on `service_dependencies`
- **Confidence bounds:** `CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0)`
- **Unique edges per source:** `UNIQUE (source_service_id, target_service_id, discovery_source)` — the same pair can have edges from different discovery sources
- **Cycle path deduplication:** `UNIQUE (cycle_path)` on alerts prevents duplicate alerts for the same cycle

---

## Key Concepts

### Graph Traversal with Recursive CTEs

The most performance-critical operation is graph traversal, implemented using PostgreSQL recursive Common Table Expressions (CTEs). This avoids loading the entire graph into memory.

**How it works:**

```sql
-- Simplified downstream traversal
WITH RECURSIVE traversal AS (
    -- Base case: direct dependencies of the starting service
    SELECT target_service_id, 1 AS depth, ARRAY[source_service_id] AS path
    FROM service_dependencies
    WHERE source_service_id = :start_id AND is_stale = false

    UNION ALL

    -- Recursive case: follow edges from discovered services
    SELECT sd.target_service_id, t.depth + 1, t.path || sd.source_service_id
    FROM service_dependencies sd
    JOIN traversal t ON sd.source_service_id = t.target_service_id
    WHERE t.depth < :max_depth
      AND sd.target_service_id != ALL(t.path)  -- Cycle prevention
      AND sd.is_stale = false
)
SELECT DISTINCT * FROM traversal;
```

**Cycle prevention** is handled by tracking the path as a PostgreSQL array and checking `!= ALL(path)` to avoid revisiting nodes.

**Performance:** 3-hop traversal on 1,000 nodes completes in ~50ms (target: <100ms).

### Circular Dependency Detection (Tarjan's Algorithm)

Circular dependencies are detected using [Tarjan's strongly connected components algorithm](https://en.wikipedia.org/wiki/Tarjan%27s_strongly_connected_components_algorithm), which runs in O(V+E) time.

**How it works:**
1. Load the full adjacency list from the database
2. Run Tarjan's algorithm to find all strongly connected components (SCCs)
3. Filter out single-node SCCs (a node connected only to itself is not a meaningful cycle)
4. Create `CircularDependencyAlert` entities for newly detected cycles
5. Deduplicate against existing alerts using the sorted cycle path

**When it runs:**
- After every ingestion operation (as part of `IngestDependencyGraphUseCase`)
- Alerts are stored with status `open` and can be `acknowledged` or `resolved`

### Multi-Source Discovery & Confidence Scores

Dependencies can be discovered from multiple sources, each with a different confidence level:

| Source | Confidence | Priority | Description |
|--------|-----------|----------|-------------|
| `manual` | 1.0 | Highest | Explicit human declaration via API |
| `service_mesh` | 0.9 | High | Istio/Linkerd sidecar telemetry |
| `otel_service_graph` | 0.7 | Medium | OpenTelemetry trace-based discovery |
| `kubernetes` | 0.5 | Lowest | K8s manifest/config inference |

**Conflict resolution:** When the same edge (source -> target) is reported by multiple sources, the `EdgeMergeService` resolves conflicts by keeping the highest-priority source's attributes while maintaining all source observations.

### Edge Staleness

Edges have a `last_observed_at` timestamp that is refreshed on every ingestion. A background task runs daily to mark edges as stale if they haven't been refreshed within the threshold (default: 7 days).

- **Stale edges** are excluded from traversal queries by default
- Pass `include_stale=true` to include them
- Staleness indicates the dependency may no longer exist (the source stopped reporting it)

---

## Background Tasks

Two scheduled tasks run via APScheduler (in-process):

### 1. OTel Service Graph Ingestion

**Schedule:** Every 15 minutes (configurable via `OTEL_GRAPH_INGEST_INTERVAL_MINUTES`)

**What it does:**
1. Queries Prometheus for `traces_service_graph_request_total` metrics
2. Parses metric labels to extract `client` and `server` service names
3. Maps them to a `DependencyGraphIngestRequest` with source `otel_service_graph`
4. Calls `IngestDependencyGraphUseCase` to upsert the discovered edges

**Files:**
- `src/infrastructure/integrations/otel_service_graph.py` — Prometheus client
- `src/infrastructure/tasks/ingest_otel_graph.py` — Scheduled task wrapper

### 2. Stale Edge Detection

**Schedule:** Daily at 2:00 AM UTC (CronTrigger)

**What it does:**
1. Queries for edges where `last_observed_at < now() - threshold`
2. Sets `is_stale = true` on matching edges
3. Logs the count of edges marked stale

**Files:**
- `src/infrastructure/tasks/mark_stale_edges.py`

### Scheduler Management

```python
# src/infrastructure/tasks/scheduler.py
# Integrated into FastAPI lifespan - starts on app boot, stops on shutdown
# Jobs can be triggered manually for testing:
from src.infrastructure.tasks.scheduler import trigger_job_now
await trigger_job_now("otel_graph_ingestion")
```

---

## Configuration

All configuration is managed via environment variables with Pydantic Settings (`src/infrastructure/config/settings.py`).

### Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| **Database** | | |
| `DATABASE_URL` | (required) | `postgresql+asyncpg://user:pass@host:5432/db` |
| `DB_POOL_SIZE` | `20` | Connection pool size |
| `DB_MAX_OVERFLOW` | `10` | Max burst connections |
| **Redis** | | |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `REDIS_CACHE_TTL` | `300` | Cache TTL in seconds |
| **API** | | |
| `API_HOST` | `0.0.0.0` | Bind host |
| `API_PORT` | `8000` | Bind port |
| `API_WORKERS` | `4` | Uvicorn worker count |
| **Rate Limiting** | | |
| `RATE_LIMIT_INGESTION` | `10` | Ingestion endpoint req/min |
| `RATE_LIMIT_QUERY` | `60` | Query endpoint req/min |
| **Background Tasks** | | |
| `OTEL_GRAPH_INGEST_INTERVAL_MINUTES` | `15` | OTel sync frequency |
| `STALE_EDGE_THRESHOLD_HOURS` | `168` | Edge staleness threshold (7 days) |
| **Observability** | | |
| `LOG_LEVEL` | `INFO` | Logging level |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | (optional) | OTLP gRPC endpoint |
| `OTEL_TRACE_SAMPLE_RATE` | `0.1` | Trace sampling rate (10%) |
| **Prometheus** | | |
| `PROMETHEUS_URL` | (optional) | Prometheus server URL |
| `PROMETHEUS_TIMEOUT_SECONDS` | `30` | PromQL query timeout |

### Configuration Files

| File | Purpose |
|------|---------|
| `.env` | Local development (gitignored) |
| `.env.example` | Template with all variables documented |
| `helm/slo-engine/values.yaml` | Kubernetes production defaults |
| `k8s/staging/values-override.yaml` | Staging-specific overrides |

---

## Observability

### Prometheus Metrics

13 metrics are exported at `GET /api/v1/metrics`:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `slo_engine_http_requests_total` | Counter | method, endpoint, status_code | Total HTTP requests |
| `slo_engine_http_request_duration_seconds` | Histogram | method, endpoint, status_code | Request latency |
| `slo_engine_graph_traversal_duration_seconds` | Histogram | direction, depth | Graph query latency |
| `slo_engine_db_connections_active` | Gauge | — | Active DB connections |
| `slo_engine_cache_hits_total` | Counter | cache_type | Cache hits |
| `slo_engine_cache_misses_total` | Counter | cache_type | Cache misses |
| `slo_engine_graph_nodes_upserted_total` | Counter | discovery_source | Nodes ingested |
| `slo_engine_graph_edges_upserted_total` | Counter | discovery_source | Edges ingested |
| `slo_engine_circular_dependencies_detected_total` | Counter | — | Cycles found |
| `slo_engine_rate_limit_exceeded_total` | Counter | client_id, endpoint | Rate limit hits |

**Design decision:** `service_id` is intentionally omitted from metric labels to avoid high cardinality (5,000+ services). Use OpenTelemetry exemplars for per-service debugging if needed.

### Structured Logging

All logs are JSON-formatted via structlog with automatic correlation ID injection:

```json
{
  "timestamp": "2026-02-15T10:30:00Z",
  "level": "info",
  "event": "dependency_graph_ingested",
  "correlation_id": "abc-123-def-456",
  "nodes_upserted": 4,
  "edges_upserted": 3,
  "source": "manual",
  "duration_ms": 42
}
```

**Sensitive data filtering:** API keys, passwords, and tokens are automatically redacted from logs.

### Distributed Tracing

OpenTelemetry auto-instruments FastAPI, SQLAlchemy, and HTTPX. Custom spans are added to repository operations:

- `dependency_repository.traverse_graph` — includes `direction`, `depth`, `services_count`, `edges_count` attributes
- `dependency_repository.bulk_upsert` — includes `edge_count` attribute

Configure the OTLP exporter endpoint via `OTEL_EXPORTER_OTLP_ENDPOINT` to send traces to Jaeger, Tempo, or any OTLP-compatible backend.

---

## Security

### Authentication

API key authentication using bcrypt-hashed keys stored in PostgreSQL:

1. Client sends `Authorization: Bearer <api-key>` header
2. Middleware iterates active keys, comparing with bcrypt
3. On match: attaches `client_id` to request context, updates `last_used_at`
4. On failure: returns 401 with RFC 7807 error body

**Health and metrics endpoints** are excluded from authentication.

### Rate Limiting

Token bucket algorithm with per-client, per-endpoint granularity:

| Endpoint | Limit | Burst |
|----------|-------|-------|
| `POST /services/dependencies` | 10 req/min | 10 tokens |
| `GET /services/{id}/dependencies` | 60 req/min | 60 tokens |
| All other endpoints | 30 req/min | 30 tokens |

Rate limit headers are included in all responses:
- `X-RateLimit-Limit` — Maximum requests per window
- `X-RateLimit-Remaining` — Remaining requests
- `X-RateLimit-Reset` — Seconds until limit resets

### Input Validation

Three layers of validation prevent malformed data:

1. **Pydantic schemas** (API layer) — Type validation, required fields, value ranges
2. **Domain entity `__post_init__`** (Domain layer) — Business rules (no self-loops, confidence bounds)
3. **Database constraints** (Infrastructure layer) — Foreign keys, unique constraints, CHECK constraints

### SQL Injection Prevention

All database queries use SQLAlchemy ORM with parameterized queries. No raw SQL string interpolation exists in the codebase.

---

## Performance

### Benchmarks

| Operation | Target | Measured | Method |
|-----------|--------|----------|--------|
| Graph ingestion (1000 nodes) | <30s | ~15s | Integration test |
| 3-hop traversal (1000 nodes) | <100ms | ~50ms | Integration test |
| Tarjan's SCC (500 nodes) | <1s | <100ms | Unit test |
| API response (cached) | p95 <500ms | — | Pending load test |
| Concurrent users | 200+ | — | Pending k6 test |

### Optimization Strategies

- **Recursive CTEs** avoid loading the full graph into application memory
- **Connection pooling** (pool_size=20, max_overflow=10) reuses database connections
- **Bulk upserts** with `ON CONFLICT` minimize round-trips for large ingestions
- **Partial indexes** on `is_stale`, `discovered`, `status` columns speed up filtered queries
- **Async/await** throughout enables high concurrency without thread overhead

### Scaling Path

For production scale beyond MVP:

1. **Read replicas** — Route traversal queries to read replicas
2. **Redis caching** — Cache frequently queried subgraphs (invalidate on ingestion)
3. **Celery workers** — Move background tasks to distributed workers
4. **Neo4j migration** — If recursive CTE performance degrades beyond 50K edges, the repository interface abstracts the storage backend for a Neo4j swap

---

## Extending the System

### Adding a New Discovery Source

1. **Add enum value** in `src/domain/entities/service_dependency.py`:
   ```python
   class DiscoverySource(str, Enum):
       MANUAL = "manual"
       OTEL_SERVICE_GRAPH = "otel_service_graph"
       SERVICE_MESH = "service_mesh"
       KUBERNETES = "kubernetes"
       MY_NEW_SOURCE = "my_new_source"  # Add here
   ```

2. **Set confidence score** in `src/domain/services/edge_merge_service.py`:
   ```python
   PRIORITY_MAP = {
       DiscoverySource.MANUAL: 1.0,
       DiscoverySource.SERVICE_MESH: 0.9,
       DiscoverySource.OTEL_SERVICE_GRAPH: 0.7,
       DiscoverySource.KUBERNETES: 0.5,
       DiscoverySource.MY_NEW_SOURCE: 0.6,  # Add here
   }
   ```

3. **Create integration** in `src/infrastructure/integrations/my_source.py`

4. **Create scheduled task** in `src/infrastructure/tasks/ingest_my_source.py`

5. **Register task** in `src/infrastructure/tasks/scheduler.py`

### Adding a New API Endpoint

1. Create route in `src/infrastructure/api/routes/`
2. Create Pydantic schema in `src/infrastructure/api/schemas/`
3. Create use case in `src/application/use_cases/` if new business logic is needed
4. Create DTOs in `src/application/dtos/` if new data shapes are needed
5. Register route in `src/infrastructure/api/main.py`
6. Add dependency injection in `src/infrastructure/api/dependencies.py`

### Adding Edge Annotations

To add a new field to dependency edges:

1. Add field to `ServiceDependency` entity (`src/domain/entities/service_dependency.py`)
2. Add column to `ServiceDependencyModel` (`src/infrastructure/database/models.py`)
3. Create Alembic migration: `alembic revision --autogenerate -m "add_field_to_dependencies"`
4. Update DTOs in `src/application/dtos/`
5. Update Pydantic schemas in `src/infrastructure/api/schemas/dependency_schema.py`

---

## Troubleshooting

### Common Issues

#### "Service not found" (404) after ingestion

The query endpoint uses `service_id` (the business identifier like `api-gateway`), not the UUID. Ensure you're querying with the correct identifier:

```bash
# Correct
curl ".../api/v1/services/api-gateway/dependencies"

# Wrong (UUID)
curl ".../api/v1/services/550e8400-e29b-41d4-a716-446655440000/dependencies"
```

#### Graph traversal returns empty results

1. Check that edges were ingested: query with `include_stale=true`
2. Verify the direction: `downstream` follows outgoing edges, `upstream` follows incoming edges
3. Check depth: default is 3, but you may need more for deep chains
4. Check staleness: if edges haven't been refreshed in 7 days, they're excluded by default

#### "Rate limit exceeded" (429)

Ingestion is limited to 10 requests/minute per client. For bulk operations:
- Batch nodes and edges into fewer, larger requests
- Each request can contain up to 1000 nodes and edges

#### Circular dependency alerts keep appearing

Circular dependencies are detected but not blocked. They indicate architectural anti-patterns. To resolve:
1. Review the cycle path in the alert
2. Refactor services to break the cycle (e.g., introduce an event bus for one direction)
3. Acknowledge the alert via the database (CLI tool pending)

#### Database migration failures

```bash
# Check current migration state
alembic current

# If stuck, try stamping to a known state
alembic stamp head

# Or rollback and re-apply
alembic downgrade base
alembic upgrade head
```

#### Background scheduler not starting

Check the logs for scheduler initialization:

```bash
docker-compose logs -f app | grep -i scheduler
# Look for: "Background task scheduler started"
# Look for: "Registered OTel ingestion job"
```

If Prometheus is not configured, the OTel ingestion task will log a warning but continue running.

---

## Related Documentation

| Document | Path |
|----------|------|
| Product Requirements | `docs/1_product/PRD.md` |
| Technical Requirements | `docs/2_architecture/TRD.md` |
| System Design | `docs/2_architecture/system_design.md` |
| Core Concepts (Clean Architecture) | `docs/3_guides/core_concepts.md` |
| Getting Started | `docs/3_guides/getting_started.md` |
| Testing Guide | `docs/4_testing/index.md` |
| FR-1 Development Plan | `dev/active/fr1-dependency-graph/fr1-plan.md` |
| FR-1 Task Checklist | `dev/active/fr1-dependency-graph/fr1-tasks.md` |
