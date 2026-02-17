"""DTOs for FR-5 SLO Recommendation Lifecycle (accept/modify/reject)."""

from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class SloModifications:
    """Modifications to a recommendation (for action=modify)."""

    availability_target: float | None = None
    latency_p95_target_ms: int | None = None
    latency_p99_target_ms: int | None = None


@dataclass
class ManageSloRequest:
    """Request to accept, modify, or reject an SLO recommendation."""

    service_id: str
    action: str  # "accept" | "modify" | "reject"
    actor: str
    selected_tier: str = "balanced"  # "conservative" | "balanced" | "aggressive"
    recommendation_id: str | None = None
    modifications: SloModifications | None = None
    rationale: str = ""


@dataclass
class ActiveSloResponse:
    """Response containing the active SLO for a service."""

    service_id: str
    availability_target: float | None = None
    latency_p95_target_ms: int | None = None
    latency_p99_target_ms: int | None = None
    source: str = ""
    recommendation_id: str | None = None
    selected_tier: str | None = None
    activated_at: str = ""
    activated_by: str = ""
    slo_id: str = ""


@dataclass
class ManageSloResponse:
    """Response after accepting/modifying/rejecting an SLO."""

    service_id: str
    status: str  # "active" | "rejected"
    action: str
    active_slo: ActiveSloResponse | None = None
    modification_delta: dict | None = None
    message: str = ""


@dataclass
class AuditEntryResponse:
    """A single audit log entry in the response."""

    id: str
    service_id: str
    action: str
    actor: str
    timestamp: str
    selected_tier: str | None = None
    rationale: str = ""
    recommendation_id: str | None = None
    previous_slo: dict | None = None
    new_slo: dict | None = None
    modification_delta: dict | None = None


@dataclass
class AuditHistoryResponse:
    """Response containing audit trail for a service."""

    service_id: str
    entries: list[AuditEntryResponse] = field(default_factory=list)
    total_count: int = 0
