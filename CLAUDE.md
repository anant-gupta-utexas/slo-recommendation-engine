# SLO Recommendation Engine

An AI-assisted backend system that analyzes telemetry data and structural dependencies across 500-5,000+ microservices to recommend achievable availability and latency SLOs.

This document is the central "signpost" for our repository. It provides quick setup commands, links to our core documentation library, and explains our development workflow.

## Quick Start: Developer Setup

```bash
# 1. Set up the virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv sync

# 2. Run the stack locally (API + PostgreSQL + Redis + Prometheus)
docker-compose up --build

# 3. Run local tests
pytest tests/unit/ tests/integration/ -v

# 4. Code quality checks
ruff check . && ruff format --check . && mypy src/ --strict
```

**Key URLs (after docker-compose up):**
- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- Prometheus: http://localhost:9090
- Health: http://localhost:8000/api/v1/health
- SLO Recommendations: http://localhost:8000/api/v1/services/{id}/slo-recommendations
- Constraint Analysis: http://localhost:8000/api/v1/services/{id}/constraint-analysis
- Error Budget: http://localhost:8000/api/v1/services/{id}/error-budget-breakdown

## Directory Structure & Walkthrough

### Core Documentation (`docs/`)
**EVERGREEN DOCS**: The single source of truth for the project.
```
docs/
├── 1_product/      # "Why": Product Requirements (PRD.md), research
├── 2_architecture/ # "High-Level How": System Design (system_design.md), TRD
├── 3_guides/       # "How-to": getting_started.md, core_concepts.md, dependency_graph_guide.md, slo_recommendations_guide.md, constraint_propagation_guide.md
└── 4_testing/      # "Quality": Testing strategy, examples, coverage goals (index.md)
```

### Development Documentation (`dev/`)
**WORK-IN-PROGRESS**: Technical designs and planning for features being built.
```
dev/
├── active/   # Active feature development plans (TDS, tasks)
│   └── fr1-dependency-graph/  # FR-1: Service Dependency Graph (COMPLETE)
└── archive/  # Historical record of completed features
```

**Dev Workflow:**
1. **Start Planning**: Create `dev/active/[feature-name]/`
2. **Define the Spec**: Create inside your feature folder:
   * `[feature-name]-plan.md` - Technical Design Specification (TDS)
   * `[feature-name]-context.md` - Key decisions, dependencies, files to touch
   * `[feature-name]-tasks.md` - Progress checklist
3. **Build**: Get TDS reviewed, then implement
4. **Update Core Docs**: Update `docs/` to reflect changes (part of Definition of Done)
5. **Archive**: Move folder from `dev/active/` to `dev/archive/` after merge

### Source Code (`src/`)
**Clean Architecture** implementation with three layers:
```
src/
├── domain/         # "Business Logic": Pure entities & rules, repository interfaces
│   ├── entities/   #   Service, ServiceDependency, CircularDependencyAlert
│   ├── services/   #   GraphTraversalService, CircularDependencyDetector, EdgeMergeService
│   └── repositories/ # Abstract interfaces (ServiceRepo, DependencyRepo, AlertRepo)
│
├── application/    # "Use Cases": Orchestrates workflows via DTOs
│   ├── use_cases/  #   IngestDependencyGraph, QueryDependencySubgraph, DetectCircularDependencies
│   └── dtos/       #   Request/response data transfer objects
│
└── infrastructure/ # "Frameworks": API (FastAPI), DB (SQLAlchemy), external integrations
    ├── api/        #   Routes, middleware (auth, rate limit, error handler), Pydantic schemas
    ├── database/   #   SQLAlchemy models, repository implementations, migrations
    ├── integrations/ # OTel Service Graph client (Prometheus)
    ├── tasks/      #   Background scheduler (APScheduler), scheduled jobs
    ├── observability/ # Prometheus metrics, structlog logging, OpenTelemetry tracing
    ├── cache/      #   Redis health checks
    └── config/     #   Pydantic Settings (centralized configuration)
```

### Tests (`tests/`)
```
tests/
├── unit/           # Domain + application tests (147 tests, ~0.5s, no external deps)
├── integration/    # Infrastructure tests with real PostgreSQL (80 tests, ~30s)
└── e2e/            # Full API workflow tests (20 tests, requires full stack)
```

### Infrastructure & Deployment
```
alembic/            # Database migrations (4 tables: services, dependencies, alerts, api_keys)
helm/slo-engine/    # Helm charts (10 templates: deployment, service, ingress, HPA, etc.)
k8s/staging/        # Staging-specific Kubernetes overrides
docker-compose.yml  # Local dev: API + PostgreSQL + Redis + Prometheus
Dockerfile          # Multi-stage build (base → api)
.github/workflows/  # CI (lint/type/security/test/build) + staging deploy
```

**Key Principles:**
* Dependency Inversion: Inner layers define interfaces, outer layers implement
* Single Responsibility: Each component has one reason to change
* Testability: Pure business logic independent of frameworks
* Async/Await: Full async throughout (FastAPI → use cases → AsyncPG)

## Current Feature Status

| Feature | Status | Key Files |
|---------|--------|-----------|
| **FR-1** Dependency Graph | Production Ready | `src/domain/entities/service_dependency.py`, `src/application/use_cases/ingest_dependency_graph.py`, `src/infrastructure/api/routes/dependencies.py` |
| **FR-2** SLO Recommendations | Complete (339 tests) | `src/domain/services/availability_calculator.py`, `src/application/use_cases/generate_slo_recommendation.py`, `src/infrastructure/api/routes/recommendations.py` |
| **FR-3** Constraint Propagation | Nearly Complete (5 E2E tests need debugging) | `src/domain/services/error_budget_analyzer.py`, `src/application/use_cases/run_constraint_analysis.py`, `src/infrastructure/api/routes/constraint_analysis.py` |
| **FR-4** Impact Analysis | Not Started | — |

## Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Graph storage | PostgreSQL recursive CTEs | Sufficient for 10K+ edges, lower ops overhead than Neo4j |
| Async pattern | Full async/await | Best performance with AsyncPG + SQLAlchemy 2.0 |
| Authentication | API keys (bcrypt) | Simple for backend-to-backend; OAuth2 planned for Phase 4 |
| Rate limiting | Token bucket (in-memory) | Per-client/endpoint; Redis for multi-replica planned |
| Background tasks | APScheduler (in-process) | Simple for MVP; Celery migration at >100 tasks/min |
| Metric labels | Omit service_id | Avoids high cardinality with 5000+ services |

## Essential Commands

```bash
# Development
docker-compose up --build                    # Start full stack
uvicorn src.infrastructure.api.main:app --reload  # Dev server (needs DB/Redis running)

# Testing
pytest tests/unit/ tests/integration/ -v     # All tests (recommended)
pytest tests/unit/domain/ -v                 # Fast domain tests
pytest tests/e2e/ -v                         # E2E tests (requires docker-compose up)
pytest --cov=src --cov-report=term-missing   # Coverage report

# Code quality
ruff check . && ruff format . && mypy src/ --strict && bandit -r src/ -c pyproject.toml

# Database
alembic upgrade head                         # Apply migrations
alembic downgrade -1                         # Rollback
alembic revision --autogenerate -m "desc"    # New migration

# Deployment
helm upgrade --install slo-engine ./helm/slo-engine -f k8s/staging/values-override.yaml
```
