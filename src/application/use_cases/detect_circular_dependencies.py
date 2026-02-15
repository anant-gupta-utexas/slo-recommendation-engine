"""Detect circular dependencies use case.

This module implements the use case for detecting circular dependencies
using Tarjan's algorithm.
"""

from uuid import UUID

from src.domain.entities.circular_dependency_alert import (
    AlertStatus,
    CircularDependencyAlert,
)
from src.domain.repositories.circular_dependency_alert_repository import (
    CircularDependencyAlertRepositoryInterface,
)
from src.domain.repositories.dependency_repository import DependencyRepositoryInterface
from src.domain.repositories.service_repository import ServiceRepositoryInterface
from src.domain.services.circular_dependency_detector import (
    CircularDependencyDetector,
)


class DetectCircularDependenciesUseCase:
    """Use case for detecting circular dependencies in the graph.

    This use case runs Tarjan's algorithm on the full dependency graph
    and creates alerts for any detected cycles.
    """

    def __init__(
        self,
        service_repository: ServiceRepositoryInterface,
        dependency_repository: DependencyRepositoryInterface,
        alert_repository: CircularDependencyAlertRepositoryInterface,
        detector: CircularDependencyDetector,
    ):
        """Initialize the use case.

        Args:
            service_repository: Repository for service operations
            dependency_repository: Repository for dependency operations
            alert_repository: Repository for alert operations
            detector: Circular dependency detector (Tarjan's algorithm)
        """
        self.service_repository = service_repository
        self.dependency_repository = dependency_repository
        self.alert_repository = alert_repository
        self.detector = detector

    async def execute(self) -> list[CircularDependencyAlert]:
        """Execute the detect circular dependencies use case.

        Returns:
            List of newly created CircularDependencyAlert entities

        Raises:
            None - Errors are logged but not raised to allow graceful handling
        """
        # Get full graph as adjacency list
        adjacency_list = await self.dependency_repository.get_adjacency_list()

        # Run Tarjan's algorithm to detect cycles
        cycles = await self.detector.detect_cycles(adjacency_list)

        # Create alerts for new cycles
        created_alerts: list[CircularDependencyAlert] = []

        for cycle in cycles:
            # Convert UUIDs to service_ids for the alert
            service_ids = await self._convert_uuids_to_service_ids(cycle)

            # Check if alert already exists for this cycle
            exists = await self.alert_repository.exists_for_cycle(service_ids)

            if not exists:
                # Create new alert
                alert = CircularDependencyAlert(
                    cycle_path=service_ids, status=AlertStatus.OPEN
                )

                try:
                    created_alert = await self.alert_repository.create(alert)
                    created_alerts.append(created_alert)
                except ValueError:
                    # Alert might have been created by another process (race condition)
                    # This is acceptable - just skip it
                    pass

        return created_alerts

    async def _convert_uuids_to_service_ids(self, uuids: list[UUID]) -> list[str]:
        """Convert list of service UUIDs to service_ids.

        Args:
            uuids: List of service UUIDs

        Returns:
            List of service business identifiers
        """
        service_ids: list[str] = []

        for uuid in uuids:
            service = await self.service_repository.get_by_id(uuid)
            if service:
                service_ids.append(service.service_id)
            else:
                # Fallback if service not found (shouldn't happen in practice)
                service_ids.append(str(uuid))

        return service_ids
