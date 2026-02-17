"""Unit tests for ErrorBudgetAnalyzer."""

from uuid import uuid4

import pytest

from src.domain.entities.constraint_analysis import RiskLevel
from src.domain.services.composite_availability_service import (
    DependencyWithAvailability,
)
from src.domain.services.error_budget_analyzer import ErrorBudgetAnalyzer


@pytest.fixture
def analyzer() -> ErrorBudgetAnalyzer:
    """Fixture providing ErrorBudgetAnalyzer instance."""
    return ErrorBudgetAnalyzer()


class TestComputeSingleDependencyConsumption:
    """Test compute_single_dependency_consumption method."""

    def test_slo_999_dep_995_consumption_500_percent(
        self, analyzer: ErrorBudgetAnalyzer
    ):
        """Test SLO=99.9%, dep=99.5% → consumption = 500%."""
        consumption = analyzer.compute_single_dependency_consumption(
            dep_availability=0.995,
            slo_target_pct=99.9,
        )
        assert consumption == pytest.approx(500.0, rel=1e-2)

    def test_slo_999_dep_9995_consumption_50_percent(
        self, analyzer: ErrorBudgetAnalyzer
    ):
        """Test SLO=99.9%, dep=99.95% → consumption = 50%."""
        consumption = analyzer.compute_single_dependency_consumption(
            dep_availability=0.9995,
            slo_target_pct=99.9,
        )
        assert consumption == pytest.approx(50.0, rel=1e-2)

    def test_slo_999_dep_9999_consumption_10_percent(
        self, analyzer: ErrorBudgetAnalyzer
    ):
        """Test SLO=99.9%, dep=99.99% → consumption = 10%."""
        consumption = analyzer.compute_single_dependency_consumption(
            dep_availability=0.9999,
            slo_target_pct=99.9,
        )
        assert consumption == pytest.approx(10.0, rel=1e-2)

    def test_slo_100_percent_returns_infinity_cap(
        self, analyzer: ErrorBudgetAnalyzer
    ):
        """Test SLO=100%, dep=99.99% → consumption capped at 999999.99."""
        consumption = analyzer.compute_single_dependency_consumption(
            dep_availability=0.9999,
            slo_target_pct=100.0,
        )
        assert consumption == 999999.99

    def test_perfect_dependency_zero_consumption(self, analyzer: ErrorBudgetAnalyzer):
        """Test dep=100% → consumption = 0%."""
        consumption = analyzer.compute_single_dependency_consumption(
            dep_availability=1.0,
            slo_target_pct=99.9,
        )
        assert consumption == pytest.approx(0.0, abs=1e-6)

    def test_low_dependency_availability_high_consumption(
        self, analyzer: ErrorBudgetAnalyzer
    ):
        """Test SLO=99.9%, dep=99% → consumption = 1000%."""
        consumption = analyzer.compute_single_dependency_consumption(
            dep_availability=0.99,
            slo_target_pct=99.9,
        )
        assert consumption == pytest.approx(1000.0, rel=1e-2)

    def test_slo_99_dep_98_consumption_200_percent(
        self, analyzer: ErrorBudgetAnalyzer
    ):
        """Test SLO=99%, dep=98% → consumption = 200%."""
        consumption = analyzer.compute_single_dependency_consumption(
            dep_availability=0.98,
            slo_target_pct=99.0,
        )
        assert consumption == pytest.approx(200.0, rel=1e-2)


class TestClassifyRisk:
    """Test classify_risk method."""

    def test_consumption_below_20_is_low_risk(self, analyzer: ErrorBudgetAnalyzer):
        """Test consumption < 20% → LOW risk."""
        assert analyzer.classify_risk(5.0) == RiskLevel.LOW
        assert analyzer.classify_risk(19.99) == RiskLevel.LOW

    def test_consumption_20_to_30_is_moderate_risk(
        self, analyzer: ErrorBudgetAnalyzer
    ):
        """Test consumption 20-30% → MODERATE risk."""
        assert analyzer.classify_risk(20.0) == RiskLevel.MODERATE
        assert analyzer.classify_risk(25.0) == RiskLevel.MODERATE
        assert analyzer.classify_risk(30.0) == RiskLevel.MODERATE

    def test_consumption_above_30_is_high_risk(self, analyzer: ErrorBudgetAnalyzer):
        """Test consumption > 30% → HIGH risk."""
        assert analyzer.classify_risk(30.01) == RiskLevel.HIGH
        assert analyzer.classify_risk(50.0) == RiskLevel.HIGH
        assert analyzer.classify_risk(500.0) == RiskLevel.HIGH

    def test_zero_consumption_is_low_risk(self, analyzer: ErrorBudgetAnalyzer):
        """Test consumption = 0% → LOW risk."""
        assert analyzer.classify_risk(0.0) == RiskLevel.LOW

    def test_threshold_boundaries(self, analyzer: ErrorBudgetAnalyzer):
        """Test exact threshold boundaries."""
        # Just below moderate threshold
        assert analyzer.classify_risk(19.999) == RiskLevel.LOW

        # Exactly at moderate threshold
        assert analyzer.classify_risk(20.0) == RiskLevel.MODERATE

        # Exactly at high threshold
        assert analyzer.classify_risk(30.0) == RiskLevel.MODERATE

        # Just above high threshold
        assert analyzer.classify_risk(30.001) == RiskLevel.HIGH


class TestComputeErrorBudgetMinutes:
    """Test compute_error_budget_minutes method."""

    def test_slo_999_gives_432_minutes(self, analyzer: ErrorBudgetAnalyzer):
        """Test 99.9% → 43.2 minutes."""
        minutes = analyzer.compute_error_budget_minutes(99.9)
        assert minutes == pytest.approx(43.2, rel=1e-6)

    def test_slo_99_gives_432_minutes(self, analyzer: ErrorBudgetAnalyzer):
        """Test 99% → 432 minutes."""
        minutes = analyzer.compute_error_budget_minutes(99.0)
        assert minutes == pytest.approx(432.0, rel=1e-6)

    def test_slo_9999_gives_432_minutes(self, analyzer: ErrorBudgetAnalyzer):
        """Test 99.99% → 4.32 minutes."""
        minutes = analyzer.compute_error_budget_minutes(99.99)
        assert minutes == pytest.approx(4.32, rel=1e-6)

    def test_slo_95_gives_2160_minutes(self, analyzer: ErrorBudgetAnalyzer):
        """Test 95% → 2160 minutes."""
        minutes = analyzer.compute_error_budget_minutes(95.0)
        assert minutes == pytest.approx(2160.0, rel=1e-6)

    def test_slo_100_gives_zero_minutes(self, analyzer: ErrorBudgetAnalyzer):
        """Test 100% → 0 minutes."""
        minutes = analyzer.compute_error_budget_minutes(100.0)
        assert minutes == pytest.approx(0.0, abs=1e-6)

    def test_monthly_minutes_constant(self, analyzer: ErrorBudgetAnalyzer):
        """Test MONTHLY_MINUTES constant is correct (43200 = 30 days * 24 hours * 60 minutes)."""
        assert analyzer.MONTHLY_MINUTES == 43200.0


class TestComputeBreakdown:
    """Test compute_breakdown method."""

    def test_single_hard_dependency(self, analyzer: ErrorBudgetAnalyzer):
        """Test breakdown with a single hard dependency."""
        service_id = "payment-api"
        slo_target = 99.9
        service_availability = 0.9999  # Perfect service → near-zero self consumption
        dependencies = [
            DependencyWithAvailability(
                service_id=uuid4(),
                service_name="auth-service",
                availability=0.9995,
                is_hard=True,
            )
        ]

        breakdown = analyzer.compute_breakdown(
            service_id=service_id,
            slo_target=slo_target,
            service_availability=service_availability,
            dependencies=dependencies,
        )

        assert breakdown.service_id == service_id
        assert breakdown.slo_target == slo_target
        assert breakdown.total_error_budget_minutes == pytest.approx(43.2, rel=1e-6)
        assert len(breakdown.dependency_assessments) == 1

        # Check first dependency assessment
        dep_assessment = breakdown.dependency_assessments[0]
        assert dep_assessment.service_id == "auth-service"
        assert dep_assessment.availability == 0.9995
        assert dep_assessment.error_budget_consumption_pct == pytest.approx(
            50.0, rel=1e-2
        )
        assert dep_assessment.risk_level == RiskLevel.HIGH
        assert dep_assessment.is_external is False

        # Check self consumption (0.9999 vs 99.9% target → 10% consumption)
        assert breakdown.self_consumption_pct == pytest.approx(10.0, rel=1e-2)

        # Check total dependency consumption
        assert breakdown.total_dependency_consumption_pct == pytest.approx(
            50.0, rel=1e-2
        )

    def test_multiple_hard_dependencies(self, analyzer: ErrorBudgetAnalyzer):
        """Test breakdown with multiple hard dependencies."""
        dependencies = [
            DependencyWithAvailability(
                service_id=uuid4(),
                service_name="dep-a",
                availability=0.9995,  # 50% consumption
                is_hard=True,
            ),
            DependencyWithAvailability(
                service_id=uuid4(),
                service_name="dep-b",
                availability=0.9999,  # 10% consumption
                is_hard=True,
            ),
            DependencyWithAvailability(
                service_id=uuid4(),
                service_name="dep-c",
                availability=0.995,  # 500% consumption
                is_hard=True,
            ),
        ]

        breakdown = analyzer.compute_breakdown(
            service_id="test-service",
            slo_target=99.9,
            service_availability=0.999,
            dependencies=dependencies,
        )

        assert len(breakdown.dependency_assessments) == 3
        assert breakdown.total_dependency_consumption_pct == pytest.approx(
            560.0, rel=1e-1
        )  # 50 + 10 + 500

        # Check risk classifications
        risks = [
            assessment.risk_level for assessment in breakdown.dependency_assessments
        ]
        assert risks.count(RiskLevel.HIGH) == 2  # dep-a (50%) and dep-c (500%)
        assert risks.count(RiskLevel.LOW) == 1  # dep-b (10%)

    def test_soft_dependencies_excluded(self, analyzer: ErrorBudgetAnalyzer):
        """Test that soft dependencies are excluded from breakdown."""
        dependencies = [
            DependencyWithAvailability(
                service_id=uuid4(),
                service_name="hard-dep",
                availability=0.9995,
                is_hard=True,
            ),
            DependencyWithAvailability(
                service_id=uuid4(),
                service_name="soft-dep",
                availability=0.95,  # Low availability but soft
                is_hard=False,
            ),
        ]

        breakdown = analyzer.compute_breakdown(
            service_id="test-service",
            slo_target=99.9,
            service_availability=0.999,
            dependencies=dependencies,
        )

        # Only hard dependency should be in assessments
        assert len(breakdown.dependency_assessments) == 1
        assert breakdown.dependency_assessments[0].service_id == "hard-dep"

    def test_no_dependencies(self, analyzer: ErrorBudgetAnalyzer):
        """Test breakdown with no dependencies."""
        breakdown = analyzer.compute_breakdown(
            service_id="test-service",
            slo_target=99.9,
            service_availability=0.999,
            dependencies=[],
        )

        assert len(breakdown.dependency_assessments) == 0
        assert breakdown.total_dependency_consumption_pct == 0.0
        assert len(breakdown.high_risk_dependencies) == 0

    def test_high_risk_dependencies_list(self, analyzer: ErrorBudgetAnalyzer):
        """Test that high-risk dependencies are correctly identified."""
        dependencies = [
            DependencyWithAvailability(
                service_id=uuid4(),
                service_name="low-risk-dep",
                availability=0.9999,  # 10% consumption → LOW
                is_hard=True,
            ),
            DependencyWithAvailability(
                service_id=uuid4(),
                service_name="moderate-risk-dep",
                availability=0.9998,  # 20% consumption → MODERATE
                is_hard=True,
            ),
            DependencyWithAvailability(
                service_id=uuid4(),
                service_name="high-risk-dep-1",
                availability=0.9995,  # 50% consumption → HIGH
                is_hard=True,
            ),
            DependencyWithAvailability(
                service_id=uuid4(),
                service_name="high-risk-dep-2",
                availability=0.995,  # 500% consumption → HIGH
                is_hard=True,
            ),
        ]

        breakdown = analyzer.compute_breakdown(
            service_id="test-service",
            slo_target=99.9,
            service_availability=0.999,
            dependencies=dependencies,
        )

        # Should have exactly 2 high-risk dependencies
        assert len(breakdown.high_risk_dependencies) == 2
        assert "high-risk-dep-1" in breakdown.high_risk_dependencies
        assert "high-risk-dep-2" in breakdown.high_risk_dependencies

    def test_self_consumption_computed(self, analyzer: ErrorBudgetAnalyzer):
        """Test that self consumption is correctly computed."""
        breakdown = analyzer.compute_breakdown(
            service_id="test-service",
            slo_target=99.9,
            service_availability=0.998,  # 200% self consumption
            dependencies=[],
        )

        assert breakdown.self_consumption_pct == pytest.approx(200.0, rel=1e-2)

    def test_perfect_service_zero_self_consumption(
        self, analyzer: ErrorBudgetAnalyzer
    ):
        """Test that perfect service (100% availability) has zero self consumption."""
        breakdown = analyzer.compute_breakdown(
            service_id="test-service",
            slo_target=99.9,
            service_availability=1.0,
            dependencies=[],
        )

        assert breakdown.self_consumption_pct == pytest.approx(0.0, abs=1e-6)
