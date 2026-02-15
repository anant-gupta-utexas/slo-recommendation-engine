"""Database configuration module.

This module provides database engine and session configuration
for the application with connection pooling and async support.
"""

import os

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from src.infrastructure.database.models import Base


def get_database_url() -> str:
    """Get database URL from environment.

    Returns:
        PostgreSQL connection URL

    Raises:
        ValueError: If DATABASE_URL environment variable is not set
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError(
            "DATABASE_URL environment variable is required. "
            "Example: postgresql+asyncpg://user:pass@localhost:5432/dbname"
        )
    return database_url


def create_async_db_engine(
    database_url: str | None = None,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    echo: bool = False,
) -> AsyncEngine:
    """Create async SQLAlchemy engine with connection pooling.

    Args:
        database_url: PostgreSQL connection URL (defaults to DATABASE_URL env var)
        pool_size: Connection pool size (defaults to DB_POOL_SIZE env or 20)
        max_overflow: Burst capacity (defaults to DB_MAX_OVERFLOW env or 10)
        echo: Enable SQL query logging (defaults to False)

    Returns:
        AsyncEngine instance configured with connection pooling

    Raises:
        ValueError: If database_url is None and DATABASE_URL env var is not set
    """
    if database_url is None:
        database_url = get_database_url()

    if pool_size is None:
        pool_size = int(os.getenv("DB_POOL_SIZE", "20"))

    if max_overflow is None:
        max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))

    engine = create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,  # Validate connections before use
        pool_recycle=3600,  # Recycle connections every hour
        echo=echo,  # Set to True for SQL query logging (development only)
    )

    return engine


def create_async_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker:
    """Create async session factory.

    Args:
        engine: AsyncEngine instance

    Returns:
        Async session factory (sessionmaker)
    """
    return async_sessionmaker(
        engine,
        expire_on_commit=False,  # Don't expire objects after commit
        autoflush=False,  # Manual flush control
        autocommit=False,  # Manual commit control
    )


# Global engine and session factory (initialized by application startup)
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker | None = None


async def init_db(
    database_url: str | None = None,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    echo: bool = False,
) -> None:
    """Initialize global database engine and session factory.

    This should be called once during application startup.

    Args:
        database_url: PostgreSQL connection URL (defaults to DATABASE_URL env var)
        pool_size: Connection pool size (defaults to DB_POOL_SIZE env or 20)
        max_overflow: Burst capacity (defaults to DB_MAX_OVERFLOW env or 10)
        echo: Enable SQL query logging (defaults to False)
    """
    global _engine, _async_session_factory

    _engine = create_async_db_engine(
        database_url=database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        echo=echo,
    )
    _async_session_factory = create_async_session_factory(_engine)


async def dispose_db() -> None:
    """Dispose database engine and close all connections.

    This should be called during application shutdown.
    """
    global _engine

    if _engine:
        await _engine.dispose()
        _engine = None


def get_engine() -> AsyncEngine:
    """Get global database engine.

    Returns:
        AsyncEngine instance

    Raises:
        RuntimeError: If database has not been initialized
    """
    if _engine is None:
        raise RuntimeError(
            "Database engine not initialized. Call init_db() first."
        )
    return _engine


def get_session_factory() -> async_sessionmaker:
    """Get global async session factory.

    Returns:
        Async session factory

    Raises:
        RuntimeError: If database has not been initialized
    """
    if _async_session_factory is None:
        raise RuntimeError(
            "Database session factory not initialized. Call init_db() first."
        )
    return _async_session_factory
