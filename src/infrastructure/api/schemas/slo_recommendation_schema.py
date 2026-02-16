"""
Pydantic schemas for SLO recommendation API endpoints.

These schemas define the API request/response contracts and provide validation.
They are separate from application layer DTOs (which use dataclasses).
"""

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Query Parameters
# ============================================================================


class SloRecommendationQueryParams(BaseModel):
    """Query parameters for SLO recommendation retrieval."""

    sli_type: str = Field(
        default="all",
        description="SLI type filter: availability, latency, or all",
        pattern="^(availability|latency|all)$",
    )
    lookback_days: int = Field(
        default=30,
        ge=7,
        le=365,
        description="Lookback window in days (7-365)",
    )
    force_regenerate: bool = Field(
        default=False,
        description="Bypass cached results and recompute",
    )


# ============================================================================
# Response Models (Nested)
# ============================================================================


class TierApiModel(BaseModel):
    """A single tier (Conservative/Balanced/Aggressive) within a recommendation."""

    level: str = Field(..., description="Tier level: conservative, balanced, aggressive")
    target: float = Field(..., description="Target value (e.g., 99.9 for availability %)")

    # Availability-specific fields
    error_budget_monthly_minutes: float | None = Field(
        None, description="Monthly error budget in minutes (availability only)"
    )
    confidence_interval: tuple[float, float] | None = Field(
        None, description="95% confidence interval [lower, upper]"
    )

    # Common fields
    estimated_breach_probability: float = Field(
        0.0, ge=0.0, le=1.0, description="Probability of breaching this target (0.0-1.0)"
    )

    # Latency-specific fields
    percentile: str | None = Field(None, description="Percentile (e.g., p99) for latency")
    target_ms: int | None = Field(None, ge=0, description="Target latency in milliseconds")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "level": "balanced",
                "target": 99.9,
                "error_budget_monthly_minutes": 43.8,
                "estimated_breach_probability": 0.08,
                "confidence_interval": [99.8, 99.95],
            }
        }
    )


class FeatureAttributionApiModel(BaseModel):
    """A single feature's contribution to the recommendation."""

    feature: str = Field(..., description="Feature name")
    contribution: float = Field(
        ..., ge=0.0, le=1.0, description="Contribution weight (0.0-1.0)"
    )
    description: str = Field(default="", description="Human-readable description")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "feature": "historical_availability_mean",
                "contribution": 0.42,
                "description": "Historical availability performance over lookback window",
            }
        }
    )


class DependencyImpactApiModel(BaseModel):
    """Dependency impact analysis for a recommendation."""

    composite_availability_bound: float = Field(
        ..., ge=0.0, le=100.0, description="Composite availability bound considering dependencies (%)"
    )
    bottleneck_service: str | None = Field(
        None, description="Service contributing most to degradation"
    )
    bottleneck_contribution: str = Field(
        default="", description="Description of bottleneck's impact"
    )
    hard_dependency_count: int = Field(
        default=0, ge=0, description="Number of hard (critical) dependencies"
    )
    soft_dependency_count: int = Field(
        default=0, ge=0, description="Number of soft (non-critical) dependencies"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "composite_availability_bound": 99.70,
                "bottleneck_service": "external-payment-api",
                "bottleneck_contribution": "Consumes 50% of error budget at 99.9% target",
                "hard_dependency_count": 3,
                "soft_dependency_count": 1,
            }
        }
    )


class ExplanationApiModel(BaseModel):
    """Full explanation for a recommendation."""

    summary: str = Field(..., description="Human-readable summary of the recommendation")
    feature_attribution: list[FeatureAttributionApiModel] = Field(
        default_factory=list, description="Feature contributions to the recommendation"
    )
    dependency_impact: DependencyImpactApiModel | None = Field(
        None, description="Dependency impact analysis (availability only)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "summary": "checkout-service achieved 99.92% availability over 30 days. The Balanced target of 99.9% provides a 0.02% margin.",
                "feature_attribution": [
                    {
                        "feature": "historical_availability_mean",
                        "contribution": 0.42,
                        "description": "",
                    }
                ],
                "dependency_impact": {
                    "composite_availability_bound": 99.70,
                    "bottleneck_service": "external-payment-api",
                    "bottleneck_contribution": "Consumes 50% of error budget",
                    "hard_dependency_count": 3,
                    "soft_dependency_count": 1,
                },
            }
        }
    )


class DataQualityApiModel(BaseModel):
    """Data quality metadata for a recommendation."""

    data_completeness: float = Field(
        ..., ge=0.0, le=1.0, description="Data completeness score (0.0-1.0)"
    )
    telemetry_gaps: list[dict] = Field(
        default_factory=list, description="Detected gaps in telemetry data"
    )
    confidence_note: str = Field(
        default="", description="Human-readable confidence assessment"
    )
    is_cold_start: bool = Field(
        default=False, description="True if extended lookback was required due to insufficient data"
    )
    lookback_days_actual: int = Field(
        default=30, ge=7, le=365, description="Actual lookback window used (may differ from requested)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "data_completeness": 0.97,
                "telemetry_gaps": [],
                "confidence_note": "Based on 30 days of continuous data with 97% completeness",
                "is_cold_start": False,
                "lookback_days_actual": 30,
            }
        }
    )


class RecommendationApiModel(BaseModel):
    """A single SLO recommendation (availability or latency)."""

    sli_type: str = Field(..., description="SLI type: availability or latency")
    metric: str = Field(..., description="Metric name (e.g., error_rate, p99_response_time_ms)")
    tiers: dict[str, TierApiModel] = Field(
        ..., description="Tier recommendations keyed by level (conservative, balanced, aggressive)"
    )
    explanation: ExplanationApiModel = Field(..., description="Explanation and attribution")
    data_quality: DataQualityApiModel = Field(..., description="Data quality metadata")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "sli_type": "availability",
                "metric": "error_rate",
                "tiers": {
                    "conservative": {
                        "level": "conservative",
                        "target": 99.5,
                        "error_budget_monthly_minutes": 219.6,
                        "estimated_breach_probability": 0.02,
                        "confidence_interval": [99.3, 99.7],
                    },
                    "balanced": {
                        "level": "balanced",
                        "target": 99.9,
                        "error_budget_monthly_minutes": 43.8,
                        "estimated_breach_probability": 0.08,
                        "confidence_interval": [99.8, 99.95],
                    },
                    "aggressive": {
                        "level": "aggressive",
                        "target": 99.95,
                        "error_budget_monthly_minutes": 21.9,
                        "estimated_breach_probability": 0.18,
                        "confidence_interval": [99.9, 99.99],
                    },
                },
                "explanation": {
                    "summary": "checkout-service achieved 99.92% availability over 30 days.",
                    "feature_attribution": [],
                    "dependency_impact": None,
                },
                "data_quality": {
                    "data_completeness": 0.97,
                    "telemetry_gaps": [],
                    "confidence_note": "Based on 30 days of continuous data",
                    "is_cold_start": False,
                    "lookback_days_actual": 30,
                },
            }
        }
    )


class LookbackWindowApiModel(BaseModel):
    """Lookback window for recommendation computation."""

    start: str = Field(..., description="Start of lookback window (ISO 8601)")
    end: str = Field(..., description="End of lookback window (ISO 8601)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "start": "2026-01-16T00:00:00Z",
                "end": "2026-02-15T00:00:00Z",
            }
        }
    )


# ============================================================================
# Response Models (Top-Level)
# ============================================================================


class SloRecommendationApiResponse(BaseModel):
    """Response containing SLO recommendations for a service."""

    service_id: str = Field(..., description="Service business identifier")
    generated_at: str = Field(..., description="When recommendations were generated (ISO 8601)")
    lookback_window: LookbackWindowApiModel = Field(..., description="Lookback window used")
    recommendations: list[RecommendationApiModel] = Field(
        default_factory=list, description="List of recommendations (availability and/or latency)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "service_id": "checkout-service",
                "generated_at": "2026-02-15T10:30:00Z",
                "lookback_window": {
                    "start": "2026-01-16T00:00:00Z",
                    "end": "2026-02-15T00:00:00Z",
                },
                "recommendations": [
                    {
                        "sli_type": "availability",
                        "metric": "error_rate",
                        "tiers": {
                            "conservative": {
                                "level": "conservative",
                                "target": 99.5,
                                "error_budget_monthly_minutes": 219.6,
                                "estimated_breach_probability": 0.02,
                                "confidence_interval": [99.3, 99.7],
                            },
                            "balanced": {
                                "level": "balanced",
                                "target": 99.9,
                                "error_budget_monthly_minutes": 43.8,
                                "estimated_breach_probability": 0.08,
                                "confidence_interval": [99.8, 99.95],
                            },
                            "aggressive": {
                                "level": "aggressive",
                                "target": 99.95,
                                "error_budget_monthly_minutes": 21.9,
                                "estimated_breach_probability": 0.18,
                                "confidence_interval": [99.9, 99.99],
                            },
                        },
                        "explanation": {
                            "summary": "checkout-service achieved 99.92% availability over 30 days.",
                            "feature_attribution": [
                                {
                                    "feature": "historical_availability_mean",
                                    "contribution": 0.42,
                                    "description": "",
                                }
                            ],
                            "dependency_impact": {
                                "composite_availability_bound": 99.70,
                                "bottleneck_service": "external-payment-api",
                                "bottleneck_contribution": "Consumes 50% of error budget",
                                "hard_dependency_count": 3,
                                "soft_dependency_count": 1,
                            },
                        },
                        "data_quality": {
                            "data_completeness": 0.97,
                            "telemetry_gaps": [],
                            "confidence_note": "Based on 30 days of continuous data",
                            "is_cold_start": False,
                            "lookback_days_actual": 30,
                        },
                    },
                    {
                        "sli_type": "latency",
                        "metric": "p99_response_time_ms",
                        "tiers": {
                            "conservative": {
                                "level": "conservative",
                                "target_ms": 1200,
                                "percentile": "p99.9",
                                "estimated_breach_probability": 0.01,
                            },
                            "balanced": {
                                "level": "balanced",
                                "target_ms": 800,
                                "percentile": "p99",
                                "estimated_breach_probability": 0.05,
                            },
                            "aggressive": {
                                "level": "aggressive",
                                "target_ms": 500,
                                "percentile": "p95",
                                "estimated_breach_probability": 0.12,
                            },
                        },
                        "explanation": {
                            "summary": "End-to-end p99 latency measured at 780ms over 30 days.",
                            "feature_attribution": [
                                {
                                    "feature": "p99_latency_historical",
                                    "contribution": 0.50,
                                    "description": "",
                                }
                            ],
                        },
                        "data_quality": {
                            "data_completeness": 0.97,
                            "telemetry_gaps": [],
                            "confidence_note": "Based on 30 days of continuous data",
                            "is_cold_start": False,
                            "lookback_days_actual": 30,
                        },
                    },
                ],
            }
        }
    )
