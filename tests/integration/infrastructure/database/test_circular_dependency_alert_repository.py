"""Integration tests for CircularDependencyAlertRepository.

This module tests the CircularDependencyAlertRepository implementation
against a real PostgreSQL database, including JSONB cycle path handling.
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.circular_dependency_alert import (
    AlertStatus,
    CircularDependencyAlert,
)
from src.infrastructure.database.repositories.circular_dependency_alert_repository import (
    CircularDependencyAlertRepository,
)


@pytest.mark.integration
class TestCircularDependencyAlertRepository:
    """Integration tests for CircularDependencyAlertRepository."""

    @pytest.fixture
    def repository(
        self, db_session: AsyncSession
    ) -> CircularDependencyAlertRepository:
        """Create CircularDependencyAlertRepository instance for testing.

        Args:
            db_session: Database session fixture

        Returns:
            CircularDependencyAlertRepository instance
        """
        return CircularDependencyAlertRepository(db_session)

    @pytest.fixture
    def sample_alert(self) -> CircularDependencyAlert:
        """Create a sample alert for testing.

        Returns:
            CircularDependencyAlert entity with test data
        """
        return CircularDependencyAlert(
            cycle_path=["service-a", "service-b", "service-c"],
            status=AlertStatus.OPEN,
        )

    async def test_create_alert(
        self,
        repository: CircularDependencyAlertRepository,
        sample_alert: CircularDependencyAlert,
    ):
        """Test creating a new circular dependency alert.

        Args:
            repository: CircularDependencyAlertRepository instance
            sample_alert: Sample alert entity
        """
        # Act
        created = await repository.create(sample_alert)

        # Assert
        assert created.id is not None
        assert created.cycle_path == ["service-a", "service-b", "service-c"]
        assert created.status == AlertStatus.OPEN
        assert created.detected_at is not None
        assert created.acknowledged_by is None
        assert created.resolution_notes is None

    async def test_create_duplicate_cycle_path_raises_error(
        self,
        repository: CircularDependencyAlertRepository,
        sample_alert: CircularDependencyAlert,
    ):
        """Test that creating an alert with duplicate cycle_path raises error.

        Args:
            repository: CircularDependencyAlertRepository instance
            sample_alert: Sample alert entity
        """
        # Arrange
        await repository.create(sample_alert)

        # Act & Assert
        duplicate_alert = CircularDependencyAlert(
            cycle_path=["service-a", "service-b", "service-c"],  # Same cycle
            status=AlertStatus.OPEN,
        )
        with pytest.raises(ValueError, match="already exists"):
            await repository.create(duplicate_alert)

    async def test_create_different_cycle_paths_allowed(
        self,
        repository: CircularDependencyAlertRepository,
    ):
        """Test that different cycle paths can coexist.

        Args:
            repository: CircularDependencyAlertRepository instance
        """
        # Arrange
        alert1 = CircularDependencyAlert(
            cycle_path=["service-a", "service-b"],
        )
        alert2 = CircularDependencyAlert(
            cycle_path=["service-x", "service-y"],
        )

        # Act
        created1 = await repository.create(alert1)
        created2 = await repository.create(alert2)

        # Assert
        assert created1.id != created2.id
        assert created1.cycle_path != created2.cycle_path

    async def test_get_by_id(
        self,
        repository: CircularDependencyAlertRepository,
        sample_alert: CircularDependencyAlert,
    ):
        """Test retrieving an alert by UUID.

        Args:
            repository: CircularDependencyAlertRepository instance
            sample_alert: Sample alert entity
        """
        # Arrange
        created = await repository.create(sample_alert)

        # Act
        retrieved = await repository.get_by_id(created.id)

        # Assert
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.cycle_path == created.cycle_path
        assert retrieved.status == created.status

    async def test_get_by_id_not_found(
        self, repository: CircularDependencyAlertRepository
    ):
        """Test that get_by_id returns None for non-existent alert.

        Args:
            repository: CircularDependencyAlertRepository instance
        """
        # Act
        result = await repository.get_by_id(uuid4())

        # Assert
        assert result is None

    async def test_list_by_status_open(
        self, repository: CircularDependencyAlertRepository
    ):
        """Test listing alerts by OPEN status.

        Args:
            repository: CircularDependencyAlertRepository instance
        """
        # Arrange - Create alerts with different statuses
        open_alert1 = CircularDependencyAlert(
            cycle_path=["service-a", "service-b"],
            status=AlertStatus.OPEN,
        )
        open_alert2 = CircularDependencyAlert(
            cycle_path=["service-c", "service-d"],
            status=AlertStatus.OPEN,
        )
        acknowledged_alert = CircularDependencyAlert(
            cycle_path=["service-e", "service-f"],
            status=AlertStatus.ACKNOWLEDGED,
        )

        await repository.create(open_alert1)
        await repository.create(open_alert2)
        await repository.create(acknowledged_alert)

        # Act
        result = await repository.list_by_status(AlertStatus.OPEN)

        # Assert
        assert len(result) == 2
        for alert in result:
            assert alert.status == AlertStatus.OPEN

    async def test_list_by_status_acknowledged(
        self, repository: CircularDependencyAlertRepository
    ):
        """Test listing alerts by ACKNOWLEDGED status.

        Args:
            repository: CircularDependencyAlertRepository instance
        """
        # Arrange
        open_alert = CircularDependencyAlert(
            cycle_path=["service-a", "service-b"],
            status=AlertStatus.OPEN,
        )
        acknowledged_alert = CircularDependencyAlert(
            cycle_path=["service-c", "service-d"],
            status=AlertStatus.ACKNOWLEDGED,
            acknowledged_by="user@example.com",
        )

        await repository.create(open_alert)
        await repository.create(acknowledged_alert)

        # Act
        result = await repository.list_by_status(AlertStatus.ACKNOWLEDGED)

        # Assert
        assert len(result) == 1
        assert result[0].status == AlertStatus.ACKNOWLEDGED
        assert result[0].acknowledged_by == "user@example.com"

    async def test_list_by_status_resolved(
        self, repository: CircularDependencyAlertRepository
    ):
        """Test listing alerts by RESOLVED status.

        Args:
            repository: CircularDependencyAlertRepository instance
        """
        # Arrange
        resolved_alert = CircularDependencyAlert(
            cycle_path=["service-a", "service-b"],
            status=AlertStatus.RESOLVED,
            resolution_notes="Fixed by removing dependency",
        )

        await repository.create(resolved_alert)

        # Act
        result = await repository.list_by_status(AlertStatus.RESOLVED)

        # Assert
        assert len(result) == 1
        assert result[0].status == AlertStatus.RESOLVED
        assert result[0].resolution_notes == "Fixed by removing dependency"

    async def test_list_by_status_pagination(
        self, repository: CircularDependencyAlertRepository
    ):
        """Test pagination in list_by_status.

        Args:
            repository: CircularDependencyAlertRepository instance
        """
        # Arrange - Create 5 open alerts
        for i in range(5):
            alert = CircularDependencyAlert(
                cycle_path=[f"service-{i}", f"service-{i+1}"],
                status=AlertStatus.OPEN,
            )
            await repository.create(alert)

        # Act - Get second page
        result = await repository.list_by_status(
            AlertStatus.OPEN, skip=2, limit=2
        )

        # Assert
        assert len(result) == 2

    async def test_list_all(self, repository: CircularDependencyAlertRepository):
        """Test listing all alerts.

        Args:
            repository: CircularDependencyAlertRepository instance
        """
        # Arrange - Create alerts with different statuses
        alerts = [
            CircularDependencyAlert(
                cycle_path=["service-a", "service-b"],
                status=AlertStatus.OPEN,
            ),
            CircularDependencyAlert(
                cycle_path=["service-c", "service-d"],
                status=AlertStatus.ACKNOWLEDGED,
            ),
            CircularDependencyAlert(
                cycle_path=["service-e", "service-f"],
                status=AlertStatus.RESOLVED,
            ),
        ]

        for alert in alerts:
            await repository.create(alert)

        # Act
        result = await repository.list_all()

        # Assert
        assert len(result) == 3
        statuses = {alert.status for alert in result}
        assert AlertStatus.OPEN in statuses
        assert AlertStatus.ACKNOWLEDGED in statuses
        assert AlertStatus.RESOLVED in statuses

    async def test_list_all_pagination(
        self, repository: CircularDependencyAlertRepository
    ):
        """Test pagination in list_all.

        Args:
            repository: CircularDependencyAlertRepository instance
        """
        # Arrange - Create 10 alerts
        for i in range(10):
            alert = CircularDependencyAlert(
                cycle_path=[f"service-{i}", f"service-{i+1}"],
            )
            await repository.create(alert)

        # Act - Get second page
        result = await repository.list_all(skip=5, limit=3)

        # Assert
        assert len(result) == 3

    async def test_update_alert_status(
        self,
        repository: CircularDependencyAlertRepository,
        sample_alert: CircularDependencyAlert,
    ):
        """Test updating an alert's status.

        Args:
            repository: CircularDependencyAlertRepository instance
            sample_alert: Sample alert entity
        """
        # Arrange
        created = await repository.create(sample_alert)

        # Modify the alert
        created.acknowledge("admin@example.com")

        # Act
        updated = await repository.update(created)

        # Assert
        assert updated.id == created.id
        assert updated.status == AlertStatus.ACKNOWLEDGED
        assert updated.acknowledged_by == "admin@example.com"

        # Verify in database
        retrieved = await repository.get_by_id(created.id)
        assert retrieved is not None
        assert retrieved.status == AlertStatus.ACKNOWLEDGED

    async def test_update_alert_resolution(
        self,
        repository: CircularDependencyAlertRepository,
        sample_alert: CircularDependencyAlert,
    ):
        """Test updating an alert to resolved status.

        Args:
            repository: CircularDependencyAlertRepository instance
            sample_alert: Sample alert entity
        """
        # Arrange
        created = await repository.create(sample_alert)

        # Resolve the alert
        created.resolve("Removed circular dependency by refactoring")

        # Act
        updated = await repository.update(created)

        # Assert
        assert updated.status == AlertStatus.RESOLVED
        assert updated.resolution_notes == "Removed circular dependency by refactoring"

    async def test_update_non_existent_alert_raises_error(
        self, repository: CircularDependencyAlertRepository
    ):
        """Test that updating a non-existent alert raises error.

        Args:
            repository: CircularDependencyAlertRepository instance
        """
        # Arrange
        non_existent_alert = CircularDependencyAlert(
            id=uuid4(),
            cycle_path=["service-a", "service-b"],
            status=AlertStatus.OPEN,
        )

        # Act & Assert
        with pytest.raises(ValueError, match="does not exist"):
            await repository.update(non_existent_alert)

    async def test_exists_for_cycle_true(
        self,
        repository: CircularDependencyAlertRepository,
        sample_alert: CircularDependencyAlert,
    ):
        """Test exists_for_cycle returns True for existing cycle.

        Args:
            repository: CircularDependencyAlertRepository instance
            sample_alert: Sample alert entity
        """
        # Arrange
        await repository.create(sample_alert)

        # Act
        exists = await repository.exists_for_cycle(
            ["service-a", "service-b", "service-c"]
        )

        # Assert
        assert exists is True

    async def test_exists_for_cycle_false(
        self, repository: CircularDependencyAlertRepository
    ):
        """Test exists_for_cycle returns False for non-existent cycle.

        Args:
            repository: CircularDependencyAlertRepository instance
        """
        # Act
        exists = await repository.exists_for_cycle(
            ["non-existent", "cycle"]
        )

        # Assert
        assert exists is False

    async def test_exists_for_cycle_different_order(
        self,
        repository: CircularDependencyAlertRepository,
    ):
        """Test that exists_for_cycle is order-sensitive.

        Args:
            repository: CircularDependencyAlertRepository instance
        """
        # Arrange
        alert = CircularDependencyAlert(
            cycle_path=["service-a", "service-b", "service-c"],
        )
        await repository.create(alert)

        # Act - Check with different order
        exists = await repository.exists_for_cycle(
            ["service-b", "service-c", "service-a"]  # Different order
        )

        # Assert - Should not exist (JSONB equality is order-sensitive)
        assert exists is False

    async def test_cycle_path_with_long_cycle(
        self, repository: CircularDependencyAlertRepository
    ):
        """Test handling of long cycle paths.

        Args:
            repository: CircularDependencyAlertRepository instance
        """
        # Arrange - Create alert with long cycle path
        long_cycle = [f"service-{i}" for i in range(20)]
        alert = CircularDependencyAlert(cycle_path=long_cycle)

        # Act
        created = await repository.create(alert)

        # Assert
        assert len(created.cycle_path) == 20
        assert created.cycle_path == long_cycle

        # Verify retrieval
        retrieved = await repository.get_by_id(created.id)
        assert retrieved is not None
        assert retrieved.cycle_path == long_cycle

    async def test_list_by_status_ordered_by_detected_at(
        self, repository: CircularDependencyAlertRepository
    ):
        """Test that list_by_status returns results ordered by detected_at DESC.

        Args:
            repository: CircularDependencyAlertRepository instance
        """
        # Arrange - Create alerts in sequence
        alert1 = CircularDependencyAlert(
            cycle_path=["service-a", "service-b"],
            status=AlertStatus.OPEN,
        )
        alert2 = CircularDependencyAlert(
            cycle_path=["service-c", "service-d"],
            status=AlertStatus.OPEN,
        )
        alert3 = CircularDependencyAlert(
            cycle_path=["service-e", "service-f"],
            status=AlertStatus.OPEN,
        )

        created1 = await repository.create(alert1)
        created2 = await repository.create(alert2)
        created3 = await repository.create(alert3)

        # Act
        result = await repository.list_by_status(AlertStatus.OPEN)

        # Assert - Should be in reverse chronological order
        assert len(result) == 3
        assert result[0].id == created3.id  # Most recent first
        assert result[1].id == created2.id
        assert result[2].id == created1.id  # Oldest last

    async def test_workflow_open_to_acknowledged_to_resolved(
        self, repository: CircularDependencyAlertRepository
    ):
        """Test complete workflow from open to acknowledged to resolved.

        Args:
            repository: CircularDependencyAlertRepository instance
        """
        # Arrange - Create open alert
        alert = CircularDependencyAlert(
            cycle_path=["api-gateway", "auth-service", "user-service"],
            status=AlertStatus.OPEN,
        )
        created = await repository.create(alert)

        # Act 1 - Acknowledge the alert
        created.acknowledge("sre-team@example.com")
        acknowledged = await repository.update(created)

        # Assert 1
        assert acknowledged.status == AlertStatus.ACKNOWLEDGED
        assert acknowledged.acknowledged_by == "sre-team@example.com"

        # Act 2 - Resolve the alert
        acknowledged.resolve("Refactored auth-service to remove circular dependency")
        resolved = await repository.update(acknowledged)

        # Assert 2
        assert resolved.status == AlertStatus.RESOLVED
        assert resolved.resolution_notes == "Refactored auth-service to remove circular dependency"

        # Verify final state
        final = await repository.get_by_id(created.id)
        assert final is not None
        assert final.status == AlertStatus.RESOLVED
        assert final.acknowledged_by == "sre-team@example.com"
        assert final.resolution_notes == "Refactored auth-service to remove circular dependency"
