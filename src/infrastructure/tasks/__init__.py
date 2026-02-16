"""Background tasks and scheduled jobs.

This package contains the APScheduler-based task scheduling infrastructure
for the SLO engine, including OTel graph ingestion and stale edge detection.
"""

from src.infrastructure.tasks.scheduler import get_scheduler, shutdown_scheduler

__all__ = [
    "get_scheduler",
    "shutdown_scheduler",
]
