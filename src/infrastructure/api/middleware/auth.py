"""Authentication middleware for API key verification.

Implements Bearer token authentication using bcrypt-hashed API keys.
Excludes health check endpoints from authentication requirements.
"""

import bcrypt
from datetime import datetime, timezone
from fastapi import Request, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import ApiKeyModel
from src.infrastructure.database.session import get_async_session


# Endpoints that don't require authentication
EXCLUDED_PATHS = {
    "/api/v1/health",
    "/api/v1/health/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
}


async def verify_api_key(request: Request) -> str:
    """Verify API key from Authorization header.

    Args:
        request: FastAPI request object

    Returns:
        API key name (client identifier) if valid

    Raises:
        HTTPException: 401 if API key is missing, invalid, or revoked
    """
    # Skip authentication for excluded paths
    if request.url.path in EXCLUDED_PATHS:
        return "health-check"

    # Extract Authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Parse Bearer token
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    provided_key = parts[1]

    # Verify against database - get session from generator
    async for session in get_async_session():
        api_key_name = await _verify_key_in_db(session, provided_key)
        # Attach client identifier to request state for logging/metrics
        request.state.client_id = api_key_name
        return api_key_name

    # Should never reach here due to exception raising in _verify_key_in_db
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or revoked API key",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _verify_key_in_db(session: AsyncSession, provided_key: str) -> str:
    """Verify provided key against bcrypt hashes in database.

    Args:
        session: Database session
        provided_key: Raw API key provided by client

    Returns:
        API key name if valid

    Raises:
        HTTPException: 401 if key is invalid or revoked
    """
    # Fetch all active API keys (small table, simple iteration acceptable for MVP)
    stmt = select(ApiKeyModel).where(ApiKeyModel.is_active == True)  # noqa: E712
    result = await session.execute(stmt)
    api_keys = result.scalars().all()

    # Check each key hash
    for api_key in api_keys:
        if bcrypt.checkpw(
            provided_key.encode("utf-8"), api_key.key_hash.encode("utf-8")
        ):
            # Valid key found - update last_used_at
            await _update_last_used(session, api_key.id)
            return api_key.name

    # No matching key found
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or revoked API key",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _update_last_used(session: AsyncSession, api_key_id: str) -> None:
    """Update last_used_at timestamp for API key.

    Args:
        session: Database session
        api_key_id: UUID of the API key
    """
    stmt = (
        update(ApiKeyModel)
        .where(ApiKeyModel.id == api_key_id)
        .values(last_used_at=datetime.now(timezone.utc))
    )
    await session.execute(stmt)
    # No explicit commit: the session generator's auto-commit handles this
