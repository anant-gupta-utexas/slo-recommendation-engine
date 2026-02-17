"""DTOs for FR-4 Impact Analysis."""

from dataclasses import dataclass, field


@dataclass
class ProposedChangeDTO:
    """A proposed SLO change."""

    sli_type: str  # "availability" | "latency"
    current_target: float
    proposed_target: float


@dataclass
class ImpactAnalysisRequest:
    """Request to run impact analysis."""

    service_id: str
    proposed_change: ProposedChangeDTO
    max_depth: int = 3


@dataclass
class ImpactedServiceDTO:
    """An upstream service impacted by the change."""

    service_id: str
    relationship: str
    current_composite_availability: float
    projected_composite_availability: float
    delta: float
    current_slo_target: float | None = None
    slo_at_risk: bool | None = None
    risk_detail: str = ""


@dataclass
class ImpactSummaryDTO:
    """Summary of impact analysis."""

    total_impacted: int = 0
    slos_at_risk: int = 0
    recommendation: str = ""
    latency_note: str = ""


@dataclass
class ImpactAnalysisResponse:
    """Response from impact analysis."""

    analysis_id: str
    service_id: str
    proposed_change: ProposedChangeDTO
    impacted_services: list[ImpactedServiceDTO] = field(default_factory=list)
    summary: ImpactSummaryDTO = field(default_factory=ImpactSummaryDTO)
