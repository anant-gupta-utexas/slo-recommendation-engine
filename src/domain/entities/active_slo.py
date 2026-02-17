"""Domain entities for FR-5 Recommendation Lifecycle.

This module defines the core entities for managing active SLOs and audit trails:
- ActiveSlo: The currently accepted SLO target for a service
- SloAuditEntry: An immutable record of an SLO lifecycle action
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4


class SloAction(str, Enum):
    """Action taken on an SLO recommendation."""

    ACCEPT = "accept"
    MODIFY = "modify"
    REJECT = "reject"
    AUTO_APPROVE = "auto_approve"
    EXPIRE = "expire"
    DRIFT_TRIGGERED = "drift_triggered"


class SloSource(str, Enum):
    """Source of the active SLO."""

    RECOMMENDATION_ACCEPTED = "recommendation_accepted"
    RECOMMENDATION_MODIFIED = "recommendation_modified"
    MANUAL = "manual"


@dataclass
class ActiveSlo:
    """The currently active SLO for a service.

    Attributes:
        service_id: Business identifier of the service
        availability_target: Availability target as percentage (e.g., 99.9)
        latency_p95_target_ms: Latency p95 target in milliseconds
        latency_p99_target_ms: Latency p99 target in milliseconds
        source: How the SLO was set
        recommendation_id: UUID of the recommendation this SLO was derived from
        selected_tier: Which tier was selected (conservative/balanced/aggressive)
        activated_at: When this SLO became active
        activated_by: Who activated this SLO (actor email)
        id: Unique identifier for this active SLO
    """

    service_id: str
    availability_target: float | None = None
    latency_p95_target_ms: int | None = None
    latency_p99_target_ms: int | None = None
    source: SloSource = SloSource.RECOMMENDATION_ACCEPTED
    recommendation_id: UUID | None = None
    selected_tier: str | None = None
    activated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    activated_by: str = ""
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self):
        """Validate active SLO constraints."""
        if not self.service_id:
            raise ValueError("service_id cannot be empty")
        if self.availability_target is not None and not (0.0 <= self.availability_target <= 100.0):
            raise ValueError(
                f"availability_target must be between 0.0 and 100.0, got {self.availability_target}"
            )


@dataclass
class SloAuditEntry:
    """An immutable audit log entry for SLO lifecycle actions.

    Attributes:
        service_id: Business identifier of the service
        action: The action taken (accept, modify, reject, etc.)
        actor: Who performed the action (email or system identifier)
        recommendation_id: UUID of the associated recommendation
        previous_slo: Snapshot of the SLO before this action
        new_slo: Snapshot of the SLO after this action
        selected_tier: Which tier was selected
        rationale: User-provided rationale for the action
        modification_delta: Description of changes from the original recommendation
        id: Unique identifier for this audit entry
        timestamp: When this action occurred
    """

    service_id: str
    action: SloAction
    actor: str
    recommendation_id: UUID | None = None
    previous_slo: dict | None = None
    new_slo: dict | None = None
    selected_tier: str | None = None
    rationale: str = ""
    modification_delta: dict | None = None
    id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        """Validate audit entry constraints."""
        if not self.service_id:
            raise ValueError("service_id cannot be empty")
        if not self.actor:
            raise ValueError("actor cannot be empty")
