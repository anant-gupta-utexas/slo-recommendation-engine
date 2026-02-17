"""Error budget analysis service for FR-3.

Computes per-dependency error budget consumption and identifies high-risk dependencies.
"""

from src.domain.entities.constraint_analysis import (
    DependencyRiskAssessment,
    ErrorBudgetBreakdown,
    RiskLevel,
)
from src.domain.services.composite_availability_service import (
    DependencyWithAvailability,
)


class ErrorBudgetAnalyzer:
    """Analyzes error budget consumption across dependencies.

    Computes how much of a service's error budget is consumed by each dependency,
    classifies risk levels, and identifies high-risk bottlenecks.

    Constants per TRD:
    - HIGH_RISK_THRESHOLD: > 30% consumption
    - MODERATE_RISK_THRESHOLD: 20-30% consumption
    - MONTHLY_MINUTES: 43,200 minutes (30 days)
    """

    HIGH_RISK_THRESHOLD: float = 0.30  # 30% error budget consumption
    MODERATE_RISK_THRESHOLD: float = 0.20  # 20% error budget consumption
    MONTHLY_MINUTES: float = 43200.0  # 30 days * 24 hours * 60 minutes

    def compute_breakdown(
        self,
        service_id: str,
        slo_target: float,
        service_availability: float,
        dependencies: list[DependencyWithAvailability],
    ) -> ErrorBudgetBreakdown:
        """Compute error budget breakdown for a service.

        Args:
            service_id: Business identifier of the service
            slo_target: SLO target as percentage (e.g., 99.9)
            service_availability: Service's own availability (0.0-1.0)
            dependencies: List of dependencies with availabilities

        Returns:
            ErrorBudgetBreakdown with per-dependency consumption and risk classifications
        """
        # Compute total error budget in minutes
        total_budget_minutes = self.compute_error_budget_minutes(slo_target)

        # Compute self consumption
        self_consumption_pct = self._compute_self_consumption(
            service_availability, slo_target
        )

        # Filter to hard sync dependencies only (soft deps don't consume error budget)
        hard_deps = [dep for dep in dependencies if dep.is_hard]

        # Compute per-dependency consumption
        dependency_assessments: list[DependencyRiskAssessment] = []
        high_risk_dependencies: list[str] = []
        total_dependency_consumption = 0.0

        for dep in hard_deps:
            consumption_pct = self.compute_single_dependency_consumption(
                dep.availability, slo_target
            )
            risk_level = self.classify_risk(consumption_pct)

            # Note: We'll populate these fields properly when used in full analysis
            # For now, create minimal assessment with required fields
            assessment = DependencyRiskAssessment(
                service_id=dep.service_name,  # Use name as business ID
                service_uuid=dep.service_id,
                availability=dep.availability,
                error_budget_consumption_pct=consumption_pct,
                risk_level=risk_level,
                is_external=False,  # Will be determined by caller
                communication_mode="sync",
                criticality="hard",
            )

            dependency_assessments.append(assessment)
            total_dependency_consumption += consumption_pct

            if risk_level == RiskLevel.HIGH:
                high_risk_dependencies.append(dep.service_name)

        return ErrorBudgetBreakdown(
            service_id=service_id,
            slo_target=slo_target,
            total_error_budget_minutes=total_budget_minutes,
            self_consumption_pct=self_consumption_pct,
            dependency_assessments=dependency_assessments,
            high_risk_dependencies=high_risk_dependencies,
            total_dependency_consumption_pct=total_dependency_consumption,
        )

    def compute_single_dependency_consumption(
        self,
        dep_availability: float,
        slo_target_pct: float,
    ) -> float:
        """Compute error budget consumption for a single dependency.

        Formula: (1 - dep_availability) / (1 - slo_target/100)

        Example:
        - SLO target: 99.9% (0.1% error budget)
        - Dependency: 99.5% (0.5% unavailability)
        - Consumption: 0.005 / 0.001 = 5.0 = 500%

        Args:
            dep_availability: Dependency availability as ratio (0.0-1.0)
            slo_target_pct: SLO target as percentage (0.0-100.0)

        Returns:
            Consumption as percentage (0.0 to infinity, can exceed 100)
        """
        # Handle edge case: 100% SLO target (zero error budget)
        if slo_target_pct >= 100.0:
            return 999999.99  # Cap at large number to represent infinity

        slo_target_ratio = slo_target_pct / 100.0
        error_budget = 1.0 - slo_target_ratio
        dep_unavailability = 1.0 - dep_availability

        # Guard against division by zero
        if error_budget <= 0.0:
            return 999999.99

        consumption_ratio = dep_unavailability / error_budget
        return consumption_ratio * 100.0  # Convert to percentage

    def classify_risk(self, consumption_pct: float) -> RiskLevel:
        """Classify dependency risk based on error budget consumption.

        Thresholds:
        - < 20%: LOW
        - 20-30%: MODERATE
        - > 30%: HIGH

        Args:
            consumption_pct: Error budget consumption as percentage

        Returns:
            RiskLevel enum (LOW, MODERATE, HIGH)
        """
        consumption_ratio = consumption_pct / 100.0

        if consumption_ratio > self.HIGH_RISK_THRESHOLD:
            return RiskLevel.HIGH
        elif consumption_ratio >= self.MODERATE_RISK_THRESHOLD:
            return RiskLevel.MODERATE
        else:
            return RiskLevel.LOW

    def compute_error_budget_minutes(self, slo_target_pct: float) -> float:
        """Compute monthly error budget in minutes.

        Formula: (1 - target/100) × 43200

        Examples:
        - 99.9% → 0.001 × 43200 = 43.2 minutes
        - 99% → 0.01 × 43200 = 432 minutes

        Args:
            slo_target_pct: SLO target as percentage (0.0-100.0)

        Returns:
            Error budget in minutes per month
        """
        error_budget_ratio = 1.0 - (slo_target_pct / 100.0)
        return error_budget_ratio * self.MONTHLY_MINUTES

    def _compute_self_consumption(
        self,
        service_availability: float,
        slo_target: float,
    ) -> float:
        """Compute self consumption of error budget.

        This is the percentage of error budget the service itself consumes
        (not counting dependencies).

        Args:
            service_availability: Service's own availability (0.0-1.0)
            slo_target: SLO target as percentage (e.g., 99.9)

        Returns:
            Self consumption as percentage
        """
        return self.compute_single_dependency_consumption(
            service_availability, slo_target
        )
