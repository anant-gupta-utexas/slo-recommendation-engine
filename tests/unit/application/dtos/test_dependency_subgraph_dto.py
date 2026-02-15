"""Unit tests for dependency subgraph DTOs."""

import pytest
from datetime import datetime
from uuid import UUID

from src.application.dtos.dependency_subgraph_dto import (
    DependencySubgraphRequest,
    ServiceNodeDTO,
    DependencyEdgeDTO,
    DependencySubgraphResponse,
)
from src.application.dtos.common import SubgraphStatistics


class TestDependencySubgraphRequest:
    """Test DependencySubgraphRequest DTO."""

    def test_create_request_with_defaults(self):
        """Test creating request with default values."""
        request = DependencySubgraphRequest(service_id="test-service")

        assert request.service_id == "test-service"
        assert request.direction == "both"
        assert request.depth == 3
        assert request.include_stale is False

    def test_create_request_with_custom_values(self):
        """Test creating request with custom values."""
        request = DependencySubgraphRequest(
            service_id="checkout-service",
            direction="downstream",
            depth=5,
            include_stale=True
        )

        assert request.service_id == "checkout-service"
        assert request.direction == "downstream"
        assert request.depth == 5
        assert request.include_stale is True

    def test_create_request_with_upstream_direction(self):
        """Test creating request with upstream direction."""
        request = DependencySubgraphRequest(
            service_id="payment-service",
            direction="upstream",
            depth=2
        )

        assert request.direction == "upstream"
        assert request.depth == 2


class TestServiceNodeDTO:
    """Test ServiceNodeDTO."""

    def test_create_service_node_minimal(self):
        """Test creating service node with minimal fields."""
        service_uuid = "12345678-1234-5678-1234-567812345678"

        node = ServiceNodeDTO(
            service_id="test-service",
            id=service_uuid,
            team=None,
            criticality="medium",
            metadata={}
        )

        assert node.service_id == "test-service"
        assert node.id == service_uuid
        assert node.team is None
        assert node.criticality == "medium"
        assert node.metadata == {}

    def test_create_service_node_with_all_fields(self):
        """Test creating service node with all fields."""
        service_uuid = "12345678-1234-5678-1234-567812345678"
        metadata = {
            "namespace": "production",
            "runtime": "python3.12"
        }

        node = ServiceNodeDTO(
            service_id="checkout-service",
            id=service_uuid,
            team="payments",
            criticality="high",
            metadata=metadata
        )

        assert node.service_id == "checkout-service"
        assert node.id == service_uuid
        assert node.team == "payments"
        assert node.criticality == "high"
        assert node.metadata == metadata


class TestDependencyEdgeDTO:
    """Test DependencyEdgeDTO."""

    def test_create_edge_minimal(self):
        """Test creating edge with minimal fields."""
        timestamp = datetime.now()

        edge = DependencyEdgeDTO(
            source="service-a",
            target="service-b",
            communication_mode="sync",
            criticality="hard",
            protocol=None,
            timeout_ms=None,
            discovery_source="manual",
            confidence_score=1.0,
            last_observed_at=timestamp,
            is_stale=False
        )

        assert edge.source == "service-a"
        assert edge.target == "service-b"
        assert edge.communication_mode == "sync"
        assert edge.criticality == "hard"
        assert edge.protocol is None
        assert edge.timeout_ms is None
        assert edge.confidence_score == 1.0
        assert edge.is_stale is False

    def test_create_edge_with_all_fields(self):
        """Test creating edge with all fields."""
        timestamp = datetime.now()

        edge = DependencyEdgeDTO(
            source="checkout-service",
            target="payment-service",
            communication_mode="sync",
            criticality="hard",
            protocol="grpc",
            timeout_ms=5000,
            discovery_source="otel_service_graph",
            confidence_score=0.95,
            last_observed_at=timestamp,
            is_stale=False
        )

        assert edge.source == "checkout-service"
        assert edge.target == "payment-service"
        assert edge.protocol == "grpc"
        assert edge.timeout_ms == 5000
        assert edge.discovery_source == "otel_service_graph"
        assert edge.confidence_score == 0.95

    def test_create_stale_edge(self):
        """Test creating a stale edge."""
        timestamp = datetime.now()

        edge = DependencyEdgeDTO(
            source="old-service",
            target="deprecated-service",
            communication_mode="sync",
            criticality="soft",
            protocol=None,
            timeout_ms=None,
            discovery_source="kubernetes",
            confidence_score=0.75,
            last_observed_at=timestamp,
            is_stale=True
        )

        assert edge.is_stale is True
        assert edge.confidence_score == 0.75


class TestDependencySubgraphResponse:
    """Test DependencySubgraphResponse."""

    def test_create_response_empty_graph(self):
        """Test creating response with empty graph."""
        stats = SubgraphStatistics(
            total_nodes=0,
            total_edges=0,
            upstream_services=0,
            downstream_services=0,
            max_depth_reached=0
        )

        response = DependencySubgraphResponse(
            service_id="isolated-service",
            direction="both",
            depth=3,
            nodes=[],
            edges=[],
            statistics=stats
        )

        assert response.service_id == "isolated-service"
        assert len(response.nodes) == 0
        assert len(response.edges) == 0
        assert response.statistics.total_nodes == 0

    def test_create_response_with_graph(self):
        """Test creating response with actual graph data."""
        service_uuid = UUID("12345678-1234-5678-1234-567812345678")
        timestamp = datetime.now()

        node1 = ServiceNodeDTO(
            service_id="service-a",
            id=service_uuid,
            team="platform",
            criticality="high",
            metadata={}
        )

        edge1 = DependencyEdgeDTO(
            source="service-a",
            target="service-b",
            communication_mode="sync",
            criticality="hard",
            protocol="http",
            timeout_ms=3000,
            discovery_source="manual",
            confidence_score=1.0,
            last_observed_at=timestamp,
            is_stale=False
        )

        stats = SubgraphStatistics(
            total_nodes=2,
            total_edges=1,
            upstream_services=0,
            downstream_services=1,
            max_depth_reached=1
        )

        response = DependencySubgraphResponse(
            service_id="service-a",
            direction="downstream",
            depth=3,
            nodes=[node1],
            edges=[edge1],
            statistics=stats
        )

        assert response.service_id == "service-a"
        assert response.direction == "downstream"
        assert len(response.nodes) == 1
        assert len(response.edges) == 1
        assert response.statistics.total_nodes == 2
        assert response.statistics.downstream_services == 1

    def test_create_response_large_graph(self):
        """Test creating response with large graph."""
        stats = SubgraphStatistics(
            total_nodes=150,
            total_edges=420,
            upstream_services=30,
            downstream_services=120,
            max_depth_reached=5
        )

        response = DependencySubgraphResponse(
            service_id="central-service",
            direction="both",
            depth=5,
            nodes=[],  # Would contain 150 nodes in real scenario
            edges=[],  # Would contain 420 edges in real scenario
            statistics=stats
        )

        assert response.statistics.total_nodes == 150
        assert response.statistics.total_edges == 420
        assert response.statistics.max_depth_reached == 5
