"""Unit tests for ExternalApiBufferService."""

from uuid import uuid4

import pytest

from src.domain.entities.constraint_analysis import ExternalProviderProfile
from src.domain.services.external_api_buffer_service import ExternalApiBufferService


class TestExternalApiBufferService:
    """Tests for ExternalApiBufferService."""

    @pytest.fixture
    def service(self) -> ExternalApiBufferService:
        """Create an ExternalApiBufferService instance."""
        return ExternalApiBufferService()

    def test_compute_effective_availability_trd_validation(self, service):
        """Test TRD validation: published 99.99% → effective 99.89% (no observed data).

        This is the canonical TRD 3.3 example that validates our formula.
        """
        profile = service.build_profile(
            service_id="external-api",
            service_uuid=uuid4(),
            published_sla=0.9999,  # 99.99%
            observed_availability=None,
            observation_window_days=0,
        )

        effective = service.compute_effective_availability(profile)

        # published_adjusted = 1 - (1 - 0.9999) * 11 = 1 - 0.0011 = 0.9989 (99.89%)
        assert abs(effective - 0.9989) < 0.0001

    def test_compute_effective_availability_both_observed_and_published(self, service):
        """Test effective availability when both observed and published are available.

        Should use min(observed, published_adjusted).
        """
        profile = service.build_profile(
            service_id="external-payment-api",
            service_uuid=uuid4(),
            published_sla=0.9999,  # 99.99%
            observed_availability=0.9960,  # 99.60%
            observation_window_days=30,
        )

        effective = service.compute_effective_availability(profile)

        # published_adjusted = 0.9989 (99.89%)
        # min(0.9960, 0.9989) = 0.9960
        assert effective == 0.9960

    def test_compute_effective_availability_observed_only(self, service):
        """Test effective availability when only observed data is available."""
        profile = service.build_profile(
            service_id="external-api",
            service_uuid=uuid4(),
            published_sla=None,
            observed_availability=0.9950,  # 99.50%
            observation_window_days=30,
        )

        effective = service.compute_effective_availability(profile)

        assert effective == 0.9950

    def test_compute_effective_availability_published_only(self, service):
        """Test effective availability when only published SLA is available."""
        profile = service.build_profile(
            service_id="external-api",
            service_uuid=uuid4(),
            published_sla=0.995,  # 99.5%
            observed_availability=None,
            observation_window_days=0,
        )

        effective = service.compute_effective_availability(profile)

        # published_adjusted = 1 - (1 - 0.995) * 11 = 1 - 0.055 = 0.945 (94.5%)
        assert abs(effective - 0.945) < 0.0001

    def test_compute_effective_availability_neither(self, service):
        """Test effective availability when neither observed nor published is available."""
        profile = service.build_profile(
            service_id="external-api",
            service_uuid=uuid4(),
            published_sla=None,
            observed_availability=None,
            observation_window_days=0,
        )

        effective = service.compute_effective_availability(profile)

        # Should default to 0.999 (99.9%)
        assert effective == 0.999

    def test_pessimistic_adjustment_formula_examples(self, service):
        """Test pessimistic adjustment formula with multiple examples."""
        examples = [
            (0.9999, 0.9989),  # 99.99% → 99.89%
            (0.999, 0.989),  # 99.9% → 98.9%
            (0.99, 0.89),  # 99% → 89%
            (0.95, 0.45),  # 95% → 45% (1 - 0.05*11 = 0.45)
        ]

        for published, expected_adjusted in examples:
            profile = service.build_profile(
                service_id="test-api",
                service_uuid=uuid4(),
                published_sla=published,
                observed_availability=None,
                observation_window_days=0,
            )

            effective = service.compute_effective_availability(profile)

            assert (
                abs(effective - expected_adjusted) < 0.001
            ), f"Failed for published={published}: got {effective}, expected {expected_adjusted}"

    def test_pessimistic_adjustment_low_sla_floors_at_zero(self, service):
        """Test that pessimistic adjustment floors at 0.0 for very low SLAs."""
        profile = service.build_profile(
            service_id="external-api",
            service_uuid=uuid4(),
            published_sla=0.05,  # 5% SLA (absurdly low)
            observed_availability=None,
            observation_window_days=0,
        )

        effective = service.compute_effective_availability(profile)

        # published_adjusted = 1 - (1 - 0.05) * 11 = 1 - 10.45 = -9.45 → floored at 0.0
        assert effective == 0.0

    def test_pessimistic_adjustment_perfect_sla(self, service):
        """Test pessimistic adjustment with 100% SLA."""
        profile = service.build_profile(
            service_id="external-api",
            service_uuid=uuid4(),
            published_sla=1.0,  # 100% SLA
            observed_availability=None,
            observation_window_days=0,
        )

        effective = service.compute_effective_availability(profile)

        # published_adjusted = 1 - (1 - 1.0) * 11 = 1 - 0 = 1.0
        assert effective == 1.0

    def test_build_profile(self, service):
        """Test building an ExternalProviderProfile."""
        service_uuid = uuid4()
        profile = service.build_profile(
            service_id="external-payment-api",
            service_uuid=service_uuid,
            published_sla=0.9999,
            observed_availability=0.9960,
            observation_window_days=30,
        )

        assert isinstance(profile, ExternalProviderProfile)
        assert profile.service_id == "external-payment-api"
        assert profile.service_uuid == service_uuid
        assert profile.published_sla == 0.9999
        assert profile.observed_availability == 0.9960
        assert profile.observation_window_days == 30

    def test_generate_availability_note_both_observed_and_published(self, service):
        """Test note generation when both observed and published are available."""
        profile = service.build_profile(
            service_id="external-api",
            service_uuid=uuid4(),
            published_sla=0.9999,
            observed_availability=0.9960,
            observation_window_days=30,
        )

        effective = service.compute_effective_availability(profile)
        note = service.generate_availability_note(profile, effective)

        assert "min(observed 99.60%, published×adj 99.89%)" in note
        assert "= 99.60%" in note

    def test_generate_availability_note_observed_only(self, service):
        """Test note generation when only observed data is available."""
        profile = service.build_profile(
            service_id="external-api",
            service_uuid=uuid4(),
            published_sla=None,
            observed_availability=0.9950,
            observation_window_days=30,
        )

        effective = service.compute_effective_availability(profile)
        note = service.generate_availability_note(profile, effective)

        assert "Using observed availability 99.50%" in note

    def test_generate_availability_note_published_only(self, service):
        """Test note generation when only published SLA is available."""
        profile = service.build_profile(
            service_id="external-api",
            service_uuid=uuid4(),
            published_sla=0.9999,
            observed_availability=None,
            observation_window_days=0,
        )

        effective = service.compute_effective_availability(profile)
        note = service.generate_availability_note(profile, effective)

        assert "No monitoring data" in note
        assert "published SLA 99.99%" in note
        assert "adjusted to 99.89%" in note

    def test_generate_availability_note_neither(self, service):
        """Test note generation when neither observed nor published is available."""
        profile = service.build_profile(
            service_id="external-api",
            service_uuid=uuid4(),
            published_sla=None,
            observed_availability=None,
            observation_window_days=0,
        )

        effective = service.compute_effective_availability(profile)
        note = service.generate_availability_note(profile, effective)

        assert "No published SLA or monitoring data" in note
        assert "conservative default 99.9%" in note

    def test_observed_lower_than_published_adjusted(self, service):
        """Test case where observed availability is lower than published adjusted.

        Should select observed (the more pessimistic value).
        """
        profile = service.build_profile(
            service_id="external-api",
            service_uuid=uuid4(),
            published_sla=0.9999,  # adjusted to 0.9989
            observed_availability=0.9985,  # lower than adjusted
            observation_window_days=30,
        )

        effective = service.compute_effective_availability(profile)

        assert effective == 0.9985

    def test_observed_higher_than_published_adjusted(self, service):
        """Test case where observed availability is higher than published adjusted.

        Should select published adjusted (the more pessimistic value).
        """
        profile = service.build_profile(
            service_id="external-api",
            service_uuid=uuid4(),
            published_sla=0.995,  # adjusted to 0.945
            observed_availability=0.999,  # higher than adjusted
            observation_window_days=30,
        )

        effective = service.compute_effective_availability(profile)

        # Should use published_adjusted (more pessimistic)
        assert abs(effective - 0.945) < 0.001

    def test_constants(self, service):
        """Test that service constants are correctly defined."""
        assert service.PESSIMISTIC_MULTIPLIER == 10
        assert service.DEFAULT_EXTERNAL_AVAILABILITY == 0.999

    def test_multiple_profiles_independent(self, service):
        """Test that multiple profiles are independent and don't interfere."""
        profile1 = service.build_profile(
            service_id="api-1",
            service_uuid=uuid4(),
            published_sla=0.9999,
            observed_availability=None,
            observation_window_days=0,
        )

        profile2 = service.build_profile(
            service_id="api-2",
            service_uuid=uuid4(),
            published_sla=0.999,
            observed_availability=None,
            observation_window_days=0,
        )

        effective1 = service.compute_effective_availability(profile1)
        effective2 = service.compute_effective_availability(profile2)

        # Each profile should compute independently
        assert abs(effective1 - 0.9989) < 0.0001
        assert abs(effective2 - 0.989) < 0.001
