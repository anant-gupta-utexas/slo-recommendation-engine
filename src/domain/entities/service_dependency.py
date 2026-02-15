"""ServiceDependency entity module.

This module defines the ServiceDependency entity representing directed edges
between services in the dependency graph.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4


class CommunicationMode(str, Enum):
    """Communication mode between services."""

    SYNC = "sync"
    ASYNC = "async"


class DependencyCriticality(str, Enum):
    """Criticality level of a dependency."""

    HARD = "hard"  # Service cannot function without this dependency
    SOFT = "soft"  # Service can degrade gracefully
    DEGRADED = "degraded"  # Service runs in degraded mode without this


class DiscoverySource(str, Enum):
    """Source of dependency discovery."""

    MANUAL = "manual"
    OTEL_SERVICE_GRAPH = "otel_service_graph"
    KUBERNETES = "kubernetes"
    SERVICE_MESH = "service_mesh"


@dataclass
class RetryConfig:
    """Retry configuration for a dependency.

    Attributes:
        max_retries: Maximum number of retry attempts
        backoff_strategy: Strategy for retry backoff (exponential, linear, constant)
    """

    max_retries: int = 3
    backoff_strategy: str = "exponential"  # exponential, linear, constant

    def __post_init__(self):
        """Validate retry configuration."""
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")

        valid_strategies = {"exponential", "linear", "constant"}
        if self.backoff_strategy not in valid_strategies:
            raise ValueError(
                f"backoff_strategy must be one of {valid_strategies}, "
                f"got: {self.backoff_strategy}"
            )


@dataclass
class ServiceDependency:
    """Represents a directed edge from source service to target service.

    Domain invariants:
    - source and target must reference valid Service entities
    - confidence_score must be in [0.0, 1.0]
    - timeout_ms must be positive if specified
    - self-loops are not allowed (source != target)

    Attributes:
        source_service_id: UUID of the source service
        target_service_id: UUID of the target service
        communication_mode: How services communicate (sync/async)
        criticality: How critical this dependency is
        protocol: Communication protocol (grpc, http, kafka, etc.)
        timeout_ms: Timeout in milliseconds
        retry_config: Retry configuration
        discovery_source: How this dependency was discovered
        confidence_score: Confidence in this dependency (0.0 to 1.0)
        last_observed_at: Last time this dependency was observed
        is_stale: Whether this dependency is stale (not observed recently)
        id: Internal UUID identifier
        created_at: Timestamp when dependency was created
        updated_at: Timestamp when dependency was last updated
    """

    source_service_id: UUID  # FK to services.id
    target_service_id: UUID  # FK to services.id
    communication_mode: CommunicationMode
    criticality: DependencyCriticality = DependencyCriticality.HARD
    protocol: str | None = None  # grpc, http, kafka, etc.
    timeout_ms: int | None = None
    retry_config: RetryConfig | None = None
    discovery_source: DiscoverySource = DiscoverySource.MANUAL
    confidence_score: float = 1.0  # 0.0 to 1.0

    # Staleness tracking
    last_observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_stale: bool = False

    # Audit fields
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        """Validate domain invariants after initialization."""
        if not (0.0 <= self.confidence_score <= 1.0):
            raise ValueError(
                f"confidence_score must be between 0.0 and 1.0, "
                f"got: {self.confidence_score}"
            )

        if self.timeout_ms is not None and self.timeout_ms <= 0:
            raise ValueError(
                f"timeout_ms must be positive, got: {self.timeout_ms}"
            )

        if self.source_service_id == self.target_service_id:
            raise ValueError(
                "Self-loops not allowed (source_service_id == target_service_id)"
            )

    def mark_as_stale(self):
        """Mark this edge as stale (not observed recently)."""
        self.is_stale = True
        self.updated_at = datetime.now(timezone.utc)

    def refresh(self):
        """Refresh this edge (observed again)."""
        self.is_stale = False
        self.last_observed_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
