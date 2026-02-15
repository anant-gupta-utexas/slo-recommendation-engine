"""SQLAlchemy models for FR-1 Service Dependency Graph.

These models map domain entities to PostgreSQL tables using SQLAlchemy ORM.
All tables use UUIDs as primary keys and include audit timestamps.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
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
