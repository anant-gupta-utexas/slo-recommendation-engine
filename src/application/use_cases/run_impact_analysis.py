"""Use case for FR-4: Impact Analysis.

Orchestrates the impact analysis workflow:
1. Validate service exists
2. Traverse graph upstream from the changed service
3. For each upstream service, gather dependencies and availabilities
4. Delegate to ImpactAnalysisService for composite recomputation
5. Return structured result
"""

import logging
from uuid import UUID

from src.application.dtos.impact_analysis_dto import (
    ImpactAnalysisRequest,
    ImpactAnalysisResponse,
    ImpactedServiceDTO,
    ImpactSummaryDTO,
    ProposedChangeDTO,
)
from src.domain.entities.impact_analysis import ProposedChange
from src.domain.entities.service_dependency import DependencyCriticality, CommunicationMode
from src.domain.repositories.dependency_repository import DependencyRepositoryInterface
from src.domain.repositories.service_repository import ServiceRepositoryInterface
from src.domain.repositories.telemetry_query_service import TelemetryQueryServiceInterface
from src.domain.services.graph_traversal_service import GraphTraversalService, TraversalDirection
from src.domain.services.impact_analysis_service import ImpactAnalysisService
from src.infrastructure.stores import in_memory_slo_store as store

logger = logging.getLogger(__name__)


class RunImpactAnalysisUseCase:
    """Run impact analysis for a proposed SLO change."""

    def __init__(
        self,
        service_repository: ServiceRepositoryInterface,
        dependency_repository: DependencyRepositoryInterface,
        telemetry_service: TelemetryQueryServiceInterface,
        graph_traversal_service: GraphTraversalService,
        impact_analysis_service: ImpactAnalysisService,
    ):
        self._service_repo = service_repository
        self._dependency_repo = dependency_repository
        self._telemetry = telemetry_service
        self._graph_traversal = graph_traversal_service
        self._impact_service = impact_analysis_service

    async def execute(self, request: ImpactAnalysisRequest) -> ImpactAnalysisResponse | None:
        """Execute impact analysis.

        Args:
            request: The impact analysis request

        Returns:
            ImpactAnalysisResponse or None if service not found
        """
        # Step 1: Validate service exists
        service = await self._service_repo.get_by_service_id(request.service_id)
        if service is None:
            return None

        # Step 2: Traverse UPSTREAM from the changed service
        upstream_nodes, upstream_edges = await self._graph_traversal.get_subgraph(
            service_id=service.id,
            direction=TraversalDirection.UPSTREAM,
            repository=self._dependency_repo,
            max_depth=request.max_depth,
        )

        # Filter out the changed service itself from upstream nodes
        upstream_nodes = [n for n in upstream_nodes if n.service_id != request.service_id]

        if not upstream_nodes:
            # No upstream services - return empty result
            proposed = ProposedChange(
                sli_type=request.proposed_change.sli_type,
                current_target=request.proposed_change.current_target,
                proposed_target=request.proposed_change.proposed_target,
            )
            from src.domain.entities.impact_analysis import ImpactAnalysisResult, ImpactSummary
            result = ImpactAnalysisResult(
                service_id=request.service_id,
                proposed_change=proposed,
                summary=ImpactSummary(
                    recommendation=f"No upstream services depend on {request.service_id}."
                ),
            )
            return self._to_response(result)

        # Step 3: For each upstream service, get its downstream dependencies
        service_availabilities: dict[str, float] = {}
        active_slo_targets: dict[str, float] = {}
        upstream_info: list[dict] = []

        # Fetch availability for the changed service
        avail_data = await self._telemetry.get_availability_sli(request.service_id, 30)
        if avail_data:
            service_availabilities[request.service_id] = avail_data.availability_ratio

        for node in upstream_nodes:
            # Get this upstream service's own availability
            node_avail = await self._telemetry.get_availability_sli(node.service_id, 30)
            if node_avail:
                service_availabilities[node.service_id] = node_avail.availability_ratio

            # Get active SLO target (from in-memory store or fallback)
            active_slo = store.get_active_slo(node.service_id)
            if active_slo and active_slo.availability_target is not None:
                active_slo_targets[node.service_id] = active_slo.availability_target

            # Get downstream dependencies of this upstream node
            down_nodes, down_edges = await self._graph_traversal.get_subgraph(
                service_id=node.id,
                direction=TraversalDirection.DOWNSTREAM,
                repository=self._dependency_repo,
                max_depth=1,
            )

            deps = []
            for edge in down_edges:
                if edge.source_service_id == node.id:
                    # Find the target service name
                    target_node = next(
                        (n for n in down_nodes if n.id == edge.target_service_id), None
                    )
                    target_name = target_node.service_id if target_node else str(edge.target_service_id)

                    is_hard = (
                        edge.criticality == DependencyCriticality.HARD
                        and edge.communication_mode == CommunicationMode.SYNC
                    )

                    # Get availability for this dependency
                    dep_avail = await self._telemetry.get_availability_sli(target_name, 30)
                    if dep_avail:
                        service_availabilities[target_name] = dep_avail.availability_ratio

                    deps.append({
                        "target_id": target_name,
                        "target_uuid": edge.target_service_id,
                        "is_hard": is_hard,
                        "availability": service_availabilities.get(target_name, 0.999),
                    })

            # Compute depth from changed service
            depth = self._compute_depth(node, upstream_edges, service.id)

            upstream_info.append({
                "service_id": node.service_id,
                "service_uuid": node.id,
                "depth": depth,
                "dependencies": deps,
            })

        # Step 4: Delegate to ImpactAnalysisService
        proposed = ProposedChange(
            sli_type=request.proposed_change.sli_type,
            current_target=request.proposed_change.current_target,
            proposed_target=request.proposed_change.proposed_target,
        )

        result = self._impact_service.compute_impact(
            changed_service_id=request.service_id,
            proposed_change=proposed,
            upstream_services=upstream_info,
            service_availabilities=service_availabilities,
            active_slo_targets=active_slo_targets,
        )

        return self._to_response(result)

    @staticmethod
    def _compute_depth(node, edges, target_service_id: UUID) -> int:
        """Compute hop distance from node to the changed service."""
        # Simple heuristic: check if directly connected
        for edge in edges:
            if edge.source_service_id == node.id and edge.target_service_id == target_service_id:
                return 1
        return 2  # Default to transitive for demo

    @staticmethod
    def _to_response(result) -> ImpactAnalysisResponse:
        """Convert domain result to response DTO."""
        return ImpactAnalysisResponse(
            analysis_id=str(result.analysis_id),
            service_id=result.service_id,
            proposed_change=ProposedChangeDTO(
                sli_type=result.proposed_change.sli_type,
                current_target=result.proposed_change.current_target,
                proposed_target=result.proposed_change.proposed_target,
            ),
            impacted_services=[
                ImpactedServiceDTO(
                    service_id=s.service_id,
                    relationship=s.relationship,
                    current_composite_availability=s.current_composite_availability,
                    projected_composite_availability=s.projected_composite_availability,
                    delta=s.delta,
                    current_slo_target=s.current_slo_target,
                    slo_at_risk=s.slo_at_risk,
                    risk_detail=s.risk_detail,
                )
                for s in result.impacted_services
            ],
            summary=ImpactSummaryDTO(
                total_impacted=result.summary.total_impacted,
                slos_at_risk=result.summary.slos_at_risk,
                recommendation=result.summary.recommendation,
                latency_note=result.summary.latency_note,
            ),
        )
