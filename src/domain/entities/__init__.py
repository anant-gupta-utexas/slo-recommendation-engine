"""Domain entities - Core business objects."""

from src.domain.entities.circular_dependency_alert import (
    AlertStatus,
    CircularDependencyAlert,
)
from src.domain.entities.service import Criticality, Service
from src.domain.entities.service_dependency import (
    CommunicationMode,
    DependencyCriticality,
    DiscoverySource,
    RetryConfig,
    ServiceDependency,
)

__all__ = [
    # Service entity
    "Service",
    "Criticality",
    # ServiceDependency entity
    "ServiceDependency",
    "CommunicationMode",
    "DependencyCriticality",
    "DiscoverySource",
    "RetryConfig",
    # CircularDependencyAlert entity
    "CircularDependencyAlert",
    "AlertStatus",
]
