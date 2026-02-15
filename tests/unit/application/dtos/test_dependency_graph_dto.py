"""Unit tests for dependency graph DTOs."""

import pytest
from datetime import datetime
from uuid import UUID

from src.application.dtos.dependency_graph_dto import (
    NodeDTO,
    RetryConfigDTO,
    EdgeAttributesDTO,
    EdgeDTO,
    DependencyGraphIngestRequest,
    CircularDependencyInfo,
    DependencyGraphIngestResponse,
)


class TestRetryConfigDTO:
    """Test RetryConfigDTO."""

    def test_create_retry_config_with_defaults(self):
        """Test creating RetryConfig with default values."""
        retry = RetryConfigDTO()

        assert retry.max_retries == 3
        assert retry.backoff_strategy == "exponential"

    def test_create_retry_config_with_custom_values(self):
        """Test creating RetryConfig with custom values."""
        retry = RetryConfigDTO(max_retries=5, backoff_strategy="linear")

        assert retry.max_retries == 5
        assert retry.backoff_strategy == "linear"


class TestEdgeAttributesDTO:
    """Test EdgeAttributesDTO."""

    def test_create_edge_attributes_minimal(self):
        """Test creating EdgeAttributes with minimal required fields."""
        attrs = EdgeAttributesDTO(
            communication_mode="sync",
            criticality="hard"
        )

        assert attrs.communication_mode == "sync"
        assert attrs.criticality == "hard"
        assert attrs.protocol is None
        assert attrs.timeout_ms is None
        assert attrs.retry_config is None

    def test_create_edge_attributes_with_all_fields(self):
        """Test creating EdgeAttributes with all fields."""
        retry_config = RetryConfigDTO(max_retries=3, backoff_strategy="exponential")

        attrs = EdgeAttributesDTO(
            communication_mode="async",
            criticality="soft",
            protocol="kafka",
            timeout_ms=30000,
            retry_config=retry_config
        )

        assert attrs.communication_mode == "async"
        assert attrs.criticality == "soft"
        assert attrs.protocol == "kafka"
        assert attrs.timeout_ms == 30000
        assert attrs.retry_config.max_retries == 3
        assert attrs.retry_config.backoff_strategy == "exponential"


class TestNodeDTO:
    """Test NodeDTO."""

    def test_create_node_with_minimal_fields(self):
        """Test creating Node with minimal required fields."""
        node = NodeDTO(service_id="test-service")

        assert node.service_id == "test-service"
        assert node.metadata == {}

    def test_create_node_with_metadata(self):
        """Test creating Node with metadata."""
        metadata = {
            "team": "platform",
            "criticality": "high",
            "tier": 1
        }

        node = NodeDTO(service_id="test-service", metadata=metadata)

        assert node.service_id == "test-service"
        assert node.metadata == metadata
        assert node.metadata["team"] == "platform"


class TestEdgeDTO:
    """Test EdgeDTO."""

    def test_create_edge_minimal(self):
        """Test creating Edge with minimal required fields."""
        attrs = EdgeAttributesDTO(
            communication_mode="sync",
            criticality="hard"
        )

        edge = EdgeDTO(
            source="service-a",
            target="service-b",
            attributes=attrs
        )

        assert edge.source == "service-a"
        assert edge.target == "service-b"
        assert edge.attributes.communication_mode == "sync"

    def test_create_edge_with_all_attributes(self):
        """Test creating Edge with all attributes."""
        retry_config = RetryConfigDTO(max_retries=5, backoff_strategy="linear")
        attrs = EdgeAttributesDTO(
            communication_mode="sync",
            criticality="hard",
            protocol="grpc",
            timeout_ms=5000,
            retry_config=retry_config
        )

        edge = EdgeDTO(
            source="checkout-service",
            target="payment-service",
            attributes=attrs
        )

        assert edge.source == "checkout-service"
        assert edge.target == "payment-service"
        assert edge.attributes.protocol == "grpc"
        assert edge.attributes.timeout_ms == 5000


class TestDependencyGraphIngestRequest:
    """Test DependencyGraphIngestRequest."""

    def test_create_ingest_request_with_valid_source(self):
        """Test creating ingest request with valid discovery source."""
        timestamp = datetime.now()
        node = NodeDTO(service_id="service-a", metadata={"team": "platform"})

        attrs = EdgeAttributesDTO(
            communication_mode="sync",
            criticality="hard"
        )
        edge = EdgeDTO(source="service-a", target="service-b", attributes=attrs)

        request = DependencyGraphIngestRequest(
            source="manual",
            timestamp=timestamp,
            nodes=[node],
            edges=[edge]
        )

        assert request.source == "manual"
        assert request.timestamp == timestamp
        assert len(request.nodes) == 1
        assert len(request.edges) == 1

    def test_create_ingest_request_with_otel_source(self):
        """Test creating ingest request with OTel source."""
        timestamp = datetime.now()

        request = DependencyGraphIngestRequest(
            source="otel_service_graph",
            timestamp=timestamp,
            nodes=[],
            edges=[]
        )

        assert request.source == "otel_service_graph"

    def test_create_ingest_request_with_empty_lists(self):
        """Test creating ingest request with empty nodes and edges."""
        timestamp = datetime.now()

        request = DependencyGraphIngestRequest(
            source="manual",
            timestamp=timestamp,
            nodes=[],
            edges=[]
        )

        assert len(request.nodes) == 0
        assert len(request.edges) == 0


class TestCircularDependencyInfo:
    """Test CircularDependencyInfo."""

    def test_create_circular_dependency_info(self):
        """Test creating CircularDependencyInfo."""
        alert_id = UUID("12345678-1234-5678-1234-567812345678")

        info = CircularDependencyInfo(
            cycle_path=["service-a", "service-b", "service-c", "service-a"],
            alert_id=alert_id
        )

        assert info.cycle_path == ["service-a", "service-b", "service-c", "service-a"]
        assert info.alert_id == alert_id


class TestDependencyGraphIngestResponse:
    """Test DependencyGraphIngestResponse."""

    def test_create_ingest_response_successful(self):
        """Test creating successful ingest response."""
        ingestion_id = UUID("12345678-1234-5678-1234-567812345678")

        response = DependencyGraphIngestResponse(
            ingestion_id=ingestion_id,
            status="completed",
            nodes_received=10,
            edges_received=20,
            nodes_upserted=10,
            edges_upserted=20,
            circular_dependencies_detected=[],
            conflicts_resolved=[],
            warnings=[],
            estimated_completion_seconds=5
        )

        assert response.ingestion_id == ingestion_id
        assert response.status == "completed"
        assert response.nodes_received == 10
        assert response.edges_received == 20
        assert response.nodes_upserted == 10
        assert response.edges_upserted == 20
        assert len(response.circular_dependencies_detected) == 0
        assert len(response.warnings) == 0

    def test_create_ingest_response_with_circular_dependencies(self):
        """Test creating ingest response with circular dependencies."""
        ingestion_id = UUID("12345678-1234-5678-1234-567812345678")
        alert_id = UUID("87654321-4321-8765-4321-876543218765")

        cycle_info = CircularDependencyInfo(
            cycle_path=["svc-a", "svc-b", "svc-a"],
            alert_id=alert_id
        )

        response = DependencyGraphIngestResponse(
            ingestion_id=ingestion_id,
            status="completed",
            nodes_received=2,
            edges_received=2,
            nodes_upserted=2,
            edges_upserted=2,
            circular_dependencies_detected=[cycle_info],
            conflicts_resolved=[],
            warnings=["Circular dependency detected"],
            estimated_completion_seconds=2
        )

        assert len(response.circular_dependencies_detected) == 1
        assert response.circular_dependencies_detected[0].cycle_path == ["svc-a", "svc-b", "svc-a"]
        assert len(response.warnings) == 1

    def test_create_ingest_response_with_warnings(self):
        """Test creating ingest response with warnings."""
        ingestion_id = UUID("12345678-1234-5678-1234-567812345678")

        response = DependencyGraphIngestResponse(
            ingestion_id=ingestion_id,
            status="completed",
            nodes_received=5,
            edges_received=10,
            nodes_upserted=5,
            edges_upserted=8,
            circular_dependencies_detected=[],
            conflicts_resolved=[],
            warnings=[
                "2 unknown services auto-created as placeholders",
                "Some edges were skipped due to validation errors"
            ],
            estimated_completion_seconds=3
        )

        assert len(response.warnings) == 2
        assert "auto-created" in response.warnings[0]
