"""E2E tests for the Constraint Analysis API endpoints."""

import time
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient


class TestConstraintAnalysisEndpoint:
    """Test constraint analysis endpoint."""

    @pytest.mark.asyncio
    async def test_successful_constraint_analysis(self, async_client: AsyncClient):
        """Test successful constraint analysis with internal services."""
        # First, ingest a graph with dependencies
        ingest_payload = {
            "source": "manual",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nodes": [
                {
                    "service_id": "api-gateway",
                    "metadata": {
                        "service_name": "API Gateway",
                        "team": "platform",
                        "criticality": "high",
                    },
                },
                {
                    "service_id": "auth-service",
                    "metadata": {
                        "service_name": "Auth Service",
                        "team": "security",
                        "criticality": "high",
                    },
                },
                {
                    "service_id": "user-service",
                    "metadata": {
                        "service_name": "User Service",
                        "team": "users",
                        "criticality": "medium",
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
                        "protocol": "grpc",
                        "timeout_ms": 1000,
                    },
                },
                {
                    "source": "api-gateway",
                    "target": "user-service",
                    "attributes": {
                        "communication_mode": "sync",
                        "criticality": "hard",
                        "protocol": "http",
                        "timeout_ms": 2000,
                    },
                },
            ],
        }

        ingest_response = await async_client.post(
            "/api/v1/services/dependencies",
            json=ingest_payload,
        )
        assert ingest_response.status_code == 202

        # Now query constraint analysis
        start_time = time.time()
        response = await async_client.get(
            "/api/v1/services/api-gateway/constraint-analysis",
            params={
                "desired_target_pct": 99.9,
                "lookback_days": 30,
                "max_depth": 3,
            },
        )
        elapsed = time.time() - start_time

        # Assert response structure
        if response.status_code != 200:
            print(f"Error response: {response.status_code} - {response.json()}")
        assert response.status_code == 200
        data = response.json()

        # Basic fields
        assert data["service_id"] == "api-gateway"
        assert data["desired_target_pct"] == 99.9
        assert "composite_availability_bound_pct" in data
        assert isinstance(data["is_achievable"], bool)
        assert data["dependency_count"] >= 2
        assert data["hard_dependency_count"] >= 2

        # Error budget breakdown
        assert "error_budget_breakdown" in data
        breakdown = data["error_budget_breakdown"]
        assert "total_error_budget_minutes" in breakdown
        assert "self_consumption_pct" in breakdown
        assert "total_dependency_consumption_pct" in breakdown
        assert "dependency_risks" in breakdown
        assert isinstance(breakdown["dependency_risks"], list)
        assert len(breakdown["dependency_risks"]) >= 2

        # Metadata
        assert "analyzed_at" in data

        # Performance check: < 2s
        assert elapsed < 2.0, f"Response took {elapsed:.2f}s, expected < 2s"

    @pytest.mark.asyncio
    async def test_constraint_analysis_with_external_service(
        self, async_client: AsyncClient
    ):
        """Test constraint analysis with external API dependencies."""
        # Ingest graph with external service
        ingest_payload = {
            "source": "manual",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nodes": [
                {
                    "service_id": "payment-service",
                    "metadata": {
                        "service_name": "Payment Service",
                        "team": "payments",
                        "criticality": "high",
                    },
                },
                {
                    "service_id": "stripe-api",
                    "metadata": {
                        "service_name": "Stripe API",
                        "team": "external",
                        "criticality": "hard",
                        "service_type": "external",
                        "published_sla": 99.99,
                    },
                },
            ],
            "edges": [
                {
                    "source": "payment-service",
                    "target": "stripe-api",
                    "attributes": {
                        "communication_mode": "sync",
                        "criticality": "hard",
                        "protocol": "https",
                        "timeout_ms": 5000,
                    },
                }
            ],
        }

        ingest_response = await async_client.post(
            "/api/v1/services/dependencies",
            json=ingest_payload,
        )
        assert ingest_response.status_code == 202

        # Query constraint analysis
        response = await async_client.get(
            "/api/v1/services/payment-service/constraint-analysis",
            params={
                "desired_target_pct": 99.95,
                "lookback_days": 30,
                "max_depth": 2,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["external_dependency_count"] >= 1

        # Check that adaptive buffer was applied
        breakdown = data["error_budget_breakdown"]
        external_deps = [
            dep for dep in breakdown["dependency_risks"] if dep["is_external"]
        ]
        assert len(external_deps) >= 1

        # External dep should have effective_availability_note
        for dep in external_deps:
            assert dep["effective_availability_note"] is not None
            assert "adjusted" in dep["effective_availability_note"].lower() or "default" in dep["effective_availability_note"].lower()

    @pytest.mark.asyncio
    async def test_constraint_analysis_unachievable_slo(
        self, async_client: AsyncClient
    ):
        """Test constraint analysis detects unachievable SLO targets."""
        # Ingest graph with multiple dependencies
        ingest_payload = {
            "source": "manual",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nodes": [
                {
                    "service_id": "frontend",
                    "metadata": {
                        "service_name": "Frontend",
                        "team": "web",
                        "criticality": "high",
                    },
                },
                {
                    "service_id": "backend-1",
                    "metadata": {
                        "service_name": "Backend 1",
                        "team": "api",
                        "criticality": "high",
                    },
                },
                {
                    "service_id": "backend-2",
                    "metadata": {
                        "service_name": "Backend 2",
                        "team": "api",
                        "criticality": "high",
                    },
                },
                {
                    "service_id": "database",
                    "metadata": {
                        "service_name": "Database",
                        "team": "data",
                        "criticality": "high",
                    },
                },
            ],
            "edges": [
                {
                    "source": "frontend",
                    "target": "backend-1",
                    "attributes": {
                        "communication_mode": "sync",
                        "criticality": "hard",
                        "protocol": "http",
                    },
                },
                {
                    "source": "frontend",
                    "target": "backend-2",
                    "attributes": {
                        "communication_mode": "sync",
                        "criticality": "hard",
                        "protocol": "http",
                    },
                },
                {
                    "source": "backend-1",
                    "target": "database",
                    "attributes": {
                        "communication_mode": "sync",
                        "criticality": "hard",
                        "protocol": "tcp",
                    },
                },
            ],
        }

        ingest_response = await async_client.post(
            "/api/v1/services/dependencies",
            json=ingest_payload,
        )
        assert ingest_response.status_code == 202

        # Query with very high target (likely unachievable with mock data)
        response = await async_client.get(
            "/api/v1/services/frontend/constraint-analysis",
            params={
                "desired_target_pct": 99.999,  # Five nines
                "lookback_days": 30,
                "max_depth": 3,
            },
        )

        assert response.status_code == 200
        data = response.json()

        # May or may not be achievable depending on mock data
        # But structure should be present
        if not data["is_achievable"]:
            assert "unachievable_warning" in data
            assert data["unachievable_warning"] is not None
            warning = data["unachievable_warning"]
            assert "message" in warning
            assert "remediation_guidance" in warning
            assert "required_dep_availability_pct" in warning

    @pytest.mark.asyncio
    async def test_constraint_analysis_service_not_found(
        self, async_client: AsyncClient
    ):
        """Test constraint analysis returns 404 for unknown service."""
        response = await async_client.get(
            "/api/v1/services/nonexistent-service/constraint-analysis",
            params={
                "desired_target_pct": 99.9,
                "lookback_days": 30,
            },
        )

        assert response.status_code == 404
        data = response.json()
        assert data["type"] == "about:blank"
        assert data["title"] == "Not Found"
        assert "nonexistent-service" in data["detail"]

    @pytest.mark.asyncio
    async def test_constraint_analysis_invalid_params(self, async_client: AsyncClient):
        """Test constraint analysis validates query parameters."""
        # Ingest a simple service first
        ingest_payload = {
            "source": "manual",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nodes": [
                {
                    "service_id": "test-service",
                    "metadata": {"service_name": "Test Service"},
                }
            ],
            "edges": [],
        }
        await async_client.post("/api/v1/services/dependencies", json=ingest_payload)

        # Test invalid desired_target_pct (out of range)
        response = await async_client.get(
            "/api/v1/services/test-service/constraint-analysis",
            params={
                "desired_target_pct": 105.0,  # > 99.9999
                "lookback_days": 30,
            },
        )
        assert response.status_code == 422  # Validation error

        # Test invalid lookback_days (out of range)
        response = await async_client.get(
            "/api/v1/services/test-service/constraint-analysis",
            params={
                "desired_target_pct": 99.9,
                "lookback_days": 400,  # > 365
            },
        )
        assert response.status_code == 422

        # Test invalid max_depth (out of range)
        response = await async_client.get(
            "/api/v1/services/test-service/constraint-analysis",
            params={
                "desired_target_pct": 99.9,
                "lookback_days": 30,
                "max_depth": 20,  # > 10
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_constraint_analysis_no_dependencies(self, async_client: AsyncClient):
        """Test constraint analysis returns 422 for service with no dependencies."""
        # Ingest a service with no edges
        ingest_payload = {
            "source": "manual",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nodes": [
                {
                    "service_id": "isolated-service",
                    "metadata": {
                        "service_name": "Isolated Service",
                        "team": "test",
                    },
                }
            ],
            "edges": [],
        }

        ingest_response = await async_client.post(
            "/api/v1/services/dependencies",
            json=ingest_payload,
        )
        assert ingest_response.status_code == 202

        # Query constraint analysis (should fail with no deps)
        response = await async_client.get(
            "/api/v1/services/isolated-service/constraint-analysis",
            params={
                "desired_target_pct": 99.9,
                "lookback_days": 30,
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert "no dependencies" in data["detail"].lower()


class TestErrorBudgetBreakdownEndpoint:
    """Test error budget breakdown endpoint."""

    @pytest.mark.asyncio
    async def test_successful_error_budget_breakdown(self, async_client: AsyncClient):
        """Test successful error budget breakdown."""
        # Ingest a graph with dependencies
        ingest_payload = {
            "source": "manual",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nodes": [
                {
                    "service_id": "web-app",
                    "metadata": {
                        "service_name": "Web App",
                        "team": "frontend",
                    },
                },
                {
                    "service_id": "api-1",
                    "metadata": {
                        "service_name": "API 1",
                        "team": "backend",
                    },
                },
                {
                    "service_id": "api-2",
                    "metadata": {
                        "service_name": "API 2",
                        "team": "backend",
                    },
                },
            ],
            "edges": [
                {
                    "source": "web-app",
                    "target": "api-1",
                    "attributes": {
                        "communication_mode": "sync",
                        "criticality": "hard",
                        "protocol": "http",
                    },
                },
                {
                    "source": "web-app",
                    "target": "api-2",
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

        # Query error budget breakdown
        start_time = time.time()
        response = await async_client.get(
            "/api/v1/services/web-app/error-budget-breakdown",
            params={
                "slo_target_pct": 99.9,
                "lookback_days": 30,
            },
        )
        elapsed = time.time() - start_time

        # Assert response structure
        assert response.status_code == 200
        data = response.json()

        # Basic fields (flat response structure)
        assert data["service_id"] == "web-app"
        assert data["slo_target_pct"] == 99.9
        assert "total_error_budget_minutes" in data
        assert data["total_error_budget_minutes"] > 0
        assert "self_consumption_pct" in data
        assert "total_dependency_consumption_pct" in data
        assert "high_risk_dependencies" in data
        assert "dependency_risks" in data
        assert isinstance(data["dependency_risks"], list)

        # Each dependency risk should have required fields
        for dep_risk in data["dependency_risks"]:
            assert "service_id" in dep_risk
            assert "availability_pct" in dep_risk
            assert "error_budget_consumption_pct" in dep_risk
            assert "risk_level" in dep_risk
            assert dep_risk["risk_level"] in ["low", "moderate", "high"]
            assert "is_external" in dep_risk

        # Metadata
        assert "analyzed_at" in data

        # Performance check: < 1s
        assert elapsed < 1.0, f"Response took {elapsed:.2f}s, expected < 1s"

    @pytest.mark.asyncio
    async def test_error_budget_breakdown_default_params(
        self, async_client: AsyncClient
    ):
        """Test error budget breakdown with default parameters."""
        # Ingest a simple service
        ingest_payload = {
            "source": "manual",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nodes": [
                {
                    "service_id": "simple-service",
                    "metadata": {"service_name": "Simple Service"},
                },
                {
                    "service_id": "dep-service",
                    "metadata": {"service_name": "Dep Service"},
                },
            ],
            "edges": [
                {
                    "source": "simple-service",
                    "target": "dep-service",
                    "attributes": {
                        "communication_mode": "sync",
                        "criticality": "hard",
                        "protocol": "http",
                    },
                }
            ],
        }

        await async_client.post("/api/v1/services/dependencies", json=ingest_payload)

        # Query without params (should use defaults)
        response = await async_client.get(
            "/api/v1/services/simple-service/error-budget-breakdown"
        )

        assert response.status_code == 200
        data = response.json()
        # Default slo_target_pct should be 99.9
        assert data["slo_target_pct"] == 99.9

    @pytest.mark.asyncio
    async def test_error_budget_breakdown_service_not_found(
        self, async_client: AsyncClient
    ):
        """Test error budget breakdown returns 404 for unknown service."""
        response = await async_client.get(
            "/api/v1/services/unknown-service/error-budget-breakdown",
            params={"slo_target_pct": 99.9},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["type"] == "about:blank"
        assert data["title"] == "Not Found"

    @pytest.mark.asyncio
    async def test_error_budget_breakdown_invalid_params(
        self, async_client: AsyncClient
    ):
        """Test error budget breakdown validates query parameters."""
        # Ingest a simple service first
        ingest_payload = {
            "source": "manual",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nodes": [
                {"service_id": "test-svc", "metadata": {"service_name": "Test"}}
            ],
            "edges": [],
        }
        await async_client.post("/api/v1/services/dependencies", json=ingest_payload)

        # Test invalid slo_target_pct
        response = await async_client.get(
            "/api/v1/services/test-svc/error-budget-breakdown",
            params={"slo_target_pct": 80.0},  # < 90
        )
        assert response.status_code == 422

        # Test invalid lookback_days
        response = await async_client.get(
            "/api/v1/services/test-svc/error-budget-breakdown",
            params={"slo_target_pct": 99.9, "lookback_days": 5},  # < 7
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_error_budget_breakdown_high_risk_dependencies(
        self, async_client: AsyncClient
    ):
        """Test error budget breakdown identifies high-risk dependencies."""
        # This test relies on mock data potentially having low-availability services
        # If high_risk_dependencies is populated, verify structure
        ingest_payload = {
            "source": "manual",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nodes": [
                {"service_id": "app", "metadata": {"service_name": "App"}},
                {"service_id": "dep-1", "metadata": {"service_name": "Dep 1"}},
                {"service_id": "dep-2", "metadata": {"service_name": "Dep 2"}},
            ],
            "edges": [
                {
                    "source": "app",
                    "target": "dep-1",
                    "attributes": {
                        "communication_mode": "sync",
                        "criticality": "hard",
                        "protocol": "http",
                    },
                },
                {
                    "source": "app",
                    "target": "dep-2",
                    "attributes": {
                        "communication_mode": "sync",
                        "criticality": "hard",
                        "protocol": "http",
                    },
                },
            ],
        }

        await async_client.post("/api/v1/services/dependencies", json=ingest_payload)

        response = await async_client.get(
            "/api/v1/services/app/error-budget-breakdown",
            params={"slo_target_pct": 99.9},
        )

        assert response.status_code == 200
        data = response.json()

        # Flat response structure
        assert "high_risk_dependencies" in data
        assert isinstance(data["high_risk_dependencies"], list)

        # If high_risk_dependencies exist, verify structure
        if len(data["high_risk_dependencies"]) > 0:
            # high_risk_dependencies is just a list of service_ids
            for service_id in data["high_risk_dependencies"]:
                assert isinstance(service_id, str)

            # Find the corresponding risks in dependency_risks
            for service_id in data["high_risk_dependencies"]:
                matching_risks = [r for r in data["dependency_risks"] if r["service_id"] == service_id]
                assert len(matching_risks) > 0
                for risk in matching_risks:
                    assert risk["risk_level"] == "high"
                    assert risk["error_budget_consumption_pct"] > 30.0


class TestAuthenticationConstraintAnalysis:
    """Test authentication for constraint analysis endpoints."""

    @pytest.mark.asyncio
    async def test_constraint_analysis_requires_auth(
        self, async_client_no_auth: AsyncClient
    ):
        """Test that constraint analysis endpoint requires authentication."""
        response = await async_client_no_auth.get(
            "/api/v1/services/some-service/constraint-analysis"
        )

        assert response.status_code == 401
        data = response.json()
        assert data["title"] == "Unauthorized"

    @pytest.mark.asyncio
    async def test_error_budget_breakdown_requires_auth(
        self, async_client_no_auth: AsyncClient
    ):
        """Test that error budget breakdown endpoint requires authentication."""
        response = await async_client_no_auth.get(
            "/api/v1/services/some-service/error-budget-breakdown"
        )

        assert response.status_code == 401
        data = response.json()
        assert data["title"] == "Unauthorized"
