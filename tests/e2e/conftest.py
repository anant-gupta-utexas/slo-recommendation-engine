"""E2E test fixtures for API layer testing."""

import os
from typing import AsyncGenerator

import bcrypt
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.api.main import app
from src.infrastructure.database.config import init_db, dispose_db, get_session_factory
from src.infrastructure.database.models import ApiKeyModel


# Module-level flag to track if DB has been initialized
_db_initialized = False


@pytest_asyncio.fixture(scope="function", autouse=True)
async def ensure_database():
    """Ensure database is initialized before each test."""
    global _db_initialized

    # Set up environment
    test_db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://slo_user:slo_password_dev@localhost:5432/slo_engine",
    )
    os.environ["DATABASE_URL"] = test_db_url

    # Initialize database if not already done
    if not _db_initialized:
        await init_db()
        _db_initialized = True

    yield

    # Note: We don't dispose here to avoid reinitializing for each test


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a clean database session for each test."""
    # Use the global session factory
    session_factory = get_session_factory()

    async with session_factory() as session:
        # Clean all tables before each test
        await session.execute(text("DELETE FROM circular_dependency_alerts"))
        await session.execute(text("DELETE FROM service_dependencies"))
        await session.execute(text("DELETE FROM services"))
        await session.execute(text("DELETE FROM api_keys"))
        await session.commit()

        yield session


@pytest_asyncio.fixture
async def test_api_key(db_session: AsyncSession) -> str:
    """Create a test API key and return the raw key."""
    raw_key = "test-api-key-123456789"
    key_hash = bcrypt.hashpw(raw_key.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    api_key = ApiKeyModel(
        name="test-key",
        key_hash=key_hash,
        created_by="test-user",
        description="Test API key for E2E tests",
    )

    db_session.add(api_key)
    await db_session.commit()
    await db_session.refresh(api_key)

    return raw_key


@pytest_asyncio.fixture
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


@pytest_asyncio.fixture
async def async_client_no_auth() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client without authentication."""
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        yield client
