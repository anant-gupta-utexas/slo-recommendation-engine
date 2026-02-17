"""Unit tests for constraint analysis DTOs."""

import pytest

from src.application.dtos.constraint_analysis_dto import (
    ConstraintAnalysisRequest,
    ConstraintAnalysisResponse,
    DependencyRiskDTO,
    ErrorBudgetBreakdownDTO,
    ErrorBudgetBreakdownRequest,
    ErrorBudgetBreakdownResponse,
    UnachievableWarningDTO,
)


class TestConstraintAnalysisRequest:
    """Tests for ConstraintAnalysisRequest DTO."""

    def test_create_with_all_fields(self) -> None:
        """Test creating request with all fields specified."""
        request = ConstraintAnalysisRequest(
            service_id="checkout-service",
            desired_target_pct=99.99,
            lookback_days=60,
            max_depth=5,
        )

        assert request.service_id == "checkout-service"
        assert request.desired_target_pct == 99.99
        assert request.lookback_days == 60
        assert request.max_depth == 5

    def test_create_with_defaults(self) -> None:
        """Test creating request with default values."""
        request = ConstraintAnalysisRequest(service_id="payment-service")

        assert request.service_id == "payment-service"
        assert request.desired_target_pct is None
        assert request.lookback_days == 30
        assert request.max_depth == 3

    def test_create_with_none_desired_target(self) -> None:
        """Test creating request with explicitly None desired_target_pct."""
        request = ConstraintAnalysisRequest(
            service_id="inventory-service", desired_target_pct=None
        )

        assert request.desired_target_pct is None


class TestErrorBudgetBreakdownRequest:
    """Tests for ErrorBudgetBreakdownRequest DTO."""

    def test_create_with_all_fields(self) -> None:
        """Test creating request with all fields specified."""
        request = ErrorBudgetBreakdownRequest(
            service_id="checkout-service", slo_target_pct=99.95, lookback_days=90
        )

        assert request.service_id == "checkout-service"
        assert request.slo_target_pct == 99.95
        assert request.lookback_days == 90

    def test_create_with_defaults(self) -> None:
        """Test creating request with default values."""
        request = ErrorBudgetBreakdownRequest(service_id="payment-service")

        assert request.service_id == "payment-service"
        assert request.slo_target_pct == 99.9
        assert request.lookback_days == 30


class TestDependencyRiskDTO:
    """Tests for DependencyRiskDTO."""

    def test_create_internal_dependency(self) -> None:
        """Test creating DTO for internal dependency."""
        risk = DependencyRiskDTO(
            service_id="payment-service",
            availability_pct=99.95,
            error_budget_consumption_pct=50.0,
            risk_level="high",
        )

        assert risk.service_id == "payment-service"
        assert risk.availability_pct == 99.95
        assert risk.error_budget_consumption_pct == 50.0
        assert risk.risk_level == "high"
        assert risk.is_external is False
        assert risk.communication_mode == "sync"
        assert risk.criticality == "hard"
        assert risk.published_sla_pct is None
        assert risk.observed_availability_pct is None
        assert risk.effective_availability_note == ""

    def test_create_external_dependency(self) -> None:
        """Test creating DTO for external dependency."""
        risk = DependencyRiskDTO(
            service_id="external-payment-api",
            availability_pct=99.50,
            error_budget_consumption_pct=500.0,
            risk_level="high",
            is_external=True,
            published_sla_pct=99.99,
            observed_availability_pct=99.60,
            effective_availability_note="Using min(observed 99.60%, published×0.9 99.89%) = 99.60%",
        )

        assert risk.service_id == "external-payment-api"
        assert risk.is_external is True
        assert risk.published_sla_pct == 99.99
        assert risk.observed_availability_pct == 99.60
        assert "99.60%" in risk.effective_availability_note

    def test_create_with_all_fields(self) -> None:
        """Test creating DTO with all fields."""
        risk = DependencyRiskDTO(
            service_id="cache-service",
            availability_pct=99.80,
            error_budget_consumption_pct=15.0,
            risk_level="low",
            is_external=False,
            communication_mode="async",
            criticality="soft",
            effective_availability_note="Using observed availability 99.80%",
        )

        assert risk.communication_mode == "async"
        assert risk.criticality == "soft"


class TestUnachievableWarningDTO:
    """Tests for UnachievableWarningDTO."""

    def test_create_warning(self) -> None:
        """Test creating unachievable warning."""
        warning = UnachievableWarningDTO(
            desired_target_pct=99.99,
            composite_bound_pct=99.70,
            gap_pct=0.29,
            message="The desired target of 99.99% is unachievable.",
            remediation_guidance="Consider: (1) Adding redundant paths...",
            required_dep_availability_pct=99.9975,
        )

        assert warning.desired_target_pct == 99.99
        assert warning.composite_bound_pct == 99.70
        assert warning.gap_pct == 0.29
        assert "unachievable" in warning.message.lower()
        assert warning.required_dep_availability_pct == 99.9975

    def test_small_gap(self) -> None:
        """Test warning with very small gap."""
        warning = UnachievableWarningDTO(
            desired_target_pct=99.95,
            composite_bound_pct=99.94,
            gap_pct=0.01,
            message="The desired target of 99.95% is unachievable.",
            remediation_guidance="Small gap guidance",
            required_dep_availability_pct=99.98,
        )

        assert warning.gap_pct == 0.01
        assert warning.gap_pct < 0.05  # Small gap still flagged


class TestErrorBudgetBreakdownDTO:
    """Tests for ErrorBudgetBreakdownDTO."""

    def test_create_with_no_dependencies(self) -> None:
        """Test creating breakdown with no dependencies."""
        breakdown = ErrorBudgetBreakdownDTO(
            service_id="isolated-service",
            slo_target_pct=99.9,
            total_error_budget_minutes=43.2,
            self_consumption_pct=8.0,
        )

        assert breakdown.service_id == "isolated-service"
        assert breakdown.slo_target_pct == 99.9
        assert breakdown.total_error_budget_minutes == 43.2
        assert breakdown.self_consumption_pct == 8.0
        assert len(breakdown.dependency_risks) == 0
        assert len(breakdown.high_risk_dependencies) == 0
        assert breakdown.total_dependency_consumption_pct == 0.0

    def test_create_with_dependencies(self) -> None:
        """Test creating breakdown with dependencies."""
        risk1 = DependencyRiskDTO(
            service_id="dep1",
            availability_pct=99.5,
            error_budget_consumption_pct=500.0,
            risk_level="high",
        )
        risk2 = DependencyRiskDTO(
            service_id="dep2",
            availability_pct=99.9,
            error_budget_consumption_pct=100.0,
            risk_level="high",
        )

        breakdown = ErrorBudgetBreakdownDTO(
            service_id="checkout-service",
            slo_target_pct=99.9,
            total_error_budget_minutes=43.2,
            self_consumption_pct=8.0,
            dependency_risks=[risk1, risk2],
            high_risk_dependencies=["dep1", "dep2"],
            total_dependency_consumption_pct=600.0,
        )

        assert len(breakdown.dependency_risks) == 2
        assert len(breakdown.high_risk_dependencies) == 2
        assert breakdown.total_dependency_consumption_pct == 600.0

    def test_high_risk_dependencies_populated(self) -> None:
        """Test that high_risk_dependencies list is populated correctly."""
        breakdown = ErrorBudgetBreakdownDTO(
            service_id="test-service",
            slo_target_pct=99.9,
            total_error_budget_minutes=43.2,
            self_consumption_pct=5.0,
            high_risk_dependencies=["dep1", "dep2", "dep3"],
        )

        assert "dep1" in breakdown.high_risk_dependencies
        assert "dep2" in breakdown.high_risk_dependencies
        assert "dep3" in breakdown.high_risk_dependencies


class TestConstraintAnalysisResponse:
    """Tests for ConstraintAnalysisResponse."""

    def test_create_achievable_analysis(self) -> None:
        """Test creating response for achievable SLO."""
        breakdown = ErrorBudgetBreakdownDTO(
            service_id="checkout-service",
            slo_target_pct=99.9,
            total_error_budget_minutes=43.2,
            self_consumption_pct=8.0,
        )

        response = ConstraintAnalysisResponse(
            service_id="checkout-service",
            analyzed_at="2026-02-15T14:00:00Z",
            composite_availability_bound_pct=99.95,
            is_achievable=True,
            has_high_risk_dependencies=False,
            error_budget_breakdown=breakdown,
            unachievable_warning=None,
            soft_dependency_risks=[],
            scc_supernodes=[],
            dependency_chain_depth=2,
            total_hard_dependencies=2,
            total_soft_dependencies=0,
            total_external_dependencies=0,
            lookback_days=30,
        )

        assert response.service_id == "checkout-service"
        assert response.is_achievable is True
        assert response.unachievable_warning is None
        assert response.has_high_risk_dependencies is False

    def test_create_unachievable_analysis(self) -> None:
        """Test creating response for unachievable SLO."""
        breakdown = ErrorBudgetBreakdownDTO(
            service_id="checkout-service",
            slo_target_pct=99.99,
            total_error_budget_minutes=4.32,
            self_consumption_pct=8.0,
            high_risk_dependencies=["dep1", "dep2"],
        )

        warning = UnachievableWarningDTO(
            desired_target_pct=99.99,
            composite_bound_pct=99.70,
            gap_pct=0.29,
            message="The desired target of 99.99% is unachievable.",
            remediation_guidance="Consider adding redundant paths.",
            required_dep_availability_pct=99.9975,
        )

        response = ConstraintAnalysisResponse(
            service_id="checkout-service",
            analyzed_at="2026-02-15T14:00:00Z",
            composite_availability_bound_pct=99.70,
            is_achievable=False,
            has_high_risk_dependencies=True,
            error_budget_breakdown=breakdown,
            unachievable_warning=warning,
            soft_dependency_risks=["recommendation-service"],
            scc_supernodes=[],
            dependency_chain_depth=3,
            total_hard_dependencies=3,
            total_soft_dependencies=1,
            total_external_dependencies=1,
            lookback_days=30,
        )

        assert response.is_achievable is False
        assert response.unachievable_warning is not None
        assert response.has_high_risk_dependencies is True
        assert len(response.soft_dependency_risks) == 1

    def test_create_with_circular_dependencies(self) -> None:
        """Test creating response with circular dependency cycles."""
        breakdown = ErrorBudgetBreakdownDTO(
            service_id="svc-a",
            slo_target_pct=99.9,
            total_error_budget_minutes=43.2,
            self_consumption_pct=5.0,
        )

        response = ConstraintAnalysisResponse(
            service_id="svc-a",
            analyzed_at="2026-02-15T14:00:00Z",
            composite_availability_bound_pct=99.85,
            is_achievable=True,
            has_high_risk_dependencies=False,
            error_budget_breakdown=breakdown,
            unachievable_warning=None,
            soft_dependency_risks=[],
            scc_supernodes=[["svc-a", "svc-b", "svc-c"]],
            dependency_chain_depth=3,
            total_hard_dependencies=2,
            total_soft_dependencies=0,
            total_external_dependencies=0,
            lookback_days=30,
        )

        assert len(response.scc_supernodes) == 1
        assert "svc-a" in response.scc_supernodes[0]

    def test_create_with_all_dependency_types(self) -> None:
        """Test creating response with mixed dependency types."""
        breakdown = ErrorBudgetBreakdownDTO(
            service_id="complex-service",
            slo_target_pct=99.9,
            total_error_budget_minutes=43.2,
            self_consumption_pct=10.0,
        )

        response = ConstraintAnalysisResponse(
            service_id="complex-service",
            analyzed_at="2026-02-15T14:00:00Z",
            composite_availability_bound_pct=99.80,
            is_achievable=True,
            has_high_risk_dependencies=False,
            error_budget_breakdown=breakdown,
            unachievable_warning=None,
            soft_dependency_risks=["cache-service", "recommendation-service"],
            scc_supernodes=[],
            dependency_chain_depth=4,
            total_hard_dependencies=5,
            total_soft_dependencies=2,
            total_external_dependencies=2,
            lookback_days=60,
        )

        assert response.total_hard_dependencies == 5
        assert response.total_soft_dependencies == 2
        assert response.total_external_dependencies == 2
        assert response.dependency_chain_depth == 4
        assert response.lookback_days == 60


class TestErrorBudgetBreakdownResponse:
    """Tests for ErrorBudgetBreakdownResponse."""

    def test_create_simple_breakdown(self) -> None:
        """Test creating simple breakdown response."""
        response = ErrorBudgetBreakdownResponse(
            service_id="payment-service",
            analyzed_at="2026-02-15T14:00:00Z",
            slo_target_pct=99.9,
            total_error_budget_minutes=43.2,
            self_consumption_pct=8.0,
        )

        assert response.service_id == "payment-service"
        assert response.slo_target_pct == 99.9
        assert response.total_error_budget_minutes == 43.2
        assert response.self_consumption_pct == 8.0
        assert len(response.dependency_risks) == 0

    def test_create_with_dependencies(self) -> None:
        """Test creating breakdown with dependency risks."""
        risk = DependencyRiskDTO(
            service_id="external-api",
            availability_pct=99.50,
            error_budget_consumption_pct=500.0,
            risk_level="high",
            is_external=True,
        )

        response = ErrorBudgetBreakdownResponse(
            service_id="checkout-service",
            analyzed_at="2026-02-15T14:00:00Z",
            slo_target_pct=99.9,
            total_error_budget_minutes=43.2,
            self_consumption_pct=8.0,
            dependency_risks=[risk],
            high_risk_dependencies=["external-api"],
            total_dependency_consumption_pct=500.0,
        )

        assert len(response.dependency_risks) == 1
        assert len(response.high_risk_dependencies) == 1
        assert response.total_dependency_consumption_pct == 500.0
