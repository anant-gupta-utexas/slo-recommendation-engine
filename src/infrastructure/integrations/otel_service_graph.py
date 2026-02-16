"""OpenTelemetry Service Graph integration.

This module provides a client for querying Prometheus to extract service
dependency graphs from the OTel Service Graph connector metrics.

The OTel Service Graph connector generates metrics like:
- traces_service_graph_request_total{client="service-a", server="service-b"}

These metrics are used to automatically discover service dependencies from
distributed traces.
"""

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.application.dtos.dependency_graph_dto import (
    DependencyGraphIngestRequest,
    EdgeAttributesDTO,
    EdgeDTO,
    NodeDTO,
)
from src.infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)


class OTelServiceGraphError(Exception):
    """Base exception for OTel Service Graph integration errors."""

    pass


class PrometheusUnavailableError(OTelServiceGraphError):
    """Prometheus server is unavailable or unresponsive."""

    pass


class InvalidMetricsError(OTelServiceGraphError):
    """Metrics data is invalid or malformed."""

    pass


class OTelServiceGraphClient:
    """Client for querying Prometheus OTel Service Graph metrics.

    This client queries Prometheus for the traces_service_graph_request_total
    metric to discover service dependencies from distributed traces.

    Attributes:
        prometheus_url: Prometheus server URL
        timeout: Query timeout in seconds
    """

    def __init__(
        self,
        prometheus_url: str | None = None,
        timeout: int | None = None,
    ) -> None:
        """Initialize the OTel Service Graph client.

        Args:
            prometheus_url: Prometheus server URL (defaults to settings)
            timeout: Query timeout in seconds (defaults to settings)
        """
        settings = get_settings()
        self.prometheus_url = prometheus_url or settings.prometheus.url
        self.timeout = timeout or settings.prometheus.timeout_seconds
        self.client = httpx.AsyncClient(timeout=self.timeout)

    async def close(self) -> None:
        """Close the HTTP client connection."""
        await self.client.aclose()

    async def __aenter__(self) -> "OTelServiceGraphClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()

    @retry(
        retry=retry_if_exception_type(httpx.RequestError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _query_prometheus(self, query: str) -> dict[str, Any]:
        """Query Prometheus with retry logic.

        Args:
            query: PromQL query string

        Returns:
            Prometheus query response data

        Raises:
            PrometheusUnavailableError: If Prometheus is unreachable after retries
            InvalidMetricsError: If response format is invalid
        """
        try:
            url = f"{self.prometheus_url}/api/v1/query"
            response = await self.client.get(url, params={"query": query})
            response.raise_for_status()

            data = response.json()
            if data.get("status") != "success":
                error_msg = data.get("error", "Unknown error")
                raise InvalidMetricsError(f"Prometheus query failed: {error_msg}")

            return data

        except httpx.HTTPStatusError as e:
            logger.error(
                "Prometheus HTTP error: status_code=%s error=%s",
                e.response.status_code,
                str(e),
            )
            raise PrometheusUnavailableError(
                f"Prometheus returned error: {e.response.status_code}"
            ) from e

        except httpx.RequestError as e:
            logger.error("Prometheus connection error: %s", str(e))
            raise PrometheusUnavailableError(
                f"Failed to connect to Prometheus: {e}"
            ) from e

    async def fetch_service_graph(self) -> DependencyGraphIngestRequest:
        """Fetch service dependency graph from Prometheus.

        Queries the traces_service_graph_request_total metric to extract
        service-to-service dependencies observed in distributed traces.

        Returns:
            DependencyGraphIngestRequest with discovered services and dependencies

        Raises:
            PrometheusUnavailableError: If Prometheus is unreachable
            InvalidMetricsError: If metrics format is invalid
        """
        logger.info("Fetching OTel Service Graph from Prometheus")

        # Query for service graph metrics
        # The metric labels typically include: client, server, connection_type
        query = "traces_service_graph_request_total"

        try:
            data = await self._query_prometheus(query)
            result = data.get("data", {}).get("result", [])

            if not result:
                logger.warning("No service graph metrics found in Prometheus")
                return DependencyGraphIngestRequest(
                    source="otel_service_graph",
                    timestamp=datetime.now(timezone.utc),
                    nodes=[],
                    edges=[],
                )

            # Parse metrics to extract service dependencies
            nodes_map: dict[str, NodeDTO] = {}
            edges: list[EdgeDTO] = []

            for metric in result:
                metric_labels = metric.get("metric", {})
                client = metric_labels.get("client")
                server = metric_labels.get("server")

                if not client or not server:
                    logger.warning(
                        "Skipping metric with missing client/server labels: %s",
                        metric_labels,
                    )
                    continue

                # Skip self-loops (service calling itself)
                if client == server:
                    continue

                # Create nodes if not already exists
                if client not in nodes_map:
                    nodes_map[client] = NodeDTO(
                        service_id=client,
                        metadata={"discovered_via": "otel_service_graph"},
                        criticality="medium",  # Default, can be overridden later
                    )

                if server not in nodes_map:
                    nodes_map[server] = NodeDTO(
                        service_id=server,
                        metadata={"discovered_via": "otel_service_graph"},
                        criticality="medium",
                    )

                # Determine communication mode based on connection_type label
                connection_type = metric_labels.get("connection_type", "").lower()
                if "async" in connection_type or "queue" in connection_type:
                    communication_mode = "async"
                else:
                    communication_mode = "sync"

                # Create dependency edge
                edge = EdgeDTO(
                    source=client,
                    target=server,
                    attributes=EdgeAttributesDTO(
                        communication_mode=communication_mode,
                        criticality="hard",  # Default, can be refined later
                        protocol=None,  # Not available from service graph metrics
                        timeout_ms=None,
                    ),
                )
                edges.append(edge)

            logger.info(
                "Successfully fetched OTel Service Graph: services=%d edges=%d",
                len(nodes_map),
                len(edges),
            )

            return DependencyGraphIngestRequest(
                source="otel_service_graph",
                timestamp=datetime.now(timezone.utc),
                nodes=list(nodes_map.values()),
                edges=edges,
            )

        except (PrometheusUnavailableError, InvalidMetricsError):
            # Re-raise known errors
            raise

        except Exception as e:
            logger.exception("Unexpected error fetching OTel Service Graph")
            raise OTelServiceGraphError(
                f"Failed to fetch service graph: {e}"
            ) from e


async def get_otel_service_graph() -> DependencyGraphIngestRequest:
    """Convenience function to fetch OTel Service Graph.

    Returns:
        DependencyGraphIngestRequest with discovered dependencies

    Raises:
        OTelServiceGraphError: If fetching fails
    """
    async with OTelServiceGraphClient() as client:
        return await client.fetch_service_graph()
