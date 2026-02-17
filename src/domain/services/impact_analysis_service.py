"""Domain service for FR-4 Impact Analysis.

Computes the cascading impact of a proposed SLO change on upstream services
by recomputing composite availability bounds with the proposed target.
"""

import logging
from uuid import UUID

from src.domain.entities.impact_analysis import (
    ImpactAnalysisResult,
    ImpactedService,
    ImpactSummary,
    ProposedChange,
)
from src.domain.entities.service import Service
from src.domain.entities.service_dependency import ServiceDependency
from src.domain.services.composite_availability_service import (
    CompositeAvailabilityService,
    DependencyWithAvailability,
)

logger = logging.getLogger(__name__)


class ImpactAnalysisService:
    """Computes impact of a proposed SLO change on upstream services.

    Algorithm:
    1. For each upstream service, get its downstream dependencies
    2. Compute current composite availability (using current target for changed service)
    3. Compute projected composite availability (using proposed target)
    4. Compare against the upstream service's SLO target to determine risk
    """

    def __init__(self, composite_service: CompositeAvailabilityService):
        self._composite_service = composite_service

    def compute_impact(
        self,
        changed_service_id: str,
        proposed_change: ProposedChange,
        upstream_services: list[dict],
        service_availabilities: dict[str, float],
        active_slo_targets: dict[str, float],
    ) -> ImpactAnalysisResult:
        """Compute impact of a proposed SLO change.

        Args:
            changed_service_id: Business ID of the service being changed
            proposed_change: The proposed SLO change
            upstream_services: List of dicts with upstream service info:
                [{"service_id": str, "service_uuid": UUID, "depth": int,
                  "dependencies": [{"target_id": str, "target_uuid": UUID,
                                    "is_hard": bool, "availability": float}]}]
            service_availabilities: Map of service_id -> observed availability ratio
            active_slo_targets: Map of service_id -> active SLO target (%)

        Returns:
            ImpactAnalysisResult with per-service impact and summary
        """
        impacted: list[ImpactedService] = []

        current_target_ratio = proposed_change.current_target / 100.0
        proposed_target_ratio = proposed_change.proposed_target / 100.0

        for upstream in upstream_services:
            upstream_id = upstream["service_id"]
            upstream_uuid = upstream["service_uuid"]
            depth = upstream.get("depth", 1)
            deps = upstream.get("dependencies", [])

            # Get the upstream service's own availability
            upstream_avail = service_availabilities.get(upstream_id, 0.999)

            # Build dependency list with CURRENT target for changed service
            current_deps = []
            projected_deps = []
            for dep in deps:
                dep_id = dep["target_id"]
                dep_uuid = dep["target_uuid"]
                is_hard = dep.get("is_hard", True)

                if dep_id == changed_service_id:
                    current_deps.append(DependencyWithAvailability(
                        service_id=dep_uuid,
                        service_name=dep_id,
                        availability=current_target_ratio,
                        is_hard=is_hard,
                    ))
                    projected_deps.append(DependencyWithAvailability(
                        service_id=dep_uuid,
                        service_name=dep_id,
                        availability=proposed_target_ratio,
                        is_hard=is_hard,
                    ))
                else:
                    dep_avail = service_availabilities.get(dep_id, 0.999)
                    dep_with_avail = DependencyWithAvailability(
                        service_id=dep_uuid,
                        service_name=dep_id,
                        availability=dep_avail,
                        is_hard=is_hard,
                    )
                    current_deps.append(dep_with_avail)
                    projected_deps.append(DependencyWithAvailability(
                        service_id=dep_uuid,
                        service_name=dep_id,
                        availability=dep_avail,
                        is_hard=is_hard,
                    ))

            # Compute composite bounds
            current_result = self._composite_service.compute_composite_bound(
                upstream_avail, current_deps
            )
            projected_result = self._composite_service.compute_composite_bound(
                upstream_avail, projected_deps
            )

            current_pct = current_result.composite_bound * 100.0
            projected_pct = projected_result.composite_bound * 100.0
            delta = projected_pct - current_pct

            # Check against SLO target
            slo_target = active_slo_targets.get(upstream_id)
            slo_at_risk: bool | None = None
            risk_detail = ""

            if slo_target is not None:
                slo_at_risk = projected_pct < slo_target
                if slo_at_risk:
                    risk_detail = (
                        f"Composite drops below SLO target "
                        f"({slo_target:.1f}% > {projected_pct:.2f}%)"
                    )

            relationship = "upstream" if depth == 1 else f"upstream (transitive, depth={depth})"

            impacted.append(ImpactedService(
                service_id=upstream_id,
                relationship=relationship,
                current_composite_availability=round(current_pct, 2),
                projected_composite_availability=round(projected_pct, 2),
                delta=round(delta, 2),
                current_slo_target=slo_target,
                slo_at_risk=slo_at_risk,
                risk_detail=risk_detail,
                depth=depth,
            ))

        # Sort by absolute delta descending (most impacted first)
        impacted.sort(key=lambda s: abs(s.delta), reverse=True)

        # Build summary
        at_risk_count = sum(1 for s in impacted if s.slo_at_risk is True)
        recommendation = self._build_recommendation(
            changed_service_id, proposed_change, len(impacted), at_risk_count
        )
        latency_note = ""
        if proposed_change.sli_type == "latency" or proposed_change.is_degradation:
            latency_note = (
                "Latency SLOs for upstream services may also be affected. "
                "Latency impact cannot be computed mathematically (percentiles are non-additive). "
                "Review upstream latency budgets manually."
            )

        summary = ImpactSummary(
            total_impacted=len(impacted),
            slos_at_risk=at_risk_count,
            recommendation=recommendation,
            latency_note=latency_note,
        )

        return ImpactAnalysisResult(
            service_id=changed_service_id,
            proposed_change=proposed_change,
            impacted_services=impacted,
            summary=summary,
        )

    @staticmethod
    def _build_recommendation(
        service_id: str,
        change: ProposedChange,
        total_impacted: int,
        at_risk: int,
    ) -> str:
        """Build a human-readable recommendation."""
        if at_risk == 0 and total_impacted == 0:
            return f"No upstream services are impacted by this change to {service_id}."

        if at_risk == 0:
            return (
                f"Changing {service_id} from {change.current_target}% to "
                f"{change.proposed_target}% affects {total_impacted} upstream "
                f"service(s) but none are at risk of SLO breach."
            )

        return (
            f"Reducing {service_id} to {change.proposed_target}% puts "
            f"{at_risk} upstream service(s) at risk of SLO breach."
        )
