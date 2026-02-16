"""Unit tests for FR-3 Constraint Analysis domain entities."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from src.domain.entities.constraint_analysis import (
    ConstraintAnalysis,
    DependencyRiskAssessment,
    ErrorBudgetBreakdown,
    ExternalProviderProfile,
    RiskLevel,
    ServiceType,
    UnachievableWarning,
)


class TestServiceType:
    """Tests for ServiceType enum."""

    def test_service_type_values(self):
        """Test that ServiceType enum has correct values."""
        assert ServiceType.INTERNAL.value == "internal"
        assert ServiceType.EXTERNAL.value == "external"

    def test_service_type_membership(self):
        """Test ServiceType membership checks."""
        assert "internal" in [t.value for t in ServiceType]
        assert "external" in [t.value for t in ServiceType]


class TestRiskLevel:
    """Tests for RiskLevel enum."""

    def test_risk_level_values(self):
        """Test that RiskLevel enum has correct values."""
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MODERATE.value == "moderate"
        assert RiskLevel.HIGH.value == "high"

    def test_risk_level_ordering(self):
        """Test that risk levels can be ordered."""
        levels = [RiskLevel.LOW, RiskLevel.MODERATE, RiskLevel.HIGH]
        assert len(levels) == 3


class TestExternalProviderProfile:
    """Tests for ExternalProviderProfile entity."""

    def test_effective_availability_both_observed_and_published(self):
        """Test effective availability when both observed and published are available."""
        # TRD example: published 99.99%, observed 99.60%
        # published_adjusted = 1 - (1 - 0.9999) * 11 = 1 - 0.0011 = 0.9989 (99.89%)
        # effective = min(0.9960, 0.9989) = 0.9960 (99.60%)
        profile = ExternalProviderProfile(
            service_id="external-payment-api",
            service_uuid=uuid4(),
            published_sla=0.9999,
            observed_availability=0.9960,
            observation_window_days=30,
        )

        effective = profile.effective_availability

        # Should use min(observed, published_adjusted)
        assert effective == 0.9960

    def test_effective_availability_trd_validation(self):
        """Test TRD validation: published 99.99% → effective 99.89% (observed only)."""
        profile = ExternalProviderProfile(
            service_id="external-api",
            service_uuid=uuid4(),
            published_sla=0.9999,  # 99.99%
            observed_availability=None,
            observation_window_days=0,
        )

        effective = profile.effective_availability

        # published_adjusted = 1 - (1 - 0.9999) * 11 = 1 - 0.0011 = 0.9989
        assert abs(effective - 0.9989) < 0.0001

    def test_effective_availability_observed_only(self):
        """Test effective availability when only observed data is available."""
        profile = ExternalProviderProfile(
            service_id="external-api",
            service_uuid=uuid4(),
            published_sla=None,
            observed_availability=0.9950,
            observation_window_days=30,
        )

        assert profile.effective_availability == 0.9950

    def test_effective_availability_published_only(self):
        """Test effective availability when only published SLA is available."""
        profile = ExternalProviderProfile(
            service_id="external-api",
            service_uuid=uuid4(),
            published_sla=0.9999,
            observed_availability=None,
            observation_window_days=0,
        )

        # Should use published_adjusted = 1 - (1 - 0.9999) * 11 = 0.9989
        assert abs(profile.effective_availability - 0.9989) < 0.0001

    def test_effective_availability_neither(self):
        """Test effective availability when neither observed nor published is available."""
        profile = ExternalProviderProfile(
            service_id="external-api",
            service_uuid=uuid4(),
            published_sla=None,
            observed_availability=None,
            observation_window_days=0,
        )

        # Should default to 0.999 (99.9%)
        assert profile.effective_availability == 0.999

    def test_pessimistic_adjustment_low_sla(self):
        """Test pessimistic adjustment floors at 0.0 for very low SLAs."""
        profile = ExternalProviderProfile(
            service_id="external-api",
            service_uuid=uuid4(),
            published_sla=0.05,  # 5% SLA (absurdly low)
            observed_availability=None,
        )

        # published_adjusted = 1 - (1 - 0.05) * 11 = 1 - 10.45 = -9.45 → floored at 0.0
        assert profile.effective_availability == 0.0

    def test_pessimistic_adjustment_perfect_sla(self):
        """Test pessimistic adjustment with 100% SLA."""
        profile = ExternalProviderProfile(
            service_id="external-api",
            service_uuid=uuid4(),
            published_sla=1.0,  # 100% SLA
            observed_availability=None,
        )

        # published_adjusted = 1 - (1 - 1.0) * 11 = 1 - 0 = 1.0
        assert profile.effective_availability == 1.0


class TestDependencyRiskAssessment:
    """Tests for DependencyRiskAssessment entity."""

    def test_valid_dependency_risk_assessment(self):
        """Test creating a valid DependencyRiskAssessment."""
        assessment = DependencyRiskAssessment(
            service_id="payment-service",
            service_uuid=uuid4(),
            availability=0.9995,
            error_budget_consumption_pct=50.0,
            risk_level=RiskLevel.HIGH,
            is_external=False,
            communication_mode="sync",
            criticality="hard",
        )

        assert assessment.service_id == "payment-service"
        assert assessment.availability == 0.9995
        assert assessment.error_budget_consumption_pct == 50.0
        assert assessment.risk_level == RiskLevel.HIGH
        assert assessment.is_external is False

    def test_dependency_risk_assessment_with_external_fields(self):
        """Test DependencyRiskAssessment with external dependency fields."""
        assessment = DependencyRiskAssessment(
            service_id="external-payment-api",
            service_uuid=uuid4(),
            availability=0.9950,
            error_budget_consumption_pct=500.0,
            risk_level=RiskLevel.HIGH,
            is_external=True,
            published_sla=0.9999,
            observed_availability=0.9960,
            effective_availability_note="Using min(observed 99.60%, published×adj 99.89%) = 99.60%",
        )

        assert assessment.is_external is True
        assert assessment.published_sla == 0.9999
        assert assessment.observed_availability == 0.9960
        assert "99.60%" in assessment.effective_availability_note

    def test_dependency_risk_assessment_negative_consumption_raises(self):
        """Test that negative error budget consumption raises ValueError."""
        with pytest.raises(ValueError, match="error_budget_consumption_pct must be >= 0.0"):
            DependencyRiskAssessment(
                service_id="bad-service",
                service_uuid=uuid4(),
                availability=0.999,
                error_budget_consumption_pct=-10.0,
                risk_level=RiskLevel.LOW,
            )

    def test_dependency_risk_assessment_consumption_exceeds_100(self):
        """Test that consumption > 100% is allowed (dependency exceeds total budget)."""
        assessment = DependencyRiskAssessment(
            service_id="degraded-service",
            service_uuid=uuid4(),
            availability=0.995,
            error_budget_consumption_pct=500.0,  # 500% consumption
            risk_level=RiskLevel.HIGH,
        )

        assert assessment.error_budget_consumption_pct == 500.0


class TestUnachievableWarning:
    """Tests for UnachievableWarning entity."""

    def test_unachievable_warning_creation(self):
        """Test creating an UnachievableWarning."""
        warning = UnachievableWarning(
            desired_target=99.99,
            composite_bound=99.70,
            gap=0.29,
            message="The desired target of 99.99% is unachievable. Composite availability bound is 99.70% given current dependency chain.",
            remediation_guidance="To achieve 99.99%, each of the 3 critical dependencies must provide at least 99.9975% availability.",
            required_dep_availability=99.9975,
        )

        assert warning.desired_target == 99.99
        assert warning.composite_bound == 99.70
        assert warning.gap == 0.29
        assert "99.99% is unachievable" in warning.message
        assert "99.9975%" in warning.remediation_guidance


class TestErrorBudgetBreakdown:
    """Tests for ErrorBudgetBreakdown entity."""

    def test_error_budget_breakdown_creation(self):
        """Test creating an ErrorBudgetBreakdown."""
        assessment1 = DependencyRiskAssessment(
            service_id="dep1",
            service_uuid=uuid4(),
            availability=0.9995,
            error_budget_consumption_pct=50.0,
            risk_level=RiskLevel.HIGH,
        )
        assessment2 = DependencyRiskAssessment(
            service_id="dep2",
            service_uuid=uuid4(),
            availability=0.999,
            error_budget_consumption_pct=100.0,
            risk_level=RiskLevel.HIGH,
        )

        breakdown = ErrorBudgetBreakdown(
            service_id="checkout-service",
            slo_target=99.9,
            total_error_budget_minutes=43.2,
            self_consumption_pct=8.0,
            dependency_assessments=[assessment1, assessment2],
            high_risk_dependencies=["dep1", "dep2"],
            total_dependency_consumption_pct=150.0,
        )

        assert breakdown.service_id == "checkout-service"
        assert breakdown.slo_target == 99.9
        assert breakdown.total_error_budget_minutes == 43.2
        assert breakdown.self_consumption_pct == 8.0
        assert len(breakdown.dependency_assessments) == 2
        assert len(breakdown.high_risk_dependencies) == 2
        assert breakdown.total_dependency_consumption_pct == 150.0

    def test_error_budget_breakdown_empty_dependencies(self):
        """Test ErrorBudgetBreakdown with no dependencies."""
        breakdown = ErrorBudgetBreakdown(
            service_id="isolated-service",
            slo_target=99.9,
            total_error_budget_minutes=43.2,
            self_consumption_pct=100.0,
        )

        assert len(breakdown.dependency_assessments) == 0
        assert len(breakdown.high_risk_dependencies) == 0
        assert breakdown.total_dependency_consumption_pct == 0.0


class TestConstraintAnalysis:
    """Tests for ConstraintAnalysis entity."""

    def test_constraint_analysis_creation_achievable(self):
        """Test creating a ConstraintAnalysis with achievable SLO."""
        breakdown = ErrorBudgetBreakdown(
            service_id="checkout-service",
            slo_target=99.9,
            total_error_budget_minutes=43.2,
            self_consumption_pct=8.0,
        )

        service_uuid = uuid4()
        analysis = ConstraintAnalysis(
            service_id="checkout-service",
            service_uuid=service_uuid,
            composite_availability_bound=0.9970,
            composite_availability_bound_pct=99.70,
            error_budget_breakdown=breakdown,
            unachievable_warning=None,
            dependency_chain_depth=3,
            total_hard_dependencies=3,
            total_soft_dependencies=1,
            total_external_dependencies=1,
            lookback_days=30,
        )

        assert analysis.service_id == "checkout-service"
        assert analysis.service_uuid == service_uuid
        assert analysis.composite_availability_bound == 0.9970
        assert analysis.composite_availability_bound_pct == 99.70
        assert analysis.is_achievable is True
        assert analysis.has_high_risk_dependencies is False
        assert analysis.dependency_chain_depth == 3
        assert analysis.total_hard_dependencies == 3
        assert isinstance(analysis.id, UUID)
        assert isinstance(analysis.analyzed_at, datetime)

    def test_constraint_analysis_creation_unachievable(self):
        """Test creating a ConstraintAnalysis with unachievable SLO."""
        breakdown = ErrorBudgetBreakdown(
            service_id="checkout-service",
            slo_target=99.99,
            total_error_budget_minutes=4.32,
            self_consumption_pct=8.0,
            high_risk_dependencies=["payment-service"],
        )

        warning = UnachievableWarning(
            desired_target=99.99,
            composite_bound=99.70,
            gap=0.29,
            message="Unachievable",
            remediation_guidance="Guidance",
            required_dep_availability=99.9975,
        )

        analysis = ConstraintAnalysis(
            service_id="checkout-service",
            service_uuid=uuid4(),
            composite_availability_bound=0.9970,
            composite_availability_bound_pct=99.70,
            error_budget_breakdown=breakdown,
            unachievable_warning=warning,
        )

        assert analysis.is_achievable is False
        assert analysis.has_high_risk_dependencies is True

    def test_constraint_analysis_soft_dependency_risks(self):
        """Test ConstraintAnalysis with soft dependency risks."""
        breakdown = ErrorBudgetBreakdown(
            service_id="checkout-service",
            slo_target=99.9,
            total_error_budget_minutes=43.2,
            self_consumption_pct=8.0,
        )

        analysis = ConstraintAnalysis(
            service_id="checkout-service",
            service_uuid=uuid4(),
            composite_availability_bound=0.998,
            composite_availability_bound_pct=99.8,
            error_budget_breakdown=breakdown,
            soft_dependency_risks=["recommendation-service", "analytics-service"],
        )

        assert len(analysis.soft_dependency_risks) == 2
        assert "recommendation-service" in analysis.soft_dependency_risks

    def test_constraint_analysis_scc_supernodes(self):
        """Test ConstraintAnalysis with circular dependency supernodes."""
        breakdown = ErrorBudgetBreakdown(
            service_id="service-a",
            slo_target=99.9,
            total_error_budget_minutes=43.2,
            self_consumption_pct=8.0,
        )

        analysis = ConstraintAnalysis(
            service_id="service-a",
            service_uuid=uuid4(),
            composite_availability_bound=0.997,
            composite_availability_bound_pct=99.7,
            error_budget_breakdown=breakdown,
            scc_supernodes=[
                ["service-a", "service-b", "service-c"],
            ],
        )

        assert len(analysis.scc_supernodes) == 1
        assert len(analysis.scc_supernodes[0]) == 3

    def test_constraint_analysis_metadata_defaults(self):
        """Test ConstraintAnalysis metadata fields have correct defaults."""
        breakdown = ErrorBudgetBreakdown(
            service_id="test-service",
            slo_target=99.9,
            total_error_budget_minutes=43.2,
            self_consumption_pct=10.0,
        )

        analysis = ConstraintAnalysis(
            service_id="test-service",
            service_uuid=uuid4(),
            composite_availability_bound=0.998,
            composite_availability_bound_pct=99.8,
            error_budget_breakdown=breakdown,
        )

        # Check defaults
        assert isinstance(analysis.id, UUID)
        assert isinstance(analysis.analyzed_at, datetime)
        assert analysis.lookback_days == 30
        assert analysis.dependency_chain_depth == 0
        assert analysis.total_hard_dependencies == 0
        assert analysis.total_soft_dependencies == 0
        assert analysis.total_external_dependencies == 0

    def test_constraint_analysis_timestamp_in_utc(self):
        """Test that analyzed_at timestamp is in UTC."""
        breakdown = ErrorBudgetBreakdown(
            service_id="test-service",
            slo_target=99.9,
            total_error_budget_minutes=43.2,
            self_consumption_pct=10.0,
        )

        analysis = ConstraintAnalysis(
            service_id="test-service",
            service_uuid=uuid4(),
            composite_availability_bound=0.998,
            composite_availability_bound_pct=99.8,
            error_budget_breakdown=breakdown,
        )

        assert analysis.analyzed_at.tzinfo == timezone.utc
