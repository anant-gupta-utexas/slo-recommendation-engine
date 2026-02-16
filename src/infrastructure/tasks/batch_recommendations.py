"""Scheduled task for batch SLO recommendation computation.

This task periodically computes SLO recommendations for all active services
that don't have recent recommendations, ensuring pre-computed results are
available for fast API responses.
"""

import time

import structlog

from src.application.use_cases.batch_compute_recommendations import (
    BatchComputeRecommendationsUseCase,
)
from src.application.use_cases.generate_slo_recommendation import (
    GenerateSloRecommendationUseCase,
)
from src.domain.repositories.telemetry_query_service import (
    TelemetryQueryServiceInterface,
)
from src.domain.services.availability_calculator import AvailabilityCalculator
from src.domain.services.composite_availability_service import (
    CompositeAvailabilityService,
)
from src.domain.services.graph_traversal_service import GraphTraversalService
from src.domain.services.latency_calculator import LatencyCalculator
from src.domain.services.weighted_attribution_service import (
    WeightedAttributionService,
)
from src.infrastructure.database.config import get_session_factory
from src.infrastructure.database.repositories.dependency_repository import (
    DependencyRepository,
)
from src.infrastructure.database.repositories.service_repository import (
    ServiceRepository,
)
from src.infrastructure.database.repositories.slo_recommendation_repository import (
    SloRecommendationRepository,
)
from src.infrastructure.observability.metrics import record_batch_recommendation_run
from src.infrastructure.telemetry.mock_prometheus_client import MockPrometheusClient

logger = structlog.get_logger(__name__)


async def batch_compute_recommendations() -> None:
    """Scheduled task to compute SLO recommendations for all active services.

    This task:
    1. Queries all services from the database
    2. Calls BatchComputeRecommendationsUseCase to compute recommendations
    3. Logs success/failure summary
    4. Emits Prometheus metrics

    Errors are logged but not raised to prevent scheduler from stopping.
    """
    logger.info("Starting batch SLO recommendation computation")
    start_time = time.time()
    status = "failure"  # Default to failure, set to success if completed

    try:
        # Initialize repositories and services
        session_factory = get_session_factory()
        async with session_factory() as session:
            service_repo = ServiceRepository(session)
            dependency_repo = DependencyRepository(session)
            slo_recommendation_repo = SloRecommendationRepository(session)

            # Initialize telemetry client
            telemetry_service: TelemetryQueryServiceInterface = MockPrometheusClient()

            # Initialize domain services
            availability_calculator = AvailabilityCalculator()
            latency_calculator = LatencyCalculator()
            composite_availability_service = CompositeAvailabilityService()
            weighted_attribution_service = WeightedAttributionService()
            graph_traversal_service = GraphTraversalService()

            # Create GenerateSloRecommendation use case
            generate_use_case = GenerateSloRecommendationUseCase(
                service_repo=service_repo,
                dependency_repo=dependency_repo,
                slo_recommendation_repo=slo_recommendation_repo,
                telemetry_service=telemetry_service,
                availability_calculator=availability_calculator,
                latency_calculator=latency_calculator,
                composite_availability_service=composite_availability_service,
                weighted_attribution_service=weighted_attribution_service,
                graph_traversal_service=graph_traversal_service,
            )

            # Create batch use case
            use_case = BatchComputeRecommendationsUseCase(
                service_repo=service_repo,
                generate_use_case=generate_use_case,
            )

            # Execute batch computation
            result = await use_case.execute()

            duration = time.time() - start_time
            status = "success"

            logger.info(
                "Batch SLO recommendation computation completed",
                total_services=result.total_services,
                successful_count=result.successful_count,
                failed_count=result.failed_count,
                duration_seconds=round(duration, 2),
            )

            # Log failures if any
            if result.failures:
                for failure in result.failures:
                    logger.warning(
                        "Failed to compute recommendation for service",
                        service_id=failure.service_id,
                        error_message=failure.error_message,
                    )

    except Exception as e:
        # Unexpected errors
        duration = time.time() - start_time
        logger.exception(
            "Unexpected error during batch SLO recommendation computation",
            error=str(e),
            error_type=type(e).__name__,
            duration_seconds=round(duration, 2),
        )

    finally:
        # Record metrics regardless of success/failure
        duration = time.time() - start_time
        record_batch_recommendation_run(status=status, duration=duration)

        logger.info(
            "Batch SLO recommendation computation task completed",
            status=status,
            duration_seconds=round(duration, 2),
        )
