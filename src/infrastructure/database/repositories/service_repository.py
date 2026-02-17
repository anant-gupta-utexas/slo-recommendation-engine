"""Service repository implementation using PostgreSQL.

This module implements the ServiceRepositoryInterface using SQLAlchemy
and AsyncPG for PostgreSQL database operations.
"""

from typing import Sequence
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.constraint_analysis import ServiceType
from src.domain.entities.service import Criticality, Service
from src.domain.repositories.service_repository import ServiceRepositoryInterface
from src.infrastructure.database.models import ServiceModel


class ServiceRepository(ServiceRepositoryInterface):
    """PostgreSQL implementation of ServiceRepositoryInterface.

    This repository handles mapping between domain Service entities
    and ServiceModel SQLAlchemy models.
    """

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self._session = session

    async def get_by_id(self, service_id: UUID) -> Service | None:
        """Get service by internal UUID.

        Args:
            service_id: Internal UUID of the service

        Returns:
            Service entity if found, None otherwise
        """
        stmt = select(ServiceModel).where(ServiceModel.id == service_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        return self._to_entity(model) if model else None

    async def get_by_service_id(self, service_id: str) -> Service | None:
        """Get service by business identifier (service_id string).

        Args:
            service_id: Business identifier (e.g., "checkout-service")

        Returns:
            Service entity if found, None otherwise
        """
        stmt = select(ServiceModel).where(ServiceModel.service_id == service_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        return self._to_entity(model) if model else None

    async def list_all(self, skip: int = 0, limit: int = 100) -> list[Service]:
        """List all services with pagination.

        Args:
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of Service entities
        """
        stmt = (
            select(ServiceModel)
            .order_by(ServiceModel.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [self._to_entity(model) for model in models]

    async def create(self, service: Service) -> Service:
        """Create a new service.

        Args:
            service: Service entity to create

        Returns:
            Created Service entity with populated audit fields

        Raises:
            ValueError: If service with same service_id already exists
        """
        # Check if service_id already exists
        existing = await self.get_by_service_id(service.service_id)
        if existing:
            raise ValueError(
                f"Service with service_id '{service.service_id}' already exists"
            )

        model = self._to_model(service)
        self._session.add(model)
        await self._session.flush()  # Flush to get generated ID and timestamps
        await self._session.refresh(model)  # Refresh to get all server-generated values

        return self._to_entity(model)

    async def bulk_upsert(self, services: list[Service]) -> list[Service]:
        """Bulk upsert services.

        Inserts new services or updates existing ones based on service_id.
        Uses ON CONFLICT clause for idempotent writes.

        Args:
            services: List of Service entities to upsert

        Returns:
            List of upserted Service entities with updated audit fields
        """
        if not services:
            return []

        # Convert services to dictionaries for bulk insert
        values = [self._to_dict(service) for service in services]

        # PostgreSQL INSERT ... ON CONFLICT ... DO UPDATE
        stmt = pg_insert(ServiceModel).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["service_id"],
            set_={
                # Both keys and values use database column names
                "metadata": stmt.excluded.metadata,
                "criticality": stmt.excluded.criticality,
                "team": stmt.excluded.team,
                "discovered": stmt.excluded.discovered,
                "service_type": stmt.excluded.service_type,
                "published_sla": stmt.excluded.published_sla,
                "updated_at": stmt.excluded.updated_at,
            },
        ).returning(ServiceModel)

        result = await self._session.execute(stmt)
        models: Sequence[ServiceModel] = result.scalars().all()

        return [self._to_entity(model) for model in models]

    async def update(self, service: Service) -> Service:
        """Update existing service.

        Args:
            service: Service entity with updated fields

        Returns:
            Updated Service entity

        Raises:
            ValueError: If service does not exist
        """
        # Check if service exists
        existing = await self.get_by_id(service.id)
        if not existing:
            raise ValueError(f"Service with id '{service.id}' does not exist")

        # Update using SQLAlchemy update statement
        # Use column references to avoid metadata attribute conflict
        stmt = (
            update(ServiceModel)
            .where(ServiceModel.id == service.id)
            .values(
                {
                    ServiceModel.service_id: service.service_id,
                    ServiceModel.metadata_: service.metadata,
                    ServiceModel.criticality: service.criticality.value,
                    ServiceModel.team: service.team,
                    ServiceModel.discovered: service.discovered,
                    ServiceModel.service_type: service.service_type.value,
                    ServiceModel.published_sla: service.published_sla,
                    ServiceModel.updated_at: service.updated_at,
                }
            )
            .returning(ServiceModel)
        )

        result = await self._session.execute(stmt)
        model = result.scalar_one()

        return self._to_entity(model)

    async def get_external_services(self) -> list[Service]:
        """Get all services with service_type='external'.

        Returns:
            List of Service entities with service_type=ServiceType.EXTERNAL
        """
        stmt = select(ServiceModel).where(ServiceModel.service_type == "external")
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [self._to_entity(model) for model in models]

    def _to_entity(self, model: ServiceModel) -> Service:
        """Convert SQLAlchemy model to domain entity.

        Args:
            model: ServiceModel instance

        Returns:
            Service domain entity
        """
        return Service(
            id=model.id,
            service_id=model.service_id,
            metadata=model.metadata_,
            criticality=Criticality(model.criticality),
            team=model.team,
            discovered=model.discovered,
            service_type=ServiceType(model.service_type),
            published_sla=float(model.published_sla) if model.published_sla is not None else None,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: Service) -> ServiceModel:
        """Convert domain entity to SQLAlchemy model.

        Args:
            entity: Service domain entity

        Returns:
            ServiceModel instance
        """
        return ServiceModel(
            id=entity.id,
            service_id=entity.service_id,
            metadata_=entity.metadata,
            criticality=entity.criticality.value,
            team=entity.team,
            discovered=entity.discovered,
            service_type=entity.service_type.value,
            published_sla=entity.published_sla,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _to_dict(self, entity: Service) -> dict:
        """Convert domain entity to dictionary for bulk operations.

        Args:
            entity: Service domain entity

        Returns:
            Dictionary representation suitable for SQLAlchemy insert
        """
        return {
            "id": entity.id,
            "service_id": entity.service_id,
            "metadata_": entity.metadata,  # Use metadata_ to avoid SQLAlchemy conflict
            "criticality": entity.criticality.value,
            "team": entity.team,
            "discovered": entity.discovered,
            "service_type": entity.service_type.value,
            "published_sla": entity.published_sla,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
        }
