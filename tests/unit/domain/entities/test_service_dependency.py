"""Unit tests for ServiceDependency entity."""

import pytest
from datetime import datetime, timezone
from uuid import UUID, uuid4

from src.domain.entities.service_dependency import (
    CommunicationMode,
    DependencyCriticality,
    DiscoverySource,
    RetryConfig,
    ServiceDependency,
)


class TestCommunicationMode:
    """Test cases for CommunicationMode enum."""

    def test_communication_mode_values(self):
        """Test that all expected communication modes exist."""
        assert CommunicationMode.SYNC.value == "sync"
        assert CommunicationMode.ASYNC.value == "async"


class TestDependencyCriticality:
    """Test cases for DependencyCriticality enum."""

    def test_dependency_criticality_values(self):
        """Test that all expected criticality levels exist."""
        assert DependencyCriticality.HARD.value == "hard"
        assert DependencyCriticality.SOFT.value == "soft"
        assert DependencyCriticality.DEGRADED.value == "degraded"


class TestDiscoverySource:
    """Test cases for DiscoverySource enum."""

    def test_discovery_source_values(self):
        """Test that all expected discovery sources exist."""
        assert DiscoverySource.MANUAL.value == "manual"
        assert DiscoverySource.OTEL_SERVICE_GRAPH.value == "otel_service_graph"
        assert DiscoverySource.KUBERNETES.value == "kubernetes"
        assert DiscoverySource.SERVICE_MESH.value == "service_mesh"


class TestRetryConfig:
    """Test cases for RetryConfig dataclass."""

    def test_retry_config_default_values(self):
        """Test RetryConfig with default values."""
        config = RetryConfig()

        assert config.max_retries == 3
        assert config.backoff_strategy == "exponential"

    def test_retry_config_custom_values(self):
        """Test RetryConfig with custom values."""
        config = RetryConfig(max_retries=5, backoff_strategy="linear")

        assert config.max_retries == 5
        assert config.backoff_strategy == "linear"

    def test_retry_config_negative_retries_raises(self):
        """Test that negative max_retries raises ValueError."""
        with pytest.raises(ValueError, match="max_retries must be non-negative"):
            RetryConfig(max_retries=-1)

    def test_retry_config_invalid_strategy_raises(self):
        """Test that invalid backoff strategy raises ValueError."""
        with pytest.raises(ValueError, match="backoff_strategy must be one of"):
            RetryConfig(backoff_strategy="invalid")

    def test_retry_config_valid_strategies(self):
        """Test all valid backoff strategies."""
        valid_strategies = ["exponential", "linear", "constant"]

        for strategy in valid_strategies:
            config = RetryConfig(backoff_strategy=strategy)
            assert config.backoff_strategy == strategy


class TestServiceDependency:
    """Test cases for ServiceDependency entity."""

    @pytest.fixture
    def source_id(self):
        """Fixture for source service UUID."""
        return uuid4()

    @pytest.fixture
    def target_id(self):
        """Fixture for target service UUID."""
        return uuid4()

    def test_dependency_creation_minimal_fields(self, source_id, target_id):
        """Test creating a dependency with only required fields."""
        dep = ServiceDependency(
            source_service_id=source_id,
            target_service_id=target_id,
            communication_mode=CommunicationMode.SYNC,
        )

        assert dep.source_service_id == source_id
        assert dep.target_service_id == target_id
        assert dep.communication_mode == CommunicationMode.SYNC
        assert dep.criticality == DependencyCriticality.HARD
        assert dep.protocol is None
        assert dep.timeout_ms is None
        assert dep.retry_config is None
        assert dep.discovery_source == DiscoverySource.MANUAL
        assert dep.confidence_score == 1.0
        assert dep.is_stale is False
        assert isinstance(dep.id, UUID)
        assert isinstance(dep.created_at, datetime)
        assert isinstance(dep.updated_at, datetime)
        assert isinstance(dep.last_observed_at, datetime)

    def test_dependency_creation_all_fields(self, source_id, target_id):
        """Test creating a dependency with all fields specified."""
        retry_config = RetryConfig(max_retries=5, backoff_strategy="linear")
        dep = ServiceDependency(
            source_service_id=source_id,
            target_service_id=target_id,
            communication_mode=CommunicationMode.ASYNC,
            criticality=DependencyCriticality.SOFT,
            protocol="kafka",
            timeout_ms=5000,
            retry_config=retry_config,
            discovery_source=DiscoverySource.OTEL_SERVICE_GRAPH,
            confidence_score=0.85,
        )

        assert dep.communication_mode == CommunicationMode.ASYNC
        assert dep.criticality == DependencyCriticality.SOFT
        assert dep.protocol == "kafka"
        assert dep.timeout_ms == 5000
        assert dep.retry_config == retry_config
        assert dep.discovery_source == DiscoverySource.OTEL_SERVICE_GRAPH
        assert dep.confidence_score == 0.85

    def test_dependency_self_loop_raises(self):
        """Test that self-loops raise ValueError."""
        same_id = uuid4()

        with pytest.raises(ValueError, match="Self-loops not allowed"):
            ServiceDependency(
                source_service_id=same_id,
                target_service_id=same_id,
                communication_mode=CommunicationMode.SYNC,
            )

    def test_dependency_confidence_score_bounds(self, source_id, target_id):
        """Test that confidence_score must be in [0.0, 1.0]."""
        # Valid bounds
        dep = ServiceDependency(
            source_service_id=source_id,
            target_service_id=target_id,
            communication_mode=CommunicationMode.SYNC,
            confidence_score=0.0,
        )
        assert dep.confidence_score == 0.0

        dep = ServiceDependency(
            source_service_id=source_id,
            target_service_id=target_id,
            communication_mode=CommunicationMode.SYNC,
            confidence_score=1.0,
        )
        assert dep.confidence_score == 1.0

        # Invalid: too low
        with pytest.raises(ValueError, match="confidence_score must be between"):
            ServiceDependency(
                source_service_id=source_id,
                target_service_id=target_id,
                communication_mode=CommunicationMode.SYNC,
                confidence_score=-0.1,
            )

        # Invalid: too high
        with pytest.raises(ValueError, match="confidence_score must be between"):
            ServiceDependency(
                source_service_id=source_id,
                target_service_id=target_id,
                communication_mode=CommunicationMode.SYNC,
                confidence_score=1.1,
            )

    def test_dependency_timeout_must_be_positive(self, source_id, target_id):
        """Test that timeout_ms must be positive."""
        # Valid
        dep = ServiceDependency(
            source_service_id=source_id,
            target_service_id=target_id,
            communication_mode=CommunicationMode.SYNC,
            timeout_ms=1000,
        )
        assert dep.timeout_ms == 1000

        # Invalid: zero
        with pytest.raises(ValueError, match="timeout_ms must be positive"):
            ServiceDependency(
                source_service_id=source_id,
                target_service_id=target_id,
                communication_mode=CommunicationMode.SYNC,
                timeout_ms=0,
            )

        # Invalid: negative
        with pytest.raises(ValueError, match="timeout_ms must be positive"):
            ServiceDependency(
                source_service_id=source_id,
                target_service_id=target_id,
                communication_mode=CommunicationMode.SYNC,
                timeout_ms=-100,
            )

    def test_mark_as_stale(self, source_id, target_id):
        """Test marking dependency as stale."""
        dep = ServiceDependency(
            source_service_id=source_id,
            target_service_id=target_id,
            communication_mode=CommunicationMode.SYNC,
        )
        original_updated_at = dep.updated_at

        assert dep.is_stale is False

        dep.mark_as_stale()

        assert dep.is_stale is True
        assert dep.updated_at > original_updated_at

    def test_refresh(self, source_id, target_id):
        """Test refreshing a stale dependency."""
        dep = ServiceDependency(
            source_service_id=source_id,
            target_service_id=target_id,
            communication_mode=CommunicationMode.SYNC,
        )

        # Mark as stale first
        dep.mark_as_stale()
        assert dep.is_stale is True
        stale_updated_at = dep.updated_at
        stale_observed_at = dep.last_observed_at

        # Refresh
        dep.refresh()

        assert dep.is_stale is False
        assert dep.updated_at > stale_updated_at
        assert dep.last_observed_at > stale_observed_at

    def test_dependency_timestamps_use_utc(self, source_id, target_id):
        """Test that timestamps use UTC timezone."""
        dep = ServiceDependency(
            source_service_id=source_id,
            target_service_id=target_id,
            communication_mode=CommunicationMode.SYNC,
        )

        assert dep.created_at.tzinfo == timezone.utc
        assert dep.updated_at.tzinfo == timezone.utc
        assert dep.last_observed_at.tzinfo == timezone.utc

    def test_dependency_with_different_protocols(self, source_id, target_id):
        """Test creating dependencies with different protocols."""
        protocols = ["grpc", "http", "kafka", "amqp", "redis"]

        for protocol in protocols:
            dep = ServiceDependency(
                source_service_id=source_id,
                target_service_id=target_id,
                communication_mode=CommunicationMode.SYNC,
                protocol=protocol,
            )
            assert dep.protocol == protocol

    def test_dependency_with_all_discovery_sources(self, source_id, target_id):
        """Test creating dependencies from each discovery source."""
        for source in DiscoverySource:
            dep = ServiceDependency(
                source_service_id=source_id,
                target_service_id=target_id,
                communication_mode=CommunicationMode.SYNC,
                discovery_source=source,
            )
            assert dep.discovery_source == source

    def test_dependency_with_all_criticalities(self, source_id, target_id):
        """Test creating dependencies with each criticality level."""
        for criticality in DependencyCriticality:
            dep = ServiceDependency(
                source_service_id=source_id,
                target_service_id=target_id,
                communication_mode=CommunicationMode.SYNC,
                criticality=criticality,
            )
            assert dep.criticality == criticality
