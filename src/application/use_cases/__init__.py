"""Use cases - Application-specific business rules.

This package contains use cases that orchestrate domain logic
and implement application-specific workflows.
"""

from src.application.use_cases.detect_circular_dependencies import (
    DetectCircularDependenciesUseCase,
)
from src.application.use_cases.ingest_dependency_graph import (
    IngestDependencyGraphUseCase,
)
from src.application.use_cases.query_dependency_subgraph import (
    QueryDependencySubgraphUseCase,
)

__all__ = [
    "IngestDependencyGraphUseCase",
    "QueryDependencySubgraphUseCase",
    "DetectCircularDependenciesUseCase",
]
