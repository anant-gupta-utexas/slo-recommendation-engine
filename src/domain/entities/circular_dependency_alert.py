"""CircularDependencyAlert entity module.

This module defines the CircularDependencyAlert entity representing
detected circular dependencies (strongly connected components).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4


class AlertStatus(str, Enum):
    """Alert status values."""

    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


@dataclass
class CircularDependencyAlert:
    """Represents a detected circular dependency (strongly connected component).

    Domain invariants:
    - cycle_path must contain at least 2 service_ids
    - cycle_path must form a closed loop (first == last in expanded form)

    Attributes:
        cycle_path: List of service_ids forming the cycle
        status: Current alert status
        acknowledged_by: Username who acknowledged the alert
        resolution_notes: Notes about how the alert was resolved
        id: Internal UUID identifier
        detected_at: Timestamp when cycle was detected
    """

    cycle_path: list[str]  # List of service_ids forming the cycle
    status: AlertStatus = AlertStatus.OPEN
    acknowledged_by: str | None = None
    resolution_notes: str | None = None

    # Audit fields
    id: UUID = field(default_factory=uuid4)
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        """Validate domain invariants after initialization."""
        if len(self.cycle_path) < 2:
            raise ValueError(
                f"Cycle path must contain at least 2 services, "
                f"got: {len(self.cycle_path)}"
            )

        # Validate that all service_ids are non-empty strings
        for service_id in self.cycle_path:
            if not service_id or not isinstance(service_id, str):
                raise ValueError(
                    f"All service_ids in cycle_path must be non-empty strings, "
                    f"got invalid value: {service_id}"
                )

    def acknowledge(self, acknowledger: str):
        """Mark this alert as acknowledged.

        Args:
            acknowledger: Username of person acknowledging the alert

        Raises:
            ValueError: If acknowledger is empty or alert is already resolved
        """
        if not acknowledger:
            raise ValueError("acknowledger cannot be empty")

        if self.status == AlertStatus.RESOLVED:
            raise ValueError("Cannot acknowledge a resolved alert")

        self.status = AlertStatus.ACKNOWLEDGED
        self.acknowledged_by = acknowledger

    def resolve(self, notes: str):
        """Mark this alert as resolved.

        Args:
            notes: Notes about how the alert was resolved

        Raises:
            ValueError: If notes are empty
        """
        if not notes:
            raise ValueError("resolution_notes cannot be empty")

        self.status = AlertStatus.RESOLVED
        self.resolution_notes = notes
