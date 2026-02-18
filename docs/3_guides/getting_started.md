# Getting Started

> **Last Updated:** 2026-02-17
> **Applies to:** SLO Recommendation Engine v0.3 (FR-1, FR-2, FR-3)

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Running the Application](#running-the-application)
- [Verifying the Setup](#verifying-the-setup)
- [Development Workflow](#development-workflow)
- [Common Commands](#common-commands)
- [Troubleshooting](#troubleshooting)
- [Next Steps](#next-steps)

---

## Prerequisites

- **Python 3.12+** (3.13 recommended)
- **uv** (recommended) or pip for dependency management
- **Docker** and **Docker Compose** for local development stack
- **Git** for version control
- **PostgreSQL 16+** (provided via Docker Compose, or install locally)
- **Redis 7+** (provided via Docker Compose, or install locally)

---

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd slo-recommendation-engine
```

### 2. Set Up Python Environment

#### Using uv (recommended)

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install all dependencies (including dev)
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv sync
```

#### Using pip

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 3. Configure Environment Variables

```bash
# Copy the environment template
cp .env.example .env
```

Edit `.env` with your local configuration. Key variables:

```bash
# Database (required)
DATABASE_URL=postgresql+asyncpg://slo_user:slo_password@localhost:5432/slo_engine

# Redis (required for rate limiting)
REDIS_URL=redis://localhost:6379/0

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=DEBUG

# Background Tasks
OTEL_GRAPH_INGEST_INTERVAL_MINUTES=15
STALE_EDGE_THRESHOLD_HOURS=168

# Prometheus Integration (optional - for OTel service graph discovery)
PROMETHEUS_URL=http://localhost:9090
PROMETHEUS_TIMEOUT_SECONDS=30

# Observability (optional)
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_TRACE_SAMPLE_RATE=0.1
```

### 4. Start the Infrastructure Stack

```bash
# Start PostgreSQL, Redis, Prometheus, and the API
docker-compose up --build
```

This starts:
- **API Server** at http://localhost:8000 (Swagger UI at http://localhost:8000/docs)
- **PostgreSQL** at localhost:5432
- **Redis** at localhost:6379
- **Prometheus** at http://localhost:9090

### 5. Run Database Migrations

If running outside Docker (Docker Compose handles this automatically):

```bash
# Apply all migrations
alembic upgrade head

# Verify migrations applied
alembic history --verbose
```

The following tables are created:
- `services` - Microservice registry
- `service_dependencies` - Directed dependency edges
- `circular_dependency_alerts` - Detected circular dependency cycles
- `api_keys` - API key authentication

---

## Running the Application

### With Docker Compose (recommended)

```bash
# Start all services
docker-compose up --build

# Start in background
docker-compose up -d --build

# View logs
docker-compose logs -f app
```

### Without Docker (local development)

```bash
source .venv/bin/activate

# Ensure PostgreSQL and Redis are running locally
# Apply migrations
alembic upgrade head

# Start the API server
uvicorn src.infrastructure.api.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Verifying the Setup

### 1. Health Checks

```bash
# Liveness probe - should return 200
curl http://localhost:8000/api/v1/health

# Readiness probe - checks DB and Redis connectivity
curl http://localhost:8000/api/v1/health/ready

# Prometheus metrics
curl http://localhost:8000/api/v1/metrics
```

### 2. Create a Test API Key

API endpoints (except health) require authentication. Create a key manually:

```bash
# Connect to the database
docker-compose exec db psql -U slo_user -d slo_engine

# Create an API key (replace the hash with a bcrypt hash of your chosen key)
# You can generate a hash with: python -c "import bcrypt; print(bcrypt.hashpw(b'test-key-123', bcrypt.gensalt()).decode())"
INSERT INTO api_keys (id, name, key_hash, is_active, created_at)
VALUES (
  gen_random_uuid(),
  'dev-testing',
  '$2b$12$YOUR_BCRYPT_HASH_HERE',
  true,
  now()
);
```

### 3. Test the API

```bash
# Ingest a dependency graph
curl -X POST http://localhost:8000/api/v1/services/dependencies \
  -H "Authorization: Bearer test-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "manual",
    "nodes": [
      {"service_id": "api-gateway", "team": "platform"},
      {"service_id": "auth-service", "team": "identity"},
      {"service_id": "checkout-service", "team": "commerce"}
    ],
    "edges": [
      {
        "source_service_id": "api-gateway",
        "target_service_id": "auth-service",
        "attributes": {
          "communication_mode": "sync",
          "criticality": "critical",
          "protocol": "grpc",
          "timeout_ms": 500
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
      }
    ]
  }'

# Query downstream dependencies
curl http://localhost:8000/api/v1/services/api-gateway/dependencies?direction=downstream&depth=3 \
  -H "Authorization: Bearer test-key-123"

# Query upstream dependencies
curl http://localhost:8000/api/v1/services/auth-service/dependencies?direction=upstream&depth=2 \
  -H "Authorization: Bearer test-key-123"
```

### 4. Explore the Swagger UI

Open http://localhost:8000/docs in your browser to see the interactive API documentation with request/response examples.

---

## Development Workflow

### Before Starting a New Feature

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Create planning documents in `dev/active/my-feature/`:
   - `my-feature-plan.md` - Technical Design Specification
   - `my-feature-context.md` - Key decisions and dependencies
   - `my-feature-tasks.md` - Progress checklist
3. Get your TDS reviewed

### During Development

1. Write tests first (TDD approach)
2. Implement following Clean Architecture layers:
   - **Domain first** (entities, services, repository interfaces)
   - **Application second** (use cases, DTOs)
   - **Infrastructure last** (routes, repositories, middleware)
3. Run tests frequently: `pytest tests/unit/ -v`
4. Check for lint errors: `ruff check .`

### Before Merging

1. Run the full test suite:
   ```bash
   pytest tests/unit/ tests/integration/ -v --cov=src --cov-report=term-missing
   ```
2. Run code quality checks:
   ```bash
   ruff check .
   ruff format --check .
   mypy src/ --strict
   bandit -r src/ -c pyproject.toml
   ```
3. Update documentation in `docs/` as needed
4. Move feature docs from `dev/active/` to `dev/archive/`

---

## Common Commands

### Testing

```bash
pytest                                          # Run all tests
pytest tests/unit/                              # Unit tests only
pytest tests/integration/                       # Integration tests only
pytest tests/e2e/                               # E2E tests only
pytest --cov=src --cov-report=html              # With HTML coverage report
pytest tests/unit/domain/ -v                    # Domain layer tests
pytest tests/unit/application/ -v               # Application layer tests
pytest tests/integration/infrastructure/ -v     # Infrastructure tests
pytest -k "test_circular"                       # Run tests matching pattern
pytest --tb=short                               # Shorter traceback output
```

### Code Quality

```bash
ruff check .                    # Lint code
ruff check . --fix              # Auto-fix lint issues
ruff format .                   # Format code
mypy src/ --strict              # Type checking
bandit -r src/ -c pyproject.toml  # Security scan
```

### Database

```bash
# Apply all pending migrations
alembic upgrade head

# Rollback last migration
alembic downgrade -1

# Show migration history
alembic history --verbose

# Generate a new migration (after modifying models.py)
alembic revision --autogenerate -m "description_of_change"

# Connect to database
docker-compose exec db psql -U slo_user -d slo_engine
```

### Docker

```bash
docker-compose up --build              # Start all services
docker-compose up -d --build           # Start in background
docker-compose down                    # Stop all services
docker-compose down -v                 # Stop and remove volumes (reset DB)
docker-compose logs -f app             # Follow API logs
docker-compose exec app bash           # Shell into API container
docker build -t slo-engine:latest --target api .  # Build API image only
```

### Kubernetes (requires cluster access)

```bash
# Deploy to staging
helm upgrade --install slo-engine ./helm/slo-engine \
  -f k8s/staging/values-override.yaml \
  --set image.tag=latest

# Check deployment status
kubectl get pods -l app.kubernetes.io/name=slo-engine

# View logs
kubectl logs -l app.kubernetes.io/name=slo-engine -f
```

---

## Troubleshooting

### Common Issues

#### Virtual Environment Issues

```bash
# Deactivate and recreate virtual environment
deactivate
rm -rf .venv
uv venv
source .venv/bin/activate
uv sync
```

#### Dependency Conflicts

```bash
# Clear cache and reinstall
uv cache clean
uv sync --reinstall
```

#### Database Connection Errors

```bash
# Check if PostgreSQL is running
docker-compose ps db

# Reset the database completely
docker-compose down -v
docker-compose up --build

# Check migration status
alembic current
alembic history
```

#### Port Already in Use

```bash
# Find process using port 8000
lsof -i :8000

# Kill the process
kill -9 <PID>

# Or use a different port
API_PORT=8001 uvicorn src.infrastructure.api.main:app --port 8001
```

#### Redis Connection Errors

```bash
# Check if Redis is running
docker-compose ps redis

# Test Redis connectivity
docker-compose exec redis redis-cli ping
# Expected output: PONG
```

#### Test Failures

```bash
# Run with verbose output for debugging
pytest tests/unit/ -vv --tb=long

# Run a single test for isolation
pytest tests/unit/domain/entities/test_service.py::test_service_creation -vv

# Check if integration tests need PostgreSQL running
docker-compose up -d db redis
pytest tests/integration/ -v
```

---

## Next Steps

- Read [Core Concepts](core_concepts.md) to understand Clean Architecture patterns
- Read the [Dependency Graph Developer Guide](dependency_graph_guide.md) for FR-1 feature details
- Read the [SLO Recommendations Guide](slo_recommendations_guide.md) for FR-2 feature details
- Read the [Constraint Propagation Guide](constraint_propagation_guide.md) for FR-3 feature details
- Review [System Design](../2_architecture/system_design.md) for architecture overview
- Check [Testing Guide](../4_testing/index.md) for testing patterns and examples
- Explore the API via Swagger UI at http://localhost:8000/docs
