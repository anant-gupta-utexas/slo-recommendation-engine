"""Common DTOs shared across application layer.

This module defines shared data transfer objects used across multiple use cases,
including error responses and common enums.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class ErrorDetail:
    """RFC 7807 Problem Details error response.

    Attributes:
        type: URI reference identifying the problem type
        title: Short human-readable summary
        status: HTTP status code
        detail: Human-readable explanation specific to this occurrence
        instance: URI reference identifying the specific occurrence
    """

    type: str
    title: str
    status: int
    detail: str
    instance: str


@dataclass
class ConflictInfo:
    """Information about a conflict during edge merging.

    Attributes:
        source: Source service identifier
        target: Target service identifier
        existing_source: Discovery source of existing edge
        new_source: Discovery source of new edge
        resolution: How the conflict was resolved
    """

    source: str
    target: str
    existing_source: str
    new_source: str
    resolution: str


@dataclass
class SubgraphStatistics:
    """Statistics about a dependency subgraph.

    Attributes:
        total_nodes: Total number of services in subgraph
        total_edges: Total number of dependencies in subgraph
        upstream_services: Number of upstream services (if applicable)
        downstream_services: Number of downstream services (if applicable)
        max_depth_reached: Maximum depth reached during traversal
    """

    total_nodes: int
    total_edges: int
    upstream_services: int
    downstream_services: int
    max_depth_reached: int
