"""Domain entities for FR-4 Impact Analysis.

This module defines the core entities for computing the cascading impact
of a proposed SLO change on upstream services.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass
class ProposedChange:
    """A proposed SLO change for a service.

    Attributes:
        sli_type: Type of SLI being changed (availability or latency)
        current_target: Current SLO target (e.g., 99.9 for availability %)
        proposed_target: Proposed new SLO target
    """

    sli_type: str
    current_target: float
    proposed_target: float

    @property
    def delta(self) -> float:
        """Difference between proposed and current target."""
        return self.proposed_target - self.current_target

    @property
    def is_degradation(self) -> bool:
        """Whether the change degrades the SLO (lower availability / higher latency)."""
        if self.sli_type == "availability":
            return self.proposed_target < self.current_target
        else:
            return self.proposed_target > self.current_target


@dataclass
class ImpactedService:
    """An upstream service impacted by a proposed SLO change.

    Attributes:
        service_id: Business identifier of the impacted service
        relationship: Relationship to the changed service (e.g., "upstream", "upstream (transitive)")
        current_composite_availability: Current composite availability (%)
        projected_composite_availability: Projected composite after the change (%)
        delta: Change in composite availability (projected - current)
        current_slo_target: The impacted service's own SLO target (if any)
        slo_at_risk: Whether projected composite drops below the service's SLO target
        risk_detail: Human-readable detail about the risk
        depth: Hops from the changed service (1 = direct, 2+ = transitive)
    """

    service_id: str
    relationship: str
    current_composite_availability: float
    projected_composite_availability: float
    delta: float
    current_slo_target: float | None = None
    slo_at_risk: bool | None = None
    risk_detail: str = ""
    depth: int = 1


@dataclass
class ImpactSummary:
    """Summary of the impact analysis.

    Attributes:
        total_impacted: Total number of services impacted
        slos_at_risk: Number of services whose SLOs are at risk
        recommendation: Human-readable recommendation based on the analysis
        latency_note: Qualitative note about latency impact (if applicable)
    """

    total_impacted: int = 0
    slos_at_risk: int = 0
    recommendation: str = ""
    latency_note: str = ""


@dataclass
class ImpactAnalysisResult:
    """Complete result of an impact analysis.

    Attributes:
        analysis_id: Unique identifier for this analysis
        service_id: Service whose SLO change was proposed
        proposed_change: The proposed SLO change
        impacted_services: List of upstream services impacted
        summary: Summary of the analysis
        analyzed_at: When the analysis was performed
    """

    service_id: str
    proposed_change: ProposedChange
    impacted_services: list[ImpactedService] = field(default_factory=list)
    summary: ImpactSummary = field(default_factory=ImpactSummary)
    analysis_id: UUID = field(default_factory=uuid4)
    analyzed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
