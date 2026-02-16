"""Integration tests for SloRecommendationRepository.

This module tests the SloRecommendationRepository implementation against
a real PostgreSQL database using testcontainers.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.service import Criticality, Service
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
from src.infrastructure.database.repositories.service_repository import ServiceRepository
from src.infrastructure.database.repositories.slo_recommendation_repository import SloRecommendationRepository


@pytest.mark.integration
class TestSloRecommendationRepository:
    """Integration tests for SloRecommendationRepository."""

    @pytest.fixture
    def repository(self, db_session: AsyncSession) -> SloRecommendationRepository:
        """Create SloRecommendationRepository instance for testing.

        Args:
            db_session: Database session fixture

        Returns:
            SloRecommendationRepository instance
        """
        return SloRecommendationRepository(db_session)

    @pytest.fixture
    def service_repository(self, db_session: AsyncSession) -> ServiceRepository:
        """Create ServiceRepository instance for testing.

        Args:
            db_session: Database session fixture

        Returns:
            ServiceRepository instance
        """
        return ServiceRepository(db_session)

    @pytest.fixture
    async def test_service(self, service_repository: ServiceRepository) -> Service:
        """Create a test service in the database.

        Args:
            service_repository: ServiceRepository instance

        Returns:
            Created Service entity
        """
        service = Service(
            service_id="payment-service",
            metadata={"version": "2.0.0"},
            criticality=Criticality.CRITICAL,
            team="payments-team",
        )
        return await service_repository.create(service)

    @pytest.fixture
    def sample_availability_recommendation(
        self, test_service: Service
    ) -> SloRecommendation:
        """Create a sample availability recommendation for testing.

        Args:
            test_service: Test service fixture

        Returns:
            SloRecommendation entity with availability data
        """
        now = datetime.now(timezone.utc)

        tiers = {
            TierLevel.CONSERVATIVE: RecommendationTier(
                level=TierLevel.CONSERVATIVE,
                target=99.5,
                error_budget_monthly_minutes=216.0,
                estimated_breach_probability=0.05,
                confidence_interval=(99.3, 99.7),
            ),
            TierLevel.BALANCED: RecommendationTier(
                level=TierLevel.BALANCED,
                target=99.0,
                error_budget_monthly_minutes=432.0,
                estimated_breach_probability=0.15,
                confidence_interval=(98.8, 99.2),
            ),
            TierLevel.AGGRESSIVE: RecommendationTier(
                level=TierLevel.AGGRESSIVE,
                target=98.0,
                error_budget_monthly_minutes=864.0,
                estimated_breach_probability=0.30,
                confidence_interval=(97.5, 98.5),
            ),
        }

        explanation = Explanation(
            summary="Recommendation based on 30 days of telemetry with 95% completeness.",
            feature_attribution=[
                FeatureAttribution(
                    feature="historical_availability_mean",
                    contribution=0.40,
                    description="Average availability over lookback period",
                ),
                FeatureAttribution(
                    feature="historical_availability_variance",
                    contribution=0.30,
                    description="Consistency of availability",
                ),
            ],
            dependency_impact=DependencyImpact(
                composite_availability_bound=0.995,
                bottleneck_service="database-service",
                bottleneck_contribution="Database availability limits to 99.5%",
                hard_dependency_count=2,
                soft_dependency_count=1,
            ),
        )

        data_quality = DataQuality(
            data_completeness=0.95,
            telemetry_gaps=[],
            confidence_note="High confidence with 30 days of data",
            is_cold_start=False,
            lookback_days_actual=30,
        )

        return SloRecommendation(
            service_id=test_service.id,
            sli_type=SliType.AVAILABILITY,
            metric="error_rate",
            tiers=tiers,
            explanation=explanation,
            data_quality=data_quality,
            lookback_window_start=now - timedelta(days=30),
            lookback_window_end=now,
            generated_at=now,
        )

    @pytest.fixture
    def sample_latency_recommendation(self, test_service: Service) -> SloRecommendation:
        """Create a sample latency recommendation for testing.

        Args:
            test_service: Test service fixture

        Returns:
            SloRecommendation entity with latency data
        """
        now = datetime.now(timezone.utc)

        tiers = {
            TierLevel.CONSERVATIVE: RecommendationTier(
                level=TierLevel.CONSERVATIVE,
                target=1050.0,
                estimated_breach_probability=0.001,
                percentile="p999",
                target_ms=1050,
            ),
            TierLevel.BALANCED: RecommendationTier(
                level=TierLevel.BALANCED,
                target=525.0,
                estimated_breach_probability=0.05,
                percentile="p99",
                target_ms=525,
            ),
            TierLevel.AGGRESSIVE: RecommendationTier(
                level=TierLevel.AGGRESSIVE,
                target=250.0,
                estimated_breach_probability=0.20,
                percentile="p95",
                target_ms=250,
            ),
        }

        explanation = Explanation(
            summary="Latency recommendation based on 30 days of telemetry.",
            feature_attribution=[
                FeatureAttribution(
                    feature="p99_latency",
                    contribution=0.50,
                    description="99th percentile latency",
                ),
                FeatureAttribution(
                    feature="latency_variance",
                    contribution=0.22,
                    description="Latency consistency",
                ),
            ],
        )

        data_quality = DataQuality(
            data_completeness=0.98,
            telemetry_gaps=[],
            confidence_note="Very high confidence",
            is_cold_start=False,
            lookback_days_actual=30,
        )

        return SloRecommendation(
            service_id=test_service.id,
            sli_type=SliType.LATENCY,
            metric="p99_response_time_ms",
            tiers=tiers,
            explanation=explanation,
            data_quality=data_quality,
            lookback_window_start=now - timedelta(days=30),
            lookback_window_end=now,
            generated_at=now,
        )

    async def test_save_recommendation(
        self,
        repository: SloRecommendationRepository,
        sample_availability_recommendation: SloRecommendation,
    ):
        """Test saving a new recommendation.

        Args:
            repository: SloRecommendationRepository instance
            sample_availability_recommendation: Sample recommendation entity
        """
        # Act
        saved = await repository.save(sample_availability_recommendation)

        # Assert
        assert saved.id is not None
        assert saved.service_id == sample_availability_recommendation.service_id
        assert saved.sli_type == SliType.AVAILABILITY
        assert saved.metric == "error_rate"
        assert saved.status == RecommendationStatus.ACTIVE
        assert len(saved.tiers) == 3
        assert TierLevel.CONSERVATIVE in saved.tiers
        assert saved.tiers[TierLevel.CONSERVATIVE].target == 99.5
        assert saved.explanation.summary.startswith("Recommendation based on")
        assert len(saved.explanation.feature_attribution) == 2
        assert saved.explanation.dependency_impact is not None
        assert (
            saved.explanation.dependency_impact.composite_availability_bound == 0.995
        )
        assert saved.data_quality.data_completeness == 0.95

    async def test_get_active_by_service(
        self,
        repository: SloRecommendationRepository,
        sample_availability_recommendation: SloRecommendation,
        sample_latency_recommendation: SloRecommendation,
    ):
        """Test retrieving active recommendations for a service.

        Args:
            repository: SloRecommendationRepository instance
            sample_availability_recommendation: Availability recommendation
            sample_latency_recommendation: Latency recommendation
        """
        # Arrange
        await repository.save(sample_availability_recommendation)
        await repository.save(sample_latency_recommendation)

        # Act
        recommendations = await repository.get_active_by_service(
            sample_availability_recommendation.service_id
        )

        # Assert
        assert len(recommendations) == 2
        sli_types = {rec.sli_type for rec in recommendations}
        assert SliType.AVAILABILITY in sli_types
        assert SliType.LATENCY in sli_types

    async def test_get_active_by_service_with_sli_type_filter(
        self,
        repository: SloRecommendationRepository,
        sample_availability_recommendation: SloRecommendation,
        sample_latency_recommendation: SloRecommendation,
    ):
        """Test filtering recommendations by SLI type.

        Args:
            repository: SloRecommendationRepository instance
            sample_availability_recommendation: Availability recommendation
            sample_latency_recommendation: Latency recommendation
        """
        # Arrange
        await repository.save(sample_availability_recommendation)
        await repository.save(sample_latency_recommendation)

        # Act
        availability_recs = await repository.get_active_by_service(
            sample_availability_recommendation.service_id, sli_type=SliType.AVAILABILITY
        )

        # Assert
        assert len(availability_recs) == 1
        assert availability_recs[0].sli_type == SliType.AVAILABILITY
        assert availability_recs[0].metric == "error_rate"

    async def test_get_active_by_service_empty_result(
        self, repository: SloRecommendationRepository
    ):
        """Test that get_active_by_service returns empty list when no recommendations exist.

        Args:
            repository: SloRecommendationRepository instance
        """
        # Act
        recommendations = await repository.get_active_by_service(uuid4())

        # Assert
        assert recommendations == []

    async def test_supersede_existing(
        self,
        repository: SloRecommendationRepository,
        sample_availability_recommendation: SloRecommendation,
    ):
        """Test marking existing recommendations as superseded.

        Args:
            repository: SloRecommendationRepository instance
            sample_availability_recommendation: Sample recommendation entity
        """
        # Arrange
        saved = await repository.save(sample_availability_recommendation)

        # Act
        count = await repository.supersede_existing(
            saved.service_id, SliType.AVAILABILITY
        )

        # Assert
        assert count == 1

        # Verify status changed
        recommendations = await repository.get_active_by_service(saved.service_id)
        assert len(recommendations) == 0

    async def test_supersede_existing_multiple_recommendations(
        self,
        repository: SloRecommendationRepository,
        test_service: Service,
    ):
        """Test superseding multiple old recommendations.

        Args:
            repository: SloRecommendationRepository instance
            test_service: Test service fixture
        """
        # Arrange: Create 3 old availability recommendations
        now = datetime.now(timezone.utc)
        for i in range(3):
            rec = SloRecommendation(
                service_id=test_service.id,
                sli_type=SliType.AVAILABILITY,
                metric="error_rate",
                tiers={
                    TierLevel.CONSERVATIVE: RecommendationTier(
                        level=TierLevel.CONSERVATIVE, target=99.0
                    )
                },
                explanation=Explanation(summary="Old recommendation"),
                data_quality=DataQuality(data_completeness=0.9),
                lookback_window_start=now - timedelta(days=30),
                lookback_window_end=now - timedelta(days=i),
                generated_at=now - timedelta(days=i),
            )
            await repository.save(rec)

        # Act
        count = await repository.supersede_existing(test_service.id, SliType.AVAILABILITY)

        # Assert
        assert count == 3
        active_recs = await repository.get_active_by_service(test_service.id)
        assert len(active_recs) == 0

    async def test_expire_stale(
        self,
        repository: SloRecommendationRepository,
        test_service: Service,
    ):
        """Test marking expired recommendations.

        Args:
            repository: SloRecommendationRepository instance
            test_service: Test service fixture
        """
        # Arrange: Create expired recommendation
        now = datetime.now(timezone.utc)
        expired_rec = SloRecommendation(
            service_id=test_service.id,
            sli_type=SliType.AVAILABILITY,
            metric="error_rate",
            tiers={
                TierLevel.CONSERVATIVE: RecommendationTier(
                    level=TierLevel.CONSERVATIVE, target=99.0
                )
            },
            explanation=Explanation(summary="Expired recommendation"),
            data_quality=DataQuality(data_completeness=0.9),
            lookback_window_start=now - timedelta(days=30),
            lookback_window_end=now - timedelta(days=2),
            generated_at=now - timedelta(days=2),
            expires_at=now - timedelta(hours=1),  # Expired 1 hour ago
        )
        await repository.save(expired_rec)

        # Create active recommendation (not expired)
        active_rec = SloRecommendation(
            service_id=test_service.id,
            sli_type=SliType.LATENCY,
            metric="p99_response_time_ms",
            tiers={
                TierLevel.CONSERVATIVE: RecommendationTier(
                    level=TierLevel.CONSERVATIVE, target=500.0
                )
            },
            explanation=Explanation(summary="Active recommendation"),
            data_quality=DataQuality(data_completeness=0.9),
            lookback_window_start=now - timedelta(days=30),
            lookback_window_end=now,
            generated_at=now,
            expires_at=now + timedelta(hours=23),  # Expires in 23 hours
        )
        await repository.save(active_rec)

        # Act
        count = await repository.expire_stale()

        # Assert
        assert count == 1

        # Verify only the non-expired recommendation is active
        active_recs = await repository.get_active_by_service(test_service.id)
        assert len(active_recs) == 1
        assert active_recs[0].sli_type == SliType.LATENCY

    async def test_save_batch(
        self,
        repository: SloRecommendationRepository,
        test_service: Service,
    ):
        """Test bulk saving recommendations.

        Args:
            repository: SloRecommendationRepository instance
            test_service: Test service fixture
        """
        # Arrange
        now = datetime.now(timezone.utc)
        recommendations = []

        for sli_type in [SliType.AVAILABILITY, SliType.LATENCY]:
            rec = SloRecommendation(
                service_id=test_service.id,
                sli_type=sli_type,
                metric=f"metric_{sli_type.value}",
                tiers={
                    TierLevel.CONSERVATIVE: RecommendationTier(
                        level=TierLevel.CONSERVATIVE, target=99.0
                    )
                },
                explanation=Explanation(summary=f"Batch {sli_type.value}"),
                data_quality=DataQuality(data_completeness=0.95),
                lookback_window_start=now - timedelta(days=30),
                lookback_window_end=now,
                generated_at=now,
            )
            recommendations.append(rec)

        # Act
        count = await repository.save_batch(recommendations)

        # Assert
        assert count == 2

        # Verify saved
        saved_recs = await repository.get_active_by_service(test_service.id)
        assert len(saved_recs) == 2

    async def test_save_batch_empty_list(
        self, repository: SloRecommendationRepository
    ):
        """Test that save_batch handles empty list gracefully.

        Args:
            repository: SloRecommendationRepository instance
        """
        # Act
        count = await repository.save_batch([])

        # Assert
        assert count == 0

    async def test_domain_model_round_trip(
        self,
        repository: SloRecommendationRepository,
        sample_availability_recommendation: SloRecommendation,
    ):
        """Test that domain entity survives save/load round trip.

        Args:
            repository: SloRecommendationRepository instance
            sample_availability_recommendation: Sample recommendation entity
        """
        # Arrange
        original = sample_availability_recommendation

        # Act: Save and retrieve
        await repository.save(original)
        retrieved_list = await repository.get_active_by_service(
            original.service_id, sli_type=original.sli_type
        )

        # Assert
        assert len(retrieved_list) == 1
        retrieved = retrieved_list[0]

        # Verify all fields
        assert retrieved.service_id == original.service_id
        assert retrieved.sli_type == original.sli_type
        assert retrieved.metric == original.metric
        assert retrieved.status == original.status

        # Verify tiers
        assert len(retrieved.tiers) == len(original.tiers)
        for level in [TierLevel.CONSERVATIVE, TierLevel.BALANCED, TierLevel.AGGRESSIVE]:
            orig_tier = original.tiers[level]
            retr_tier = retrieved.tiers[level]
            assert retr_tier.level == orig_tier.level
            assert retr_tier.target == orig_tier.target
            assert (
                retr_tier.error_budget_monthly_minutes
                == orig_tier.error_budget_monthly_minutes
            )
            assert (
                retr_tier.estimated_breach_probability
                == orig_tier.estimated_breach_probability
            )

        # Verify explanation
        assert retrieved.explanation.summary == original.explanation.summary
        assert len(retrieved.explanation.feature_attribution) == len(
            original.explanation.feature_attribution
        )
        assert retrieved.explanation.dependency_impact is not None
        assert (
            retrieved.explanation.dependency_impact.composite_availability_bound
            == original.explanation.dependency_impact.composite_availability_bound
        )

        # Verify data quality
        assert (
            retrieved.data_quality.data_completeness
            == original.data_quality.data_completeness
        )
        assert retrieved.data_quality.is_cold_start == original.data_quality.is_cold_start

    async def test_latency_recommendation_without_dependency_impact(
        self,
        repository: SloRecommendationRepository,
        sample_latency_recommendation: SloRecommendation,
    ):
        """Test that latency recommendations without dependency impact are saved correctly.

        Args:
            repository: SloRecommendationRepository instance
            sample_latency_recommendation: Sample latency recommendation
        """
        # Arrange
        assert sample_latency_recommendation.explanation.dependency_impact is None

        # Act
        saved = await repository.save(sample_latency_recommendation)

        # Assert
        assert saved.explanation.dependency_impact is None

        # Verify retrieval
        retrieved = await repository.get_active_by_service(
            saved.service_id, sli_type=SliType.LATENCY
        )
        assert len(retrieved) == 1
        assert retrieved[0].explanation.dependency_impact is None

    async def test_multiple_services_isolation(
        self,
        repository: SloRecommendationRepository,
        service_repository: ServiceRepository,
    ):
        """Test that recommendations are properly isolated by service_id.

        Args:
            repository: SloRecommendationRepository instance
            service_repository: ServiceRepository instance
        """
        # Arrange: Create two services
        service1 = await service_repository.create(
            Service(service_id="service-1", criticality=Criticality.HIGH)
        )
        service2 = await service_repository.create(
            Service(service_id="service-2", criticality=Criticality.LOW)
        )

        now = datetime.now(timezone.utc)

        # Create recommendations for both services
        for service in [service1, service2]:
            rec = SloRecommendation(
                service_id=service.id,
                sli_type=SliType.AVAILABILITY,
                metric="error_rate",
                tiers={
                    TierLevel.CONSERVATIVE: RecommendationTier(
                        level=TierLevel.CONSERVATIVE, target=99.0
                    )
                },
                explanation=Explanation(summary=f"Rec for {service.service_id}"),
                data_quality=DataQuality(data_completeness=0.9),
                lookback_window_start=now - timedelta(days=30),
                lookback_window_end=now,
                generated_at=now,
            )
            await repository.save(rec)

        # Act
        service1_recs = await repository.get_active_by_service(service1.id)
        service2_recs = await repository.get_active_by_service(service2.id)

        # Assert
        assert len(service1_recs) == 1
        assert len(service2_recs) == 1
        assert service1_recs[0].service_id == service1.id
        assert service2_recs[0].service_id == service2.id
