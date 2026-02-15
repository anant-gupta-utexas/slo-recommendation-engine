"""Circular dependency alert repository implementation using PostgreSQL.

This module implements the CircularDependencyAlertRepositoryInterface using
SQLAlchemy with JSONB operations for cycle path handling.
"""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.circular_dependency_alert import (
    AlertStatus,
    CircularDependencyAlert,
)
from src.domain.repositories.circular_dependency_alert_repository import (
    CircularDependencyAlertRepositoryInterface,
)
from src.infrastructure.database.models import CircularDependencyAlertModel


class CircularDependencyAlertRepository(
    CircularDependencyAlertRepositoryInterface
):
    """PostgreSQL implementation of CircularDependencyAlertRepositoryInterface.

    This repository handles mapping between domain CircularDependencyAlert
    entities and CircularDependencyAlertModel SQLAlchemy models.
    """

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self._session = session

    async def get_by_id(self, alert_id: UUID) -> CircularDependencyAlert | None:
        """Get alert by UUID.

        Args:
            alert_id: Internal UUID of the alert

        Returns:
            CircularDependencyAlert entity if found, None otherwise
        """
        stmt = select(CircularDependencyAlertModel).where(
            CircularDependencyAlertModel.id == alert_id
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        return self._to_entity(model) if model else None

    async def create(
        self, alert: CircularDependencyAlert
    ) -> CircularDependencyAlert:
        """Create a new circular dependency alert.

        Args:
            alert: CircularDependencyAlert entity to create

        Returns:
            Created CircularDependencyAlert entity

        Raises:
            ValueError: If alert with same cycle_path already exists
        """
        model = self._to_model(alert)
        self._session.add(model)

        try:
            await self._session.flush()  # Flush to catch unique constraint violations
            await self._session.refresh(model)  # Refresh to get server-generated values
        except IntegrityError as e:
            if "uq_cycle_path" in str(e.orig):
                raise ValueError(
                    f"Alert with cycle_path {alert.cycle_path} already exists"
                )
            raise

        return self._to_entity(model)

    async def list_by_status(
        self, status: AlertStatus, skip: int = 0, limit: int = 100
    ) -> list[CircularDependencyAlert]:
        """List alerts by status with pagination.

        Args:
            status: Alert status to filter by
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of CircularDependencyAlert entities matching the status
        """
        stmt = (
            select(CircularDependencyAlertModel)
            .where(CircularDependencyAlertModel.status == status.value)
            .order_by(CircularDependencyAlertModel.detected_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [self._to_entity(model) for model in models]

    async def list_all(
        self, skip: int = 0, limit: int = 100
    ) -> list[CircularDependencyAlert]:
        """List all alerts with pagination.

        Args:
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of all CircularDependencyAlert entities
        """
        stmt = (
            select(CircularDependencyAlertModel)
            .order_by(CircularDependencyAlertModel.detected_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [self._to_entity(model) for model in models]

    async def update(
        self, alert: CircularDependencyAlert
    ) -> CircularDependencyAlert:
        """Update existing alert.

        Args:
            alert: CircularDependencyAlert entity with updated fields

        Returns:
            Updated CircularDependencyAlert entity

        Raises:
            ValueError: If alert does not exist
        """
        # Check if alert exists
        existing = await self.get_by_id(alert.id)
        if not existing:
            raise ValueError(f"Alert with id '{alert.id}' does not exist")

        # Update using SQLAlchemy update statement
        stmt = (
            update(CircularDependencyAlertModel)
            .where(CircularDependencyAlertModel.id == alert.id)
            .values(
                cycle_path=alert.cycle_path,
                status=alert.status.value,
                acknowledged_by=alert.acknowledged_by,
                resolution_notes=alert.resolution_notes,
            )
            .returning(CircularDependencyAlertModel)
        )

        result = await self._session.execute(stmt)
        model = result.scalar_one()

        return self._to_entity(model)

    async def exists_for_cycle(self, cycle_path: list[str]) -> bool:
        """Check if an alert already exists for a given cycle path.

        This method checks for exact JSONB match using the unique constraint.
        PostgreSQL JSONB equality handles array element order, so the cycle_path
        must match exactly (no rotation normalization).

        Args:
            cycle_path: List of service_ids forming the cycle

        Returns:
            True if alert exists for this cycle, False otherwise
        """
        stmt = select(CircularDependencyAlertModel).where(
            CircularDependencyAlertModel.cycle_path == cycle_path
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        return model is not None

    def _to_entity(
        self, model: CircularDependencyAlertModel
    ) -> CircularDependencyAlert:
        """Convert SQLAlchemy model to domain entity.

        Args:
            model: CircularDependencyAlertModel instance

        Returns:
            CircularDependencyAlert domain entity
        """
        return CircularDependencyAlert(
            id=model.id,
            cycle_path=model.cycle_path,
            status=AlertStatus(model.status),
            acknowledged_by=model.acknowledged_by,
            resolution_notes=model.resolution_notes,
            detected_at=model.detected_at,
        )

    def _to_model(
        self, entity: CircularDependencyAlert
    ) -> CircularDependencyAlertModel:
        """Convert domain entity to SQLAlchemy model.

        Args:
            entity: CircularDependencyAlert domain entity

        Returns:
            CircularDependencyAlertModel instance
        """
        return CircularDependencyAlertModel(
            id=entity.id,
            cycle_path=entity.cycle_path,
            status=entity.status.value,
            acknowledged_by=entity.acknowledged_by,
            resolution_notes=entity.resolution_notes,
            detected_at=entity.detected_at,
        )
