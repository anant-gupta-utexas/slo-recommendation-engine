"""Pydantic schemas for FR-5 SLO Lifecycle API endpoints."""

from pydantic import BaseModel, ConfigDict, Field


class SloModificationsApiModel(BaseModel):
    """Modifications to apply when action is 'modify'."""

    availability_target: float | None = Field(
        None, ge=0.0, le=100.0, description="Modified availability target (%)"
    )
    latency_p95_target_ms: int | None = Field(
        None, ge=0, description="Modified latency p95 target (ms)"
    )
    latency_p99_target_ms: int | None = Field(
        None, ge=0, description="Modified latency p99 target (ms)"
    )


class ManageSloApiRequest(BaseModel):
    """Request to accept, modify, or reject an SLO recommendation."""

    action: str = Field(
        ...,
        description="Action to perform: accept, modify, or reject",
        pattern="^(accept|modify|reject)$",
    )
    selected_tier: str = Field(
        default="balanced",
        description="Tier to accept: conservative, balanced, or aggressive",
        pattern="^(conservative|balanced|aggressive)$",
    )
    recommendation_id: str | None = Field(
        None, description="UUID of the recommendation being acted upon"
    )
    modifications: SloModificationsApiModel | None = Field(
        None, description="Modifications to apply (only for action=modify)"
    )
    rationale: str = Field(
        default="", description="Rationale for the action"
    )
    actor: str = Field(
        ..., description="Email or identifier of the person taking the action"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "action": "accept",
                "selected_tier": "balanced",
                "rationale": "Recommended target aligns with team risk tolerance",
                "actor": "jane.doe@company.com",
            }
        }
    )


class ActiveSloApiResponse(BaseModel):
    """Active SLO for a service."""

    service_id: str = Field(..., description="Service business identifier")
    slo_id: str = Field(default="", description="UUID of the active SLO")
    availability_target: float | None = Field(None, description="Availability target (%)")
    latency_p95_target_ms: int | None = Field(None, description="Latency p95 target (ms)")
    latency_p99_target_ms: int | None = Field(None, description="Latency p99 target (ms)")
    source: str = Field(default="", description="How the SLO was set")
    recommendation_id: str | None = Field(None, description="Associated recommendation UUID")
    selected_tier: str | None = Field(None, description="Which tier was selected")
    activated_at: str = Field(default="", description="When this SLO became active (ISO 8601)")
    activated_by: str = Field(default="", description="Who activated this SLO")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "service_id": "payment-service",
                "slo_id": "550e8400-e29b-41d4-a716-446655440000",
                "availability_target": 99.9,
                "latency_p99_target_ms": 800,
                "source": "recommendation_accepted",
                "selected_tier": "balanced",
                "activated_at": "2026-02-16T11:00:00Z",
                "activated_by": "jane.doe@company.com",
            }
        }
    )


class ManageSloApiResponse(BaseModel):
    """Response after accepting/modifying/rejecting an SLO."""

    service_id: str = Field(..., description="Service business identifier")
    status: str = Field(..., description="Resulting status: active or rejected")
    action: str = Field(..., description="Action that was performed")
    active_slo: ActiveSloApiResponse | None = Field(
        None, description="Active SLO (present for accept/modify, absent for reject)"
    )
    modification_delta: dict | None = Field(
        None, description="Changes from the original recommendation (for modify)"
    )
    message: str = Field(default="", description="Human-readable summary")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "service_id": "payment-service",
                "status": "active",
                "action": "accept",
                "active_slo": {
                    "service_id": "payment-service",
                    "availability_target": 99.9,
                    "latency_p99_target_ms": 800,
                    "source": "recommendation_accepted",
                    "selected_tier": "balanced",
                    "activated_by": "jane.doe@company.com",
                },
                "message": "SLO accepted for payment-service at balanced tier.",
            }
        }
    )


class AuditEntryApiModel(BaseModel):
    """A single audit log entry."""

    id: str = Field(..., description="UUID of the audit entry")
    service_id: str = Field(..., description="Service business identifier")
    action: str = Field(..., description="Action taken")
    actor: str = Field(..., description="Who performed the action")
    timestamp: str = Field(..., description="When the action occurred (ISO 8601)")
    selected_tier: str | None = Field(None, description="Tier that was selected")
    rationale: str = Field(default="", description="Rationale for the action")
    recommendation_id: str | None = Field(None, description="Associated recommendation UUID")
    previous_slo: dict | None = Field(None, description="SLO snapshot before the action")
    new_slo: dict | None = Field(None, description="SLO snapshot after the action")
    modification_delta: dict | None = Field(None, description="What changed")


class AuditHistoryApiResponse(BaseModel):
    """Audit trail for a service."""

    service_id: str = Field(..., description="Service business identifier")
    entries: list[AuditEntryApiModel] = Field(
        default_factory=list, description="Audit log entries, newest first"
    )
    total_count: int = Field(default=0, description="Total number of entries")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "service_id": "payment-service",
                "total_count": 2,
                "entries": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440001",
                        "service_id": "payment-service",
                        "action": "accept",
                        "actor": "jane.doe@company.com",
                        "timestamp": "2026-02-16T11:00:00Z",
                        "selected_tier": "balanced",
                        "rationale": "Good fit for our risk tolerance",
                    }
                ],
            }
        }
    )
