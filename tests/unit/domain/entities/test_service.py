"""Unit tests for Service entity."""

import pytest
from datetime import datetime, timezone
from uuid import UUID

from src.domain.entities.service import Criticality, Service


class TestCriticality:
    """Test cases for Criticality enum."""

    def test_criticality_values(self):
        """Test that all expected criticality levels exist."""
        assert Criticality.CRITICAL.value == "critical"
        assert Criticality.HIGH.value == "high"
        assert Criticality.MEDIUM.value == "medium"
        assert Criticality.LOW.value == "low"

    def test_criticality_is_string_enum(self):
        """Test that Criticality is a string enum."""
        assert isinstance(Criticality.CRITICAL, str)
        assert Criticality.CRITICAL == "critical"


class TestService:
    """Test cases for Service entity."""

    def test_service_creation_with_minimal_fields(self):
        """Test creating a service with only required fields."""
        service = Service(service_id="test-service")

        assert service.service_id == "test-service"
        assert service.metadata == {}
        assert service.criticality == Criticality.MEDIUM
        assert service.team is None
        assert service.discovered is False
        assert isinstance(service.id, UUID)
        assert isinstance(service.created_at, datetime)
        assert isinstance(service.updated_at, datetime)

    def test_service_creation_with_all_fields(self):
        """Test creating a service with all fields specified."""
        metadata = {"namespace": "production", "runtime": "python3.12"}
        service = Service(
            service_id="checkout-service",
            metadata=metadata,
            criticality=Criticality.HIGH,
            team="payments",
            discovered=False,
        )

        assert service.service_id == "checkout-service"
        assert service.metadata == metadata
        assert service.criticality == Criticality.HIGH
        assert service.team == "payments"
        assert service.discovered is False

    def test_service_creation_empty_service_id_raises(self):
        """Test that empty service_id raises ValueError."""
        with pytest.raises(ValueError, match="service_id cannot be empty"):
            Service(service_id="")

    def test_discovered_service_gets_auto_metadata(self):
        """Test that discovered services get minimal metadata automatically."""
        service = Service(service_id="auto-service", discovered=True)

        assert service.discovered is True
        assert service.metadata == {"source": "auto_discovered"}

    def test_discovered_service_with_existing_metadata_unchanged(self):
        """Test that discovered services with metadata keep their metadata."""
        existing_metadata = {"key": "value"}
        service = Service(
            service_id="auto-service",
            discovered=True,
            metadata=existing_metadata,
        )

        assert service.metadata == existing_metadata

    def test_mark_as_registered_updates_fields(self):
        """Test that mark_as_registered updates service fields correctly."""
        service = Service(service_id="test-service", discovered=True)
        original_updated_at = service.updated_at

        new_metadata = {"team": "platform", "tier": 1}
        service.mark_as_registered(
            team="platform",
            criticality=Criticality.HIGH,
            metadata=new_metadata,
        )

        assert service.discovered is False
        assert service.team == "platform"
        assert service.criticality == Criticality.HIGH
        assert service.metadata == new_metadata
        assert service.updated_at > original_updated_at

    def test_mark_as_registered_empty_team_raises(self):
        """Test that mark_as_registered with empty team raises ValueError."""
        service = Service(service_id="test-service", discovered=True)

        with pytest.raises(ValueError, match="team cannot be empty"):
            service.mark_as_registered(
                team="",
                criticality=Criticality.HIGH,
                metadata={},
            )

    def test_service_timestamps_use_utc(self):
        """Test that timestamps use UTC timezone."""
        service = Service(service_id="test-service")

        assert service.created_at.tzinfo == timezone.utc
        assert service.updated_at.tzinfo == timezone.utc

    def test_service_id_is_immutable_business_key(self):
        """Test that service_id is the business identifier."""
        service = Service(service_id="immutable-id")

        # service_id should be the business key, not the UUID
        assert service.service_id == "immutable-id"
        assert isinstance(service.id, UUID)
        assert str(service.id) != service.service_id

    def test_default_criticality_is_medium(self):
        """Test that default criticality is MEDIUM."""
        service = Service(service_id="test-service")

        assert service.criticality == Criticality.MEDIUM

    def test_service_equality_based_on_id(self):
        """Test that services can be compared (for testing purposes)."""
        service1 = Service(service_id="test-service")
        service2 = Service(service_id="test-service")

        # Different instances should have different UUIDs
        assert service1.id != service2.id
        # But same service_id (business key)
        assert service1.service_id == service2.service_id

    def test_service_with_different_criticality_levels(self):
        """Test creating services with each criticality level."""
        for criticality in Criticality:
            service = Service(
                service_id=f"service-{criticality.value}",
                criticality=criticality,
            )
            assert service.criticality == criticality
