"""Generate SLO Recommendations Use Case (FR-2).

Orchestrates the full recommendation generation pipeline for a single service.
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from src.application.dtos.slo_recommendation_dto import (
    DataQualityDTO,
    DependencyImpactDTO,
    ExplanationDTO,
    FeatureAttributionDTO,
    GenerateRecommendationRequest,
    GenerateRecommendationResponse,
    LookbackWindowDTO,
    RecommendationDTO,
    TierDTO,
)
from src.domain.entities.service_dependency import (
    CommunicationMode,
    DependencyCriticality,
)
from src.domain.entities.sli_data import AvailabilitySliData, LatencySliData
from src.domain.entities.slo_recommendation import (
    DataQuality,
    DependencyImpact,
    Explanation,
    FeatureAttribution,
    RecommendationStatus,
    RecommendationTier,
    SliType,
    SloRecommendation,
    TierLevel,
)
from src.domain.repositories.dependency_repository import (
    DependencyRepositoryInterface,
)
from src.domain.repositories.service_repository import ServiceRepositoryInterface
from src.domain.repositories.slo_recommendation_repository import (
    SloRecommendationRepositoryInterface,
)
from src.domain.repositories.telemetry_query_service import (
    TelemetryQueryServiceInterface,
)
from src.domain.services.availability_calculator import AvailabilityCalculator
from src.domain.services.composite_availability_service import (
    CompositeAvailabilityService,
    DependencyWithAvailability,
)
from src.domain.services.graph_traversal_service import (
    GraphTraversalService,
    TraversalDirection,
)
from src.domain.services.latency_calculator import LatencyCalculator
from src.domain.services.weighted_attribution_service import (
    WeightedAttributionService,
)

logger = logging.getLogger(__name__)


# Constants
DATA_COMPLETENESS_THRESHOLD = 0.90
DEFAULT_LOOKBACK_DAYS = 30
EXTENDED_LOOKBACK_DAYS = 90
DEFAULT_DEPENDENCY_AVAILABILITY = 0.999  # 99.9%
DEPENDENCY_GRAPH_MAX_DEPTH = 3


class GenerateSloRecommendationUseCase:
    """Generate SLO recommendations for a single service.

    Pipeline:
    1. Validate service exists and has sufficient data
    2. Determine lookback window (standard 30d or extended cold-start)
    3. Query telemetry data via TelemetryQueryServiceInterface
    4. Retrieve dependency subgraph (downstream, depth=3)
    5. Compute composite availability bound
    6. Compute availability recommendation tiers
    7. Compute latency recommendation tiers
    8. Generate weighted feature attribution
    9. Build explanation and data quality metadata
    10. Supersede existing recommendations
    11. Save new recommendations
    12. Return response DTO
    """

    def __init__(
        self,
        service_repository: ServiceRepositoryInterface,
        dependency_repository: DependencyRepositoryInterface,
        recommendation_repository: SloRecommendationRepositoryInterface,
        telemetry_service: TelemetryQueryServiceInterface,
        availability_calculator: AvailabilityCalculator,
        latency_calculator: LatencyCalculator,
        composite_service: CompositeAvailabilityService,
        attribution_service: WeightedAttributionService,
        graph_traversal_service: GraphTraversalService,
    ):
        self.service_repository = service_repository
        self.dependency_repository = dependency_repository
        self.recommendation_repository = recommendation_repository
        self.telemetry_service = telemetry_service
        self.availability_calculator = availability_calculator
        self.latency_calculator = latency_calculator
        self.composite_service = composite_service
        self.attribution_service = attribution_service
        self.graph_traversal_service = graph_traversal_service

    async def execute(
        self, request: GenerateRecommendationRequest
    ) -> GenerateRecommendationResponse | None:
        """Execute the recommendation generation pipeline.

        Returns:
            GenerateRecommendationResponse if successful, None if service not found
        """
        logger.info(f"Generating SLO recommendations for service: {request.service_id}")

        # Step 1: Validate service exists
        service = await self.service_repository.get_by_service_id(request.service_id)
        if not service:
            logger.warning(f"Service not found: {request.service_id}")
            return None

        # Step 2: Determine lookback window (with cold-start logic)
        lookback_days, is_cold_start = await self._determine_lookback_window(
            request.service_id, request.lookback_days
        )
        window_end = datetime.now(timezone.utc)
        window_start = window_end - timedelta(days=lookback_days)

        logger.info(
            f"Using lookback window: {lookback_days} days "
            f"(cold_start={is_cold_start}) for {request.service_id}"
        )

        # Step 3: Determine which SLIs to compute
        compute_availability = request.sli_type in ("all", "availability")
        compute_latency = request.sli_type in ("all", "latency")

        recommendations: list[RecommendationDTO] = []

        # Step 4: Generate availability recommendation if requested
        if compute_availability:
            avail_rec = await self._generate_availability_recommendation(
                service.id,
                request.service_id,
                lookback_days,
                is_cold_start,
                window_start,
                window_end,
            )
            if avail_rec:
                recommendations.append(avail_rec)

        # Step 5: Generate latency recommendation if requested
        if compute_latency:
            latency_rec = await self._generate_latency_recommendation(
                service.id,
                request.service_id,
                lookback_days,
                is_cold_start,
                window_start,
                window_end,
            )
            if latency_rec:
                recommendations.append(latency_rec)

        # Step 6: Build response
        response = GenerateRecommendationResponse(
            service_id=request.service_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            lookback_window=LookbackWindowDTO(
                start=window_start.isoformat(), end=window_end.isoformat()
            ),
            recommendations=recommendations,
        )

        logger.info(
            f"Generated {len(recommendations)} recommendation(s) for {request.service_id}"
        )
        return response

    async def _determine_lookback_window(
        self, service_id: str, requested_lookback_days: int
    ) -> tuple[int, bool]:
        """Determine lookback window with cold-start logic.

        Returns:
            (actual_lookback_days, is_cold_start)
        """
        # Check data completeness for requested window
        data_completeness = await self.telemetry_service.get_data_completeness(
            service_id, requested_lookback_days
        )

        # If sufficient data, use requested window
        if data_completeness >= DATA_COMPLETENESS_THRESHOLD:
            return requested_lookback_days, False

        # Otherwise, try extended lookback for cold-start
        logger.warning(
            f"Insufficient data completeness ({data_completeness:.2%}) "
            f"for {service_id}, attempting extended lookback"
        )

        extended_completeness = await self.telemetry_service.get_data_completeness(
            service_id, EXTENDED_LOOKBACK_DAYS
        )

        return EXTENDED_LOOKBACK_DAYS, True

    async def _generate_availability_recommendation(
        self,
        service_uuid: UUID,
        service_id: str,
        lookback_days: int,
        is_cold_start: bool,
        window_start: datetime,
        window_end: datetime,
    ) -> RecommendationDTO | None:
        """Generate availability SLO recommendation."""
        logger.info(f"Generating availability recommendation for {service_id}")

        # Fetch availability telemetry
        avail_sli = await self.telemetry_service.get_availability_sli(
            service_id, lookback_days
        )
        if not avail_sli:
            logger.warning(f"No availability telemetry for {service_id}")
            return None

        # Fetch rolling availability for breach probability estimation
        rolling_avail = await self.telemetry_service.get_rolling_availability(
            service_id, lookback_days, bucket_hours=24
        )

        # Fetch dependency subgraph (include stale edges to get full picture)
        nodes, edges = await self.graph_traversal_service.get_subgraph(
            service_uuid,
            direction=TraversalDirection.DOWNSTREAM,
            repository=self.dependency_repository,
            max_depth=DEPENDENCY_GRAPH_MAX_DEPTH,
            include_stale=False,  # Only include active dependencies
        )

        # Filter hard sync dependencies
        hard_deps = [
            e
            for e in edges
            if e.criticality == DependencyCriticality.HARD
            and e.communication_mode == CommunicationMode.SYNC
        ]
        soft_dep_count = len(
            [e for e in edges if e.criticality in (DependencyCriticality.SOFT, DependencyCriticality.DEGRADED)]
        )

        # Fetch dependency availabilities
        dep_availabilities: list[DependencyWithAvailability] = []
        for dep in hard_deps:
            target_service = next(
                (n for n in nodes if n.id == dep.target_service_id), None
            )
            if not target_service:
                continue

            dep_avail_sli = await self.telemetry_service.get_availability_sli(
                target_service.service_id, lookback_days
            )
            dep_avail = (
                dep_avail_sli.availability_ratio
                if dep_avail_sli
                else DEFAULT_DEPENDENCY_AVAILABILITY
            )
            dep_availabilities.append(
                DependencyWithAvailability(
                    service_id=target_service.id,
                    service_name=target_service.service_id,
                    availability=dep_avail,
                    is_hard=True,
                )
            )

        # Compute composite availability bound
        composite_result = self.composite_service.compute_composite_bound(
            service_availability=avail_sli.availability_ratio,
            dependencies=dep_availabilities,
        )

        # Compute tiers
        tiers_domain = self.availability_calculator.compute_tiers(
            historical_availability=avail_sli.availability_ratio,
            rolling_availabilities=rolling_avail,
            composite_bound=composite_result.composite_bound,
        )

        # Compute feature attribution
        feature_values = {
            "historical_availability_mean": avail_sli.availability_ratio,
            "downstream_dependency_risk": 1.0 - composite_result.composite_bound,
            "external_api_reliability": (
                min(d.availability for d in dep_availabilities)
                if dep_availabilities
                else 1.0
            ),
            "deployment_frequency": 0.5,  # Placeholder
        }
        attributions = self.attribution_service.compute_attribution(
            SliType.AVAILABILITY, feature_values
        )

        # Build explanation summary
        summary = self._build_availability_summary(
            service_id,
            avail_sli.availability_ratio,
            tiers_domain[TierLevel.BALANCED].target,
            composite_result.composite_bound,
            len(hard_deps),
            lookback_days,
        )

        # Build domain entities
        explanation_domain = Explanation(
            summary=summary,
            feature_attribution=[
                FeatureAttribution(a.feature, a.contribution, a.description)
                for a in attributions
            ],
            dependency_impact=DependencyImpact(
                composite_availability_bound=composite_result.composite_bound,
                bottleneck_service=composite_result.bottleneck_service_name,
                bottleneck_contribution=composite_result.bottleneck_contribution,
                hard_dependency_count=len(hard_deps),
                soft_dependency_count=soft_dep_count,
            ),
        )

        data_completeness = await self.telemetry_service.get_data_completeness(
            service_id, lookback_days
        )
        data_quality_domain = DataQuality(
            data_completeness=data_completeness,
            telemetry_gaps=[],  # Populated if gaps detected
            confidence_note=self._build_confidence_note(
                data_completeness, is_cold_start, lookback_days
            ),
            is_cold_start=is_cold_start,
            lookback_days_actual=lookback_days,
        )

        # Create and save domain entity
        recommendation_entity = SloRecommendation(
            service_id=service_uuid,
            sli_type=SliType.AVAILABILITY,
            tiers=tiers_domain,
            explanation=explanation_domain,
            data_quality=data_quality_domain,
            lookback_window_start=window_start,
            lookback_window_end=window_end,
            metric="error_rate",
            status=RecommendationStatus.ACTIVE,
        )

        # Supersede existing recommendations
        await self.recommendation_repository.supersede_existing(
            service_uuid, SliType.AVAILABILITY
        )

        # Save new recommendation
        await self.recommendation_repository.save(recommendation_entity)

        # Convert to DTO
        return self._convert_to_recommendation_dto(
            recommendation_entity, tiers_domain, explanation_domain, data_quality_domain
        )

    async def _generate_latency_recommendation(
        self,
        service_uuid: UUID,
        service_id: str,
        lookback_days: int,
        is_cold_start: bool,
        window_start: datetime,
        window_end: datetime,
    ) -> RecommendationDTO | None:
        """Generate latency SLO recommendation."""
        logger.info(f"Generating latency recommendation for {service_id}")

        # Fetch latency telemetry
        latency_sli = await self.telemetry_service.get_latency_percentiles(
            service_id, lookback_days
        )
        if not latency_sli:
            logger.warning(f"No latency telemetry for {service_id}")
            return None

        # Compute tiers (assuming no shared infrastructure for MVP)
        # Note: Calculator expects a list of data points, but we have one aggregate
        tiers_list = self.latency_calculator.compute_tiers(
            sli_data=[latency_sli], shared_infrastructure=False
        )
        # Convert list to dict keyed by tier level
        tiers_domain = {tier.level: tier for tier in tiers_list}

        # Compute feature attribution
        feature_values = {
            "p99_latency_historical": latency_sli.p99_ms,
            "call_chain_depth": 3.0,  # Placeholder
            "noisy_neighbor_margin": 0.05,  # 5%
            "traffic_seasonality": 0.5,  # Placeholder
        }
        attributions = self.attribution_service.compute_attribution(
            SliType.LATENCY, feature_values
        )

        # Build explanation summary
        summary = self._build_latency_summary(
            service_id,
            latency_sli.p99_ms,
            tiers_domain[TierLevel.BALANCED].target_ms or 0,
            lookback_days,
        )

        # Build domain entities
        explanation_domain = Explanation(
            summary=summary,
            feature_attribution=[
                FeatureAttribution(a.feature, a.contribution, a.description)
                for a in attributions
            ],
            dependency_impact=None,  # Latency doesn't use dependency impact
        )

        data_completeness = await self.telemetry_service.get_data_completeness(
            service_id, lookback_days
        )
        data_quality_domain = DataQuality(
            data_completeness=data_completeness,
            telemetry_gaps=[],
            confidence_note=self._build_confidence_note(
                data_completeness, is_cold_start, lookback_days
            ),
            is_cold_start=is_cold_start,
            lookback_days_actual=lookback_days,
        )

        # Create and save domain entity
        recommendation_entity = SloRecommendation(
            service_id=service_uuid,
            sli_type=SliType.LATENCY,
            tiers=tiers_domain,
            explanation=explanation_domain,
            data_quality=data_quality_domain,
            lookback_window_start=window_start,
            lookback_window_end=window_end,
            metric="p99_response_time_ms",
            status=RecommendationStatus.ACTIVE,
        )

        # Supersede existing recommendations
        await self.recommendation_repository.supersede_existing(
            service_uuid, SliType.LATENCY
        )

        # Save new recommendation
        await self.recommendation_repository.save(recommendation_entity)

        # Convert to DTO
        return self._convert_to_recommendation_dto(
            recommendation_entity, tiers_domain, explanation_domain, data_quality_domain
        )

    def _build_availability_summary(
        self,
        service_id: str,
        actual_availability: float,
        balanced_target: float,
        composite_bound: float,
        hard_dep_count: int,
        lookback_days: int,
    ) -> str:
        """Build human-readable summary for availability recommendation."""
        margin = (actual_availability * 100) - balanced_target
        summary = (
            f"{service_id} achieved {actual_availability * 100:.2f}% availability "
            f"over {lookback_days} days. The Balanced target of {balanced_target:.1f}% "
            f"provides a {abs(margin):.2f}% {'margin' if margin > 0 else 'deficit'}."
        )
        if hard_dep_count > 0:
            summary += (
                f" Composite availability bound is {composite_bound * 100:.2f}% "
                f"given {hard_dep_count} hard {'dependency' if hard_dep_count == 1 else 'dependencies'}."
            )
        return summary

    def _build_latency_summary(
        self,
        service_id: str,
        p99_latency: float,
        balanced_target_ms: int,
        lookback_days: int,
    ) -> str:
        """Build human-readable summary for latency recommendation."""
        headroom_pct = ((balanced_target_ms - p99_latency) / p99_latency) * 100
        return (
            f"End-to-end p99 latency measured at {p99_latency:.0f}ms over {lookback_days} days. "
            f"Balanced target of {balanced_target_ms}ms provides {abs(headroom_pct):.1f}% headroom."
        )

    def _build_confidence_note(
        self, data_completeness: float, is_cold_start: bool, lookback_days: int
    ) -> str:
        """Build confidence note based on data quality."""
        if is_cold_start:
            return (
                f"Extended lookback to {lookback_days} days due to sparse data. "
                f"Data completeness: {data_completeness:.0%}."
            )
        if data_completeness >= 0.95:
            return (
                f"Based on {lookback_days} days of continuous data with "
                f"{data_completeness:.0%} completeness."
            )
        return (
            f"Based on {lookback_days} days with {data_completeness:.0%} completeness. "
            "Some telemetry gaps detected."
        )

    def _convert_to_recommendation_dto(
        self,
        entity: SloRecommendation,
        tiers_domain: dict[TierLevel, RecommendationTier],
        explanation_domain: Explanation,
        data_quality_domain: DataQuality,
    ) -> RecommendationDTO:
        """Convert domain entity to DTO."""
        # Convert tiers
        tiers_dto = {
            level.value: TierDTO(
                level=level.value,
                target=tier.target,
                error_budget_monthly_minutes=tier.error_budget_monthly_minutes,
                estimated_breach_probability=tier.estimated_breach_probability,
                confidence_interval=tier.confidence_interval,
                percentile=tier.percentile,
                target_ms=tier.target_ms,
            )
            for level, tier in tiers_domain.items()
        }

        # Convert explanation
        explanation_dto = ExplanationDTO(
            summary=explanation_domain.summary,
            feature_attribution=[
                FeatureAttributionDTO(a.feature, a.contribution, a.description)
                for a in explanation_domain.feature_attribution
            ],
            dependency_impact=(
                DependencyImpactDTO(
                    composite_availability_bound=explanation_domain.dependency_impact.composite_availability_bound,
                    bottleneck_service=explanation_domain.dependency_impact.bottleneck_service,
                    bottleneck_contribution=explanation_domain.dependency_impact.bottleneck_contribution,
                    hard_dependency_count=explanation_domain.dependency_impact.hard_dependency_count,
                    soft_dependency_count=explanation_domain.dependency_impact.soft_dependency_count,
                )
                if explanation_domain.dependency_impact
                else None
            ),
        )

        # Convert data quality
        data_quality_dto = DataQualityDTO(
            data_completeness=data_quality_domain.data_completeness,
            telemetry_gaps=data_quality_domain.telemetry_gaps,
            confidence_note=data_quality_domain.confidence_note,
            is_cold_start=data_quality_domain.is_cold_start,
            lookback_days_actual=data_quality_domain.lookback_days_actual,
        )

        return RecommendationDTO(
            sli_type=entity.sli_type.value,
            metric=entity.metric,
            tiers=tiers_dto,
            explanation=explanation_dto,
            data_quality=data_quality_dto,
        )
