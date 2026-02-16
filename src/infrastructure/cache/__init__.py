"""Cache infrastructure module.

Provides Redis caching and health check functionality.
"""

from src.infrastructure.cache.health import check_redis_health

__all__ = ["check_redis_health"]
