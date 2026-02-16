# SLO Recommendation Engine

An AI-assisted backend system that analyzes telemetry data and structural dependencies across microservices to recommend achievable availability and latency SLOs.

## Overview

In cloud-native organizations at scale (500-5,000+ microservices), SLO setting is manual, error-prone, and fails to account for the interconnected nature of distributed systems. This engine models service dependencies as a directed graph and uses that topology — combined with telemetry from Prometheus, OpenTelemetry, and Grafana Tempo — to recommend dependency-aware SLOs.

**Current Status:** FR-1 (Service Dependency Graph) is production-ready. See [Feature Roadmap](#feature-roadmap) for upcoming work.

## Features

- **Service Dependency Graph** — Ingest, store, query, and manage directed dependency graphs between microservices
- **Multi-Source Discovery** — Combine manual declarations with automated discovery from OpenTelemetry traces
- **Circular Dependency Detection** — Tarjan's SCC algorithm detects architectural anti-patterns in real time
- **Graph Traversal** — PostgreSQL recursive CTEs for efficient upstream/downstream subgraph queries
- **Observability** — 13 Prometheus metrics, structured JSON logging (structlog), distributed tracing (OpenTelemetry)
- **Production-Ready Deployment** — Docker Compose, Helm charts, GitHub Actions CI/CD, horizontal autoscaling

### Architecture

Built with **Clean Architecture** (Domain → Application → Infrastructure) on:

| Component | Technology |
|-----------|-----------|
| API Framework | FastAPI (async) |
| Database | PostgreSQL 16 + SQLAlchemy 2.0 (async) |
| Cache / Rate Limiting | Redis 7 |
| Background Tasks | APScheduler |
| Tracing | OpenTelemetry + OTLP |
| Metrics | Prometheus client |
| Logging | structlog (JSON) |
| Deployment | Docker, Helm, Kubernetes |

## Quick Start

### Prerequisites

- Python 3.12+ (3.13 recommended)
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- Docker and Docker Compose

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd slo-recommendation-engine

# Set up virtual environment with uv
uv venv
source .venv/bin/activate
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your settings (defaults work with docker-compose)

# Start the full stack (API + PostgreSQL + Redis + Prometheus)
docker-compose up --build
```

### Verify It's Working

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Readiness check (verifies DB + Redis)
curl http://localhost:8000/api/v1/health/ready

# Explore the API
open http://localhost:8000/docs    # Swagger UI
```

### Ingest a Dependency Graph

```bash
# First, create an API key (see docs/3_guides/getting_started.md for details)

# Ingest services and dependencies
curl -X POST http://localhost:8000/api/v1/services/dependencies \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "manual",
    "nodes": [
      {"service_id": "api-gateway", "team": "platform", "criticality": "critical"},
      {"service_id": "auth-service", "team": "identity", "criticality": "critical"},
      {"service_id": "checkout-service", "team": "commerce", "criticality": "high"}
    ],
    "edges": [
      {
        "source_service_id": "api-gateway",
        "target_service_id": "auth-service",
        "attributes": {"communication_mode": "sync", "criticality": "critical", "protocol": "grpc", "timeout_ms": 500}
      },
      {
        "source_service_id": "api-gateway",
        "target_service_id": "checkout-service",
        "attributes": {"communication_mode": "sync", "criticality": "high", "protocol": "http", "timeout_ms": 2000}
      }
    ]
  }'

# Query downstream dependencies
curl "http://localhost:8000/api/v1/services/api-gateway/dependencies?direction=downstream&depth=3" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

## Project Structure

```
slo-recommendation-engine/
├── src/                          # Source code (Clean Architecture)
│   ├── domain/                   #   Pure business logic (entities, services, interfaces)
│   │   ├── entities/             #     Service, ServiceDependency, CircularDependencyAlert
│   │   ├── services/             #     GraphTraversal, CircularDependencyDetector, EdgeMerge
│   │   └── repositories/         #     Abstract repository interfaces
│   ├── application/              #   Use cases and DTOs
│   │   ├── use_cases/            #     Ingest, Query, DetectCircularDependencies
│   │   └── dtos/                 #     Request/response data transfer objects
│   └── infrastructure/           #   Frameworks and external integrations
│       ├── api/                  #     FastAPI routes, middleware, schemas
│       ├── database/             #     SQLAlchemy models, repositories, migrations
│       ├── integrations/         #     OTel Service Graph client
│       ├── tasks/                #     Background scheduler (APScheduler)
│       ├── observability/        #     Metrics, logging, tracing
│       ├── cache/                #     Redis health checks
│       └── config/               #     Pydantic Settings
│
├── tests/                        # Test suite (~4,000 LOC)
│   ├── unit/                     #   Domain + application tests (147 tests)
│   ├── integration/              #   Infrastructure tests with real PostgreSQL (80 tests)
│   └── e2e/                      #   Full API workflow tests (20 tests)
│
├── alembic/                      # Database migrations (4 migrations)
├── helm/slo-engine/              # Helm charts for Kubernetes deployment
├── k8s/staging/                  # Staging environment overrides
├── docs/                         # Evergreen documentation
│   ├── 1_product/                #   PRD, problem statement, research
│   ├── 2_architecture/           #   System design, TRD
│   ├── 3_guides/                 #   Getting started, core concepts, dependency graph guide
│   └── 4_testing/                #   Testing strategy and examples
├── dev/                          # Work-in-progress feature plans
│   ├── active/                   #   Current feature development
│   └── archive/                  #   Completed feature records
│
├── docker-compose.yml            # Local dev stack (API + PostgreSQL + Redis + Prometheus)
├── Dockerfile                    # Multi-stage Docker build
├── pyproject.toml                # Python project config, dependencies, tool settings
├── alembic.ini                   # Alembic migration config
├── main.py                       # Application entry point
├── CLAUDE.md                     # AI assistant project signpost
└── CONTRIBUTING.md               # Contribution guidelines
```

## Development

### Running Tests

```bash
# All unit + integration tests (recommended)
pytest tests/unit/ tests/integration/ -v

# Domain layer only (fastest, no deps)
pytest tests/unit/domain/ -v

# With coverage report
pytest tests/unit/ tests/integration/ --cov=src --cov-report=term-missing

# Single test
pytest tests/unit/domain/services/test_circular_dependency_detector.py -v
```

### Code Quality

```bash
ruff check .                       # Lint
ruff format .                      # Format
mypy src/ --strict                 # Type check
bandit -r src/ -c pyproject.toml   # Security scan
```

### Database Migrations

```bash
alembic upgrade head               # Apply all migrations
alembic downgrade -1               # Rollback last migration
alembic history --verbose           # Show migration history
alembic revision --autogenerate -m "description"  # Generate new migration
```

### Docker

```bash
docker-compose up --build           # Start full stack
docker-compose down -v              # Stop and reset database
docker-compose logs -f app          # Follow API logs
docker build -t slo-engine --target api .  # Build API image
```

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/v1/services/dependencies` | Yes | Ingest dependency graph (bulk upsert) |
| `GET` | `/api/v1/services/{service_id}/dependencies` | Yes | Query dependency subgraph |
| `GET` | `/api/v1/health` | No | Liveness probe |
| `GET` | `/api/v1/health/ready` | No | Readiness probe (DB + Redis) |
| `GET` | `/api/v1/metrics` | No | Prometheus metrics |

All authenticated endpoints require `Authorization: Bearer <api-key>`. Error responses follow [RFC 7807](https://datatracker.ietf.org/doc/html/rfc7807) Problem Details format.

See the [Dependency Graph Developer Guide](docs/3_guides/dependency_graph_guide.md) for complete API documentation with examples.

## Deployment

### Local Development

```bash
docker-compose up --build
# API: http://localhost:8000/docs
```

### Kubernetes (Staging)

```bash
helm upgrade --install slo-engine ./helm/slo-engine \
  -f k8s/staging/values-override.yaml \
  --set image.tag=latest
```

### CI/CD Pipeline

```
PR → Lint → Type Check → Security Scan → Test → Build Docker Image
Main merge → Push to GHCR → Deploy to Staging → Smoke Tests
```

## Feature Roadmap

| Feature | Status | Description |
|---------|--------|-------------|
| **FR-1** Service Dependency Graph | Production Ready | Ingest, store, query, manage dependency graphs |
| **FR-2** SLO Recommendations | Planned | Compute dependency-aware availability + latency SLOs |
| **FR-3** Composite SLOs | Planned | Aggregate SLOs across service chains |
| **FR-4** Impact Analysis | Planned | Upstream impact traversal for degraded services |

## Documentation

| Document | Description |
|----------|-------------|
| [Getting Started](docs/3_guides/getting_started.md) | Developer setup, environment config, first API calls |
| [Dependency Graph Guide](docs/3_guides/dependency_graph_guide.md) | Complete FR-1 developer guide with API reference |
| [Core Concepts](docs/3_guides/core_concepts.md) | Clean Architecture patterns and conventions |
| [System Design](docs/2_architecture/system_design.md) | High-level architecture with diagrams |
| [Technical Requirements](docs/2_architecture/TRD.md) | Complete technical specification |
| [Testing Guide](docs/4_testing/index.md) | Testing strategy, examples, coverage goals |
| [Product Requirements](docs/1_product/PRD.md) | Business goals, user stories, success metrics |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow and code standards.

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.
