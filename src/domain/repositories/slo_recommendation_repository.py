"""Repository interface for SLO recommendations."""

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.slo_recommendation import SliType, SloRecommendation


class SloRecommendationRepositoryInterface(ABC):
    """Interface for persisting and retrieving SLO recommendations."""

    @abstractmethod
    async def get_active_by_service(
        self, service_id: UUID, sli_type: SliType | None = None
    ) -> list[SloRecommendation]:
        """Get active (non-expired, non-superseded) recommendations for a service.

        Args:
            service_id: UUID of the service
            sli_type: Optional filter by SLI type (availability or latency)

        Returns:
            List of active recommendations (empty list if none found)
        """
        pass

    @abstractmethod
    async def save(self, recommendation: SloRecommendation) -> SloRecommendation:
        """Insert or update a recommendation.

        Args:
            recommendation: The recommendation entity to persist

        Returns:
            The persisted recommendation (with any generated fields populated)
        """
        pass

    @abstractmethod
    async def save_batch(self, recommendations: list[SloRecommendation]) -> int:
        """Bulk save recommendations.

        Args:
            recommendations: List of recommendation entities to persist

        Returns:
            Count of recommendations successfully saved
        """
        pass

    @abstractmethod
    async def supersede_existing(self, service_id: UUID, sli_type: SliType) -> int:
        """Mark all active recommendations for service+sli_type as superseded.

        This is typically called before saving a new recommendation to ensure
        only one active recommendation per service+sli_type combination.

        Args:
            service_id: UUID of the service
            sli_type: Type of SLI (availability or latency)

        Returns:
            Count of recommendations marked as superseded
        """
        pass

    @abstractmethod
    async def expire_stale(self) -> int:
        """Mark expired recommendations (past expires_at timestamp).

        Typically run as a background task to clean up stale recommendations.

        Returns:
            Count of recommendations marked as expired
        """
        pass
