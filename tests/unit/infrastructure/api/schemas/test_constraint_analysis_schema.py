"""Unit tests for constraint analysis API schemas.

Tests validation rules, defaults, and serialization for the Pydantic models
used in the constraint analysis API endpoints.
"""

import pytest
from pydantic import ValidationError

from src.infrastructure.api.schemas.constraint_analysis_schema import (
    ConstraintAnalysisApiResponse,
    ConstraintAnalysisQueryParams,
    DependencyRiskApiModel,
    ErrorBudgetBreakdownApiModel,
    ErrorBudgetBreakdownApiResponse,
    ErrorBudgetBreakdownQueryParams,
    UnachievableWarningApiModel,
)


# ==================== ConstraintAnalysisQueryParams ====================


class TestConstraintAnalysisQueryParams:
    """Test ConstraintAnalysisQueryParams validation."""

    def test_defaults_applied(self):
        """Test that default values are applied correctly."""
        params = ConstraintAnalysisQueryParams()
        assert params.desired_target_pct is None
        assert params.lookback_days == 30
        assert params.max_depth == 3

    def test_valid_desired_target_pct(self):
        """Test valid desired_target_pct values."""
        params = ConstraintAnalysisQueryParams(desired_target_pct=99.9)
        assert params.desired_target_pct == 99.9

        params = ConstraintAnalysisQueryParams(desired_target_pct=90.0)
        assert params.desired_target_pct == 90.0

        params = ConstraintAnalysisQueryParams(desired_target_pct=99.9999)
        assert params.desired_target_pct == 99.9999

    def test_desired_target_pct_below_range_raises(self):
        """Test that desired_target_pct below 90.0 raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ConstraintAnalysisQueryParams(desired_target_pct=89.9)
        assert "greater than or equal to 90" in str(exc_info.value)

    def test_desired_target_pct_above_range_raises(self):
        """Test that desired_target_pct above 99.9999 raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ConstraintAnalysisQueryParams(desired_target_pct=100.0)
        assert "less than or equal to 99.9999" in str(exc_info.value)

    def test_valid_lookback_days(self):
        """Test valid lookback_days values."""
        params = ConstraintAnalysisQueryParams(lookback_days=7)
        assert params.lookback_days == 7

        params = ConstraintAnalysisQueryParams(lookback_days=365)
        assert params.lookback_days == 365

    def test_lookback_days_below_range_raises(self):
        """Test that lookback_days below 7 raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ConstraintAnalysisQueryParams(lookback_days=6)
        assert "greater than or equal to 7" in str(exc_info.value)

    def test_lookback_days_above_range_raises(self):
        """Test that lookback_days above 365 raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ConstraintAnalysisQueryParams(lookback_days=366)
        assert "less than or equal to 365" in str(exc_info.value)

    def test_valid_max_depth(self):
        """Test valid max_depth values."""
        params = ConstraintAnalysisQueryParams(max_depth=1)
        assert params.max_depth == 1

        params = ConstraintAnalysisQueryParams(max_depth=10)
        assert params.max_depth == 10

    def test_max_depth_below_range_raises(self):
        """Test that max_depth below 1 raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ConstraintAnalysisQueryParams(max_depth=0)
        assert "greater than or equal to 1" in str(exc_info.value)

    def test_max_depth_above_range_raises(self):
        """Test that max_depth above 10 raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ConstraintAnalysisQueryParams(max_depth=11)
        assert "less than or equal to 10" in str(exc_info.value)


# ==================== ErrorBudgetBreakdownQueryParams ====================


class TestErrorBudgetBreakdownQueryParams:
    """Test ErrorBudgetBreakdownQueryParams validation."""

    def test_defaults_applied(self):
        """Test that default values are applied correctly."""
        params = ErrorBudgetBreakdownQueryParams()
        assert params.slo_target_pct == 99.9
        assert params.lookback_days == 30

    def test_valid_slo_target_pct(self):
        """Test valid slo_target_pct values."""
        params = ErrorBudgetBreakdownQueryParams(slo_target_pct=99.99)
        assert params.slo_target_pct == 99.99

    def test_slo_target_pct_below_range_raises(self):
        """Test that slo_target_pct below 90.0 raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ErrorBudgetBreakdownQueryParams(slo_target_pct=89.9)
        assert "greater than or equal to 90" in str(exc_info.value)

    def test_slo_target_pct_above_range_raises(self):
        """Test that slo_target_pct above 99.9999 raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ErrorBudgetBreakdownQueryParams(slo_target_pct=100.0)
        assert "less than or equal to 99.9999" in str(exc_info.value)


# ==================== Response Models ====================


class TestDependencyRiskApiModel:
    """Test DependencyRiskApiModel serialization."""

    def test_valid_dependency_risk(self):
        """Test creating a valid dependency risk model."""
        risk = DependencyRiskApiModel(
            service_id="payment-service",
            availability_pct=99.95,
            error_budget_consumption_pct=50.0,
            risk_level="high",
            is_external=False,
            communication_mode="sync",
            criticality="hard",
            published_sla_pct=None,
            observed_availability_pct=99.95,
            effective_availability_note="Using observed availability 99.95%",
        )
        assert risk.service_id == "payment-service"
        assert risk.availability_pct == 99.95
        assert risk.error_budget_consumption_pct == 50.0
        assert risk.risk_level == "high"


class TestUnachievableWarningApiModel:
    """Test UnachievableWarningApiModel serialization."""

    def test_valid_unachievable_warning(self):
        """Test creating a valid unachievable warning model."""
        warning = UnachievableWarningApiModel(
            desired_target_pct=99.99,
            composite_bound_pct=99.70,
            gap_pct=0.29,
            message="The desired target of 99.99% is unachievable.",
            remediation_guidance="Consider adding redundant paths.",
            required_dep_availability_pct=99.9975,
        )
        assert warning.desired_target_pct == 99.99
        assert warning.composite_bound_pct == 99.70
        assert warning.gap_pct == 0.29


class TestErrorBudgetBreakdownApiModel:
    """Test ErrorBudgetBreakdownApiModel serialization."""

    def test_valid_error_budget_breakdown(self):
        """Test creating a valid error budget breakdown model."""
        risk = DependencyRiskApiModel(
            service_id="payment-service",
            availability_pct=99.95,
            error_budget_consumption_pct=50.0,
            risk_level="high",
            is_external=False,
            communication_mode="sync",
            criticality="hard",
            published_sla_pct=None,
            observed_availability_pct=99.95,
            effective_availability_note="Using observed availability 99.95%",
        )

        breakdown = ErrorBudgetBreakdownApiModel(
            service_id="checkout-service",
            slo_target_pct=99.9,
            total_error_budget_minutes=43.2,
            self_consumption_pct=8.0,
            dependency_risks=[risk],
            high_risk_dependencies=["payment-service"],
            total_dependency_consumption_pct=50.0,
        )

        assert breakdown.service_id == "checkout-service"
        assert breakdown.slo_target_pct == 99.9
        assert len(breakdown.dependency_risks) == 1
        assert len(breakdown.high_risk_dependencies) == 1


class TestConstraintAnalysisApiResponse:
    """Test ConstraintAnalysisApiResponse serialization."""

    def test_valid_constraint_analysis_response(self):
        """Test creating a valid constraint analysis response."""
        risk = DependencyRiskApiModel(
            service_id="payment-service",
            availability_pct=99.95,
            error_budget_consumption_pct=50.0,
            risk_level="high",
            is_external=False,
            communication_mode="sync",
            criticality="hard",
            published_sla_pct=None,
            observed_availability_pct=99.95,
            effective_availability_note="Using observed availability 99.95%",
        )

        breakdown = ErrorBudgetBreakdownApiModel(
            service_id="checkout-service",
            slo_target_pct=99.9,
            total_error_budget_minutes=43.2,
            self_consumption_pct=8.0,
            dependency_risks=[risk],
            high_risk_dependencies=["payment-service"],
            total_dependency_consumption_pct=50.0,
        )

        response = ConstraintAnalysisApiResponse(
            service_id="checkout-service",
            analyzed_at="2026-02-15T14:00:00Z",
            composite_availability_bound_pct=99.70,
            is_achievable=True,
            has_high_risk_dependencies=True,
            dependency_chain_depth=3,
            total_hard_dependencies=3,
            total_soft_dependencies=1,
            total_external_dependencies=1,
            lookback_days=30,
            error_budget_breakdown=breakdown,
            unachievable_warning=None,
            soft_dependency_risks=["recommendation-service"],
            scc_supernodes=[],
        )

        assert response.service_id == "checkout-service"
        assert response.is_achievable is True
        assert response.has_high_risk_dependencies is True
        assert response.total_hard_dependencies == 3
        assert len(response.soft_dependency_risks) == 1


class TestErrorBudgetBreakdownApiResponse:
    """Test ErrorBudgetBreakdownApiResponse serialization."""

    def test_valid_error_budget_breakdown_response(self):
        """Test creating a valid error budget breakdown response."""
        risk = DependencyRiskApiModel(
            service_id="payment-service",
            availability_pct=99.95,
            error_budget_consumption_pct=50.0,
            risk_level="high",
            is_external=False,
            communication_mode="sync",
            criticality="hard",
            published_sla_pct=None,
            observed_availability_pct=99.95,
            effective_availability_note="Using observed availability 99.95%",
        )

        response = ErrorBudgetBreakdownApiResponse(
            service_id="checkout-service",
            analyzed_at="2026-02-15T14:00:00Z",
            slo_target_pct=99.9,
            total_error_budget_minutes=43.2,
            self_consumption_pct=8.0,
            dependency_risks=[risk],
            high_risk_dependencies=["payment-service"],
            total_dependency_consumption_pct=50.0,
        )

        assert response.service_id == "checkout-service"
        assert response.slo_target_pct == 99.9
        assert len(response.dependency_risks) == 1
        assert len(response.high_risk_dependencies) == 1
