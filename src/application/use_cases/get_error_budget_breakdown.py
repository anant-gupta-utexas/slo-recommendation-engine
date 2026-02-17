"""Use case for retrieving error budget breakdown."""

import asyncio
from datetime import datetime, timezone

from src.application.dtos.constraint_analysis_dto import (
    DependencyRiskDTO,
    ErrorBudgetBreakdownRequest,
    ErrorBudgetBreakdownResponse,
)
from src.domain.entities.constraint_analysis import ServiceType
from src.domain.entities.service_dependency import (
    CommunicationMode,
    DependencyCriticality,
)
from src.domain.repositories.dependency_repository import (
    DependencyRepositoryInterface,
)
from src.domain.repositories.service_repository import ServiceRepositoryInterface
from src.domain.repositories.telemetry_query_service import (
    TelemetryQueryServiceInterface,
)
from src.domain.services.composite_availability_service import (
    DependencyWithAvailability,
)
from src.domain.services.error_budget_analyzer import ErrorBudgetAnalyzer
from src.domain.services.external_api_buffer_service import ExternalApiBufferService
from src.domain.services.graph_traversal_service import (
    GraphTraversalService,
    TraversalDirection,
)


class GetErrorBudgetBreakdownUseCase:
    """Retrieve error budget breakdown for a service.

    This use case provides a lighter-weight alternative to full constraint analysis,
    focusing only on per-dependency error budget consumption at a given SLO target.

    It retrieves direct dependencies only (depth=1) and computes budget consumption
    for each hard sync dependency, applying adaptive buffer for external services.
    """

    def __init__(
        self,
        service_repository: ServiceRepositoryInterface,
        dependency_repository: DependencyRepositoryInterface,
        telemetry_service: TelemetryQueryServiceInterface,
        graph_traversal_service: GraphTraversalService,
        external_buffer_service: ExternalApiBufferService,
        error_budget_analyzer: ErrorBudgetAnalyzer,
    ) -> None:
        """Initialize use case with injected dependencies.

        Args:
            service_repository: Service data access
            dependency_repository: Dependency graph access
            telemetry_service: Telemetry data source
            graph_traversal_service: Graph traversal operations
            external_buffer_service: External API adaptive buffer
            error_budget_analyzer: Error budget breakdown computation
        """
        self._service_repo = service_repository
        self._dependency_repo = dependency_repository
        self._telemetry = telemetry_service
        self._graph_traversal = graph_traversal_service
        self._external_buffer = external_buffer_service
        self._budget_analyzer = error_budget_analyzer

    async def execute(
        self, request: ErrorBudgetBreakdownRequest
    ) -> ErrorBudgetBreakdownResponse | None:
        """Execute error budget breakdown computation.

        Args:
            request: Breakdown request with service_id and SLO target

        Returns:
            ErrorBudgetBreakdownResponse if analysis succeeds
            None if service not found
        """
        # Validate service exists
        service = await self._service_repo.get_by_service_id(request.service_id)
        if service is None:
            return None

        # Retrieve direct dependencies only (depth=1)
        nodes, edges = await self._graph_traversal.get_subgraph(
            service_id=service.id,
            direction=TraversalDirection.DOWNSTREAM,
            repository=self._dependency_repo,
            max_depth=1,
            include_stale=False,
        )

        # Build service lookup map
        service_map = {s.id: s for s in nodes}

        # Filter to hard sync dependencies only
        hard_sync_deps = [
            edge
            for edge in edges
            if edge.criticality == DependencyCriticality.HARD
            and edge.communication_mode == CommunicationMode.SYNC
        ]

        # Resolve dependency availabilities (parallel queries)
        deps_with_availability = await self._resolve_dependency_availabilities(
            hard_sync_deps, service_map, request.lookback_days
        )

        # Fetch service's own availability
        self_avail_sli = await self._telemetry.get_availability_sli(
            service_id=request.service_id, window_days=request.lookback_days
        )
        self_availability = (
            self_avail_sli.availability_ratio if self_avail_sli else 0.999
        )

        # Compute error budget breakdown
        error_budget_breakdown = self._budget_analyzer.compute_breakdown(
            service_id=request.service_id,
            slo_target=request.slo_target_pct,
            service_availability=self_availability,
            dependencies=deps_with_availability,
        )

        # Convert to DTO
        breakdown_dto = await self._convert_error_budget_breakdown(
            error_budget_breakdown, service_map, request.lookback_days
        )

        # Build response
        analyzed_at = datetime.now(timezone.utc).isoformat()

        return ErrorBudgetBreakdownResponse(
            service_id=request.service_id,
            analyzed_at=analyzed_at,
            slo_target_pct=breakdown_dto.slo_target_pct,
            total_error_budget_minutes=breakdown_dto.total_error_budget_minutes,
            self_consumption_pct=breakdown_dto.self_consumption_pct,
            dependency_risks=breakdown_dto.dependency_risks,
            high_risk_dependencies=breakdown_dto.high_risk_dependencies,
            total_dependency_consumption_pct=breakdown_dto.total_dependency_consumption_pct,
        )

    async def _resolve_dependency_availabilities(
        self, hard_sync_deps, service_map, lookback_days: int
    ) -> list[DependencyWithAvailability]:
        """Resolve availabilities for all hard sync dependencies in parallel.

        External dependencies use adaptive buffer. Internal dependencies use
        observed telemetry. Missing data defaults to 99.9%.

        Args:
            hard_sync_deps: List of hard sync dependency edges
            service_map: Mapping from UUID to Service entity
            lookback_days: Telemetry lookback window

        Returns:
            List of dependencies with resolved availabilities
        """

        async def resolve_single(edge):
            target_service = service_map.get(edge.target_service_id)
            if target_service is None:
                return None

            # Fetch observed availability from telemetry
            avail_sli = await self._telemetry.get_availability_sli(
                service_id=target_service.service_id, window_days=lookback_days
            )

            observed_availability = (
                avail_sli.availability_ratio if avail_sli else None
            )

            # External services: apply adaptive buffer
            service_type = getattr(target_service, 'service_type', ServiceType.INTERNAL)
            if service_type == ServiceType.EXTERNAL:
                published_sla = getattr(target_service, 'published_sla', None)
                profile = self._external_buffer.build_profile(
                    service_id=target_service.service_id,
                    service_uuid=target_service.id,
                    published_sla=published_sla,
                    observed_availability=observed_availability,
                    observation_window_days=lookback_days,
                )
                effective = self._external_buffer.compute_effective_availability(
                    profile
                )
            else:
                # Internal services: use observed or default
                effective = observed_availability if observed_availability else 0.999

            return DependencyWithAvailability(
                service_id=target_service.id,
                service_name=target_service.service_id,
                availability=effective,
                is_hard=True,
                is_redundant_group=False,
            )

        # Execute all queries in parallel
        results = await asyncio.gather(
            *[resolve_single(edge) for edge in hard_sync_deps]
        )

        # Filter out None results
        return [r for r in results if r is not None]

    async def _convert_error_budget_breakdown(
        self, breakdown, service_map, lookback_days: int
    ) -> ErrorBudgetBreakdownResponse:
        """Convert domain ErrorBudgetBreakdown to response DTO.

        Args:
            breakdown: Domain ErrorBudgetBreakdown entity
            service_map: Mapping from UUID to Service entity
            lookback_days: Telemetry lookback window

        Returns:
            ErrorBudgetBreakdownResponse DTO (not the nested breakdown DTO)
        """
        # Convert each DependencyRiskAssessment to DTO
        risk_dtos = []
        for risk in breakdown.dependency_assessments:
            service_entity = service_map.get(risk.service_uuid)
            if service_entity is None:
                continue

            risk_dto = DependencyRiskDTO(
                service_id=risk.service_id,
                availability_pct=risk.availability * 100,
                error_budget_consumption_pct=risk.error_budget_consumption_pct,
                risk_level=risk.risk_level.value,
                is_external=risk.is_external,
                communication_mode=risk.communication_mode,
                criticality=risk.criticality,
                published_sla_pct=(
                    risk.published_sla * 100 if risk.published_sla else None
                ),
                observed_availability_pct=(
                    risk.observed_availability * 100
                    if risk.observed_availability
                    else None
                ),
                effective_availability_note=risk.effective_availability_note,
            )
            risk_dtos.append(risk_dto)

        # Return the response DTO directly (not nested breakdown)
        return ErrorBudgetBreakdownResponse(
            service_id=breakdown.service_id,
            analyzed_at=datetime.now(timezone.utc).isoformat(),
            slo_target_pct=breakdown.slo_target,
            total_error_budget_minutes=breakdown.total_error_budget_minutes,
            self_consumption_pct=breakdown.self_consumption_pct,
            dependency_risks=risk_dtos,
            high_risk_dependencies=breakdown.high_risk_dependencies,
            total_dependency_consumption_pct=breakdown.total_dependency_consumption_pct,
        )
