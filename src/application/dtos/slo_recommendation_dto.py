"""Data Transfer Objects for SLO Recommendation Generation (FR-2).

DTOs for use case input/output in the application layer.
These are dataclasses (not Pydantic) following Clean Architecture principles.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GenerateRecommendationRequest:
    """Request to generate SLO recommendations for a service."""

    service_id: str  # Business identifier (e.g., "checkout-service")
    sli_type: str = "all"  # "availability" | "latency" | "all"
    lookback_days: int = 30  # Lookback window (7-365)
    force_regenerate: bool = False  # Bypass cached results


@dataclass
class GetRecommendationRequest:
    """Request to retrieve SLO recommendations for a service."""

    service_id: str
    sli_type: str = "all"  # "availability" | "latency" | "all"
    lookback_days: int = 30
    force_regenerate: bool = False


@dataclass
class TierDTO:
    """A single tier (Conservative/Balanced/Aggressive) within a recommendation."""

    level: str  # "conservative" | "balanced" | "aggressive"
    target: float  # e.g., 99.9 for availability, 800 for latency ms

    # Availability-specific fields
    error_budget_monthly_minutes: float | None = None
    confidence_interval: tuple[float, float] | None = None

    # Common fields
    estimated_breach_probability: float = 0.0

    # Latency-specific fields
    percentile: str | None = None  # e.g., "p99"
    target_ms: int | None = None


@dataclass
class FeatureAttributionDTO:
    """A single feature's contribution to the recommendation."""

    feature: str
    contribution: float  # 0.0 to 1.0, all contributions sum to 1.0
    description: str = ""


@dataclass
class DependencyImpactDTO:
    """Dependency impact analysis for a recommendation."""

    composite_availability_bound: float
    bottleneck_service: str | None = None
    bottleneck_contribution: str = ""
    hard_dependency_count: int = 0
    soft_dependency_count: int = 0


@dataclass
class ExplanationDTO:
    """Full explanation for a recommendation."""

    summary: str
    feature_attribution: list[FeatureAttributionDTO] = field(default_factory=list)
    dependency_impact: DependencyImpactDTO | None = None


@dataclass
class DataQualityDTO:
    """Data quality metadata for a recommendation."""

    data_completeness: float  # 0.0 to 1.0
    telemetry_gaps: list[dict[str, Any]] = field(default_factory=list)
    confidence_note: str = ""
    is_cold_start: bool = False
    lookback_days_actual: int = 30


@dataclass
class RecommendationDTO:
    """A single SLO recommendation (availability or latency)."""

    sli_type: str  # "availability" | "latency"
    metric: str  # e.g., "error_rate", "p99_response_time_ms"
    tiers: dict[str, TierDTO]  # keyed by tier level ("conservative", etc.)
    explanation: ExplanationDTO
    data_quality: DataQualityDTO


@dataclass
class LookbackWindowDTO:
    """Lookback window for recommendation computation."""

    start: str  # ISO 8601
    end: str  # ISO 8601


@dataclass
class GetRecommendationResponse:
    """Response for retrieving pre-computed SLO recommendations."""

    service_id: str
    generated_at: str  # ISO 8601
    lookback_window: LookbackWindowDTO
    recommendations: list[RecommendationDTO] = field(default_factory=list)


@dataclass
class GenerateRecommendationResponse:
    """Response for generating new SLO recommendations."""

    service_id: str
    generated_at: str  # ISO 8601
    lookback_window: LookbackWindowDTO
    recommendations: list[RecommendationDTO] = field(default_factory=list)


@dataclass
class BatchComputeResult:
    """Result of batch recommendation computation."""

    total_services: int
    successful: int
    failed: int
    skipped: int  # discovered-only or insufficient data
    duration_seconds: float
    failures: list[dict[str, str]] = field(default_factory=list)  # [{"service_id": "...", "error": "..."}]
