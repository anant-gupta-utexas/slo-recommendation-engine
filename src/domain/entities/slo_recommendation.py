"""Domain entities for SLO recommendations.

This module defines the core domain entities for representing SLO recommendations,
including recommendation tiers, feature attributions, dependency impacts, and data quality metadata.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import UUID, uuid4


class SliType(str, Enum):
    """Type of Service Level Indicator."""

    AVAILABILITY = "availability"
    LATENCY = "latency"


class RecommendationStatus(str, Enum):
    """Status of an SLO recommendation."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class TierLevel(str, Enum):
    """Tier level for SLO recommendations."""

    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


@dataclass
class RecommendationTier:
    """A single tier (Conservative/Balanced/Aggressive) within a recommendation.

    Attributes:
        level: The tier level (conservative, balanced, or aggressive)
        target: Target value (e.g., 99.9 for availability %, 800 for latency ms)
        error_budget_monthly_minutes: Monthly error budget in minutes (availability only)
        estimated_breach_probability: Probability of breaching this target (0.0-1.0)
        confidence_interval: Lower and upper bounds of confidence interval
        percentile: Percentile string (latency only, e.g., "p99")
        target_ms: Target in milliseconds (latency only)
    """

    level: TierLevel
    target: float
    error_budget_monthly_minutes: float | None = None
    estimated_breach_probability: float = 0.0
    confidence_interval: tuple[float, float] | None = None
    percentile: str | None = None
    target_ms: int | None = None

    def __post_init__(self):
        """Validate tier constraints."""
        if not (0.0 <= self.estimated_breach_probability <= 1.0):
            raise ValueError(
                f"estimated_breach_probability must be between 0.0 and 1.0, got {self.estimated_breach_probability}"
            )


@dataclass
class FeatureAttribution:
    """A single feature's contribution to the recommendation.

    Attributes:
        feature: Feature name (e.g., "historical_availability_mean")
        contribution: Normalized contribution weight (0.0-1.0, all sum to 1.0)
        description: Human-readable description of the feature
    """

    feature: str
    contribution: float
    description: str = ""

    def __post_init__(self):
        """Validate attribution constraints."""
        if not (0.0 <= self.contribution <= 1.0):
            raise ValueError(
                f"contribution must be between 0.0 and 1.0, got {self.contribution}"
            )


@dataclass
class DependencyImpact:
    """Dependency impact analysis for a recommendation.

    Attributes:
        composite_availability_bound: Upper bound on achievable availability given dependencies
        bottleneck_service: Name of the dependency contributing most to degradation
        bottleneck_contribution: Description of bottleneck's impact
        hard_dependency_count: Number of hard (synchronous, critical) dependencies
        soft_dependency_count: Number of soft dependencies
    """

    composite_availability_bound: float
    bottleneck_service: str | None = None
    bottleneck_contribution: str = ""
    hard_dependency_count: int = 0
    soft_dependency_count: int = 0

    def __post_init__(self):
        """Validate dependency impact constraints."""
        if not (0.0 <= self.composite_availability_bound <= 1.0):
            raise ValueError(
                f"composite_availability_bound must be between 0.0 and 1.0, got {self.composite_availability_bound}"
            )
        if self.hard_dependency_count < 0:
            raise ValueError(
                f"hard_dependency_count must be non-negative, got {self.hard_dependency_count}"
            )
        if self.soft_dependency_count < 0:
            raise ValueError(
                f"soft_dependency_count must be non-negative, got {self.soft_dependency_count}"
            )


@dataclass
class DataQuality:
    """Data quality metadata for a recommendation.

    Attributes:
        data_completeness: Fraction of expected data points present (0.0-1.0)
        telemetry_gaps: List of gap descriptions (e.g., [{"start": "...", "end": "...", "reason": "..."}])
        confidence_note: Human-readable note about confidence level
        is_cold_start: Whether extended lookback was triggered due to insufficient data
        lookback_days_actual: Actual number of days used for lookback
    """

    data_completeness: float
    telemetry_gaps: list[dict] = field(default_factory=list)
    confidence_note: str = ""
    is_cold_start: bool = False
    lookback_days_actual: int = 30

    def __post_init__(self):
        """Validate data quality constraints."""
        if not (0.0 <= self.data_completeness <= 1.0):
            raise ValueError(
                f"data_completeness must be between 0.0 and 1.0, got {self.data_completeness}"
            )
        if self.lookback_days_actual < 1:
            raise ValueError(
                f"lookback_days_actual must be positive, got {self.lookback_days_actual}"
            )


@dataclass
class Counterfactual:
    """A single counterfactual "what-if" statement for FR-7 explainability.

    Attributes:
        condition: Human-readable condition (e.g., "If external-payment-api improved to 99.99%")
        result: Human-readable result (e.g., "Recommended target would increase to 99.95%")
        feature: The feature that was perturbed
        original_value: Original feature value
        perturbed_value: Perturbed feature value
    """

    condition: str
    result: str
    feature: str = ""
    original_value: float = 0.0
    perturbed_value: float = 0.0


@dataclass
class DataProvenance:
    """Data provenance metadata for FR-7 explainability.

    Attributes:
        dependency_graph_version: Timestamp of the graph snapshot used
        telemetry_window_start: Start of telemetry window (ISO 8601)
        telemetry_window_end: End of telemetry window (ISO 8601)
        data_completeness: Data completeness score (0.0-1.0)
        computation_method: Algorithm used for computation
        telemetry_source: Source of telemetry data
    """

    dependency_graph_version: str = ""
    telemetry_window_start: str = ""
    telemetry_window_end: str = ""
    data_completeness: float = 0.0
    computation_method: str = "composite_reliability_math_v1"
    telemetry_source: str = "mock_prometheus"


@dataclass
class Explanation:
    """Full explanation for a recommendation.

    Attributes:
        summary: High-level summary of the recommendation
        feature_attribution: List of feature contributions
        dependency_impact: Dependency impact analysis (availability only)
        counterfactuals: List of "what-if" counterfactual statements (FR-7)
        provenance: Data provenance metadata (FR-7)
    """

    summary: str
    feature_attribution: list[FeatureAttribution] = field(default_factory=list)
    dependency_impact: DependencyImpact | None = None
    counterfactuals: list[Counterfactual] = field(default_factory=list)
    provenance: DataProvenance | None = None


@dataclass
class SloRecommendation:
    """Represents a single SLO recommendation for one SLI type.

    Attributes:
        service_id: UUID of the service this recommendation is for
        sli_type: Type of SLI (availability or latency)
        tiers: Map of tier levels to recommendation tiers
        explanation: Full explanation of the recommendation
        data_quality: Data quality metadata
        lookback_window_start: Start of the telemetry lookback window
        lookback_window_end: End of the telemetry lookback window
        metric: Metric name (e.g., "error_rate", "p99_response_time_ms")
        id: Unique identifier for this recommendation
        status: Current status of the recommendation
        generated_at: When this recommendation was generated
        expires_at: When this recommendation expires
    """

    service_id: UUID
    sli_type: SliType
    tiers: dict[TierLevel, RecommendationTier]
    explanation: Explanation
    data_quality: DataQuality
    lookback_window_start: datetime
    lookback_window_end: datetime
    metric: str
    id: UUID = field(default_factory=uuid4)
    status: RecommendationStatus = RecommendationStatus.ACTIVE
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None

    def __post_init__(self):
        """Auto-compute expiry timestamp if not provided."""
        if self.expires_at is None:
            self.expires_at = self.generated_at + timedelta(hours=24)

        # Validate required tiers
        if not self.tiers:
            raise ValueError("tiers dict cannot be empty")

        # Validate lookback window
        if self.lookback_window_end <= self.lookback_window_start:
            raise ValueError(
                "lookback_window_end must be after lookback_window_start"
            )

    def supersede(self) -> None:
        """Mark this recommendation as superseded by a newer one."""
        self.status = RecommendationStatus.SUPERSEDED

    def expire(self) -> None:
        """Mark this recommendation as expired."""
        self.status = RecommendationStatus.EXPIRED

    @property
    def is_expired(self) -> bool:
        """Check if this recommendation has expired.

        Returns:
            True if the current time is past the expiry timestamp
        """
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at
