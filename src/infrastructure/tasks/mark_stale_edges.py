"""Scheduled task for marking stale dependency edges.

This task identifies edges that haven't been observed recently and marks
them as stale. Stale edges can be filtered out from query results.
"""

import logging

from src.infrastructure.config.settings import get_settings
from src.infrastructure.database.config import get_session_factory
from src.infrastructure.database.repositories.dependency_repository import (
    DependencyRepository,
)

logger = logging.getLogger(__name__)


async def mark_stale_edges_task() -> None:
    """Scheduled task to mark stale dependency edges.

    Marks edges as stale if they haven't been observed within the configured
    threshold (default: 7 days). Uses a global threshold for all discovery sources.

    Errors are logged but not raised to prevent scheduler from stopping.
    """
    logger.info("Starting stale edge detection task")

    try:
        settings = get_settings()
        threshold_hours = settings.background_tasks.stale_edge_threshold_hours

        logger.info(
            "Marking edges as stale",
            threshold_hours=threshold_hours,
        )

        # Initialize repository and mark stale edges
        session_factory = get_session_factory()
        async with session_factory() as session:
            dependency_repo = DependencyRepository(session)

            # Mark edges that haven't been observed within threshold hours
            updated_count = await dependency_repo.mark_stale_edges(
                staleness_threshold_hours=threshold_hours
            )

            await session.commit()

            logger.info(
                "Stale edge detection completed",
                edges_marked_stale=updated_count,
                threshold_hours=threshold_hours,
            )

    except Exception as e:
        # Log error but don't raise to keep scheduler running
        logger.exception(
            "Unexpected error during stale edge detection",
            error=str(e),
        )

    logger.info("Stale edge detection task completed")
