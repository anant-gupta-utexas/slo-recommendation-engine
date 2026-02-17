"""Pydantic schemas for FR-4 Impact Analysis API endpoints."""

from pydantic import BaseModel, ConfigDict, Field


class ProposedChangeApiModel(BaseModel):
    """A proposed SLO change."""

    sli_type: str = Field(
        ...,
        description="SLI type: availability or latency",
        pattern="^(availability|latency)$",
    )
    current_target: float = Field(
        ..., ge=0.0, le=100.0, description="Current SLO target (%)"
    )
    proposed_target: float = Field(
        ..., ge=0.0, le=100.0, description="Proposed new SLO target (%)"
    )


class ImpactAnalysisApiRequest(BaseModel):
    """Request to run impact analysis."""

    service_id: str = Field(..., description="Service whose SLO is being changed")
    proposed_change: ProposedChangeApiModel = Field(
        ..., description="The proposed SLO change"
    )
    max_depth: int = Field(
        default=3, ge=1, le=10, description="Maximum upstream traversal depth"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "service_id": "payment-service",
                "proposed_change": {
                    "sli_type": "availability",
                    "current_target": 99.9,
                    "proposed_target": 99.5,
                },
                "max_depth": 3,
            }
        }
    )


class ImpactedServiceApiModel(BaseModel):
    """An upstream service impacted by the proposed change."""

    service_id: str = Field(..., description="Service business identifier")
    relationship: str = Field(..., description="Relationship to the changed service")
    current_composite_availability: float = Field(
        ..., description="Current composite availability (%)"
    )
    projected_composite_availability: float = Field(
        ..., description="Projected composite availability after change (%)"
    )
    delta: float = Field(..., description="Change in composite availability")
    current_slo_target: float | None = Field(
        None, description="Service's active SLO target (if any)"
    )
    slo_at_risk: bool | None = Field(
        None, description="Whether SLO is at risk (None if no active SLO)"
    )
    risk_detail: str = Field(default="", description="Risk explanation")


class ImpactSummaryApiModel(BaseModel):
    """Summary of the impact analysis."""

    total_impacted: int = Field(default=0, description="Total services impacted")
    slos_at_risk: int = Field(default=0, description="Services with SLOs at risk")
    recommendation: str = Field(default="", description="Human-readable recommendation")
    latency_note: str = Field(default="", description="Qualitative latency impact note")


class ImpactAnalysisApiResponse(BaseModel):
    """Response from impact analysis."""

    analysis_id: str = Field(..., description="UUID of this analysis")
    service_id: str = Field(..., description="Service whose SLO change was proposed")
    proposed_change: ProposedChangeApiModel = Field(
        ..., description="The proposed change"
    )
    impacted_services: list[ImpactedServiceApiModel] = Field(
        default_factory=list, description="Impacted upstream services"
    )
    summary: ImpactSummaryApiModel = Field(
        default_factory=ImpactSummaryApiModel, description="Analysis summary"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
                "service_id": "payment-service",
                "proposed_change": {
                    "sli_type": "availability",
                    "current_target": 99.9,
                    "proposed_target": 99.5,
                },
                "impacted_services": [
                    {
                        "service_id": "checkout-service",
                        "relationship": "upstream",
                        "current_composite_availability": 99.70,
                        "projected_composite_availability": 99.35,
                        "delta": -0.35,
                        "current_slo_target": 99.9,
                        "slo_at_risk": True,
                        "risk_detail": "Composite drops below SLO target (99.9% > 99.35%)",
                    }
                ],
                "summary": {
                    "total_impacted": 1,
                    "slos_at_risk": 1,
                    "recommendation": "Reducing payment-service to 99.5% puts 1 upstream service(s) at risk of SLO breach.",
                },
            }
        }
    )
