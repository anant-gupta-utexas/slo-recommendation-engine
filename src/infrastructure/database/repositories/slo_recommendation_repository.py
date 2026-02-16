"""SLO Recommendation repository implementation using PostgreSQL.

This module implements the SloRecommendationRepositoryInterface using SQLAlchemy
and AsyncPG for PostgreSQL database operations.
"""

from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

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
from src.domain.repositories.slo_recommendation_repository import (
    SloRecommendationRepositoryInterface,
)
from src.infrastructure.database.models import SloRecommendationModel


class SloRecommendationRepository(SloRecommendationRepositoryInterface):
    """PostgreSQL implementation of SloRecommendationRepositoryInterface.

    This repository handles mapping between domain SloRecommendation entities
    and SloRecommendationModel SQLAlchemy models, including JSONB serialization
    for nested structures (tiers, explanation, data_quality).
    """

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self._session = session

    async def get_active_by_service(
        self, service_id: UUID, sli_type: SliType | None = None
    ) -> list[SloRecommendation]:
        """Get active recommendations for a service.

        Args:
            service_id: UUID of the service
            sli_type: Optional filter by SLI type

        Returns:
            List of active recommendations (empty list if none found)
        """
        stmt = select(SloRecommendationModel).where(
            SloRecommendationModel.service_id == service_id,
            SloRecommendationModel.status == RecommendationStatus.ACTIVE.value,
        )

        if sli_type:
            stmt = stmt.where(SloRecommendationModel.sli_type == sli_type.value)

        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [self._to_entity(model) for model in models]

    async def save(self, recommendation: SloRecommendation) -> SloRecommendation:
        """Insert a new recommendation.

        Args:
            recommendation: The recommendation entity to persist

        Returns:
            The persisted recommendation with any generated fields populated
        """
        model = self._to_model(recommendation)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)

        return self._to_entity(model)

    async def save_batch(self, recommendations: list[SloRecommendation]) -> int:
        """Bulk save recommendations.

        Args:
            recommendations: List of recommendation entities to persist

        Returns:
            Count of recommendations successfully saved
        """
        if not recommendations:
            return 0

        models = [self._to_model(rec) for rec in recommendations]
        self._session.add_all(models)
        await self._session.flush()

        return len(models)

    async def supersede_existing(self, service_id: UUID, sli_type: SliType) -> int:
        """Mark all active recommendations as superseded.

        Args:
            service_id: UUID of the service
            sli_type: Type of SLI

        Returns:
            Count of recommendations marked as superseded
        """
        stmt = (
            update(SloRecommendationModel)
            .where(
                SloRecommendationModel.service_id == service_id,
                SloRecommendationModel.sli_type == sli_type.value,
                SloRecommendationModel.status == RecommendationStatus.ACTIVE.value,
            )
            .values(status=RecommendationStatus.SUPERSEDED.value)
        )

        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore

    async def expire_stale(self) -> int:
        """Mark expired recommendations.

        Returns:
            Count of recommendations marked as expired
        """
        now = datetime.now(timezone.utc)

        stmt = (
            update(SloRecommendationModel)
            .where(
                SloRecommendationModel.status == RecommendationStatus.ACTIVE.value,
                SloRecommendationModel.expires_at <= now,
            )
            .values(status=RecommendationStatus.EXPIRED.value)
        )

        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore

    def _to_entity(self, model: SloRecommendationModel) -> SloRecommendation:
        """Convert SQLAlchemy model to domain entity.

        Args:
            model: SloRecommendationModel instance

        Returns:
            SloRecommendation domain entity
        """
        # Parse tiers from JSONB
        tiers: dict[TierLevel, RecommendationTier] = {}
        for level_str, tier_data in model.tiers.items():
            level = TierLevel(level_str)
            tiers[level] = RecommendationTier(
                level=level,
                target=tier_data["target"],
                error_budget_monthly_minutes=tier_data.get("error_budget_monthly_minutes"),
                estimated_breach_probability=tier_data.get("estimated_breach_probability", 0.0),
                confidence_interval=tuple(tier_data["confidence_interval"]) if tier_data.get("confidence_interval") else None,
                percentile=tier_data.get("percentile"),
                target_ms=tier_data.get("target_ms"),
            )

        # Parse explanation from JSONB
        explanation_data = model.explanation
        feature_attribution = [
            FeatureAttribution(
                feature=attr["feature"],
                contribution=attr["contribution"],
                description=attr.get("description", ""),
            )
            for attr in explanation_data.get("feature_attribution", [])
        ]

        dependency_impact = None
        if "dependency_impact" in explanation_data and explanation_data["dependency_impact"]:
            dep_data = explanation_data["dependency_impact"]
            dependency_impact = DependencyImpact(
                composite_availability_bound=dep_data["composite_availability_bound"],
                bottleneck_service=dep_data.get("bottleneck_service"),
                bottleneck_contribution=dep_data.get("bottleneck_contribution", ""),
                hard_dependency_count=dep_data.get("hard_dependency_count", 0),
                soft_dependency_count=dep_data.get("soft_dependency_count", 0),
            )

        explanation = Explanation(
            summary=explanation_data["summary"],
            feature_attribution=feature_attribution,
            dependency_impact=dependency_impact,
        )

        # Parse data quality from JSONB
        quality_data = model.data_quality
        data_quality = DataQuality(
            data_completeness=quality_data["data_completeness"],
            telemetry_gaps=quality_data.get("telemetry_gaps", []),
            confidence_note=quality_data.get("confidence_note", ""),
            is_cold_start=quality_data.get("is_cold_start", False),
            lookback_days_actual=quality_data.get("lookback_days_actual", 30),
        )

        return SloRecommendation(
            id=model.id,
            service_id=model.service_id,
            sli_type=SliType(model.sli_type),
            metric=model.metric,
            tiers=tiers,
            explanation=explanation,
            data_quality=data_quality,
            lookback_window_start=model.lookback_window_start,
            lookback_window_end=model.lookback_window_end,
            generated_at=model.generated_at,
            expires_at=model.expires_at,
            status=RecommendationStatus(model.status),
        )

    def _to_model(self, entity: SloRecommendation) -> SloRecommendationModel:
        """Convert domain entity to SQLAlchemy model.

        Args:
            entity: SloRecommendation domain entity

        Returns:
            SloRecommendationModel instance
        """
        # Serialize tiers to JSONB
        tiers_dict: dict[str, dict] = {}
        for level, tier in entity.tiers.items():
            tiers_dict[level.value] = {
                "target": tier.target,
                "error_budget_monthly_minutes": tier.error_budget_monthly_minutes,
                "estimated_breach_probability": tier.estimated_breach_probability,
                "confidence_interval": list(tier.confidence_interval) if tier.confidence_interval else None,
                "percentile": tier.percentile,
                "target_ms": tier.target_ms,
            }

        # Serialize explanation to JSONB
        feature_attribution_list = [
            {
                "feature": attr.feature,
                "contribution": attr.contribution,
                "description": attr.description,
            }
            for attr in entity.explanation.feature_attribution
        ]

        dependency_impact_dict = None
        if entity.explanation.dependency_impact:
            dep = entity.explanation.dependency_impact
            dependency_impact_dict = {
                "composite_availability_bound": dep.composite_availability_bound,
                "bottleneck_service": dep.bottleneck_service,
                "bottleneck_contribution": dep.bottleneck_contribution,
                "hard_dependency_count": dep.hard_dependency_count,
                "soft_dependency_count": dep.soft_dependency_count,
            }

        explanation_dict = {
            "summary": entity.explanation.summary,
            "feature_attribution": feature_attribution_list,
            "dependency_impact": dependency_impact_dict,
        }

        # Serialize data quality to JSONB
        data_quality_dict = {
            "data_completeness": entity.data_quality.data_completeness,
            "telemetry_gaps": entity.data_quality.telemetry_gaps,
            "confidence_note": entity.data_quality.confidence_note,
            "is_cold_start": entity.data_quality.is_cold_start,
            "lookback_days_actual": entity.data_quality.lookback_days_actual,
        }

        return SloRecommendationModel(
            id=entity.id,
            service_id=entity.service_id,
            sli_type=entity.sli_type.value,
            metric=entity.metric,
            tiers=tiers_dict,
            explanation=explanation_dict,
            data_quality=data_quality_dict,
            lookback_window_start=entity.lookback_window_start,
            lookback_window_end=entity.lookback_window_end,
            generated_at=entity.generated_at,
            expires_at=entity.expires_at,
            status=entity.status.value,
        )
