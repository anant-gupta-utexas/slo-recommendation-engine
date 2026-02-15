"""Service repository interface module.

This module defines the abstract interface for Service entity operations.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from src.domain.entities.service import Service


class ServiceRepositoryInterface(ABC):
    """Repository interface for Service entity operations.

    This interface defines the contract for persisting and retrieving
    Service entities. Implementations should handle database-specific
    details while maintaining these method signatures.
    """

    @abstractmethod
    async def get_by_id(self, service_id: UUID) -> "Service | None":
        """Get service by internal UUID.

        Args:
            service_id: Internal UUID of the service

        Returns:
            Service entity if found, None otherwise
        """
        pass

    @abstractmethod
    async def get_by_service_id(self, service_id: str) -> "Service | None":
        """Get service by business identifier (service_id string).

        Args:
            service_id: Business identifier (e.g., "checkout-service")

        Returns:
            Service entity if found, None otherwise
        """
        pass

    @abstractmethod
    async def list_all(self, skip: int = 0, limit: int = 100) -> list["Service"]:
        """List all services with pagination.

        Args:
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of Service entities
        """
        pass

    @abstractmethod
    async def create(self, service: "Service") -> "Service":
        """Create a new service.

        Args:
            service: Service entity to create

        Returns:
            Created Service entity with populated audit fields

        Raises:
            ValueError: If service with same service_id already exists
        """
        pass

    @abstractmethod
    async def bulk_upsert(self, services: list["Service"]) -> list["Service"]:
        """Bulk upsert services.

        Inserts new services or updates existing ones based on service_id.
        Uses ON CONFLICT clause for idempotent writes.

        Args:
            services: List of Service entities to upsert

        Returns:
            List of upserted Service entities with updated audit fields
        """
        pass

    @abstractmethod
    async def update(self, service: "Service") -> "Service":
        """Update existing service.

        Args:
            service: Service entity with updated fields

        Returns:
            Updated Service entity

        Raises:
            ValueError: If service does not exist
        """
        pass
