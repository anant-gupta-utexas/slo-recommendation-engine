"""External integrations for service discovery.

This package contains integrations with external systems for automatic
service dependency graph discovery.
"""

from src.infrastructure.integrations.otel_service_graph import (
    OTelServiceGraphClient,
    OTelServiceGraphError,
)

__all__ = [
    "OTelServiceGraphClient",
    "OTelServiceGraphError",
]
