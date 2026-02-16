"""E2E tests for the Dependency Graph API endpoints."""

import pytest
from httpx import AsyncClient


class TestHealthEndpoints:
    """Test health check endpoints."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self, async_client_no_auth: AsyncClient):
        """Test liveness probe endpoint."""
        response = await async_client_no_auth.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_ready_endpoint(self, async_client_no_auth: AsyncClient):
        """Test readiness probe endpoint."""
        response = await async_client_no_auth.get("/api/v1/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["checks"]["database"] == "healthy"


class TestAuthentication:
    """Test API authentication."""

    @pytest.mark.asyncio
    async def test_missing_api_key(self, async_client_no_auth: AsyncClient):
        """Test that requests without API key are rejected."""
        response = await async_client_no_auth.post(
            "/api/v1/services/dependencies",
            json={
                "source": "manual",
                "timestamp": "2026-02-15T10:00:00Z",
                "nodes": [],
                "edges": [],
            },
        )

        assert response.status_code == 401
        data = response.json()
        assert data["type"] == "about:blank"
        assert data["title"] == "Unauthorized"
        assert "correlation_id" in data

    @pytest.mark.asyncio
    async def test_invalid_api_key(self, async_client_no_auth: AsyncClient):
        """Test that requests with invalid API key are rejected."""
        response = await async_client_no_auth.post(
            "/api/v1/services/dependencies",
            json={
                "source": "manual",
                "timestamp": "2026-02-15T10:00:00Z",
                "nodes": [],
                "edges": [],
            },
            headers={"Authorization": "Bearer invalid-key"},
        )

        assert response.status_code == 401
        data = response.json()
        assert data["title"] == "Unauthorized"
        assert "correlation_id" in data

    @pytest.mark.asyncio
    async def test_valid_api_key(self, async_client: AsyncClient):
        """Test that requests with valid API key are accepted."""
        response = await async_client.post(
            "/api/v1/services/dependencies",
            json={
                "source": "manual",
                "timestamp": "2026-02-15T10:00:00Z",
                "nodes": [],
                "edges": [],
            },
        )

        # Should not be 401
        assert response.status_code != 401


class TestDependencyIngestion:
    """Test dependency graph ingestion endpoint."""

    @pytest.mark.asyncio
    async def test_successful_ingestion(self, async_client: AsyncClient):
        """Test successful dependency graph ingestion."""
        payload = {
            "source": "manual",
            "timestamp": "2026-02-15T10:00:00Z",
            "nodes": [
                {
                    "service_id": "service-a",
                    "metadata": {
                        "service_name": "Service A",
                        "team": "team-alpha",
                        "criticality": "high",
                    },
                },
                {
                    "service_id": "service-b",
                    "metadata": {
                        "service_name": "Service B",
                        "team": "team-beta",
                        "criticality": "medium",
                    },
                },
            ],
            "edges": [
                {
                    "source": "service-a",
                    "target": "service-b",
                    "attributes": {
                        "communication_mode": "sync",
                        "criticality": "hard",
                        "protocol": "http",
                    },
                }
            ],
        }

        response = await async_client.post(
            "/api/v1/services/dependencies",
            json=payload,
        )

        assert response.status_code == 202
        data = response.json()
        assert data["nodes_upserted"] == 2
        assert data["edges_upserted"] == 1
        assert len(data["circular_dependencies_detected"]) == 0
        assert isinstance(data["conflicts_resolved"], list)

    @pytest.mark.asyncio
    async def test_ingestion_with_auto_discovery(self, async_client: AsyncClient):
        """Test that unknown services are auto-created during ingestion."""
        payload = {
            "source": "otel_service_graph",
            "timestamp": "2026-02-15T10:00:00Z",
            "nodes": [
                {
                    "service_id": "known-service",
                    "metadata": {
                        "service_name": "Known Service",
                        "team": "team-alpha",
                        "criticality": "high",
                    },
                }
            ],
            "edges": [
                {
                    "source": "known-service",
                    "target": "unknown-service",
                    "attributes": {
                        "communication_mode": "sync",
                        "criticality": "hard",
                        "protocol": "http",
                    },
                }
            ],
        }

        response = await async_client.post(
            "/api/v1/services/dependencies",
            json=payload,
        )

        assert response.status_code == 202
        data = response.json()
        # Should create both services (1 known + 1 auto-discovered)
        assert data["nodes_upserted"] >= 1
        assert data["edges_upserted"] == 1

    @pytest.mark.asyncio
    async def test_ingestion_invalid_schema(self, async_client: AsyncClient):
        """Test that invalid schema is rejected with 422."""
        payload = {
            # Missing required 'source' and 'timestamp' fields
            "nodes": [
                {
                    "service_id": "test-service",
                    "metadata": {},
                }
            ],
            "edges": [],
        }

        response = await async_client.post(
            "/api/v1/services/dependencies",
            json=payload,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_ingestion_empty_payload(self, async_client: AsyncClient):
        """Test ingestion with empty nodes and edges."""
        payload = {
            "source": "manual",
            "timestamp": "2026-02-15T10:00:00Z",
            "nodes": [],
            "edges": [],
        }

        response = await async_client.post(
            "/api/v1/services/dependencies",
            json=payload,
        )

        assert response.status_code == 202
        data = response.json()
        assert data["nodes_upserted"] == 0
        assert data["edges_upserted"] == 0


class TestDependencyQuery:
    """Test dependency subgraph query endpoint."""

    @pytest.mark.asyncio
    async def test_query_nonexistent_service(self, async_client: AsyncClient):
        """Test querying a service that doesn't exist."""
        response = await async_client.get(
            "/api/v1/services/nonexistent-service/dependencies"
        )

        assert response.status_code == 404
        data = response.json()
        assert data["type"] == "about:blank"
        assert data["title"] == "Not Found"
        assert "correlation_id" in data

    @pytest.mark.asyncio
    async def test_query_service_with_no_dependencies(self, async_client: AsyncClient):
        """Test querying a service that exists but has no dependencies."""
        # First ingest a service with no edges
        ingest_payload = {
            "source": "manual",
            "timestamp": "2026-02-15T10:00:00Z",
            "nodes": [
                {
                    "service_id": "isolated-service",
                    "metadata": {
                        "service_name": "Isolated Service",
                        "team": "team-alpha",
                        "criticality": "low",
                    },
                }
            ],
            "edges": [],
        }

        await async_client.post("/api/v1/services/dependencies", json=ingest_payload)

        # Now query it
        response = await async_client.get(
            "/api/v1/services/isolated-service/dependencies"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["service_id"] == "isolated-service"
        assert len(data["nodes"]) == 1
        assert len(data["edges"]) == 0
        assert data["statistics"]["total_edges"] == 0

    @pytest.mark.asyncio
    async def test_query_service_with_dependencies(self, async_client: AsyncClient):
        """Test querying a service with dependencies."""
        # Ingest a small dependency graph
        ingest_payload = {
            "source": "otel_service_graph",
            "timestamp": "2026-02-15T10:00:00Z",
            "nodes": [
                {
                    "service_id": "frontend",
                    "metadata": {
                        "service_name": "Frontend",
                        "team": "team-web",
                        "criticality": "high",
                    },
                },
                {
                    "service_id": "backend",
                    "metadata": {
                        "service_name": "Backend API",
                        "team": "team-api",
                        "criticality": "high",
                    },
                },
                {
                    "service_id": "database",
                    "metadata": {
                        "service_name": "Database",
                        "team": "team-data",
                        "criticality": "critical",
                    },
                },
            ],
            "edges": [
                {
                    "source": "frontend",
                    "target": "backend",
                    "attributes": {
                        "communication_mode": "sync",
                        "criticality": "hard",
                        "protocol": "http",
                    },
                },
                {
                    "source": "backend",
                    "target": "database",
                    "attributes": {
                        "communication_mode": "sync",
                        "criticality": "hard",
                        "protocol": "tcp",
                    },
                },
            ],
        }

        await async_client.post("/api/v1/services/dependencies", json=ingest_payload)

        # Query frontend's downstream dependencies
        response = await async_client.get(
            "/api/v1/services/frontend/dependencies",
            params={"direction": "downstream", "depth": 2},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["service_id"] == "frontend"
        assert len(data["nodes"]) >= 2  # frontend + backend (+ possibly database)
        assert len(data["edges"]) >= 1  # frontend -> backend
        assert data["statistics"]["downstream_services"] >= 1

    @pytest.mark.asyncio
    async def test_query_with_direction_upstream(self, async_client: AsyncClient):
        """Test querying upstream dependencies."""
        # Ingest a dependency graph
        ingest_payload = {
            "source": "otel_service_graph",
            "timestamp": "2026-02-15T10:00:00Z",
            "nodes": [
                {
                    "service_id": "service-x",
                    "metadata": {
                        "service_name": "Service X",
                        "team": "team-x",
                        "criticality": "medium",
                    },
                },
                {
                    "service_id": "service-y",
                    "metadata": {
                        "service_name": "Service Y",
                        "team": "team-y",
                        "criticality": "medium",
                    },
                },
            ],
            "edges": [
                {
                    "source": "service-x",
                    "target": "service-y",
                    "attributes": {
                        "communication_mode": "sync",
                        "criticality": "hard",
                        "protocol": "http",
                    },
                }
            ],
        }

        await async_client.post("/api/v1/services/dependencies", json=ingest_payload)

        # Query service-y's upstream dependencies
        response = await async_client.get(
            "/api/v1/services/service-y/dependencies",
            params={"direction": "upstream", "depth": 1},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["service_id"] == "service-y"
        # Should include service-x as upstream
        service_ids = [node["service_id"] for node in data["nodes"]]
        assert "service-x" in service_ids

    @pytest.mark.asyncio
    async def test_query_with_invalid_depth(self, async_client: AsyncClient):
        """Test that invalid depth parameter is rejected."""
        # First create a service
        ingest_payload = {
            "source": "manual",
            "timestamp": "2026-02-15T10:00:00Z",
            "nodes": [
                {
                    "service_id": "test-service",
                    "metadata": {
                        "service_name": "Test Service",
                        "team": "team-test",
                        "criticality": "low",
                    },
                }
            ],
            "edges": [],
        }

        await async_client.post("/api/v1/services/dependencies", json=ingest_payload)

        # Query with invalid depth (>10)
        response = await async_client.get(
            "/api/v1/services/test-service/dependencies",
            params={"depth": 15},
        )

        # FastAPI's query parameter validation (le=10) returns 422
        assert response.status_code == 422
        data = response.json()
        assert "correlation_id" in data


class TestRateLimiting:
    """Test rate limiting middleware."""

    @pytest.mark.asyncio
    async def test_rate_limit_headers_present(self, async_client: AsyncClient):
        """Test that rate limit headers are present in responses."""
        response = await async_client.post(
            "/api/v1/services/dependencies",
            json={"source": "manual", "timestamp": "2026-02-15T10:00:00Z", "nodes": [], "edges": []},
        )

        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    @pytest.mark.asyncio
    async def test_rate_limit_enforcement(self, async_client: AsyncClient):
        """Test that rate limiting is enforced."""
        # Make multiple requests rapidly to trigger rate limit
        # POST /dependencies has limit of 10 req/min
        responses = []
        for _ in range(12):  # Exceed the limit
            response = await async_client.post(
                "/api/v1/services/dependencies",
                json={"source": "manual", "timestamp": "2026-02-15T10:00:00Z", "nodes": [], "edges": []},
            )
            responses.append(response)

        # At least one should be rate limited
        status_codes = [r.status_code for r in responses]
        assert 429 in status_codes

        # Check 429 response format
        rate_limited_response = next(r for r in responses if r.status_code == 429)
        data = rate_limited_response.json()
        assert data["type"] == "https://httpstatuses.com/429"
        assert data["title"] == "Too Many Requests"
        assert "Retry-After" in rate_limited_response.headers


class TestErrorHandling:
    """Test error handling and correlation IDs."""

    @pytest.mark.asyncio
    async def test_correlation_id_in_success_response(self, async_client: AsyncClient):
        """Test that correlation ID is present in successful responses."""
        response = await async_client.get("/api/v1/health")

        assert "X-Correlation-ID" in response.headers
        correlation_id = response.headers["X-Correlation-ID"]
        assert len(correlation_id) > 0

    @pytest.mark.asyncio
    async def test_correlation_id_in_error_response(self, async_client: AsyncClient):
        """Test that correlation ID is present in error responses."""
        response = await async_client.get(
            "/api/v1/services/nonexistent-service/dependencies"
        )

        assert response.status_code == 404
        assert "X-Correlation-ID" in response.headers

        data = response.json()
        assert "correlation_id" in data
        # Header and body should match
        assert data["correlation_id"] == response.headers["X-Correlation-ID"]

    @pytest.mark.asyncio
    async def test_rfc7807_error_format(self, async_client: AsyncClient):
        """Test that errors follow RFC 7807 Problem Details format."""
        response = await async_client.get(
            "/api/v1/services/nonexistent/dependencies"
        )

        assert response.status_code == 404
        data = response.json()

        # RFC 7807 required fields
        assert "type" in data
        assert "title" in data
        assert "status" in data
        assert data["status"] == 404

        # Our custom fields
        assert "correlation_id" in data


class TestFullWorkflow:
    """Test complete end-to-end workflows."""

    @pytest.mark.asyncio
    async def test_ingest_and_query_workflow(self, async_client: AsyncClient):
        """Test the complete workflow: ingest a graph then query it."""
        # Step 1: Ingest a dependency graph
        ingest_payload = {
            "source": "otel_service_graph",
            "timestamp": "2026-02-15T10:00:00Z",
            "nodes": [
                {
                    "service_id": "api-gateway",
                    "metadata": {
                        "service_name": "API Gateway",
                        "team": "platform",
                        "criticality": "critical",
                    },
                },
                {
                    "service_id": "auth-service",
                    "metadata": {
                        "service_name": "Auth Service",
                        "team": "security",
                        "criticality": "critical",
                    },
                },
                {
                    "service_id": "user-service",
                    "metadata": {
                        "service_name": "User Service",
                        "team": "identity",
                        "criticality": "high",
                    },
                },
            ],
            "edges": [
                {
                    "source": "api-gateway",
                    "target": "auth-service",
                    "attributes": {
                        "communication_mode": "sync",
                        "criticality": "hard",
                        "protocol": "http",
                    },
                },
                {
                    "source": "api-gateway",
                    "target": "user-service",
                    "attributes": {
                        "communication_mode": "sync",
                        "criticality": "hard",
                        "protocol": "http",
                    },
                },
            ],
        }

        ingest_response = await async_client.post(
            "/api/v1/services/dependencies",
            json=ingest_payload,
        )

        assert ingest_response.status_code == 202
        ingest_data = ingest_response.json()
        assert ingest_data["nodes_upserted"] == 3
        assert ingest_data["edges_upserted"] == 2

        # Step 2: Query the ingested graph
        query_response = await async_client.get(
            "/api/v1/services/api-gateway/dependencies",
            params={"direction": "downstream", "depth": 2},
        )

        assert query_response.status_code == 200
        query_data = query_response.json()
        assert query_data["service_id"] == "api-gateway"
        assert len(query_data["nodes"]) >= 2  # At least api-gateway + 1 downstream
        assert len(query_data["edges"]) >= 1

        # Step 3: Query from a different perspective (upstream of auth-service)
        upstream_response = await async_client.get(
            "/api/v1/services/auth-service/dependencies",
            params={"direction": "upstream", "depth": 1},
        )

        assert upstream_response.status_code == 200
        upstream_data = upstream_response.json()
        service_ids = [node["service_id"] for node in upstream_data["nodes"]]
        assert "api-gateway" in service_ids  # api-gateway depends on auth-service
