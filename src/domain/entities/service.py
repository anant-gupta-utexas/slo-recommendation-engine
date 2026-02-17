"""Service entity module.

This module defines the Service entity representing a microservice in the system.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

# Import ServiceType from constraint_analysis for FR-3
from src.domain.entities.constraint_analysis import ServiceType


class Criticality(str, Enum):
    """Service criticality levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Service:
    """Represents a microservice in the system.

    Domain invariants:
    - service_id must be unique and immutable
    - discovered services must have minimal metadata until registered

    Attributes:
        service_id: Business identifier (e.g., "checkout-service")
        metadata: Additional service metadata
        criticality: Service criticality level
        team: Owning team identifier
        discovered: True if auto-created from unknown edge reference
        service_type: Service type (internal or external) - FR-3
        published_sla: Published SLA as ratio (e.g., 0.9999 for 99.99%) - FR-3, external only
        id: Internal UUID identifier
        created_at: Timestamp when service was created
        updated_at: Timestamp when service was last updated
    """

    service_id: str  # Business identifier (e.g., "checkout-service")
    metadata: dict = field(default_factory=dict)
    criticality: Criticality = Criticality.MEDIUM
    team: str | None = None
    discovered: bool = False  # True if auto-created from unknown edge reference
    service_type: ServiceType = ServiceType.INTERNAL  # FR-3: default to internal
    published_sla: float | None = None  # FR-3: published SLA for external services

    # Audit fields
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        """Validate domain invariants after initialization."""
        if not self.service_id:
            raise ValueError("service_id cannot be empty")
        if self.discovered and not self.metadata:
            # Discovered services start with minimal metadata
            self.metadata = {"source": "auto_discovered"}

    def mark_as_registered(self, team: str, criticality: Criticality, metadata: dict):
        """Convert a discovered service to a registered one.

        Args:
            team: Team owning this service
            criticality: Service criticality level
            metadata: Service metadata

        Raises:
            ValueError: If team is empty
        """
        if not team:
            raise ValueError("team cannot be empty")

        self.discovered = False
        self.team = team
        self.criticality = criticality
        self.metadata = metadata
        self.updated_at = datetime.now(timezone.utc)
