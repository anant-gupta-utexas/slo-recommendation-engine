"""Unit tests for common DTOs."""

import pytest
from datetime import datetime
from uuid import uuid4

from src.application.dtos.common import ErrorDetail, ConflictInfo, SubgraphStatistics


class TestErrorDetail:
    """Test ErrorDetail DTO."""

    def test_create_error_detail_with_all_fields(self):
        """Test creating ErrorDetail with all fields."""
        error = ErrorDetail(
            type="https://example.com/errors/not-found",
            title="Not Found",
            status=404,
            detail="Service with ID 'test-service' not found",
            instance="/api/v1/services/test-service/dependencies"
        )

        assert error.type == "https://example.com/errors/not-found"
        assert error.title == "Not Found"
        assert error.status == 404
        assert error.detail == "Service with ID 'test-service' not found"
        assert error.instance == "/api/v1/services/test-service/dependencies"

    def test_create_error_detail_with_minimal_fields(self):
        """Test creating ErrorDetail with required fields only."""
        error = ErrorDetail(
            type="https://example.com/errors/internal",
            title="Internal Server Error",
            status=500,
            detail="An unexpected error occurred",
            instance="/api/v1/services/dependencies"
        )

        assert error.type == "https://example.com/errors/internal"
        assert error.status == 500


class TestConflictInfo:
    """Test ConflictInfo DTO."""

    def test_create_conflict_info(self):
        """Test creating ConflictInfo."""
        conflict = ConflictInfo(
            source="service-a",
            target="service-b",
            existing_source="otel_service_graph",
            new_source="manual",
            resolution="kept_higher_priority"
        )

        assert conflict.source == "service-a"
        assert conflict.target == "service-b"
        assert conflict.existing_source == "otel_service_graph"
        assert conflict.new_source == "manual"
        assert conflict.resolution == "kept_higher_priority"


class TestSubgraphStatistics:
    """Test SubgraphStatistics DTO."""

    def test_create_subgraph_statistics_with_all_fields(self):
        """Test creating SubgraphStatistics with all fields."""
        stats = SubgraphStatistics(
            total_nodes=15,
            total_edges=42,
            upstream_services=3,
            downstream_services=11,
            max_depth_reached=3
        )

        assert stats.total_nodes == 15
        assert stats.total_edges == 42
        assert stats.upstream_services == 3
        assert stats.downstream_services == 11
        assert stats.max_depth_reached == 3

    def test_create_subgraph_statistics_with_zeros(self):
        """Test creating SubgraphStatistics with zero values."""
        stats = SubgraphStatistics(
            total_nodes=0,
            total_edges=0,
            upstream_services=0,
            downstream_services=0,
            max_depth_reached=0
        )

        assert stats.total_nodes == 0
        assert stats.total_edges == 0
        assert stats.upstream_services == 0
        assert stats.downstream_services == 0
        assert stats.max_depth_reached == 0
