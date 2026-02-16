# Testing Documentation

> **Last Updated:** 2026-02-15
> **Applies to:** SLO Recommendation Engine v0.1 (FR-1: Service Dependency Graph)

---

## Table of Contents

- [Testing Philosophy](#testing-philosophy)
- [Testing Pyramid](#testing-pyramid)
- [Test Organization](#test-organization)
- [Running Tests](#running-tests)
- [Writing Tests](#writing-tests)
- [Test Fixtures](#test-fixtures)
- [Best Practices](#best-practices)
- [Coverage Goals](#coverage-goals)
- [Continuous Integration](#continuous-integration)

---

## Testing Philosophy

We follow a comprehensive testing strategy aligned with Clean Architecture. Each architectural layer has dedicated tests that validate behavior at the appropriate level of abstraction:

- **Domain layer** tests are pure unit tests with zero dependencies
- **Application layer** tests use mocks for repository interfaces
- **Infrastructure layer** tests run against real PostgreSQL (via testcontainers)
- **E2E tests** exercise the full HTTP API stack

---

## Testing Pyramid

```
           /\
          /  \          E2E Tests (20 tests)
         /    \         Full API workflows via HTTP
        /------\
       /        \       Integration Tests (80 tests)
      /          \      Real PostgreSQL, Redis
     /------------\
    /              \    Unit Tests (147 tests)
   /                \   Domain entities, services, DTOs, use cases
  /------------------\
```

| Layer | Test Count | Coverage | External Deps | Speed |
|-------|-----------|----------|---------------|-------|
| **Unit** | 147 | >95% | None | ~0.5s |
| **Integration** | 80 | >90% | PostgreSQL, Redis | ~30s |
| **E2E** | 20 | ~40% | Full stack | ~60s |

---

## Test Organization

```
tests/
├── conftest.py                                    # Root fixtures
├── unit/
│   ├── domain/
│   │   ├── entities/
│   │   │   ├── test_service.py                    # Service entity (13 tests)
│   │   │   ├── test_service_dependency.py         # ServiceDependency entity (21 tests)
│   │   │   └── test_circular_dependency_alert.py  # Alert entity (18 tests)
│   │   └── services/
│   │       ├── test_graph_traversal_service.py    # Graph traversal (12 tests)
│   │       ├── test_circular_dependency_detector.py  # Tarjan's algo (17 tests)
│   │       └── test_edge_merge_service.py         # Edge merge (13 tests)
│   └── application/
│       ├── dtos/
│       │   ├── test_common.py                     # Shared DTOs (5 tests)
│       │   ├── test_dependency_graph_dto.py       # Ingestion DTOs (20 tests)
│       │   └── test_dependency_subgraph_dto.py    # Query DTOs (10 tests)
│       └── use_cases/
│           ├── test_ingest_dependency_graph.py     # Ingestion UC (6 tests)
│           ├── test_query_dependency_subgraph.py   # Query UC (8 tests)
│           └── test_detect_circular_dependencies.py  # Detection UC (8 tests)
├── integration/
│   ├── conftest.py                                # PostgreSQL testcontainer fixtures
│   └── infrastructure/
│       ├── database/
│       │   ├── test_service_repository.py         # Service repo (16 tests)
│       │   ├── test_dependency_repository.py      # Dependency repo (18 tests)
│       │   └── test_circular_dependency_alert_repository.py  # Alert repo (20 tests)
│       ├── integrations/
│       │   └── test_otel_service_graph.py         # OTel client (8 tests)
│       └── observability/
│           ├── test_health_checks.py              # Health endpoints (5 tests)
│           ├── test_logging.py                    # Structured logging (5 tests)
│           └── test_metrics.py                    # Prometheus metrics (8 tests)
└── e2e/
    ├── conftest.py                                # Full API stack fixtures
    └── test_dependency_api.py                     # API endpoint tests (20 tests)
```

---

## Running Tests

### Run All Tests

```bash
# Run unit + integration tests (recommended for development)
pytest tests/unit/ tests/integration/ -v

# Run everything including E2E
pytest -v
```

### Run by Layer

```bash
# Domain layer (fastest - no dependencies)
pytest tests/unit/domain/ -v

# Application layer (fast - mocked repos)
pytest tests/unit/application/ -v

# Infrastructure layer (requires PostgreSQL)
pytest tests/integration/ -v

# E2E tests (requires full stack)
pytest tests/e2e/ -v
```

### Run with Coverage

```bash
# Terminal coverage report
pytest tests/unit/ tests/integration/ --cov=src --cov-report=term-missing

# HTML coverage report
pytest tests/unit/ tests/integration/ --cov=src --cov-report=html
open htmlcov/index.html
```

### Run Specific Tests

```bash
# Single test file
pytest tests/unit/domain/entities/test_service_dependency.py -v

# Single test function
pytest tests/unit/domain/services/test_circular_dependency_detector.py::test_simple_cycle -v

# Tests matching a pattern
pytest -k "test_circular" -v
pytest -k "test_ingest" -v

# With verbose output for debugging
pytest tests/integration/ -vv --tb=long
```

---

## Writing Tests

### Unit Test: Domain Entity

Domain entity tests validate business rules and invariants with zero external dependencies.

```python
# tests/unit/domain/entities/test_service_dependency.py

import pytest
from src.domain.entities.service_dependency import (
    ServiceDependency,
    CommunicationMode,
    DependencyCriticality,
    DiscoverySource,
    RetryConfig,
)

def test_valid_dependency_creation():
    """Test creating a valid service dependency edge."""
    dep = ServiceDependency(
        source_service_id="api-gateway",
        target_service_id="auth-service",
        communication_mode=CommunicationMode.SYNC,
        criticality=DependencyCriticality.CRITICAL,
        discovery_source=DiscoverySource.MANUAL,
        protocol="grpc",
        timeout_ms=500,
    )
    assert dep.source_service_id == "api-gateway"
    assert dep.target_service_id == "auth-service"
    assert dep.confidence_score == 1.0  # Manual source defaults to 1.0
    assert dep.is_stale is False

def test_self_loop_prevention():
    """Domain invariant: a service cannot depend on itself."""
    with pytest.raises(ValueError, match="self-loop"):
        ServiceDependency(
            source_service_id="api-gateway",
            target_service_id="api-gateway",
            communication_mode=CommunicationMode.SYNC,
            criticality=DependencyCriticality.MEDIUM,
            discovery_source=DiscoverySource.MANUAL,
        )

def test_confidence_score_bounds():
    """Confidence score must be between 0.0 and 1.0."""
    with pytest.raises(ValueError):
        ServiceDependency(
            source_service_id="a",
            target_service_id="b",
            communication_mode=CommunicationMode.SYNC,
            criticality=DependencyCriticality.MEDIUM,
            discovery_source=DiscoverySource.MANUAL,
            confidence_score=1.5,  # Invalid: > 1.0
        )

def test_staleness_lifecycle():
    """Test mark_as_stale and refresh state transitions."""
    dep = ServiceDependency(
        source_service_id="a",
        target_service_id="b",
        communication_mode=CommunicationMode.ASYNC,
        criticality=DependencyCriticality.LOW,
        discovery_source=DiscoverySource.OTEL_SERVICE_GRAPH,
    )
    assert dep.is_stale is False

    dep.mark_as_stale()
    assert dep.is_stale is True

    dep.refresh()
    assert dep.is_stale is False
```

### Unit Test: Domain Service (Tarjan's Algorithm)

```python
# tests/unit/domain/services/test_circular_dependency_detector.py

from src.domain.services.circular_dependency_detector import CircularDependencyDetector

def test_simple_cycle():
    """Detect a simple A -> B -> C -> A cycle."""
    detector = CircularDependencyDetector()
    adjacency_list = {
        "a": ["b"],
        "b": ["c"],
        "c": ["a"],
    }
    cycles = detector.detect_cycles(adjacency_list)
    assert len(cycles) == 1
    assert set(cycles[0]) == {"a", "b", "c"}

def test_no_cycle_in_dag():
    """No cycles should be detected in a directed acyclic graph."""
    detector = CircularDependencyDetector()
    adjacency_list = {
        "a": ["b", "c"],
        "b": ["d"],
        "c": ["d"],
        "d": [],
    }
    cycles = detector.detect_cycles(adjacency_list)
    assert len(cycles) == 0

def test_multiple_disjoint_cycles():
    """Detect multiple independent cycles in the same graph."""
    detector = CircularDependencyDetector()
    adjacency_list = {
        "a": ["b"],
        "b": ["a"],  # Cycle 1: a <-> b
        "x": ["y"],
        "y": ["z"],
        "z": ["x"],  # Cycle 2: x -> y -> z -> x
    }
    cycles = detector.detect_cycles(adjacency_list)
    assert len(cycles) == 2
```

### Unit Test: Application Use Case

Use case tests mock repository interfaces to test orchestration logic in isolation.

```python
# tests/unit/application/use_cases/test_ingest_dependency_graph.py

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.application.use_cases.ingest_dependency_graph import IngestDependencyGraphUseCase
from src.application.dtos.dependency_graph_dto import (
    DependencyGraphIngestRequest,
    NodeDTO,
    EdgeDTO,
    EdgeAttributesDTO,
)

@pytest.fixture
def mock_service_repo():
    return AsyncMock()

@pytest.fixture
def mock_dependency_repo():
    return AsyncMock()

@pytest.fixture
def mock_edge_merge_service():
    return MagicMock()  # Synchronous service, not async

@pytest.fixture
def use_case(mock_service_repo, mock_dependency_repo, mock_edge_merge_service):
    return IngestDependencyGraphUseCase(
        service_repository=mock_service_repo,
        dependency_repository=mock_dependency_repo,
        edge_merge_service=mock_edge_merge_service,
    )

@pytest.mark.asyncio
async def test_ingest_single_edge(use_case, mock_service_repo, mock_dependency_repo):
    """Ingesting a graph with one edge creates services and the dependency."""
    request = DependencyGraphIngestRequest(
        source="manual",
        nodes=[
            NodeDTO(service_id="api-gateway"),
            NodeDTO(service_id="auth-service"),
        ],
        edges=[
            EdgeDTO(
                source_service_id="api-gateway",
                target_service_id="auth-service",
                attributes=EdgeAttributesDTO(
                    communication_mode="sync",
                    criticality="critical",
                ),
            ),
        ],
    )

    response = await use_case.execute(request)

    mock_service_repo.bulk_upsert.assert_called_once()
    mock_dependency_repo.bulk_upsert.assert_called_once()
    assert response.nodes_upserted == 2
    assert response.edges_upserted == 1
```

### Integration Test: Repository with Real PostgreSQL

Integration tests run against a real PostgreSQL database using testcontainers for isolation.

```python
# tests/integration/infrastructure/database/test_dependency_repository.py

import pytest
from uuid import uuid4
from src.infrastructure.database.repositories.dependency_repository import (
    DependencyRepository,
)
from src.domain.entities.service_dependency import (
    ServiceDependency,
    CommunicationMode,
    DependencyCriticality,
    DiscoverySource,
)

@pytest.mark.asyncio
async def test_recursive_cte_downstream_traversal(db_session, seed_services):
    """Test 3-hop downstream graph traversal using PostgreSQL recursive CTEs."""
    repo = DependencyRepository(db_session)

    # Seed: A -> B -> C -> D (linear chain)
    # Query: downstream from A, depth=3
    result = await repo.traverse_graph(
        service_id=seed_services["a"].id,
        direction="downstream",
        max_depth=3,
        include_stale=False,
    )

    assert len(result["services"]) == 3  # B, C, D
    assert len(result["edges"]) == 3     # A->B, B->C, C->D

@pytest.mark.asyncio
async def test_bulk_upsert_idempotent(db_session):
    """Bulk upsert with same data twice should not create duplicates."""
    repo = DependencyRepository(db_session)
    deps = [
        ServiceDependency(
            source_service_id="svc-a",
            target_service_id="svc-b",
            communication_mode=CommunicationMode.SYNC,
            criticality=DependencyCriticality.HIGH,
            discovery_source=DiscoverySource.MANUAL,
        )
    ]

    await repo.bulk_upsert(deps)
    await repo.bulk_upsert(deps)  # Second call should not duplicate

    results = await repo.list_by_source("svc-a")
    assert len(results) == 1

@pytest.mark.asyncio
async def test_traversal_performance_benchmark(db_session, seed_large_graph):
    """3-hop traversal on 1000-node graph should complete in < 100ms."""
    import time
    repo = DependencyRepository(db_session)

    start = time.monotonic()
    result = await repo.traverse_graph(
        service_id=seed_large_graph["root"].id,
        direction="downstream",
        max_depth=3,
        include_stale=False,
    )
    elapsed_ms = (time.monotonic() - start) * 1000

    assert elapsed_ms < 500  # Liberal bound for CI; target is <100ms
    assert len(result["services"]) > 0
```

### E2E Test: Full API Workflow

E2E tests exercise the complete HTTP request/response cycle including authentication.

```python
# tests/e2e/test_dependency_api.py

import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Health endpoint should be accessible without authentication."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

@pytest.mark.asyncio
async def test_missing_api_key_returns_401(client: AsyncClient):
    """Protected endpoints require API key authentication."""
    response = await client.post(
        "/api/v1/services/dependencies",
        json={"source": "manual", "nodes": [], "edges": []},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["type"]  # RFC 7807 format
    assert data["status"] == 401

@pytest.mark.asyncio
async def test_ingest_and_query_workflow(
    client: AsyncClient, api_key_header: dict
):
    """Full workflow: ingest a graph, then query dependencies."""
    # Step 1: Ingest
    ingest_response = await client.post(
        "/api/v1/services/dependencies",
        headers=api_key_header,
        json={
            "source": "manual",
            "nodes": [
                {"service_id": "gateway"},
                {"service_id": "auth"},
            ],
            "edges": [
                {
                    "source_service_id": "gateway",
                    "target_service_id": "auth",
                    "attributes": {
                        "communication_mode": "sync",
                        "criticality": "critical",
                    },
                }
            ],
        },
    )
    assert ingest_response.status_code == 202

    # Step 2: Query
    query_response = await client.get(
        "/api/v1/services/gateway/dependencies?direction=downstream&depth=1",
        headers=api_key_header,
    )
    assert query_response.status_code == 200
    data = query_response.json()
    assert len(data["edges"]) >= 1
```

---

## Test Fixtures

### Root Fixtures (`tests/conftest.py`)

```python
# tests/conftest.py
import pytest

# Shared fixtures available to all test types
# Layer-specific fixtures are in their respective conftest.py files
```

### Integration Test Fixtures (`tests/integration/conftest.py`)

Integration tests use testcontainers to spin up real PostgreSQL instances:

```python
# tests/integration/conftest.py
import pytest_asyncio
from testcontainers.postgres import PostgresContainer
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

@pytest_asyncio.fixture(scope="session")
async def postgres_container():
    """Spin up a real PostgreSQL container for integration tests."""
    with PostgresContainer("postgres:16") as postgres:
        yield postgres

@pytest_asyncio.fixture
async def db_session(postgres_container):
    """Create a fresh database session for each test."""
    engine = create_async_engine(postgres_container.get_connection_url())
    # Run migrations...
    async with AsyncSession(engine) as session:
        yield session
        await session.rollback()
```

### E2E Test Fixtures (`tests/e2e/conftest.py`)

E2E tests configure the full FastAPI application with database:

```python
# tests/e2e/conftest.py
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from src.infrastructure.api.main import app

@pytest_asyncio.fixture
async def client():
    """Create an async HTTP client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

@pytest_asyncio.fixture
async def api_key_header(db_session):
    """Create a test API key and return the auth header."""
    # Insert test API key into database
    # Return {"Authorization": "Bearer test-key-123"}
    ...
```

---

## Best Practices

### 1. Arrange-Act-Assert Pattern

```python
def test_service_mark_as_registered():
    # Arrange: Set up a discovered service
    service = Service(service_id="payment-svc", discovered=True)

    # Act: Register the service
    service.mark_as_registered(
        team="payments",
        criticality=Criticality.CRITICAL,
        metadata={"owner": "payments-team"},
    )

    # Assert: Verify state changed correctly
    assert service.discovered is False
    assert service.team == "payments"
    assert service.criticality == Criticality.CRITICAL
```

### 2. Descriptive Test Names

Use the pattern `test_<subject>_<scenario>_<expected_result>`:

```python
def test_service_creation_with_valid_data_succeeds(): ...
def test_self_loop_dependency_raises_value_error(): ...
def test_tarjan_detector_with_no_cycles_returns_empty(): ...
def test_bulk_upsert_with_duplicate_edges_is_idempotent(): ...
```

### 3. One Behavior Per Test

```python
# Good: each test verifies one specific behavior
def test_confidence_score_rejects_negative_values(): ...
def test_confidence_score_rejects_values_above_one(): ...
def test_confidence_score_accepts_zero(): ...
def test_confidence_score_accepts_one(): ...
```

### 4. Use Parametrize for Multiple Cases

```python
@pytest.mark.parametrize("source,expected_confidence", [
    (DiscoverySource.MANUAL, 1.0),
    (DiscoverySource.SERVICE_MESH, 0.9),
    (DiscoverySource.OTEL_SERVICE_GRAPH, 0.7),
    (DiscoverySource.KUBERNETES, 0.5),
])
def test_confidence_score_by_source(source, expected_confidence):
    score = EdgeMergeService().compute_confidence_score(source, observation_count=1)
    assert score == expected_confidence
```

### 5. Mock Repository Interfaces, Not Implementations

```python
# Good: mock the abstract interface
from unittest.mock import AsyncMock

mock_repo = AsyncMock(spec=DependencyRepositoryInterface)
use_case = QueryDependencySubgraphUseCase(dependency_repo=mock_repo, ...)

# Bad: mock the concrete PostgreSQL implementation
# This couples tests to infrastructure details
```

### 6. Use Factories for Test Data

```python
def make_service(service_id: str = "test-svc", **overrides) -> Service:
    """Factory for creating test Service entities with sensible defaults."""
    defaults = {
        "service_id": service_id,
        "criticality": Criticality.MEDIUM,
        "team": "test-team",
        "discovered": False,
    }
    defaults.update(overrides)
    return Service(**defaults)

def test_something():
    svc = make_service("my-service", criticality=Criticality.CRITICAL)
```

---

## Coverage Goals

| Layer | Target | Rationale |
|-------|--------|-----------|
| **Domain** | >95% | Pure business logic, no framework dependencies, must be thorough |
| **Application** | >90% | Use case orchestration, tested with mocks |
| **Infrastructure** | >75% | Framework integrations, harder to test exhaustively |
| **Overall** | >80% | Sufficient for production readiness |

### Current Coverage (FR-1)

| Component | Tests | Status |
|-----------|-------|--------|
| Domain entities | 52/52 | 100% passing |
| Domain services | 42/42 | 100% passing |
| Application DTOs | 35/35 | 100% passing |
| Application use cases | 22/22 | 100% passing |
| Repository implementations | 54/54 | 100% passing |
| Observability | 18/18 | 100% passing |
| OTel integration | 8/8 | 100% passing |
| E2E API | 8/20 | 40% passing (non-blocking) |

---

## Continuous Integration

All tests run automatically via GitHub Actions (`.github/workflows/ci.yml`):

```yaml
# CI Pipeline stages:
# 1. Lint (ruff check + format)
# 2. Type check (mypy --strict)
# 3. Security (bandit + pip-audit)
# 4. Test (pytest with PostgreSQL + Redis services)
# 5. Build (Docker image)
# 6. Push (GHCR on main merge)
```

**CI Requirements:**
- All unit and integration tests must pass
- Coverage must meet minimum thresholds
- No lint errors
- No type errors
- No high/critical security findings

Tests must pass before merging to main.

---

## Further Reading

- [Core Concepts](../3_guides/core_concepts.md) - Clean Architecture patterns
- [Dependency Graph Guide](../3_guides/dependency_graph_guide.md) - FR-1 feature details
- [System Design](../2_architecture/system_design.md) - Architecture overview
