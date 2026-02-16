"""Redis health check utilities.

Provides health check functionality for Redis connectivity.
"""

import redis.asyncio as aioredis

from src.infrastructure.config import get_settings


async def check_redis_health() -> bool:
    """Check Redis connectivity.

    Attempts to ping Redis server to verify connectivity.

    Returns:
        True if Redis is healthy, False otherwise
    """
    settings = get_settings()
    try:
        # Create Redis client
        redis_client = aioredis.from_url(
            settings.redis.url,
            encoding="utf-8",
            decode_responses=True,
        )

        # Ping Redis
        result = await redis_client.ping()

        # Close connection
        await redis_client.aclose()

        return result is True

    except Exception:
        return False
