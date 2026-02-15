"""Unit tests for CircularDependencyAlert entity."""

import pytest
from datetime import datetime, timezone
from uuid import UUID

from src.domain.entities.circular_dependency_alert import (
    AlertStatus,
    CircularDependencyAlert,
)


class TestAlertStatus:
    """Test cases for AlertStatus enum."""

    def test_alert_status_values(self):
        """Test that all expected alert statuses exist."""
        assert AlertStatus.OPEN.value == "open"
        assert AlertStatus.ACKNOWLEDGED.value == "acknowledged"
        assert AlertStatus.RESOLVED.value == "resolved"


class TestCircularDependencyAlert:
    """Test cases for CircularDependencyAlert entity."""

    def test_alert_creation_minimal_fields(self):
        """Test creating an alert with only required fields."""
        cycle_path = ["service-a", "service-b", "service-c"]
        alert = CircularDependencyAlert(cycle_path=cycle_path)

        assert alert.cycle_path == cycle_path
        assert alert.status == AlertStatus.OPEN
        assert alert.acknowledged_by is None
        assert alert.resolution_notes is None
        assert isinstance(alert.id, UUID)
        assert isinstance(alert.detected_at, datetime)

    def test_alert_creation_all_fields(self):
        """Test creating an alert with all fields specified."""
        cycle_path = ["service-a", "service-b"]
        alert = CircularDependencyAlert(
            cycle_path=cycle_path,
            status=AlertStatus.ACKNOWLEDGED,
            acknowledged_by="admin",
            resolution_notes="Working on fix",
        )

        assert alert.cycle_path == cycle_path
        assert alert.status == AlertStatus.ACKNOWLEDGED
        assert alert.acknowledged_by == "admin"
        assert alert.resolution_notes == "Working on fix"

    def test_alert_cycle_path_minimum_size(self):
        """Test that cycle_path must contain at least 2 services."""
        # Valid: exactly 2 services
        alert = CircularDependencyAlert(cycle_path=["service-a", "service-b"])
        assert len(alert.cycle_path) == 2

        # Invalid: single service
        with pytest.raises(ValueError, match="Cycle path must contain at least 2"):
            CircularDependencyAlert(cycle_path=["service-a"])

        # Invalid: empty list
        with pytest.raises(ValueError, match="Cycle path must contain at least 2"):
            CircularDependencyAlert(cycle_path=[])

    def test_alert_cycle_path_validates_service_ids(self):
        """Test that all service_ids in cycle_path must be non-empty strings."""
        # Valid: all non-empty strings
        alert = CircularDependencyAlert(
            cycle_path=["service-a", "service-b", "service-c"]
        )
        assert len(alert.cycle_path) == 3

        # Invalid: empty string in path
        with pytest.raises(ValueError, match="must be non-empty strings"):
            CircularDependencyAlert(cycle_path=["service-a", "", "service-c"])

        # Invalid: None in path
        with pytest.raises(ValueError, match="must be non-empty strings"):
            CircularDependencyAlert(cycle_path=["service-a", None, "service-c"])

    def test_acknowledge_updates_status(self):
        """Test that acknowledge method updates status and acknowledger."""
        alert = CircularDependencyAlert(cycle_path=["service-a", "service-b"])

        assert alert.status == AlertStatus.OPEN
        assert alert.acknowledged_by is None

        alert.acknowledge("john.doe")

        assert alert.status == AlertStatus.ACKNOWLEDGED
        assert alert.acknowledged_by == "john.doe"

    def test_acknowledge_empty_acknowledger_raises(self):
        """Test that acknowledge with empty acknowledger raises ValueError."""
        alert = CircularDependencyAlert(cycle_path=["service-a", "service-b"])

        with pytest.raises(ValueError, match="acknowledger cannot be empty"):
            alert.acknowledge("")

    def test_acknowledge_resolved_alert_raises(self):
        """Test that acknowledging a resolved alert raises ValueError."""
        alert = CircularDependencyAlert(
            cycle_path=["service-a", "service-b"],
            status=AlertStatus.RESOLVED,
        )

        with pytest.raises(ValueError, match="Cannot acknowledge a resolved alert"):
            alert.acknowledge("john.doe")

    def test_acknowledge_already_acknowledged_alert_succeeds(self):
        """Test that acknowledging an already acknowledged alert succeeds."""
        alert = CircularDependencyAlert(cycle_path=["service-a", "service-b"])

        alert.acknowledge("john.doe")
        assert alert.acknowledged_by == "john.doe"

        # Re-acknowledge with different user
        alert.acknowledge("jane.smith")
        assert alert.acknowledged_by == "jane.smith"

    def test_resolve_updates_status_and_notes(self):
        """Test that resolve method updates status and notes."""
        alert = CircularDependencyAlert(cycle_path=["service-a", "service-b"])

        assert alert.status == AlertStatus.OPEN
        assert alert.resolution_notes is None

        alert.resolve("Removed circular dependency by introducing message queue")

        assert alert.status == AlertStatus.RESOLVED
        assert alert.resolution_notes == "Removed circular dependency by introducing message queue"

    def test_resolve_empty_notes_raises(self):
        """Test that resolve with empty notes raises ValueError."""
        alert = CircularDependencyAlert(cycle_path=["service-a", "service-b"])

        with pytest.raises(ValueError, match="resolution_notes cannot be empty"):
            alert.resolve("")

    def test_resolve_acknowledged_alert_succeeds(self):
        """Test that resolving an acknowledged alert succeeds."""
        alert = CircularDependencyAlert(cycle_path=["service-a", "service-b"])

        alert.acknowledge("john.doe")
        assert alert.status == AlertStatus.ACKNOWLEDGED

        alert.resolve("Fixed the cycle")
        assert alert.status == AlertStatus.RESOLVED

    def test_resolve_already_resolved_alert_succeeds(self):
        """Test that resolving an already resolved alert succeeds (updates notes)."""
        alert = CircularDependencyAlert(cycle_path=["service-a", "service-b"])

        alert.resolve("Initial fix")
        assert alert.resolution_notes == "Initial fix"

        # Re-resolve with updated notes
        alert.resolve("Updated fix details")
        assert alert.resolution_notes == "Updated fix details"
        assert alert.status == AlertStatus.RESOLVED

    def test_alert_timestamps_use_utc(self):
        """Test that timestamps use UTC timezone."""
        alert = CircularDependencyAlert(cycle_path=["service-a", "service-b"])

        assert alert.detected_at.tzinfo == timezone.utc

    def test_alert_with_large_cycle_path(self):
        """Test creating alert with large cycle (many services)."""
        # Create a large cycle
        large_cycle = [f"service-{i}" for i in range(100)]
        alert = CircularDependencyAlert(cycle_path=large_cycle)

        assert len(alert.cycle_path) == 100
        assert alert.cycle_path[0] == "service-0"
        assert alert.cycle_path[-1] == "service-99"

    def test_alert_lifecycle_transitions(self):
        """Test complete alert lifecycle: open -> acknowledged -> resolved."""
        alert = CircularDependencyAlert(cycle_path=["service-a", "service-b"])

        # Initial state: OPEN
        assert alert.status == AlertStatus.OPEN
        assert alert.acknowledged_by is None
        assert alert.resolution_notes is None

        # Transition to ACKNOWLEDGED
        alert.acknowledge("john.doe")
        assert alert.status == AlertStatus.ACKNOWLEDGED
        assert alert.acknowledged_by == "john.doe"
        assert alert.resolution_notes is None

        # Transition to RESOLVED
        alert.resolve("Implemented async communication pattern")
        assert alert.status == AlertStatus.RESOLVED
        assert alert.acknowledged_by == "john.doe"
        assert alert.resolution_notes == "Implemented async communication pattern"

    def test_alert_direct_resolution_without_acknowledgement(self):
        """Test that alerts can be resolved directly without acknowledgement."""
        alert = CircularDependencyAlert(cycle_path=["service-a", "service-b"])

        # Skip acknowledgement and go straight to resolved
        alert.resolve("Quick fix applied")

        assert alert.status == AlertStatus.RESOLVED
        assert alert.acknowledged_by is None  # Never acknowledged
        assert alert.resolution_notes == "Quick fix applied"

    def test_alert_cycle_path_immutable_after_creation(self):
        """Test that cycle_path is set at creation (business requirement)."""
        cycle_path = ["service-a", "service-b", "service-c"]
        alert = CircularDependencyAlert(cycle_path=cycle_path)

        # Verify we can read it
        assert alert.cycle_path == cycle_path

        # Note: Python dataclasses allow mutation by default,
        # but domain logic should treat cycle_path as immutable
        # (it represents the detected cycle at a point in time)
