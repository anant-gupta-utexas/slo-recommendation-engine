"""Domain services - Business logic that doesn't fit in entities."""

from src.domain.services.circular_dependency_detector import (
    CircularDependencyDetector,
)
from src.domain.services.edge_merge_service import EdgeMergeService
from src.domain.services.graph_traversal_service import (
    GraphTraversalService,
    TraversalDirection,
)

__all__ = [
    "GraphTraversalService",
    "TraversalDirection",
    "CircularDependencyDetector",
    "EdgeMergeService",
]
