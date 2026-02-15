"""Circular dependency alert repository interface module.

This module defines the abstract interface for CircularDependencyAlert operations.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from src.domain.entities.circular_dependency_alert import (
        AlertStatus,
        CircularDependencyAlert,
    )


class CircularDependencyAlertRepositoryInterface(ABC):
    """Repository interface for CircularDependencyAlert operations.

    This interface defines the contract for persisting and retrieving
    circular dependency alerts. Implementations should handle database-specific
    details including deduplication of cycle paths.
    """

    @abstractmethod
    async def get_by_id(self, alert_id: UUID) -> "CircularDependencyAlert | None":
        """Get alert by UUID.

        Args:
            alert_id: Internal UUID of the alert

        Returns:
            CircularDependencyAlert entity if found, None otherwise
        """
        pass

    @abstractmethod
    async def create(
        self, alert: "CircularDependencyAlert"
    ) -> "CircularDependencyAlert":
        """Create a new circular dependency alert.

        Args:
            alert: CircularDependencyAlert entity to create

        Returns:
            Created CircularDependencyAlert entity

        Raises:
            ValueError: If alert with same cycle_path already exists
        """
        pass

    @abstractmethod
    async def list_by_status(
        self, status: "AlertStatus", skip: int = 0, limit: int = 100
    ) -> list["CircularDependencyAlert"]:
        """List alerts by status with pagination.

        Args:
            status: Alert status to filter by
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of CircularDependencyAlert entities matching the status
        """
        pass

    @abstractmethod
    async def list_all(
        self, skip: int = 0, limit: int = 100
    ) -> list["CircularDependencyAlert"]:
        """List all alerts with pagination.

        Args:
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of all CircularDependencyAlert entities
        """
        pass

    @abstractmethod
    async def update(
        self, alert: "CircularDependencyAlert"
    ) -> "CircularDependencyAlert":
        """Update existing alert.

        Args:
            alert: CircularDependencyAlert entity with updated fields

        Returns:
            Updated CircularDependencyAlert entity

        Raises:
            ValueError: If alert does not exist
        """
        pass

    @abstractmethod
    async def exists_for_cycle(self, cycle_path: list[str]) -> bool:
        """Check if an alert already exists for a given cycle path.

        This method should normalize the cycle path before checking
        (e.g., handle different rotations of the same cycle).

        Args:
            cycle_path: List of service_ids forming the cycle

        Returns:
            True if alert exists for this cycle, False otherwise
        """
        pass
