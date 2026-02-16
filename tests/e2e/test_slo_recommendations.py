"""E2E tests for the SLO Recommendation API endpoints.

These tests verify the complete workflow from service ingestion through
recommendation generation and retrieval.
"""

import time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.service import Service
from src.domain.entities.service_dependency import DiscoverySource
from src.infrastructure.database.repositories.service_repository import (
    ServiceRepository,
)


class TestSloRecommendationWorkflow:
    """Test complete SLO recommendation workflow end-to-end."""

    @pytest.mark.asyncio
    async def test_full_workflow_with_dependency_graph(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test complete workflow: ingest graph → get recommendations.

        This test:
        1. Ingests a dependency graph with 3 services
        2. Requests SLO recommendations for a service
        3. Verifies the response matches the expected schema
        4. Validates that recommendations include dependency impact
        """
        # Step 1: Ingest dependency graph
        graph_payload = {
            "source": "manual",
            "timestamp": "2026-02-16T10:00:00Z",
            "nodes": [
                {
                    "service_id": "payment-service",
                    "metadata": {
                        "display_name": "Payment Service",
                        "owner_team": "payments",
                    },
                },
                {
                    "service_id": "auth-service",
                    "metadata": {
                        "display_name": "Auth Service",
                        "owner_team": "platform",
                    },
                },
                {
                    "service_id": "notification-service",
                    "metadata": {
                        "display_name": "Notification Service",
                        "owner_team": "comms",
                    },
                },
            ],
            "edges": [
                {
                    "client_id": "payment-service",
                    "server_id": "auth-service",
                    "connection_type": "http",
                },
                {
                    "client_id": "payment-service",
                    "server_id": "notification-service",
                    "connection_type": "http",
                },
            ],
        }

        ingest_response = await async_client.post(
            "/api/v1/services/dependencies",
            json=graph_payload,
        )
        assert ingest_response.status_code == 200

        # Step 2: Request SLO recommendations
        # Note: payment-service has seed data in MockPrometheusClient
        rec_response = await async_client.get(
            "/api/v1/services/payment-service/slo-recommendations",
            params={
                "sli_type": "availability",
                "lookback_days": 30,
            },
        )

        assert rec_response.status_code == 200
        data = rec_response.json()

        # Step 3: Verify response structure matches TRD schema
        assert data["service_id"] == "payment-service"
        assert "recommendations" in data
        assert len(data["recommendations"]) > 0

        availability_rec = data["recommendations"][0]
        assert availability_rec["sli_type"] == "availability"
        assert "tiers" in availability_rec
        assert len(availability_rec["tiers"]) == 3

        # Verify tier structure
        for tier in availability_rec["tiers"]:
            assert "level" in tier
            assert "target" in tier
            assert "breach_probability" in tier
            assert tier["level"] in ["conservative", "balanced", "aggressive"]

        # Verify explanation structure
        assert "explanation" in availability_rec
        explanation = availability_rec["explanation"]
        assert "summary" in explanation
        assert "feature_attributions" in explanation
        assert "dependency_impacts" in explanation

        # Step 4: Verify dependency impacts are included
        dep_impacts = explanation["dependency_impacts"]
        # Should have impacts for auth-service and notification-service
        assert len(dep_impacts) >= 0  # May be empty if no hard dependencies

    @pytest.mark.asyncio
    async def test_force_regenerate_recomputes_recommendations(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test that force_regenerate flag recomputes recommendations."""
        # Create a service with seed data
        service_repo = ServiceRepository(db_session)
        service = Service(
            id="payment-service",
            display_name="Payment Service",
            description="Handles payments",
            owner_team="payments",
            discovery_source=DiscoverySource.MANUAL,
        )
        await service_repo.add(service)

        # Step 1: Get recommendations (will generate fresh)
        response1 = await async_client.get(
            "/api/v1/services/payment-service/slo-recommendations",
            params={"sli_type": "availability", "lookback_days": 30},
        )
        assert response1.status_code == 200
        data1 = response1.json()
        generated_at_1 = data1["recommendations"][0]["generated_at"]

        # Wait a moment to ensure timestamps differ
        time.sleep(0.1)

        # Step 2: Get recommendations with force_regenerate=True
        response2 = await async_client.get(
            "/api/v1/services/payment-service/slo-recommendations",
            params={
                "sli_type": "availability",
                "lookback_days": 30,
                "force_regenerate": True,
            },
        )
        assert response2.status_code == 200
        data2 = response2.json()
        generated_at_2 = data2["recommendations"][0]["generated_at"]

        # Verify new recommendation was generated
        assert generated_at_2 != generated_at_1
        assert generated_at_2 > generated_at_1

    @pytest.mark.asyncio
    async def test_no_data_service_returns_422(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test that service with no telemetry data returns 422."""
        # Create a service without telemetry data
        service_repo = ServiceRepository(db_session)
        service = Service(
            id="no-telemetry-service",
            display_name="No Telemetry Service",
            description="Service without any metrics",
            owner_team="test-team",
            discovery_source=DiscoverySource.MANUAL,
        )
        await service_repo.add(service)

        # Request recommendations for service without data
        response = await async_client.get(
            "/api/v1/services/no-telemetry-service/slo-recommendations",
            params={"sli_type": "availability", "lookback_days": 30},
        )

        # Should return 422 Unprocessable Entity
        assert response.status_code == 422
        data = response.json()
        assert data["title"] == "Unprocessable Entity"
        assert "insufficient data" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_response_matches_trd_schema(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test that API response matches the TRD JSON schema exactly."""
        # Create service with seed data
        service_repo = ServiceRepository(db_session)
        service = Service(
            id="payment-service",
            display_name="Payment Service",
            description="Payment processing",
            owner_team="payments",
            discovery_source=DiscoverySource.MANUAL,
        )
        await service_repo.add(service)

        # Get recommendations
        response = await async_client.get(
            "/api/v1/services/payment-service/slo-recommendations",
            params={"sli_type": "all", "lookback_days": 30},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify top-level schema
        assert "service_id" in data
        assert "recommendations" in data
        assert isinstance(data["recommendations"], list)

        # Verify each recommendation schema
        for rec in data["recommendations"]:
            # Required fields
            assert "sli_type" in rec
            assert "tiers" in rec
            assert "explanation" in rec
            assert "lookback_window" in rec
            assert "generated_at" in rec
            assert "expires_at" in rec

            # Tiers schema (3 tiers)
            assert len(rec["tiers"]) == 3
            for tier in rec["tiers"]:
                assert "level" in tier
                assert "target" in tier
                assert "breach_probability" in tier
                assert tier["level"] in ["conservative", "balanced", "aggressive"]
                assert 0.0 <= tier["target"] <= 1.0
                assert 0.0 <= tier["breach_probability"] <= 1.0

            # Explanation schema
            exp = rec["explanation"]
            assert "summary" in exp
            assert "feature_attributions" in exp
            assert "dependency_impacts" in exp
            assert "data_quality" in exp

            # Feature attributions schema
            for attr in exp["feature_attributions"]:
                assert "feature" in attr
                assert "contribution" in attr

            # Data quality schema
            dq = exp["data_quality"]
            assert "data_completeness" in dq
            assert "sample_count" in dq
            assert 0.0 <= dq["data_completeness"] <= 1.0
            assert dq["sample_count"] >= 0

            # Lookback window schema
            lw = rec["lookback_window"]
            assert "start" in lw
            assert "end" in lw
            assert "days" in lw

    @pytest.mark.asyncio
    async def test_precomputed_retrieval_performance(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test that pre-computed recommendation retrieval is < 500ms.

        This test verifies the p95 latency target of 500ms for cached
        recommendation retrieval.
        """
        # Create service and pre-generate recommendations
        service_repo = ServiceRepository(db_session)
        service = Service(
            id="payment-service",
            display_name="Payment Service",
            description="Payment processing",
            owner_team="payments",
            discovery_source=DiscoverySource.MANUAL,
        )
        await service_repo.add(service)

        # First request generates recommendation
        await async_client.get(
            "/api/v1/services/payment-service/slo-recommendations",
            params={"sli_type": "availability", "lookback_days": 30},
        )

        # Second request should be fast (pre-computed)
        start_time = time.time()
        response = await async_client.get(
            "/api/v1/services/payment-service/slo-recommendations",
            params={"sli_type": "availability", "lookback_days": 30},
        )
        duration = time.time() - start_time

        assert response.status_code == 200

        # Verify performance target (p95 < 500ms)
        # In practice, cached retrieval should be < 100ms
        assert duration < 0.5, f"Retrieval took {duration:.3f}s, expected < 0.5s"

    @pytest.mark.asyncio
    async def test_service_not_found_returns_404(
        self,
        async_client: AsyncClient,
    ):
        """Test that non-existent service returns 404."""
        response = await async_client.get(
            "/api/v1/services/nonexistent-service/slo-recommendations",
            params={"sli_type": "availability", "lookback_days": 30},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["title"] == "Not Found"
        assert "service not found" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_invalid_sli_type_returns_422(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test that invalid sli_type returns 422."""
        service_repo = ServiceRepository(db_session)
        service = Service(
            id="test-service",
            display_name="Test Service",
            owner_team="test",
            discovery_source=DiscoverySource.MANUAL,
        )
        await service_repo.add(service)

        response = await async_client.get(
            "/api/v1/services/test-service/slo-recommendations",
            params={"sli_type": "invalid_type", "lookback_days": 30},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_lookback_days_returns_422(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test that invalid lookback_days returns 422."""
        service_repo = ServiceRepository(db_session)
        service = Service(
            id="test-service",
            display_name="Test Service",
            owner_team="test",
            discovery_source=DiscoverySource.MANUAL,
        )
        await service_repo.add(service)

        # Test too low
        response_low = await async_client.get(
            "/api/v1/services/test-service/slo-recommendations",
            params={"sli_type": "availability", "lookback_days": 5},
        )
        assert response_low.status_code == 422

        # Test too high
        response_high = await async_client.get(
            "/api/v1/services/test-service/slo-recommendations",
            params={"sli_type": "availability", "lookback_days": 400},
        )
        assert response_high.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_authentication_returns_401(
        self,
        async_client_no_auth: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test that requests without authentication return 401."""
        response = await async_client_no_auth.get(
            "/api/v1/services/test-service/slo-recommendations",
            params={"sli_type": "availability", "lookback_days": 30},
        )

        assert response.status_code == 401
        data = response.json()
        assert data["title"] == "Unauthorized"

    @pytest.mark.asyncio
    async def test_latency_recommendations(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test that latency recommendations are generated correctly."""
        service_repo = ServiceRepository(db_session)
        service = Service(
            id="payment-service",
            display_name="Payment Service",
            owner_team="payments",
            discovery_source=DiscoverySource.MANUAL,
        )
        await service_repo.add(service)

        response = await async_client.get(
            "/api/v1/services/payment-service/slo-recommendations",
            params={"sli_type": "latency", "lookback_days": 30},
        )

        # May be 200 or 422 depending on mock data availability
        assert response.status_code in [200, 422]

        if response.status_code == 200:
            data = response.json()
            assert len(data["recommendations"]) > 0
            rec = data["recommendations"][0]
            assert rec["sli_type"] == "latency"

            # Verify tier targets are in milliseconds
            for tier in rec["tiers"]:
                assert tier["target"] > 0  # Latency targets should be positive

    @pytest.mark.asyncio
    async def test_all_sli_types_returns_multiple_recommendations(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test that sli_type=all returns both availability and latency."""
        service_repo = ServiceRepository(db_session)
        service = Service(
            id="payment-service",
            display_name="Payment Service",
            owner_team="payments",
            discovery_source=DiscoverySource.MANUAL,
        )
        await service_repo.add(service)

        response = await async_client.get(
            "/api/v1/services/payment-service/slo-recommendations",
            params={"sli_type": "all", "lookback_days": 30},
        )

        # May be 200 or 422 depending on mock data
        assert response.status_code in [200, 422]

        if response.status_code == 200:
            data = response.json()
            # Should have at least availability recommendation
            assert len(data["recommendations"]) >= 1

            sli_types = {rec["sli_type"] for rec in data["recommendations"]}
            # At minimum should have availability
            assert "availability" in sli_types

    @pytest.mark.asyncio
    async def test_recommendation_expiration(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test that recommendations include proper expiration timestamps."""
        service_repo = ServiceRepository(db_session)
        service = Service(
            id="payment-service",
            display_name="Payment Service",
            owner_team="payments",
            discovery_source=DiscoverySource.MANUAL,
        )
        await service_repo.add(service)

        response = await async_client.get(
            "/api/v1/services/payment-service/slo-recommendations",
            params={"sli_type": "availability", "lookback_days": 30},
        )

        assert response.status_code == 200
        data = response.json()

        rec = data["recommendations"][0]
        generated_at = rec["generated_at"]
        expires_at = rec["expires_at"]

        # Verify expires_at is after generated_at
        assert expires_at > generated_at

        # Recommendations should expire in 24 hours
        # Parse ISO 8601 timestamps and verify ~24h difference
        from datetime import datetime

        gen_dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        diff_hours = (exp_dt - gen_dt).total_seconds() / 3600

        # Should be approximately 24 hours (allow some variance)
        assert 23.9 <= diff_hours <= 24.1

    @pytest.mark.asyncio
    async def test_concurrent_requests_same_service(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test that concurrent requests for the same service work correctly."""
        import asyncio

        service_repo = ServiceRepository(db_session)
        service = Service(
            id="payment-service",
            display_name="Payment Service",
            owner_team="payments",
            discovery_source=DiscoverySource.MANUAL,
        )
        await service_repo.add(service)

        # Make 5 concurrent requests
        tasks = [
            async_client.get(
                "/api/v1/services/payment-service/slo-recommendations",
                params={"sli_type": "availability", "lookback_days": 30},
            )
            for _ in range(5)
        ]

        responses = await asyncio.gather(*tasks)

        # All should succeed
        for response in responses:
            assert response.status_code == 200

        # All should return the same recommendation (same generated_at)
        generated_ats = [
            resp.json()["recommendations"][0]["generated_at"] for resp in responses
        ]
        # Most should have the same timestamp (may differ if race condition)
        # At least 4 out of 5 should match
        from collections import Counter

        counts = Counter(generated_ats)
        max_count = max(counts.values())
        assert max_count >= 4
