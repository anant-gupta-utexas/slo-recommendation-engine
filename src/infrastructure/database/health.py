"""Database health check module.

This module provides health check utilities for verifying database connectivity.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.infrastructure.database.config import get_engine


async def check_database_health(engine: AsyncEngine | None = None) -> bool:
    """Check database connectivity and basic functionality.

    Executes a simple SELECT 1 query to verify the database is reachable
    and responding to queries.

    Args:
        engine: AsyncEngine to use (defaults to global engine)

    Returns:
        True if database is healthy, False otherwise
    """
    if engine is None:
        try:
            engine = get_engine()
        except RuntimeError:
            # Database not initialized
            return False

    try:
        async with engine.connect() as conn:
            # Execute simple health check query
            result = await conn.execute(text("SELECT 1"))
            row = result.scalar()
            return row == 1
    except Exception:
        # Any exception means database is unhealthy
        return False


async def check_database_health_with_session(session: AsyncSession) -> bool:
    """Check database health using an existing session.

    This is useful for health checks within request handlers where
    a session is already available via dependency injection.

    Args:
        session: AsyncSession to use for health check

    Returns:
        True if database is healthy, False otherwise
    """
    try:
        result = await session.execute(text("SELECT 1"))
        row = result.scalar()
        return row == 1
    except Exception:
        return False
