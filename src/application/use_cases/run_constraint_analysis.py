"""Use case for running full constraint propagation analysis."""

import asyncio
from datetime import datetime, timezone

from src.application.dtos.constraint_analysis_dto import (
    ConstraintAnalysisRequest,
    ConstraintAnalysisResponse,
    DependencyRiskDTO,
    ErrorBudgetBreakdownDTO,
    UnachievableWarningDTO,
)
from src.domain.entities.constraint_analysis import ServiceType
from src.domain.entities.service_dependency import (
    CommunicationMode,
    DependencyCriticality,
)
from src.domain.repositories.circular_dependency_alert_repository import (
    CircularDependencyAlertRepositoryInterface,
)
from src.domain.repositories.dependency_repository import (
    DependencyRepositoryInterface,
)
from src.domain.repositories.service_repository import ServiceRepositoryInterface
from src.domain.repositories.telemetry_query_service import (
    TelemetryQueryServiceInterface,
)
from src.domain.services.composite_availability_service import (
    CompositeAvailabilityService,
    DependencyWithAvailability,
)
from src.domain.services.error_budget_analyzer import ErrorBudgetAnalyzer
from src.domain.services.external_api_buffer_service import ExternalApiBufferService
from src.domain.services.graph_traversal_service import (
    GraphTraversalService,
    TraversalDirection,
)
from src.domain.services.unachievable_slo_detector import UnachievableSloDetector


class RunConstraintAnalysisUseCase:
    """Run full constraint propagation analysis for a service.

    This use case orchestrates the complete constraint analysis pipeline:
    1. Validate service exists
    2. Determine desired SLO target
    3. Retrieve dependency subgraph
    4. Classify dependencies (hard/soft, internal/external)
    5. Resolve dependency availabilities (with external adaptive buffer)
    6. Compute composite availability bound
    7. Compute error budget breakdown
    8. Check for unachievable SLOs
    9. Identify circular dependency cycles
    10. Build complete response

    The use case applies the external API adaptive buffer strategy and
    provides detailed per-dependency risk assessments.
    """

    def __init__(
        self,
        service_repository: ServiceRepositoryInterface,
        dependency_repository: DependencyRepositoryInterface,
        telemetry_service: TelemetryQueryServiceInterface,
        alert_repository: CircularDependencyAlertRepositoryInterface,
        graph_traversal_service: GraphTraversalService,
        composite_service: CompositeAvailabilityService,
        external_buffer_service: ExternalApiBufferService,
        error_budget_analyzer: ErrorBudgetAnalyzer,
        unachievable_detector: UnachievableSloDetector,
    ) -> None:
        """Initialize use case with injected dependencies.

        Args:
            service_repository: Service data access
            dependency_repository: Dependency graph access
            telemetry_service: Telemetry data source
            alert_repository: Circular dependency alerts
            graph_traversal_service: Graph traversal operations
            composite_service: Composite availability computation
            external_buffer_service: External API adaptive buffer
            error_budget_analyzer: Error budget breakdown
            unachievable_detector: Unachievable SLO detection
        """
        self._service_repo = service_repository
        self._dependency_repo = dependency_repository
        self._telemetry = telemetry_service
        self._alert_repo = alert_repository
        self._graph_traversal = graph_traversal_service
        self._composite = composite_service
        self._external_buffer = external_buffer_service
        self._budget_analyzer = error_budget_analyzer
        self._unachievable_detector = unachievable_detector

    async def execute(
        self, request: ConstraintAnalysisRequest
    ) -> ConstraintAnalysisResponse | None:
        """Execute constraint analysis pipeline.

        Args:
            request: Constraint analysis request with service_id and parameters

        Returns:
            ConstraintAnalysisResponse if analysis succeeds
            None if service not found

        Raises:
            ValueError: If service has no dependencies (cannot analyze)
        """
        # Step 1: Validate service exists
        service = await self._service_repo.get_by_service_id(request.service_id)
        if service is None:
            return None

        # Step 2: Determine desired SLO target
        # Priority: request param > active SLO (future FR-5) > 99.9% default
        desired_target_pct = request.desired_target_pct or 99.9

        # Step 3: Retrieve dependency subgraph
        nodes, edges = await self._graph_traversal.get_subgraph(
            service_id=service.id,
            direction=TraversalDirection.DOWNSTREAM,
            repository=self._dependency_repo,
            max_depth=request.max_depth,
            include_stale=False,
        )

        if not edges:
            raise ValueError(
                f"Service '{request.service_id}' has no dependencies registered. "
                "Cannot perform constraint analysis."
            )

        # Step 4: Classify dependencies
        hard_sync_deps = []
        soft_deps = []
        external_service_ids = set()

        # Build service lookup map
        service_map = {s.id: s for s in nodes}

        for edge in edges:
            target_service = service_map.get(edge.target_service_id)
            if target_service is None:
                continue  # Skip if target not in subgraph

            # Classify as hard/soft
            is_hard = (
                edge.criticality == DependencyCriticality.HARD
                and edge.communication_mode == CommunicationMode.SYNC
            )

            if is_hard:
                hard_sync_deps.append(edge)
            else:
                soft_deps.append(edge)

            # Track external services
            service_type = getattr(target_service, 'service_type', ServiceType.INTERNAL)
            if service_type == ServiceType.EXTERNAL:
                external_service_ids.add(target_service.id)

        # Step 5: Resolve dependency availabilities (parallel queries)
        deps_with_availability = await self._resolve_dependency_availabilities(
            hard_sync_deps, service_map, request.lookback_days
        )

        # Step 6: Fetch service's own availability
        self_avail_sli = await self._telemetry.get_availability_sli(
            service_id=request.service_id, window_days=request.lookback_days
        )
        self_availability = (
            self_avail_sli.availability_ratio if self_avail_sli else 0.999
        )

        # Step 7: Compute composite bound
        composite_result = self._composite.compute_composite_bound(
            service_availability=self_availability,
            dependencies=deps_with_availability,
        )

        # Step 8: Compute error budget breakdown
        error_budget_breakdown = self._budget_analyzer.compute_breakdown(
            service_id=request.service_id,
            slo_target=desired_target_pct,
            service_availability=self_availability,
            dependencies=deps_with_availability,
        )

        # Convert domain breakdown to DTO
        breakdown_dto = await self._convert_error_budget_breakdown(
            error_budget_breakdown, service_map, request.lookback_days
        )

        # Step 9: Check unachievability
        unachievable_warning = self._unachievable_detector.check(
            desired_target_pct=desired_target_pct,
            composite_bound=composite_result.composite_bound,
            hard_dependency_count=len(hard_sync_deps),
        )

        unachievable_warning_dto = None
        if unachievable_warning:
            unachievable_warning_dto = UnachievableWarningDTO(
                desired_target_pct=unachievable_warning.desired_target,
                composite_bound_pct=unachievable_warning.composite_bound,
                gap_pct=unachievable_warning.gap,
                message=unachievable_warning.message,
                remediation_guidance=unachievable_warning.remediation_guidance,
                required_dep_availability_pct=unachievable_warning.required_dep_availability,
            )

        # Step 10: Identify SCC supernodes
        all_alerts = await self._alert_repo.list_by_status(status="open")
        scc_supernodes = [
            alert.cycle_path
            for alert in all_alerts
            if request.service_id in alert.cycle_path
        ]

        # Step 11: Build complete response
        analyzed_at = datetime.now(timezone.utc).isoformat()

        return ConstraintAnalysisResponse(
            service_id=request.service_id,
            analyzed_at=analyzed_at,
            composite_availability_bound_pct=composite_result.composite_bound * 100,
            is_achievable=(unachievable_warning is None),
            has_high_risk_dependencies=bool(
                error_budget_breakdown.high_risk_dependencies
            ),
            error_budget_breakdown=breakdown_dto,
            unachievable_warning=unachievable_warning_dto,
            soft_dependency_risks=[
                service_map[edge.target_service_id].service_id
                for edge in soft_deps
                if edge.target_service_id in service_map
            ],
            scc_supernodes=scc_supernodes,
            dependency_chain_depth=request.max_depth,
            total_hard_dependencies=len(hard_sync_deps),
            total_soft_dependencies=len(soft_deps),
            total_external_dependencies=len(external_service_ids),
            lookback_days=request.lookback_days,
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
        # Prepare parallel telemetry queries
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
    ) -> ErrorBudgetBreakdownDTO:
        """Convert domain ErrorBudgetBreakdown to DTO.

        Args:
            breakdown: Domain ErrorBudgetBreakdown entity
            service_map: Mapping from UUID to Service entity
            lookback_days: Telemetry lookback window

        Returns:
            ErrorBudgetBreakdownDTO
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

        return ErrorBudgetBreakdownDTO(
            service_id=breakdown.service_id,
            slo_target_pct=breakdown.slo_target,
            total_error_budget_minutes=breakdown.total_error_budget_minutes,
            self_consumption_pct=breakdown.self_consumption_pct,
            dependency_risks=risk_dtos,
            high_risk_dependencies=breakdown.high_risk_dependencies,
            total_dependency_consumption_pct=breakdown.total_dependency_consumption_pct,
        )
