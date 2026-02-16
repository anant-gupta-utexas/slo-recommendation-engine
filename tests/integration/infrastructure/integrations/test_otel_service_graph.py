"""Integration tests for OTel Service Graph integration.

These tests verify the Prometheus query client and metric parsing logic.
Uses httpx mock to simulate Prometheus responses without requiring a real instance.
"""

import pytest
from httpx import AsyncClient, Response

from src.infrastructure.integrations.otel_service_graph import (
    InvalidMetricsError,
    OTelServiceGraphClient,
    PrometheusUnavailableError,
)


class TestOTelServiceGraphClient:
    """Test OTel Service Graph Prometheus integration."""

    @pytest.fixture
    async def mock_prometheus(self, monkeypatch: pytest.MonkeyPatch):
        """Mock Prometheus HTTP responses."""
        responses = {}

        async def mock_get(self, url: str, **kwargs):
            """Mock httpx.AsyncClient.get()"""
            query = kwargs.get("params", {}).get("query", "")
            if query in responses:
                return responses[query]
            # Default: no metrics found
            return Response(
                200,
                json={
                    "status": "success",
                    "data": {"resultType": "vector", "result": []},
                },
            )

        monkeypatch.setattr(AsyncClient, "get", mock_get)
        return responses

    @pytest.mark.asyncio
    async def test_fetch_service_graph_success(self, mock_prometheus):
        """Test successful fetch of service graph metrics."""
        # Mock Prometheus response with service graph metrics
        mock_prometheus["traces_service_graph_request_total"] = Response(
            200,
            json={
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {
                            "metric": {
                                "client": "checkout-service",
                                "server": "payment-service",
                                "connection_type": "sync",
                            },
                            "value": [1234567890, "100"],
                        },
                        {
                            "metric": {
                                "client": "checkout-service",
                                "server": "inventory-service",
                                "connection_type": "sync",
                            },
                            "value": [1234567890, "50"],
                        },
                        {
                            "metric": {
                                "client": "order-processor",
                                "server": "notification-queue",
                                "connection_type": "async",
                            },
                            "value": [1234567890, "200"],
                        },
                    ],
                },
            },
        )

        async with OTelServiceGraphClient(
            prometheus_url="http://mock-prometheus:9090"
        ) as client:
            graph = await client.fetch_service_graph()

        # Verify request structure
        assert graph.source == "otel_service_graph"
        assert len(graph.nodes) == 5  # 5 unique services
        assert len(graph.edges) == 3  # 3 dependencies

        # Verify nodes
        service_ids = {node.service_id for node in graph.nodes}
        assert service_ids == {
            "checkout-service",
            "payment-service",
            "inventory-service",
            "order-processor",
            "notification-queue",
        }

        # Verify edges
        edges_map = {(e.source, e.target): e for e in graph.edges}
        assert ("checkout-service", "payment-service") in edges_map
        assert ("checkout-service", "inventory-service") in edges_map
        assert ("order-processor", "notification-queue") in edges_map

        # Verify communication mode detection
        sync_edge = edges_map[("checkout-service", "payment-service")]
        assert sync_edge.attributes.communication_mode == "sync"

        async_edge = edges_map[("order-processor", "notification-queue")]
        assert async_edge.attributes.communication_mode == "async"

    @pytest.mark.asyncio
    async def test_fetch_service_graph_empty(self, mock_prometheus):
        """Test handling of empty metrics (no services discovered)."""
        # Mock empty response
        mock_prometheus["traces_service_graph_request_total"] = Response(
            200,
            json={
                "status": "success",
                "data": {"resultType": "vector", "result": []},
            },
        )

        async with OTelServiceGraphClient(
            prometheus_url="http://mock-prometheus:9090"
        ) as client:
            graph = await client.fetch_service_graph()

        assert graph.source == "otel_service_graph"
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0

    @pytest.mark.asyncio
    async def test_fetch_service_graph_missing_labels(self, mock_prometheus):
        """Test handling of metrics with missing client/server labels."""
        # Mock response with invalid metrics
        mock_prometheus["traces_service_graph_request_total"] = Response(
            200,
            json={
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {
                            "metric": {
                                "client": "service-a",
                                # Missing 'server' label
                            },
                            "value": [1234567890, "10"],
                        },
                        {
                            "metric": {
                                "client": "service-b",
                                "server": "service-c",
                            },
                            "value": [1234567890, "20"],
                        },
                    ],
                },
            },
        )

        async with OTelServiceGraphClient(
            prometheus_url="http://mock-prometheus:9090"
        ) as client:
            graph = await client.fetch_service_graph()

        # Should skip invalid metric, only process valid one
        assert len(graph.nodes) == 2  # service-b, service-c
        assert len(graph.edges) == 1  # service-b -> service-c

    @pytest.mark.asyncio
    async def test_fetch_service_graph_self_loop_filtered(self, mock_prometheus):
        """Test that self-loops (service calling itself) are filtered out."""
        # Mock response with self-loop
        mock_prometheus["traces_service_graph_request_total"] = Response(
            200,
            json={
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {
                            "metric": {
                                "client": "service-a",
                                "server": "service-a",  # Self-loop
                            },
                            "value": [1234567890, "10"],
                        },
                        {
                            "metric": {
                                "client": "service-a",
                                "server": "service-b",
                            },
                            "value": [1234567890, "20"],
                        },
                    ],
                },
            },
        )

        async with OTelServiceGraphClient(
            prometheus_url="http://mock-prometheus:9090"
        ) as client:
            graph = await client.fetch_service_graph()

        # Should filter out self-loop
        assert len(graph.edges) == 1
        assert graph.edges[0].source == "service-a"
        assert graph.edges[0].target == "service-b"

    @pytest.mark.asyncio
    async def test_prometheus_unavailable(self, monkeypatch: pytest.MonkeyPatch):
        """Test handling of Prometheus connection errors."""
        import httpx

        async def mock_get_error(*args, **kwargs):
            raise httpx.ConnectError("Connection refused")

        monkeypatch.setattr(AsyncClient, "get", mock_get_error)

        async with OTelServiceGraphClient(
            prometheus_url="http://unreachable:9090"
        ) as client:
            # Should retry 3 times then raise PrometheusUnavailableError
            with pytest.raises(PrometheusUnavailableError):
                await client.fetch_service_graph()

    @pytest.mark.asyncio
    async def test_prometheus_error_response(self, mock_prometheus):
        """Test handling of Prometheus error responses."""
        # Mock error response
        mock_prometheus["traces_service_graph_request_total"] = Response(
            200,
            json={
                "status": "error",
                "errorType": "bad_data",
                "error": "parse error at char 10: unexpected character",
            },
        )

        async with OTelServiceGraphClient(
            prometheus_url="http://mock-prometheus:9090"
        ) as client:
            with pytest.raises(InvalidMetricsError, match="Prometheus query failed"):
                await client.fetch_service_graph()

    @pytest.mark.asyncio
    async def test_prometheus_http_error(self, monkeypatch: pytest.MonkeyPatch):
        """Test handling of Prometheus HTTP errors (500, 503, etc.)."""

        async def mock_get_500(*args, **kwargs):
            return Response(500, text="Internal Server Error")

        monkeypatch.setattr(AsyncClient, "get", mock_get_500)

        async with OTelServiceGraphClient(
            prometheus_url="http://mock-prometheus:9090"
        ) as client:
            with pytest.raises(PrometheusUnavailableError, match="500"):
                await client.fetch_service_graph()
