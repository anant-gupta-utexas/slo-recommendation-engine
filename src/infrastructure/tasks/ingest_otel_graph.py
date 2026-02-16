"""Scheduled task for OTel Service Graph ingestion.

This task periodically queries Prometheus for OTel Service Graph metrics
and ingests discovered service dependencies into the graph database.
"""

import logging

from src.application.use_cases.ingest_dependency_graph import (
    IngestDependencyGraphUseCase,
)
from src.infrastructure.database.config import get_session_factory
from src.infrastructure.database.repositories.circular_dependency_alert_repository import (
    CircularDependencyAlertRepository,
)
from src.infrastructure.database.repositories.dependency_repository import (
    DependencyRepository,
)
from src.infrastructure.database.repositories.service_repository import (
    ServiceRepository,
)
from src.infrastructure.integrations.otel_service_graph import (
    OTelServiceGraphClient,
    OTelServiceGraphError,
)

logger = logging.getLogger(__name__)


async def ingest_otel_service_graph() -> None:
    """Scheduled task to ingest OTel Service Graph from Prometheus.

    This task:
    1. Queries Prometheus for service graph metrics
    2. Converts metrics to DependencyGraphIngestRequest
    3. Calls IngestDependencyGraphUseCase to persist the graph

    Errors are logged but not raised to prevent scheduler from stopping.
    """
    logger.info("Starting OTel Service Graph ingestion task")

    try:
        # Fetch service graph from Prometheus
        async with OTelServiceGraphClient() as client:
            graph_request = await client.fetch_service_graph()

        # Skip if no data discovered
        if not graph_request.nodes and not graph_request.edges:
            logger.info(
                "No service graph data found in Prometheus, skipping ingestion"
            )
            return

        # Initialize repositories and use case
        session_factory = get_session_factory()
        async with session_factory() as session:
            service_repo = ServiceRepository(session)
            dependency_repo = DependencyRepository(session)
            alert_repo = CircularDependencyAlertRepository(session)

            use_case = IngestDependencyGraphUseCase(
                service_repository=service_repo,
                dependency_repository=dependency_repo,
                alert_repository=alert_repo,
            )

            # Execute ingestion
            response = await use_case.execute(graph_request)

            logger.info(
                "OTel Service Graph ingestion completed",
                nodes_upserted=response.nodes_upserted,
                edges_upserted=response.edges_upserted,
                circular_dependencies=len(response.circular_dependencies_detected),
                warnings_count=len(response.warnings),
            )

            # Log any warnings
            for warning in response.warnings:
                logger.warning(
                    "Ingestion warning",
                    code=warning.code,
                    message=warning.message,
                )

            # Log circular dependencies detected
            for circular_dep in response.circular_dependencies_detected:
                logger.warning(
                    "Circular dependency detected",
                    alert_id=str(circular_dep.alert_id),
                    cycle_path=circular_dep.cycle_path,
                )

    except OTelServiceGraphError as e:
        # OTel-specific errors (Prometheus unavailable, invalid metrics)
        logger.error(
            "Failed to fetch OTel Service Graph",
            error=str(e),
            error_type=type(e).__name__,
        )

    except Exception as e:
        # Unexpected errors
        logger.exception(
            "Unexpected error during OTel Service Graph ingestion",
            error=str(e),
        )

    logger.info("OTel Service Graph ingestion task completed")
