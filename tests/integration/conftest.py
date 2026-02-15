"""Integration test fixtures for database testing.

This module provides PostgreSQL testcontainer fixtures and database
session management for integration tests.
"""

import asyncio
import os
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer

from src.infrastructure.database.config import create_async_session_factory
from src.infrastructure.database.models import Base


# Use session scope for postgres container but function scope for async fixtures
# This avoids event loop issues with pytest-asyncio
_postgres_container_cache = {}


@pytest.fixture(scope="session")
def postgres_container():
    """Start PostgreSQL testcontainer for the test session.

    Yields:
        PostgresContainer instance with running PostgreSQL database
    """
    if "container" not in _postgres_container_cache:
        container = PostgresContainer("postgres:16-alpine")
        container.start()
        _postgres_container_cache["container"] = container

    yield _postgres_container_cache["container"]


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    """Get database URL from testcontainer.

    Args:
        postgres_container: Running PostgreSQL container

    Returns:
        PostgreSQL connection URL for asyncpg
    """
    # Get JDBC URL and convert to asyncpg format
    jdbc_url = postgres_container.get_connection_url()
    # Replace psycopg2 driver with asyncpg
    asyncpg_url = jdbc_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    # Also handle case where it's just postgresql://
    asyncpg_url = asyncpg_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return asyncpg_url


# Engine is created fresh for each test to avoid event loop issues
@pytest.fixture
async def db_engine(database_url: str) -> AsyncGenerator[AsyncEngine, None]:
    """Create async database engine for each test.

    Args:
        database_url: PostgreSQL connection URL

    Yields:
        AsyncEngine instance
    """
    engine = create_async_engine(
        database_url,
        echo=False,  # Set to True for SQL query debugging
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0,
    )

    # Create all tables using SQLAlchemy metadata (idempotent)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Create async database session for each test.

    This fixture provides a clean database session for each test.
    Changes are committed by default (not rolled back).

    Args:
        db_engine: Database engine

    Yields:
        AsyncSession instance
    """
    session_factory = create_async_session_factory(db_engine)

    async with session_factory() as session:
        yield session


@pytest.fixture(autouse=True)
async def clean_db(db_session: AsyncSession) -> None:
    """Clean all tables before each test.

    This fixture ensures each test starts with a clean database state.
    Uses autouse=True to run automatically before every test.

    Args:
        db_session: Database session
    """
    # Delete all data from tables in reverse order of dependencies
    await db_session.execute(text("DELETE FROM circular_dependency_alerts"))
    await db_session.execute(text("DELETE FROM service_dependencies"))
    await db_session.execute(text("DELETE FROM services"))
    await db_session.commit()
