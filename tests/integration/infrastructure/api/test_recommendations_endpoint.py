"""Integration tests for SLO recommendations API endpoint."""

import os
from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import uuid4

import bcrypt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.api.main import app
from src.infrastructure.database.config import (
    dispose_db,
    get_session_factory,
    init_db,
)
from src.infrastructure.database.models import ApiKeyModel, ServiceModel


@pytest.fixture(scope="function", autouse=True)
async def ensure_database():
    """Ensure database is initialized before each test.

    Re-initializes the connection pool for each test to avoid
    'Future attached to a different loop' errors when pytest-asyncio
    creates a new event loop per test function.
    Also resets the in-memory rate limiter to prevent cross-test interference.
    """
    # Set up environment
    test_db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://slo_user:slo_password_dev@localhost:5432/slo_engine",
    )
    os.environ["DATABASE_URL"] = test_db_url

    # Always re-initialize: each test gets a fresh event loop,
    # so the connection pool must be recreated to match.
    await dispose_db()
    await init_db()

    # Reset rate limiter state so tests don't interfere with each other
    for middleware in app.user_middleware:
        if (
            hasattr(middleware, "cls")
            and middleware.cls.__name__ == "RateLimitMiddleware"
        ):
            break
    # Walk the middleware stack to find the RateLimitMiddleware instance
    current = app.middleware_stack
    while current is not None:
        if hasattr(current, "buckets"):
            current.buckets.clear()
            break
        current = getattr(current, "app", None)

    yield

    await dispose_db()


@pytest.fixture
async def db_session(ensure_database) -> AsyncGenerator[AsyncSession, None]:
    """Provide a clean database session for each test."""
    # Use the global session factory (initialized by ensure_database fixture)
    session_factory = get_session_factory()

    async with session_factory() as session:
        # Clean all tables before each test
        await session.execute(text("DELETE FROM circular_dependency_alerts"))
        await session.execute(text("DELETE FROM service_dependencies"))
        await session.execute(text("DELETE FROM slo_recommendations"))
        await session.execute(text("DELETE FROM sli_aggregates"))
        await session.execute(text("DELETE FROM services"))
        await session.execute(text("DELETE FROM api_keys"))
        await session.commit()

        yield session


@pytest.fixture
async def test_api_key(db_session: AsyncSession) -> str:
    """Create a test API key and return the raw key."""
    raw_key = "test-api-key-recommendations-789"
    key_hash = bcrypt.hashpw(raw_key.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    api_key = ApiKeyModel(
        name="test-key-recommendations",
        key_hash=key_hash,
        created_by="test-user",
        description="Test API key for recommendations endpoint",
    )

    db_session.add(api_key)
    await db_session.commit()
    await db_session.refresh(api_key)

    return raw_key


@pytest.fixture
async def async_client(test_api_key: str) -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client for testing the API."""
    # Create ASGITransport for httpx to work with FastAPI
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {test_api_key}"},
    ) as client:
        yield client


@pytest.fixture
async def async_client_no_auth() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client without authentication."""
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.fixture
async def test_service(db_session: AsyncSession) -> ServiceModel:
    """Create a test service with telemetry data.

    Uses 'payment-service' which has seed data in MockPrometheusClient.
    """
    service = ServiceModel(
        id=uuid4(),
        service_id="payment-service",  # Has seed data with 30 days, 98% completeness
        team="payments",
        criticality="high",
        metadata_={"environment": "production"},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    db_session.add(service)
    await db_session.commit()
    await db_session.refresh(service)

    return service


# ============================================================================
# Tests: Success Cases
# ============================================================================


@pytest.mark.asyncio
async def test_get_recommendations_success_availability_only(
    async_client: AsyncClient, test_service: ServiceModel
):
    """Test successful recommendation retrieval for availability only."""
    # Act
    response = await async_client.get(
        f"/api/v1/services/{test_service.service_id}/slo-recommendations",
        params={"sli_type": "availability", "lookback_days": 30},
    )

    # Assert
    assert response.status_code == 200
    data = response.json()

    # Verify structure
    assert data["service_id"] == test_service.service_id
    assert "generated_at" in data
    assert "lookback_window" in data
    assert "recommendations" in data
    assert len(data["recommendations"]) >= 1

    # Verify availability recommendation
    avail_rec = next(
        (r for r in data["recommendations"] if r["sli_type"] == "availability"), None
    )
    assert avail_rec is not None
    assert avail_rec["metric"] == "error_rate"
    assert "conservative" in avail_rec["tiers"]
    assert "balanced" in avail_rec["tiers"]
    assert "aggressive" in avail_rec["tiers"]

    # Verify tier structure
    conservative = avail_rec["tiers"]["conservative"]
    assert conservative["level"] == "conservative"
    assert "target" in conservative
    assert "error_budget_monthly_minutes" in conservative
    assert "estimated_breach_probability" in conservative
    assert "confidence_interval" in conservative

    # Verify explanation
    assert "explanation" in avail_rec
    assert "summary" in avail_rec["explanation"]
    assert "feature_attribution" in avail_rec["explanation"]
    assert "dependency_impact" in avail_rec["explanation"]

    # Verify data quality
    assert "data_quality" in avail_rec
    assert "data_completeness" in avail_rec["data_quality"]
    assert "is_cold_start" in avail_rec["data_quality"]


@pytest.mark.asyncio
async def test_get_recommendations_success_latency_only(
    async_client: AsyncClient, test_service: ServiceModel
):
    """Test successful recommendation retrieval for latency only."""
    # Act
    response = await async_client.get(
        f"/api/v1/services/{test_service.service_id}/slo-recommendations",
        params={"sli_type": "latency", "lookback_days": 30},
    )

    # Assert
    assert response.status_code == 200
    data = response.json()

    # Verify latency recommendation
    latency_rec = next(
        (r for r in data["recommendations"] if r["sli_type"] == "latency"), None
    )
    assert latency_rec is not None
    assert latency_rec["metric"] == "p99_response_time_ms"
    assert "conservative" in latency_rec["tiers"]
    assert "balanced" in latency_rec["tiers"]
    assert "aggressive" in latency_rec["tiers"]

    # Verify tier structure (latency-specific)
    balanced = latency_rec["tiers"]["balanced"]
    assert balanced["level"] == "balanced"
    assert "target_ms" in balanced
    assert "percentile" in balanced
    assert "estimated_breach_probability" in balanced
    assert balanced["error_budget_monthly_minutes"] is None  # Not for latency


@pytest.mark.asyncio
async def test_get_recommendations_success_all_types(
    async_client: AsyncClient, test_service: ServiceModel
):
    """Test successful recommendation retrieval for all SLI types."""
    # Act
    response = await async_client.get(
        f"/api/v1/services/{test_service.service_id}/slo-recommendations",
        params={"sli_type": "all", "lookback_days": 30},
    )

    # Assert
    assert response.status_code == 200
    data = response.json()

    # Should have both availability and latency
    sli_types = {r["sli_type"] for r in data["recommendations"]}
    assert "availability" in sli_types
    assert "latency" in sli_types
    assert len(data["recommendations"]) == 2


@pytest.mark.asyncio
async def test_get_recommendations_force_regenerate(
    async_client: AsyncClient, test_service: ServiceModel
):
    """Test force regeneration of recommendations."""
    # Act
    response = await async_client.get(
        f"/api/v1/services/{test_service.service_id}/slo-recommendations",
        params={
            "sli_type": "availability",
            "lookback_days": 30,
            "force_regenerate": True,
        },
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["service_id"] == test_service.service_id
    assert len(data["recommendations"]) >= 1


@pytest.mark.asyncio
async def test_get_recommendations_different_lookback_windows(
    async_client: AsyncClient, test_service: ServiceModel
):
    """Test recommendations with different lookback windows.

    Note: payment-service has 30 days of data, so we test 7 and 30 days.
    Testing 90 days would result in 422 (insufficient data), which is expected behavior.
    """
    lookback_days_values = [7, 30]

    for lookback_days in lookback_days_values:
        response = await async_client.get(
            f"/api/v1/services/{test_service.service_id}/slo-recommendations",
            params={"sli_type": "availability", "lookback_days": lookback_days},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["service_id"] == test_service.service_id


# ============================================================================
# Tests: Error Cases
# ============================================================================


@pytest.mark.asyncio
async def test_get_recommendations_service_not_found(async_client: AsyncClient):
    """Test 404 when service doesn't exist."""
    # Act
    response = await async_client.get(
        "/api/v1/services/nonexistent-service/slo-recommendations",
        params={"sli_type": "availability", "lookback_days": 30},
    )

    # Assert
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "nonexistent-service" in data["detail"]


@pytest.mark.asyncio
async def test_get_recommendations_insufficient_data(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Test 422 when service has no telemetry data."""
    # Create service with no telemetry data (not in seed data)
    service_no_data = ServiceModel(
        id=uuid4(),
        service_id="service-no-telemetry-xyz",
        team="test-team",
        criticality="medium",
        metadata_={"environment": "staging"},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    db_session.add(service_no_data)
    await db_session.commit()
    await db_session.refresh(service_no_data)

    # Act
    response = await async_client.get(
        f"/api/v1/services/{service_no_data.service_id}/slo-recommendations",
        params={"sli_type": "availability", "lookback_days": 30},
    )

    # Assert
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data
    assert "Insufficient telemetry data" in data["detail"]


@pytest.mark.asyncio
async def test_get_recommendations_invalid_sli_type(
    async_client: AsyncClient, test_service: ServiceModel
):
    """Test 422 when sli_type is invalid."""
    # Act
    response = await async_client.get(
        f"/api/v1/services/{test_service.service_id}/slo-recommendations",
        params={"sli_type": "invalid-type", "lookback_days": 30},
    )

    # Assert
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_get_recommendations_invalid_lookback_days_too_low(
    async_client: AsyncClient, test_service: ServiceModel
):
    """Test 422 when lookback_days < 7."""
    # Act
    response = await async_client.get(
        f"/api/v1/services/{test_service.service_id}/slo-recommendations",
        params={"sli_type": "availability", "lookback_days": 3},
    )

    # Assert
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_get_recommendations_invalid_lookback_days_too_high(
    async_client: AsyncClient, test_service: ServiceModel
):
    """Test 422 when lookback_days > 365."""
    # Act
    response = await async_client.get(
        f"/api/v1/services/{test_service.service_id}/slo-recommendations",
        params={"sli_type": "availability", "lookback_days": 400},
    )

    # Assert
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_get_recommendations_missing_api_key(
    async_client_no_auth: AsyncClient, test_service: ServiceModel
):
    """Test 401 when API key is missing."""
    # Act
    response = await async_client_no_auth.get(
        f"/api/v1/services/{test_service.service_id}/slo-recommendations",
        params={"sli_type": "availability", "lookback_days": 30},
    )

    # Assert
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_get_recommendations_invalid_api_key(
    async_client_no_auth: AsyncClient, test_service: ServiceModel
):
    """Test 401 when API key is invalid."""
    # Act
    response = await async_client_no_auth.get(
        f"/api/v1/services/{test_service.service_id}/slo-recommendations",
        params={"sli_type": "availability", "lookback_days": 30},
        headers={"Authorization": "Bearer invalid-api-key-12345"},
    )

    # Assert
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
