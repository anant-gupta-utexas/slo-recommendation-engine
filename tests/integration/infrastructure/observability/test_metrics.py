"""Integration tests for Prometheus metrics.

Tests that metrics are correctly recorded and exposed via /metrics endpoint.
"""

import pytest
from fastapi.testclient import TestClient

from src.infrastructure.api.main import create_app
from src.infrastructure.observability import metrics


@pytest.fixture
def app():
    """Create FastAPI app for testing."""
    return create_app()


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestMetricsEndpoint:
    """Tests for /metrics endpoint."""

    def test_metrics_endpoint_returns_prometheus_format(self, client):
        """Test that /metrics endpoint returns Prometheus exposition format."""
        response = client.get("/api/v1/metrics")

        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

        # Check for expected metric names in output
        content = response.text
        assert "slo_engine_http_requests_total" in content
        assert "slo_engine_http_request_duration_seconds" in content

    def test_metrics_recorded_for_requests(self, client):
        """Test that HTTP requests are recorded in metrics."""
        # Make a request to health endpoint
        response = client.get("/api/v1/health")
        assert response.status_code == 200

        # Check metrics endpoint
        metrics_response = client.get("/api/v1/metrics")
        content = metrics_response.text

        # Verify request was recorded
        assert 'endpoint="/api/v1/health"' in content
        assert 'method="GET"' in content
        assert 'status_code="200"' in content


class TestMetricsRecording:
    """Tests for metric recording functions."""

    def test_record_http_request(self):
        """Test HTTP request metric recording."""
        # Record a sample request
        metrics.record_http_request(
            method="POST",
            endpoint="/api/v1/test",
            status_code=201,
            duration=0.123,
        )

        # Get metrics content
        content, _ = metrics.get_metrics_content()
        content_str = content.decode("utf-8")

        # Verify metric was recorded
        assert "slo_engine_http_requests_total" in content_str

    def test_record_graph_traversal(self):
        """Test graph traversal metric recording."""
        # Record a sample traversal
        metrics.record_graph_traversal(
            direction="downstream",
            depth=3,
            duration=0.050,
        )

        # Get metrics content
        content, _ = metrics.get_metrics_content()
        content_str = content.decode("utf-8")

        # Verify metric was recorded
        assert "slo_engine_graph_traversal_duration_seconds" in content_str

    def test_record_graph_ingestion(self):
        """Test graph ingestion metric recording."""
        # Record sample ingestion
        metrics.record_graph_ingestion(
            nodes_upserted=10,
            edges_upserted=25,
            discovery_source="manual",
        )

        # Get metrics content
        content, _ = metrics.get_metrics_content()
        content_str = content.decode("utf-8")

        # Verify metrics were recorded
        assert "slo_engine_graph_nodes_upserted_total" in content_str
        assert "slo_engine_graph_edges_upserted_total" in content_str
        assert 'discovery_source="manual"' in content_str

    def test_cache_metrics(self):
        """Test cache hit/miss metric recording."""
        # Record cache hit and miss
        metrics.record_cache_hit("subgraph")
        metrics.record_cache_miss("subgraph")

        # Get metrics content
        content, _ = metrics.get_metrics_content()
        content_str = content.decode("utf-8")

        # Verify metrics were recorded
        assert "slo_engine_cache_hits_total" in content_str
        assert "slo_engine_cache_misses_total" in content_str
        assert 'cache_type="subgraph"' in content_str
