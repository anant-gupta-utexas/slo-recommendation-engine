"""Database session management for FastAPI dependency injection.

This module provides FastAPI dependencies for obtaining database sessions.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.config import get_session_factory


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session for FastAPI dependency injection.

    This function is used as a FastAPI dependency to provide database
    sessions to route handlers. It ensures sessions are properly closed
    after request completion.

    Yields:
        AsyncSession instance

    Example:
        ```python
        @router.get("/services")
        async def list_services(
            session: AsyncSession = Depends(get_async_session)
        ):
            # Use session here
            pass
        ```

    Raises:
        RuntimeError: If database has not been initialized
    """
    session_factory = get_session_factory()

    async with session_factory() as session:
        try:
            yield session
            await session.commit()  # Auto-commit on success
        except Exception:
            await session.rollback()  # Auto-rollback on error
            raise
        finally:
            await session.close()  # Ensure session is closed
