"""
Dependency injection for FastAPI routes.

Provides factory functions for creating use cases with their required dependencies.
Uses FastAPI's Depends() for dependency injection.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.use_cases.detect_circular_dependencies import (
    DetectCircularDependenciesUseCase,
)
from src.application.use_cases.generate_slo_recommendation import (
    GenerateSloRecommendationUseCase,
)
from src.application.use_cases.get_slo_recommendation import (
    GetSloRecommendationUseCase,
)
from src.application.use_cases.ingest_dependency_graph import (
    IngestDependencyGraphUseCase,
)
from src.application.use_cases.query_dependency_subgraph import (
    QueryDependencySubgraphUseCase,
)
from src.domain.services.availability_calculator import AvailabilityCalculator
from src.domain.services.circular_dependency_detector import CircularDependencyDetector
from src.domain.services.composite_availability_service import (
    CompositeAvailabilityService,
)
from src.domain.services.edge_merge_service import EdgeMergeService
from src.domain.services.graph_traversal_service import GraphTraversalService
from src.domain.services.latency_calculator import LatencyCalculator
from src.domain.services.weighted_attribution_service import (
    WeightedAttributionService,
)
from src.infrastructure.database.repositories.circular_dependency_alert_repository import (
    CircularDependencyAlertRepository,
)
from src.infrastructure.database.repositories.dependency_repository import (
    DependencyRepository,
)
from src.infrastructure.database.repositories.service_repository import (
    ServiceRepository,
)
from src.infrastructure.database.repositories.slo_recommendation_repository import (
    SloRecommendationRepository,
)
from src.infrastructure.database.session import get_async_session
from src.infrastructure.telemetry.mock_prometheus_client import MockPrometheusClient


# Repository factories


async def get_service_repository(
    session: AsyncSession = Depends(get_async_session),
) -> ServiceRepository:
    """Get ServiceRepository instance."""
    return ServiceRepository(session)


async def get_dependency_repository(
    session: AsyncSession = Depends(get_async_session),
) -> DependencyRepository:
    """Get DependencyRepository instance."""
    return DependencyRepository(session)


async def get_circular_dependency_alert_repository(
    session: AsyncSession = Depends(get_async_session),
) -> CircularDependencyAlertRepository:
    """Get CircularDependencyAlertRepository instance."""
    return CircularDependencyAlertRepository(session)


async def get_slo_recommendation_repository(
    session: AsyncSession = Depends(get_async_session),
) -> SloRecommendationRepository:
    """Get SloRecommendationRepository instance."""
    return SloRecommendationRepository(session)


# Domain service factories


def get_edge_merge_service() -> EdgeMergeService:
    """Get EdgeMergeService instance."""
    return EdgeMergeService()


def get_graph_traversal_service() -> GraphTraversalService:
    """Get GraphTraversalService instance."""
    return GraphTraversalService()


def get_circular_dependency_detector() -> CircularDependencyDetector:
    """Get CircularDependencyDetector instance."""
    return CircularDependencyDetector()


def get_availability_calculator() -> AvailabilityCalculator:
    """Get AvailabilityCalculator instance."""
    return AvailabilityCalculator()


def get_latency_calculator() -> LatencyCalculator:
    """Get LatencyCalculator instance."""
    return LatencyCalculator()


def get_composite_availability_service() -> CompositeAvailabilityService:
    """Get CompositeAvailabilityService instance."""
    return CompositeAvailabilityService()


def get_weighted_attribution_service() -> WeightedAttributionService:
    """Get WeightedAttributionService instance."""
    return WeightedAttributionService()


def get_telemetry_service() -> MockPrometheusClient:
    """Get MockPrometheusClient instance (FR-2 telemetry source)."""
    return MockPrometheusClient()


# Use case factories


async def get_ingest_dependency_graph_use_case(
    service_repo: ServiceRepository = Depends(get_service_repository),
    dependency_repo: DependencyRepository = Depends(get_dependency_repository),
    edge_merge_service: EdgeMergeService = Depends(get_edge_merge_service),
) -> IngestDependencyGraphUseCase:
    """Get IngestDependencyGraphUseCase instance."""
    return IngestDependencyGraphUseCase(
        service_repository=service_repo,
        dependency_repository=dependency_repo,
        edge_merge_service=edge_merge_service,
    )


async def get_query_dependency_subgraph_use_case(
    service_repo: ServiceRepository = Depends(get_service_repository),
    dependency_repo: DependencyRepository = Depends(get_dependency_repository),
    graph_traversal_service: GraphTraversalService = Depends(
        get_graph_traversal_service
    ),
) -> QueryDependencySubgraphUseCase:
    """Get QueryDependencySubgraphUseCase instance."""
    return QueryDependencySubgraphUseCase(
        service_repository=service_repo,
        dependency_repository=dependency_repo,
        graph_traversal_service=graph_traversal_service,
    )


async def get_detect_circular_dependencies_use_case(
    service_repo: ServiceRepository = Depends(get_service_repository),
    dependency_repo: DependencyRepository = Depends(get_dependency_repository),
    alert_repo: CircularDependencyAlertRepository = Depends(
        get_circular_dependency_alert_repository
    ),
    detector: CircularDependencyDetector = Depends(get_circular_dependency_detector),
) -> DetectCircularDependenciesUseCase:
    """Get DetectCircularDependenciesUseCase instance."""
    return DetectCircularDependenciesUseCase(
        service_repository=service_repo,
        dependency_repository=dependency_repo,
        alert_repository=alert_repo,
        detector=detector,
    )


async def get_generate_slo_recommendation_use_case(
    service_repo: ServiceRepository = Depends(get_service_repository),
    dependency_repo: DependencyRepository = Depends(get_dependency_repository),
    recommendation_repo: SloRecommendationRepository = Depends(
        get_slo_recommendation_repository
    ),
    telemetry_service: MockPrometheusClient = Depends(get_telemetry_service),
    availability_calculator: AvailabilityCalculator = Depends(
        get_availability_calculator
    ),
    latency_calculator: LatencyCalculator = Depends(get_latency_calculator),
    composite_service: CompositeAvailabilityService = Depends(
        get_composite_availability_service
    ),
    attribution_service: WeightedAttributionService = Depends(
        get_weighted_attribution_service
    ),
    graph_traversal_service: GraphTraversalService = Depends(
        get_graph_traversal_service
    ),
) -> GenerateSloRecommendationUseCase:
    """Get GenerateSloRecommendationUseCase instance."""
    return GenerateSloRecommendationUseCase(
        service_repository=service_repo,
        dependency_repository=dependency_repo,
        recommendation_repository=recommendation_repo,
        telemetry_service=telemetry_service,
        availability_calculator=availability_calculator,
        latency_calculator=latency_calculator,
        composite_service=composite_service,
        attribution_service=attribution_service,
        graph_traversal_service=graph_traversal_service,
    )


async def get_get_slo_recommendation_use_case(
    service_repo: ServiceRepository = Depends(get_service_repository),
    generate_use_case: GenerateSloRecommendationUseCase = Depends(
        get_generate_slo_recommendation_use_case
    ),
) -> GetSloRecommendationUseCase:
    """Get GetSloRecommendationUseCase instance."""
    return GetSloRecommendationUseCase(
        service_repo=service_repo,
        generate_use_case=generate_use_case,
    )
