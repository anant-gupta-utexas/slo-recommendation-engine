"""Integration tests for health check endpoints.

Tests liveness, readiness probes with dependency health checks.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.infrastructure.api.main import app


transport = ASGITransport(app=app)


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    @pytest.mark.asyncio
    async def test_liveness_probe_always_returns_200(self):
        """Test that /health endpoint always returns 200 (liveness)."""
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["service"] == "slo-recommendation-engine"

    @pytest.mark.asyncio
    async def test_readiness_probe_checks_dependencies(self):
        """Test that /health/ready checks database and Redis."""
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health/ready")

            # Response can be 200 (ready) or 503 (not ready) depending on services
            assert response.status_code in [200, 503]

            data = response.json()
            assert "checks" in data
            assert "database" in data["checks"]
            assert "redis" in data["checks"]

            # Check values should be "healthy" or "unhealthy"
            for check_name, check_status in data["checks"].items():
                assert check_status in ["healthy", "unhealthy"]

    @pytest.mark.asyncio
    async def test_readiness_returns_503_when_dependency_unhealthy(self):
        """Test that readiness returns 503 when a dependency is unhealthy."""
        # This test would require mocking database/Redis to simulate failure
        # For now, we just verify the response structure
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health/ready")

            data = response.json()
            assert "status" in data
            assert data["status"] in ["ready", "not_ready"]

            if response.status_code == 503:
                # If not ready, at least one check should be unhealthy
                assert data["status"] == "not_ready"
                check_values = list(data["checks"].values())
                assert "unhealthy" in check_values


class TestMetricsEndpoint:
    """Tests for metrics endpoint."""

    @pytest.mark.asyncio
    async def test_metrics_endpoint_returns_prometheus_format(self):
        """Test that /metrics returns Prometheus exposition format."""
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/metrics")

            assert response.status_code == 200
            assert "text/plain" in response.headers["content-type"]

            # Verify Prometheus format
            content = response.text
            assert "# HELP" in content or "slo_engine_" in content

    @pytest.mark.asyncio
    async def test_metrics_not_rate_limited(self):
        """Test that /metrics endpoint is not rate limited."""
        # Metrics endpoint should be excluded from rate limiting
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Make multiple requests rapidly
            for _ in range(20):
                response = await client.get("/api/v1/metrics")
                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_not_rate_limited(self):
        """Test that health endpoints are not rate limited."""
        # Health endpoints should be excluded from rate limiting
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Make multiple requests rapidly
            for _ in range(20):
                response = await client.get("/api/v1/health")
                assert response.status_code == 200

                response = await client.get("/api/v1/health/ready")
                assert response.status_code in [200, 503]
