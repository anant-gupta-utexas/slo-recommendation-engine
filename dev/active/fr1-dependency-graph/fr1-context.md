# FR-1 Context Document
## Service Dependency Graph Ingestion & Management

**Created:** 2026-02-14
**Last Updated:** 2026-02-14

---

## Key Decisions Made

### Architecture Decisions

| Decision | Options Considered | Choice Made | Rationale | Date |
|----------|-------------------|-------------|-----------|------|
| **Graph Storage** | PostgreSQL vs Neo4j | PostgreSQL with recursive CTEs | Sufficient for 10K+ edges, lower ops overhead, team expertise | 2026-02-14 |
| **Async Pattern** | Full async vs Hybrid sync/async | Full async/await throughout | Best performance, modern Python, AsyncPG + SQLAlchemy 2.0 support | 2026-02-14 |
| **Discovery Sources (MVP)** | Manual only vs Manual+OTel vs All sources | Manual API + OTel Service Graph | Balance completeness and scope; defer K8s/Service Mesh | 2026-02-14 |
| **Circular Dependency Handling** | Block ingestion vs Store alert vs Auto-contract | Store alert, allow ingestion, warn in response | Non-blocking for teams, gradual remediation path | 2026-02-14 |
| **Task Queue** | APScheduler vs Celery | APScheduler for MVP | Simpler, in-process, sufficient for MVP task volume. Migrate to Celery if task volume > 100/min | 2026-02-14 |
| **Cache Invalidation** | Invalidate all vs Selective invalidation | Invalidate all cached subgraphs on update | Simple for MVP. Optimize to selective invalidation if cache thrashing observed in production | 2026-02-14 |
| **Staleness Threshold** | Global threshold vs Per-source threshold | Global threshold (7 days, `STALE_EDGE_THRESHOLD_HOURS=168`) | Simpler single config value. Per-source thresholds deferred to Phase 3+ if needed | 2026-02-14 |
| **API Key Management** | CLI tool vs Admin API vs Both | CLI tool only (`slo-cli api-keys create`) | Simplest initial setup UX. Admin API deferred to Phase 3 | 2026-02-14 |
| **Prometheus Metric Labels** | Include service_id vs Omit service_id | Omit service_id from all metric labels | Avoids high cardinality (5000+ services). Use exemplars for per-service sampling | 2026-02-14 |

### Technical Stack Decisions

| Layer | Technology | Version | Justification |
|-------|-----------|---------|---------------|
| **Language** | Python | 3.12+ | Team expertise, async support, rich ecosystem |
| **API Framework** | FastAPI | 0.115+ | Async-native, auto OpenAPI, Pydantic validation |
| **ORM** | SQLAlchemy | 2.0+ | Async support, mature PostgreSQL integration |
| **Database** | PostgreSQL | 16+ | Recursive CTEs, JSONB, proven at scale |
| **Async Driver** | AsyncPG | 0.29+ | High-performance async PostgreSQL driver |
| **Migrations** | Alembic | 1.13+ | Standard SQLAlchemy migration tool |
| **Task Scheduler** | APScheduler | 3.10+ | Lightweight, sufficient for MVP |
| **Cache/Rate Limit** | Redis | 7+ | Fast, distributed state for rate limiting |
| **Testing** | pytest | Latest | De facto Python test framework |
| **Load Testing** | k6 | Latest | Modern, scriptable load testing |

---

## Dependencies

### Internal Module Dependencies

```
infrastructure/api/routes/dependencies.py
    └── application/use_cases/ingest_dependency_graph.py
    └── application/use_cases/query_dependency_subgraph.py
        └── domain/services/graph_traversal_service.py
        └── domain/repositories/dependency_repository.py
            └── infrastructure/database/repositories/dependency_repository.py
                └── infrastructure/database/models.py
```

**Dependency Flow:**
- API layer depends on Application layer (use cases, DTOs)
- Application layer depends on Domain layer (entities, services, repository interfaces)
- Infrastructure layer implements Domain layer interfaces
- **No reverse dependencies** (Clean Architecture principle)

### External Service Dependencies

| Service | Purpose | Criticality | Fallback |
|---------|---------|-------------|----------|
| **PostgreSQL** | Primary data store | Critical | None (hard requirement) |
| **Redis** | Rate limiting, caching | High | In-memory fallback for rate limiting (single instance only) |
| **Prometheus** | OTel Service Graph metrics source | Medium | Continue with manual ingestion only |

### Library Dependencies

See `pyproject.toml` for full dependency list. Key libraries:
- `fastapi[all]>=0.115.0` - API framework
- `sqlalchemy[asyncio]>=2.0.0` - ORM
- `asyncpg>=0.29.0` - PostgreSQL driver
- `alembic>=1.13.0` - Migrations
- `pydantic>=2.0.0` - Validation
- `redis[hiredis]>=5.0.0` - Caching/rate limiting
- `apscheduler>=3.10.0` - Background tasks
- `prometheus-client>=0.19.0` - Metrics export
- `pytest>=8.0.0` - Testing
- `pytest-asyncio>=0.23.0` - Async test support
- `testcontainers>=3.7.0` - Integration testing

---

## Integration Points

### Upstream Consumers (Who calls FR-1)

| Consumer | Endpoint Used | Frequency | Purpose |
|----------|--------------|-----------|---------|
| **Backstage Plugin** | GET /services/{id}/dependencies | ~100 req/min | Display dependency graph in service catalog |
| **FR-2 (SLO Recommendations)** | QueryDependencySubgraphUseCase (internal) | On-demand | Retrieve dependencies for composite SLO calculation |
| **FR-4 (Impact Analysis)** | QueryDependencySubgraphUseCase (internal) | On-demand | Traverse graph for upstream impact |
| **Manual Admin** | POST /services/dependencies | ~1 req/hour | Manual graph corrections/additions |
| **OTel Integration** | POST /services/dependencies (via background task) | Every 15 min | Automated discovery from traces |

### Downstream Dependencies (What FR-1 calls)

| Service | Purpose | Interaction Pattern |
|---------|---------|-------------------|
| **PostgreSQL** | Graph storage | Async queries via AsyncPG |
| **Redis** | Rate limiting, cache | Async operations via aioredis |
| **Prometheus** | OTel Service Graph metrics | HTTP GET (PromQL remote read API) - FR-6 integration |

---

## Files Created/Modified

### Phase 1: Domain Foundation

**New Files:**
- `src/domain/entities/service.py`
- `src/domain/entities/service_dependency.py`
- `src/domain/entities/circular_dependency_alert.py`
- `src/domain/services/graph_traversal_service.py`
- `src/domain/services/circular_dependency_detector.py`
- `src/domain/services/edge_merge_service.py`
- `src/domain/repositories/service_repository.py`
- `src/domain/repositories/dependency_repository.py`
- `src/domain/repositories/circular_dependency_alert_repository.py`
- `tests/unit/domain/entities/test_*.py` (multiple test files)
- `tests/unit/domain/services/test_*.py` (multiple test files)

### Phase 2: Infrastructure & Persistence

**New Files:**
- `alembic/versions/001_create_services_table.py`
- `alembic/versions/002_create_service_dependencies_table.py`
- `alembic/versions/003_create_circular_dependency_alerts_table.py`
- `src/infrastructure/database/models.py`
- `src/infrastructure/database/repositories/service_repository.py`
- `src/infrastructure/database/repositories/dependency_repository.py`
- `src/infrastructure/database/repositories/circular_dependency_alert_repository.py`
- `src/infrastructure/database/session.py`
- `src/infrastructure/database/config.py`
- `src/infrastructure/database/health.py`
- `tests/integration/infrastructure/database/test_*.py` (multiple test files)
- `tests/integration/conftest.py` (test fixtures)

**Modified Files:**
- `.env.example` (database configuration)

### Phase 3: Application Layer

**New Files:**
- `src/application/dtos/dependency_graph_dto.py`
- `src/application/dtos/dependency_subgraph_dto.py`
- `src/application/dtos/common.py`
- `src/application/use_cases/ingest_dependency_graph.py`
- `src/application/use_cases/query_dependency_subgraph.py`
- `src/application/use_cases/detect_circular_dependencies.py`
- `tests/unit/application/dtos/test_*.py`
- `tests/unit/application/use_cases/test_*.py`
- `tests/integration/application/test_*.py`

### Phase 4: API Layer

**New Files:**
- `src/infrastructure/api/routes/dependencies.py`
- `src/infrastructure/api/main.py`
- `src/infrastructure/api/middleware/auth.py`
- `src/infrastructure/api/middleware/rate_limit.py`
- `src/infrastructure/api/middleware/error_handler.py`
- `src/infrastructure/api/schemas/error_schema.py`
- `src/infrastructure/database/models/api_key.py`
- `src/infrastructure/cli/api_keys.py` - CLI tool for API key management (MVP: CLI-only, admin API deferred)
- `tests/integration/infrastructure/api/test_auth.py`
- `tests/unit/infrastructure/cli/test_api_keys.py`
- `tests/e2e/test_dependency_api.py`

### Phase 5: Observability

**New Files:**
- `src/infrastructure/observability/metrics.py`
- `src/infrastructure/observability/logging.py`
- `src/infrastructure/observability/tracing.py`
- `src/infrastructure/api/middleware/metrics.py`
- `src/infrastructure/api/middleware/logging.py`
- `src/infrastructure/api/middleware/tracing.py`
- `src/infrastructure/api/routes/health.py`
- `tests/integration/infrastructure/api/test_health.py`

### Phase 6: Integration & Deployment

**New Files:**
- `src/infrastructure/integrations/otel_service_graph.py`
- `src/infrastructure/tasks/scheduler.py`
- `src/infrastructure/tasks/ingest_otel_graph.py`
- `src/infrastructure/tasks/mark_stale_edges.py`
- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`
- `.github/workflows/ci.yml`
- `.github/workflows/deploy-staging.yml`
- `helm/slo-engine/Chart.yaml`
- `helm/slo-engine/values.yaml`
- `helm/slo-engine/templates/*.yaml` (multiple K8s manifests)
- `k8s/staging/values-override.yaml`
- `tests/integration/infrastructure/integrations/test_otel_service_graph.py`

**Modified Files:**
- `pyproject.toml` (add dependencies)
- `README.md` (update with FR-1 documentation)
- `.env.example` (full configuration)

---

## Database Schema Summary

### Tables Created

1. **services** (5 columns + audit fields)
   - Primary Key: `id` (UUID)
   - Unique: `service_id` (business identifier)
   - Indexes: service_id, team, criticality, discovered

2. **service_dependencies** (12 columns + audit fields)
   - Primary Key: `id` (UUID)
   - Foreign Keys: source_service_id, target_service_id → services.id
   - Unique Constraint: (source, target, discovery_source)
   - Indexes: source_service_id, target_service_id, (source, target), discovery_source, last_observed_at, is_stale

3. **circular_dependency_alerts** (5 columns + audit field)
   - Primary Key: `id` (UUID)
   - Unique Constraint: cycle_path (JSONB)
   - Indexes: status, detected_at

### Key Queries to Optimize

1. **Recursive Graph Traversal** (most frequent)
   - Indexed on: source_service_id, is_stale
   - Target: <100ms for 3-hop on 5000 nodes

2. **Bulk Upsert** (ingestion)
   - Uses ON CONFLICT for idempotent writes
   - Target: <2s for 1000 records

3. **Adjacency List** (cycle detection)
   - Full table scan with GROUP BY
   - Cached in memory for Tarjan's algorithm

---

## Configuration Management

### Environment Variables

**Database:**
- `DATABASE_URL` - PostgreSQL connection string
- `DB_POOL_SIZE` - Connection pool size (default: 20)
- `DB_MAX_OVERFLOW` - Burst capacity (default: 10)

**Redis:**
- `REDIS_URL` - Redis connection string
- `REDIS_CACHE_TTL` - Cache TTL in seconds (default: 300)

**API:**
- `API_HOST` - Host to bind (default: 0.0.0.0)
- `API_PORT` - Port to bind (default: 8000)
- `API_WORKERS` - Number of Uvicorn workers (default: 4)

**Rate Limiting:**
- `RATE_LIMIT_INGESTION` - Ingestion endpoint limit (default: 10 req/min)
- `RATE_LIMIT_QUERY` - Query endpoint limit (default: 60 req/min)

**Background Tasks:**
- `OTEL_GRAPH_INGEST_INTERVAL_MINUTES` - OTel sync frequency (default: 15)
- `STALE_EDGE_THRESHOLD_HOURS` - Staleness threshold (default: 168 = 7 days)

**Observability:**
- `LOG_LEVEL` - Logging level (default: INFO)
- `OTEL_EXPORTER_OTLP_ENDPOINT` - OTLP trace exporter endpoint (optional)
- `OTEL_TRACE_SAMPLE_RATE` - Trace sampling rate (default: 0.1)

**Prometheus Integration (FR-6):**
- `PROMETHEUS_URL` - Prometheus server URL
- `PROMETHEUS_TIMEOUT_SECONDS` - Query timeout (default: 30)

### Configuration Files

- `.env` - Local development (gitignored)
- `.env.example` - Template (committed)
- `helm/slo-engine/values.yaml` - Kubernetes production config
- `k8s/staging/values-override.yaml` - Staging overrides

---

## Testing Strategy Summary

### Test Coverage Targets

| Layer | Coverage Target | Rationale |
|-------|----------------|-----------|
| **Domain** | >90% | Core business logic, no framework dependencies |
| **Application** | >85% | Use case orchestration |
| **Infrastructure** | >75% | Framework integrations, harder to test |
| **Overall** | >80% | Sufficient for production readiness |

### Test Types Distribution

- **Unit Tests (70%)**: Domain entities, services, use cases
- **Integration Tests (25%)**: Repository implementations, API endpoints, database operations
- **E2E Tests (5%)**: Full API workflows

### Test Data

**Synthetic Graphs:**
- Small graph: 10 services, 20 edges (for unit tests)
- Medium graph: 100 services, 500 edges (for integration tests)
- Large graph: 1000 services, 5000 edges (for load tests)
- Cyclic graph: 5 circular dependencies (for cycle detection tests)

**Test Fixtures:**
- Located in `tests/fixtures/`
- Faker library for generating realistic metadata
- Seed scripts for populating test databases

---

## Performance Benchmarks

### Established Targets

| Operation | Target | Rationale |
|-----------|--------|-----------|
| Graph ingestion (1000 nodes) | <30s | From TRD NFR1.2 |
| Subgraph query (3-hop, cached) | <500ms | From TRD NFR1.1 |
| Subgraph query (on-demand) | <5s | From TRD NFR1.1 |
| Graph traversal (3-hop, 5000 nodes) | <100ms | From TRD PERF-004 |
| Tarjan's SCC detection (5000 nodes) | <10s | Estimated O(V+E) complexity |
| API concurrent users | 200+ | From TRD PERF-005 |

### Monitoring Metrics

**To Track in Production:**
- API request duration (p50, p95, p99)
- Graph traversal duration by depth
- Database connection pool utilization
- Cache hit/miss rates
- Background task execution time
- Ingestion throughput (services/sec, edges/sec)

---

## Security Considerations Summary

### Input Validation Layers

1. **Pydantic Schema Validation** (API layer)
2. **Domain Entity Validation** (Domain layer)
3. **Database Constraints** (Infrastructure layer)

### Authentication Flow

```
Request
  → Extract X-API-Key header
  → Verify against hashed keys in DB (bcrypt)
  → Attach client_id to request context
  → Check rate limit bucket for client_id
  → Allow/Deny with 401/429
```

### Rate Limiting Algorithm

**Token Bucket:**
- Bucket capacity: 10 tokens (ingestion), 60 tokens (query)
- Refill rate: 1 token per 6 seconds (ingestion), 1 token per second (query)
- Storage: Redis (distributed across instances)

### SQL Injection Prevention

- ✅ All queries via SQLAlchemy ORM (parameterized)
- ✅ No raw SQL string interpolation
- ✅ Pydantic validation before hitting database
- ✅ Database constraints as final safety net

---

## Risks & Mitigations

### Identified Risks

| Risk | Impact | Probability | Mitigation Status |
|------|--------|-------------|------------------|
| PostgreSQL CTE performance degrades at scale | Medium | Medium | Benchmark early; abstract repository for Neo4j migration path |
| OTel Service Graph provides incomplete topology | High | High | Multi-source discovery; confidence scores; manual override |
| Circular dependencies common in legacy architecture | Medium | High | Non-blocking ingestion; alert system; gradual remediation |
| Redis failure impacts rate limiting | Medium | Low | In-memory fallback (per-instance, not distributed) |
| Database migrations lock tables | High | Low | Use CONCURRENTLY for indexes; test on staging first |

### Technical Debt Accepted

| Item | Rationale | Repayment Plan |
|------|-----------|---------------|
| APScheduler instead of Celery | Simpler for MVP task volume | Migrate to Celery if task count > 100/min |
| Cache invalidation invalidates all subgraphs | Simple implementation | Optimize to selective invalidation if cache thrashing observed |
| Global staleness threshold | Single config value for MVP | Add per-source thresholds in Phase 3+ if needed |
| CLI-only API key management | Simplest initial setup UX | Add admin API (`POST /admin/api-keys`) in Phase 3 |
| No service_id in metric labels | Avoids high cardinality with 5000+ services | Use exemplars for per-service sampling if granularity needed |
| Single-region deployment | MVP scope constraint | Design supports multi-region via service metadata |
| No OAuth2 support in MVP | API keys sufficient for backend-to-backend | Add OAuth2 in Phase 4 for user-facing Backstage integration |

---

## Next Steps

**Immediate (This Week):**
1. ✅ Complete planning document
2. ✅ All decisions finalized (no pending questions)
3. ⬜ Review plan with team (schedule 1-hour meeting)
4. ⬜ Set up project board with tasks

**Phase 1 Kickoff (Week 1):**
1. ⬜ Assign Phase 1 tasks to engineers
2. ⬜ Set up daily standups
3. ⬜ Create feature branch: `feature/fr1-dependency-graph`
4. ⬜ Begin domain entity implementation

**Weekly Milestones:**
- Week 1: Domain layer complete, unit tests passing
- Week 2: Database schema deployed, repositories implemented
- Week 3: Use cases complete, application layer tested
- Week 4: API endpoints live, E2E tests passing
- Week 5: Observability integrated, monitoring operational
- Week 6: OTel integration complete, deployed to staging

---

**Document Version:** 1.1
**Last Updated:** 2026-02-14
**Change Log:**
- v1.1 (2026-02-14): Finalized all 5 pending decisions with recommended options
