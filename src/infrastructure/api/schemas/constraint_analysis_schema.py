"""Pydantic API schemas for constraint analysis endpoints.

This module defines the request/response models for the constraint analysis
API endpoints, providing validation and serialization for FR-3.
"""

from pydantic import BaseModel, Field


# ==================== Query Parameters ====================


class ConstraintAnalysisQueryParams(BaseModel):
    """Query parameters for constraint analysis endpoint."""

    desired_target_pct: float | None = Field(
        default=None,
        ge=90.0,
        le=99.9999,
        description="Desired SLO target as percentage (e.g., 99.9 for 99.9%). If omitted, uses active SLO or 99.9% default.",
    )
    lookback_days: int = Field(
        default=30,
        ge=7,
        le=365,
        description="Lookback window for telemetry data in days",
    )
    max_depth: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum dependency chain depth to analyze",
    )


class ErrorBudgetBreakdownQueryParams(BaseModel):
    """Query parameters for error budget breakdown endpoint."""

    slo_target_pct: float = Field(
        default=99.9,
        ge=90.0,
        le=99.9999,
        description="SLO target for budget calculation as percentage (e.g., 99.9 for 99.9%)",
    )
    lookback_days: int = Field(
        default=30,
        ge=7,
        le=365,
        description="Lookback window for telemetry data in days",
    )


# ==================== Response Models ====================


class DependencyRiskApiModel(BaseModel):
    """API model for a single dependency's risk assessment."""

    service_id: str
    availability_pct: float
    error_budget_consumption_pct: float
    risk_level: str  # "low" | "moderate" | "high"
    is_external: bool
    communication_mode: str
    criticality: str
    published_sla_pct: float | None = None
    observed_availability_pct: float | None = None
    effective_availability_note: str


class UnachievableWarningApiModel(BaseModel):
    """API model for unachievable SLO warning."""

    desired_target_pct: float
    composite_bound_pct: float
    gap_pct: float
    message: str
    remediation_guidance: str
    required_dep_availability_pct: float


class ErrorBudgetBreakdownApiModel(BaseModel):
    """API model for error budget breakdown."""

    service_id: str
    slo_target_pct: float
    total_error_budget_minutes: float
    self_consumption_pct: float
    dependency_risks: list[DependencyRiskApiModel]
    high_risk_dependencies: list[str]
    total_dependency_consumption_pct: float


class ConstraintAnalysisApiResponse(BaseModel):
    """Complete constraint analysis response."""

    service_id: str
    analyzed_at: str  # ISO 8601 timestamp
    composite_availability_bound_pct: float
    is_achievable: bool
    has_high_risk_dependencies: bool
    dependency_chain_depth: int
    total_hard_dependencies: int
    total_soft_dependencies: int
    total_external_dependencies: int
    lookback_days: int
    error_budget_breakdown: ErrorBudgetBreakdownApiModel
    unachievable_warning: UnachievableWarningApiModel | None = None
    soft_dependency_risks: list[str] = Field(default_factory=list)
    scc_supernodes: list[list[str]] = Field(default_factory=list)


class ErrorBudgetBreakdownApiResponse(BaseModel):
    """Error budget breakdown response."""

    service_id: str
    analyzed_at: str  # ISO 8601 timestamp
    slo_target_pct: float
    total_error_budget_minutes: float
    self_consumption_pct: float
    dependency_risks: list[DependencyRiskApiModel]
    high_risk_dependencies: list[str]
    total_dependency_consumption_pct: float
