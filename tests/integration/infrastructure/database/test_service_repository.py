"""Integration tests for ServiceRepository.

This module tests the ServiceRepository implementation against
a real PostgreSQL database using testcontainers.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.service import Criticality, Service
from src.infrastructure.database.repositories.service_repository import (
    ServiceRepository,
)


@pytest.mark.integration
class TestServiceRepository:
    """Integration tests for ServiceRepository."""

    @pytest.fixture
    def repository(self, db_session: AsyncSession) -> ServiceRepository:
        """Create ServiceRepository instance for testing.

        Args:
            db_session: Database session fixture

        Returns:
            ServiceRepository instance
        """
        return ServiceRepository(db_session)

    @pytest.fixture
    def sample_service(self) -> Service:
        """Create a sample service for testing.

        Returns:
            Service entity with test data
        """
        return Service(
            service_id="test-service",
            metadata={"version": "1.0.0", "region": "us-west-2"},
            criticality=Criticality.HIGH,
            team="platform-team",
            discovered=False,
        )

    async def test_create_service(
        self, repository: ServiceRepository, sample_service: Service
    ):
        """Test creating a new service.

        Args:
            repository: ServiceRepository instance
            sample_service: Sample service entity
        """
        # Act
        created = await repository.create(sample_service)

        # Assert
        assert created.id is not None
        assert created.service_id == "test-service"
        assert created.metadata == {"version": "1.0.0", "region": "us-west-2"}
        assert created.criticality == Criticality.HIGH
        assert created.team == "platform-team"
        assert created.discovered is False
        assert created.created_at is not None
        assert created.updated_at is not None

    async def test_create_duplicate_service_id_raises_error(
        self, repository: ServiceRepository, sample_service: Service
    ):
        """Test that creating a service with duplicate service_id raises error.

        Args:
            repository: ServiceRepository instance
            sample_service: Sample service entity
        """
        # Arrange
        await repository.create(sample_service)

        # Act & Assert
        duplicate_service = Service(
            service_id="test-service",  # Same service_id
            metadata={"different": "metadata"},
            criticality=Criticality.LOW,
        )
        with pytest.raises(ValueError, match="already exists"):
            await repository.create(duplicate_service)

    async def test_get_by_id(
        self, repository: ServiceRepository, sample_service: Service
    ):
        """Test retrieving a service by internal UUID.

        Args:
            repository: ServiceRepository instance
            sample_service: Sample service entity
        """
        # Arrange
        created = await repository.create(sample_service)

        # Act
        retrieved = await repository.get_by_id(created.id)

        # Assert
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.service_id == created.service_id
        assert retrieved.metadata == created.metadata

    async def test_get_by_id_not_found(self, repository: ServiceRepository):
        """Test that get_by_id returns None for non-existent service.

        Args:
            repository: ServiceRepository instance
        """
        # Act
        result = await repository.get_by_id(uuid4())

        # Assert
        assert result is None

    async def test_get_by_service_id(
        self, repository: ServiceRepository, sample_service: Service
    ):
        """Test retrieving a service by business identifier.

        Args:
            repository: ServiceRepository instance
            sample_service: Sample service entity
        """
        # Arrange
        created = await repository.create(sample_service)

        # Act
        retrieved = await repository.get_by_service_id("test-service")

        # Assert
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.service_id == "test-service"

    async def test_get_by_service_id_not_found(self, repository: ServiceRepository):
        """Test that get_by_service_id returns None for non-existent service.

        Args:
            repository: ServiceRepository instance
        """
        # Act
        result = await repository.get_by_service_id("non-existent-service")

        # Assert
        assert result is None

    async def test_list_all(self, repository: ServiceRepository):
        """Test listing all services with pagination.

        Args:
            repository: ServiceRepository instance
        """
        # Arrange - Create multiple services
        services = [
            Service(service_id=f"service-{i}", criticality=Criticality.MEDIUM)
            for i in range(5)
        ]
        for service in services:
            await repository.create(service)

        # Act
        result = await repository.list_all(skip=0, limit=10)

        # Assert
        assert len(result) == 5
        # Results should be ordered by created_at DESC
        assert result[0].service_id == "service-4"
        assert result[4].service_id == "service-0"

    async def test_list_all_pagination(self, repository: ServiceRepository):
        """Test pagination in list_all.

        Args:
            repository: ServiceRepository instance
        """
        # Arrange - Create 10 services
        services = [
            Service(service_id=f"service-{i:02d}", criticality=Criticality.MEDIUM)
            for i in range(10)
        ]
        for service in services:
            await repository.create(service)

        # Act - Get second page
        result = await repository.list_all(skip=5, limit=3)

        # Assert
        assert len(result) == 3
        # Should get services 4, 3, 2 (ordered by created_at DESC, skip first 5)
        assert result[0].service_id == "service-04"
        assert result[2].service_id == "service-02"

    async def test_update_service(
        self, repository: ServiceRepository, sample_service: Service
    ):
        """Test updating an existing service.

        Args:
            repository: ServiceRepository instance
            sample_service: Sample service entity
        """
        # Arrange
        created = await repository.create(sample_service)

        # Modify the service
        created.criticality = Criticality.CRITICAL
        created.metadata = {"version": "2.0.0", "region": "us-east-1"}
        created.team = "security-team"

        # Act
        updated = await repository.update(created)

        # Assert
        assert updated.id == created.id
        assert updated.criticality == Criticality.CRITICAL
        assert updated.metadata == {"version": "2.0.0", "region": "us-east-1"}
        assert updated.team == "security-team"

        # Verify in database
        retrieved = await repository.get_by_id(created.id)
        assert retrieved is not None
        assert retrieved.criticality == Criticality.CRITICAL

    async def test_update_non_existent_service_raises_error(
        self, repository: ServiceRepository
    ):
        """Test that updating a non-existent service raises error.

        Args:
            repository: ServiceRepository instance
        """
        # Arrange
        non_existent_service = Service(
            id=uuid4(),
            service_id="non-existent",
            criticality=Criticality.LOW,
        )

        # Act & Assert
        with pytest.raises(ValueError, match="does not exist"):
            await repository.update(non_existent_service)

    async def test_bulk_upsert_insert_new_services(
        self, repository: ServiceRepository
    ):
        """Test bulk upsert with all new services.

        Args:
            repository: ServiceRepository instance
        """
        # Arrange
        services = [
            Service(
                service_id=f"bulk-service-{i}",
                criticality=Criticality.MEDIUM,
                team=f"team-{i}",
            )
            for i in range(3)
        ]

        # Act
        result = await repository.bulk_upsert(services)

        # Assert
        assert len(result) == 3
        for i, service in enumerate(result):
            assert service.service_id == f"bulk-service-{i}"
            assert service.team == f"team-{i}"
            assert service.id is not None
            assert service.created_at is not None

    async def test_bulk_upsert_update_existing_services(
        self, repository: ServiceRepository
    ):
        """Test bulk upsert updating existing services.

        Args:
            repository: ServiceRepository instance
        """
        # Arrange - Create initial services
        initial_services = [
            Service(
                service_id=f"upsert-service-{i}",
                criticality=Criticality.LOW,
                team="old-team",
                metadata={"version": "1.0.0"},
            )
            for i in range(2)
        ]
        created = await repository.bulk_upsert(initial_services)
        initial_ids = {s.id for s in created}

        # Modify services
        updated_services = [
            Service(
                service_id=f"upsert-service-{i}",
                criticality=Criticality.HIGH,
                team="new-team",
                metadata={"version": "2.0.0"},
            )
            for i in range(2)
        ]

        # Act
        result = await repository.bulk_upsert(updated_services)

        # Assert
        assert len(result) == 2
        for service in result:
            assert service.criticality == Criticality.HIGH
            assert service.team == "new-team"
            assert service.metadata == {"version": "2.0.0"}
            # IDs should be preserved (same service_id)
            assert service.id in initial_ids

    async def test_bulk_upsert_mixed_insert_and_update(
        self, repository: ServiceRepository
    ):
        """Test bulk upsert with mix of new and existing services.

        Args:
            repository: ServiceRepository instance
        """
        # Arrange - Create one existing service
        existing = await repository.create(
            Service(
                service_id="existing-service",
                criticality=Criticality.LOW,
                team="old-team",
            )
        )

        # Prepare upsert with 1 existing + 2 new
        services = [
            Service(
                service_id="existing-service",
                criticality=Criticality.CRITICAL,
                team="updated-team",
            ),
            Service(service_id="new-service-1", criticality=Criticality.MEDIUM),
            Service(service_id="new-service-2", criticality=Criticality.HIGH),
        ]

        # Act
        result = await repository.bulk_upsert(services)

        # Assert
        assert len(result) == 3

        # Find the updated existing service
        updated_existing = next(s for s in result if s.service_id == "existing-service")
        assert updated_existing.id == existing.id  # Same ID
        assert updated_existing.criticality == Criticality.CRITICAL
        assert updated_existing.team == "updated-team"

        # Verify new services were created
        new_services = [s for s in result if s.service_id.startswith("new-service")]
        assert len(new_services) == 2

    async def test_bulk_upsert_empty_list(self, repository: ServiceRepository):
        """Test bulk upsert with empty list.

        Args:
            repository: ServiceRepository instance
        """
        # Act
        result = await repository.bulk_upsert([])

        # Assert
        assert result == []

    async def test_bulk_upsert_idempotency(self, repository: ServiceRepository):
        """Test that bulk upsert is idempotent.

        Args:
            repository: ServiceRepository instance
        """
        # Arrange
        services = [
            Service(
                service_id="idempotent-service",
                criticality=Criticality.MEDIUM,
                team="test-team",
                metadata={"key": "value"},
            )
        ]

        # Act - Upsert same service multiple times
        result1 = await repository.bulk_upsert(services)
        result2 = await repository.bulk_upsert(services)
        result3 = await repository.bulk_upsert(services)

        # Assert - Should have same ID across all upserts
        assert result1[0].id == result2[0].id == result3[0].id
        assert result1[0].service_id == "idempotent-service"

        # Verify only one service exists in database
        all_services = await repository.list_all()
        assert len(all_services) == 1

    async def test_discovered_service(self, repository: ServiceRepository):
        """Test creating and managing discovered services.

        Args:
            repository: ServiceRepository instance
        """
        # Arrange
        discovered_service = Service(
            service_id="auto-discovered-service",
            discovered=True,
            criticality=Criticality.MEDIUM,
        )

        # Act
        created = await repository.create(discovered_service)

        # Assert
        assert created.discovered is True
        assert created.metadata == {"source": "auto_discovered"}
        assert created.team is None

        # Update to registered service
        created.mark_as_registered(
            team="platform-team",
            criticality=Criticality.HIGH,
            metadata={"registered": True},
        )
        updated = await repository.update(created)

        # Assert
        assert updated.discovered is False
        assert updated.team == "platform-team"
        assert updated.criticality == Criticality.HIGH
        assert updated.metadata == {"registered": True}
