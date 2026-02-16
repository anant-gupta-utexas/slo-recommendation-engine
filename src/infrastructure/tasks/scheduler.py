"""Background task scheduler using APScheduler.

This module configures and manages scheduled background tasks for:
- OTel Service Graph ingestion (every 15 minutes)
- Stale edge detection (daily)
- Batch SLO recommendation computation (every 24 hours)

Uses APScheduler's AsyncIOScheduler for in-process scheduling.
For production deployments with multiple replicas, consider migrating to Celery.
"""

from typing import Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.infrastructure.config.settings import get_settings

logger = structlog.get_logger(__name__)

# Global scheduler instance
_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the global scheduler instance.

    Returns:
        AsyncIOScheduler instance configured for background tasks

    Raises:
        RuntimeError: If scheduler initialization fails
    """
    global _scheduler
    if _scheduler is None:
        _scheduler = _create_scheduler()
    return _scheduler


def _create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler instance.

    Returns:
        Configured AsyncIOScheduler
    """
    settings = get_settings()

    # Create scheduler with memory-based job store (MVP)
    # For production with multiple replicas, use PostgreSQL job store
    scheduler = AsyncIOScheduler(
        timezone="UTC",
        job_defaults={
            "coalesce": True,  # Combine missed runs into one
            "max_instances": 1,  # Prevent concurrent runs of the same job
            "misfire_grace_time": 300,  # Allow 5 min grace for misfires
        },
    )

    # Register scheduled jobs
    _register_jobs(scheduler, settings)

    logger.info("Background task scheduler created")
    return scheduler


def _register_jobs(scheduler: AsyncIOScheduler, settings: Any) -> None:
    """Register all scheduled jobs.

    Args:
        scheduler: APScheduler instance
        settings: Application settings
    """
    # Import job functions here to avoid circular imports
    from src.infrastructure.tasks.ingest_otel_graph import ingest_otel_service_graph
    from src.infrastructure.tasks.mark_stale_edges import mark_stale_edges_task
    from src.infrastructure.tasks.batch_recommendations import (
        batch_compute_recommendations,
    )

    # OTel Service Graph ingestion (every N minutes, configurable)
    interval_minutes = settings.background_tasks.otel_graph_ingest_interval_minutes
    scheduler.add_job(
        ingest_otel_service_graph,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="ingest_otel_service_graph",
        name="Ingest OTel Service Graph from Prometheus",
        replace_existing=True,
    )
    logger.info(
        "Registered OTel ingestion job",
        interval_minutes=interval_minutes,
    )

    # Stale edge detection (daily at 2 AM UTC)
    scheduler.add_job(
        mark_stale_edges_task,
        trigger=CronTrigger(hour=2, minute=0),
        id="mark_stale_edges",
        name="Mark stale dependency edges",
        replace_existing=True,
    )
    logger.info("Registered stale edge detection job", schedule="daily at 02:00 UTC")

    # Batch SLO recommendation computation (every N hours, configurable)
    interval_hours = settings.background_tasks.slo_batch_interval_hours
    scheduler.add_job(
        batch_compute_recommendations,
        trigger=IntervalTrigger(hours=interval_hours),
        id="batch_compute_recommendations",
        name="Batch compute SLO recommendations for all services",
        replace_existing=True,
    )
    logger.info(
        "Registered batch SLO recommendation job",
        interval_hours=interval_hours,
    )


async def start_scheduler() -> None:
    """Start the background task scheduler.

    This should be called during application startup.
    Jobs will begin executing according to their schedules.
    """
    scheduler = get_scheduler()

    if scheduler.running:
        logger.warning("Scheduler already running, skipping start")
        return

    scheduler.start()
    logger.info("Background task scheduler started")


async def shutdown_scheduler() -> None:
    """Gracefully shutdown the background task scheduler.

    This should be called during application shutdown.
    Waits for currently executing jobs to complete (up to 30 seconds).
    """
    global _scheduler

    if _scheduler is None:
        logger.warning("Scheduler not initialized, skipping shutdown")
        return

    if not _scheduler.running:
        logger.warning("Scheduler not running, skipping shutdown")
        return

    logger.info("Shutting down background task scheduler...")

    # Shutdown with wait (give jobs up to 30 seconds to complete)
    _scheduler.shutdown(wait=True)

    logger.info("Background task scheduler shut down successfully")
    _scheduler = None


def trigger_job_now(job_id: str) -> None:
    """Manually trigger a scheduled job immediately.

    Useful for testing and manual operations.

    Args:
        job_id: ID of the job to trigger (e.g., "ingest_otel_service_graph")

    Raises:
        ValueError: If job_id not found
    """
    scheduler = get_scheduler()
    job = scheduler.get_job(job_id)

    if job is None:
        raise ValueError(f"Job not found: {job_id}")

    # Trigger the job immediately (doesn't wait for completion)
    job.modify(next_run_time=None)  # type: ignore
    logger.info("Manually triggered job", job_id=job_id)
