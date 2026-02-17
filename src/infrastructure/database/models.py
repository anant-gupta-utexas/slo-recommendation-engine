"""SQLAlchemy models for Service Dependency Graph and SLO Recommendations.

These models map domain entities to PostgreSQL tables using SQLAlchemy ORM.
All tables use UUIDs as primary keys and include audit timestamps.

FR-1: ServiceModel, ServiceDependencyModel, CircularDependencyAlertModel, ApiKeyModel
FR-2: SloRecommendationModel, SliAggregateModel
"""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DECIMAL,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy models with async support."""

    pass


class ServiceModel(Base):
    """SQLAlchemy model for the services table.

    Represents a microservice in the dependency graph.
    """

    __tablename__ = "services"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )

    # Business identifier (unique)
    service_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Service metadata (JSONB for flexible schema)
    # Note: Using metadata_ to avoid conflict with SQLAlchemy's reserved metadata attribute
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )

    # Criticality level
    criticality: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")

    # Owning team
    team: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Discovered flag (true if auto-created from unknown edge reference)
    discovered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # FR-3: Service type (internal or external)
    service_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="internal"
    )

    # FR-3: Published SLA for external services (as ratio, e.g., 0.9999 for 99.99%)
    published_sla: Mapped[float | None] = mapped_column(
        DECIMAL(precision=8, scale=6), nullable=True
    )

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        CheckConstraint(
            "criticality IN ('critical', 'high', 'medium', 'low')",
            name="ck_services_criticality",
        ),
        CheckConstraint(
            "service_type IN ('internal', 'external')",
            name="ck_service_type",
        ),
    )


class ServiceDependencyModel(Base):
    """SQLAlchemy model for the service_dependencies table.

    Represents a directed edge from source service to target service.
    """

    __tablename__ = "service_dependencies"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )

    # Foreign keys to services
    source_service_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    target_service_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    # Edge attributes
    communication_mode: Mapped[str] = mapped_column(String(10), nullable=False)
    criticality: Mapped[str] = mapped_column(String(20), nullable=False, default="hard")
    protocol: Mapped[str | None] = mapped_column(String(50), nullable=True)
    timeout_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Discovery metadata
    discovery_source: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0
    )

    # Staleness tracking
    last_observed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        # Unique constraint: same edge from same source (allow different sources)
        UniqueConstraint(
            "source_service_id",
            "target_service_id",
            "discovery_source",
            name="uq_edge_per_source",
        ),
        # Prevent self-loops
        CheckConstraint(
            "source_service_id != target_service_id",
            name="ck_no_self_loops",
        ),
        # Communication mode validation
        CheckConstraint(
            "communication_mode IN ('sync', 'async')",
            name="ck_communication_mode",
        ),
        # Dependency criticality validation
        CheckConstraint(
            "criticality IN ('hard', 'soft', 'degraded')",
            name="ck_dependency_criticality",
        ),
        # Discovery source validation
        CheckConstraint(
            "discovery_source IN ('manual', 'otel_service_graph', 'kubernetes', 'service_mesh')",
            name="ck_discovery_source",
        ),
        # Confidence score bounds
        CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 1.0",
            name="ck_confidence_score_bounds",
        ),
        # Timeout positivity
        CheckConstraint(
            "timeout_ms IS NULL OR timeout_ms > 0",
            name="ck_timeout_positive",
        ),
    )


class CircularDependencyAlertModel(Base):
    """SQLAlchemy model for the circular_dependency_alerts table.

    Represents a detected circular dependency (strongly connected component).
    """

    __tablename__ = "circular_dependency_alerts"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )

    # Cycle path (array of service_ids forming the cycle)
    cycle_path: Mapped[list[str]] = mapped_column(JSONB, nullable=False)

    # Alert status
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")

    # Resolution tracking
    acknowledged_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Audit timestamp
    detected_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        # Unique constraint: prevent duplicate alerts for same cycle
        UniqueConstraint("cycle_path", name="uq_cycle_path"),
        # Status validation
        CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved')",
            name="ck_alert_status",
        ),
    )


class ApiKeyModel(Base):
    """SQLAlchemy model for the api_keys table.

    Stores API keys for authenticating API clients.
    Keys are stored as bcrypt hashes for security.
    """

    __tablename__ = "api_keys"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )

    # Key identifier (human-readable name)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Bcrypt hash of the API key
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Client metadata
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Revocation
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    revoked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    revoked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )


class SloRecommendationModel(Base):
    """SQLAlchemy model for the slo_recommendations table (FR-2).

    Stores pre-computed SLO recommendations for services with tiers and explanations.
    """

    __tablename__ = "slo_recommendations"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )

    # Foreign key to services
    service_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # SLI type
    sli_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # Metric name
    metric: Mapped[str] = mapped_column(String(50), nullable=False)

    # Recommendation tiers (JSONB)
    tiers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Explanation (JSONB)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Data quality metadata (JSONB)
    data_quality: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Lookback window
    lookback_window_start: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    lookback_window_end: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )

    # Generation and expiry timestamps
    generated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )

    # Status
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    __table_args__ = (
        # SLI type validation
        CheckConstraint(
            "sli_type IN ('availability', 'latency')",
            name="ck_slo_rec_sli_type",
        ),
        # Status validation
        CheckConstraint(
            "status IN ('active', 'superseded', 'expired')",
            name="ck_slo_rec_status",
        ),
        # Lookback window sanity check
        CheckConstraint(
            "lookback_window_start < lookback_window_end",
            name="ck_slo_rec_lookback_window",
        ),
    )


class SliAggregateModel(Base):
    """SQLAlchemy model for the sli_aggregates table (FR-2).

    Stores pre-aggregated SLI metrics for efficient recommendation computation.
    """

    __tablename__ = "sli_aggregates"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )

    # Foreign key to services
    service_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # SLI type
    sli_type: Mapped[str] = mapped_column(String(30), nullable=False)

    # Time window (quoted because "window" is a SQL reserved keyword)
    window: Mapped[str] = mapped_column("time_window", String(10), nullable=False)

    # Aggregated value
    value: Mapped[float] = mapped_column(DECIMAL, nullable=False)

    # Sample count
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Computation timestamp
    computed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        # SLI type validation
        CheckConstraint(
            "sli_type IN ('availability', 'latency_p50', 'latency_p95', 'latency_p99', 'latency_p999', 'error_rate', 'request_rate')",
            name="ck_sli_type",
        ),
        # Window validation
        CheckConstraint(
            "time_window IN ('1h', '1d', '7d', '28d', '90d')",
            name="ck_sli_window",
        ),
        # Sample count non-negative
        CheckConstraint(
            "sample_count >= 0",
            name="ck_sli_sample_count",
        ),
    )
