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
from src.application.use_cases.ingest_dependency_graph import (
    IngestDependencyGraphUseCase,
)
from src.application.use_cases.query_dependency_subgraph import (
    QueryDependencySubgraphUseCase,
)
from src.domain.services.circular_dependency_detector import CircularDependencyDetector
from src.domain.services.edge_merge_service import EdgeMergeService
from src.domain.services.graph_traversal_service import GraphTraversalService
from src.infrastructure.database.repositories.circular_dependency_alert_repository import (
    CircularDependencyAlertRepository,
)
from src.infrastructure.database.repositories.dependency_repository import (
    DependencyRepository,
)
from src.infrastructure.database.repositories.service_repository import (
    ServiceRepository,
)
from src.infrastructure.database.session import get_async_session


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
