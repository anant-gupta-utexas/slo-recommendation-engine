# FR-1: Service Dependency Graph Ingestion & Management
## Technical Requirements Specification (TRS)

**Feature ID:** FR-1
**Feature Name:** Service Dependency Graph Ingestion & Management
**Created:** 2026-02-14
**Status:** Planning
**Owner:** Backend Team

---

## Overview & Scope

### Purpose
Implement the foundational capability to ingest, store, query, and manage service dependency graphs that represent the interconnections between microservices in the platform. This is the cornerstone requirement that enables all dependency-aware SLO recommendations in subsequent features.

### Business Value
- Enables dependency-aware SLO recommendations (FR-2, FR-3)
- Provides visibility into service topology for impact analysis (FR-4)
- Detects architectural anti-patterns (circular dependencies) early
- Supports multi-source discovery (manual, automated) with confidence scoring

### Scope Definition

**In Scope:**
- Bulk dependency graph ingestion API endpoint (`POST /api/v1/services/dependencies`)
- Dependency graph query API endpoint (`GET /api/v1/services/{service-id}/dependencies`)
- PostgreSQL storage with recursive CTE-based traversal
- Circular dependency detection using Tarjan's algorithm
- Multi-source graph discovery:
  - Manual API submission
  - OpenTelemetry Service Graph Connector integration
- Edge annotations: communication_mode, criticality, protocol, timeout, retry config
- Staleness detection and handling
- Graph validation and conflict resolution

**Out of Scope (Deferred):**
- Kubernetes manifest parsing (future enhancement)
- Service mesh integration (Istio/Linkerd) (future enhancement)
- Real-time graph updates via streaming (batch ingestion only for MVP)
- Graph visualization API (consumed by Backstage frontend, not this service's concern)
- SLO computation logic (belongs to FR-2)

### Key Decisions Made
1. **Storage:** PostgreSQL with recursive CTEs (not Neo4j) - sufficient for 10K+ edges, lower ops overhead
2. **Async Pattern:** Full async/await throughout all layers (FastAPI → use cases → repositories → AsyncPG)
3. **Discovery Sources:** Manual API + OTel Service Graph (K8s/Service Mesh deferred)
4. **Circular Dependency Handling:** Non-blocking - store alert, allow ingestion, return warning
5. **Staleness Threshold:** Global threshold (7 days) for all discovery sources; per-source thresholds deferred to Phase 3+
6. **API Key Management:** CLI tool only for MVP (`slo-cli api-keys create --name backstage`); admin API deferred to Phase 3
7. **Background Task Queue:** APScheduler (in-process) for MVP; migrate to Celery if task volume exceeds 100/min
8. **Prometheus Metric Labels:** Omit `service_id` from metric labels to avoid high cardinality; use exemplars for sampling if granularity needed
9. **Cache Invalidation:** Invalidate all cached subgraphs on any graph update; optimize to selective invalidation if cache thrashing observed

---

## Requirements Summary

### Functional Requirements (from TRD FR-1)

| Req ID | Requirement | Priority | Acceptance Criteria |
|--------|-------------|----------|---------------------|
| FR1.1 | Bulk upsert dependency graph via API | P0 | Accept 1000-node graph in <30s, store with correct annotations |
| FR1.2 | Query dependency subgraph (upstream/downstream/both) | P0 | Return 3-hop traversal in <100ms on 5000-node graph |
| FR1.3 | Detect circular dependencies (Tarjan's algorithm) | P0 | Identify all SCCs, store alerts, return cycle paths in API response |
| FR1.4 | Multi-source graph discovery with confidence scores | P0 | Merge edges from manual + OTel sources with priority resolution |
| FR1.5 | Handle edge staleness (edges not refreshed within 7 days) | P1 | Mark stale edges, exclude from traversal queries |
| FR1.6 | Conflict resolution for overlapping edges | P1 | Priority: manual > service_mesh > otel > kubernetes |
| FR1.7 | Auto-create placeholder nodes for unknown service_ids | P1 | Create service with discovered=true flag |

### Non-Functional Requirements

| NFR ID | Requirement | Target | Measurement |
|--------|-------------|--------|-------------|
| NFR1.1 | API response time (cached retrieval) | p95 < 500ms | APM metrics |
| NFR1.2 | Graph ingestion throughput | 1000 services in <30s | Integration test |
| NFR1.3 | Graph traversal performance | 3-hop query <100ms on 5000 nodes | Load test |
| NFR1.4 | Concurrent API users | 200+ without degradation | Load test (k6) |
| NFR1.5 | Database connection pooling | Max 50 connections per instance | PostgreSQL metrics |
| NFR1.6 | Input validation | Reject invalid schemas immediately | Schema validation tests |

---

## Detailed Component Design

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      Infrastructure Layer                        │
│  ┌────────────────────┐            ┌────────────────────────┐  │
│  │   FastAPI Routes   │            │  PostgreSQL Repository │  │
│  │  (api/routes/      │            │  (database/repos/      │  │
│  │   dependencies.py) │            │   dependency_repo.py)  │  │
│  └─────────┬──────────┘            └──────────┬─────────────┘  │
└────────────┼────────────────────────────────────┼────────────────┘
             │                                    │
             ▼                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Application Layer                            │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │              Use Cases (application/use_cases/)            │ │
│  │  • IngestDependencyGraphUseCase                            │ │
│  │  • QueryDependencySubgraphUseCase                          │ │
│  │  • DetectCircularDependenciesUseCase                       │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                 DTOs (application/dtos/)                   │ │
│  │  • DependencyGraphIngestRequest                            │ │
│  │  • DependencyGraphIngestResponse                           │ │
│  │  • DependencySubgraphRequest                               │ │
│  │  • DependencySubgraphResponse                              │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
             │                                    ▲
             ▼                                    │
┌─────────────────────────────────────────────────────────────────┐
│                        Domain Layer                              │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │           Entities (domain/entities/)                      │ │
│  │  • Service (service_id, metadata, criticality, team)       │ │
│  │  • ServiceDependency (source, target, attributes)          │ │
│  │  • CircularDependencyAlert (cycle_path, status)            │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │     Repository Interfaces (domain/repositories/)           │ │
│  │  • ServiceRepositoryInterface                              │ │
│  │  • DependencyRepositoryInterface                           │ │
│  │  • CircularDependencyAlertRepositoryInterface              │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │       Domain Services (domain/services/)                   │ │
│  │  • GraphTraversalService (recursive CTE queries)           │ │
│  │  • CircularDependencyDetector (Tarjan's algorithm)         │ │
│  │  • EdgeMergeService (conflict resolution, confidence)      │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Domain Entities

#### 1. Service Entity

```python
# src/domain/entities/service.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from enum import Enum

class Criticality(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

@dataclass
class Service:
    """
    Represents a microservice in the system.

    Domain invariants:
    - service_id must be unique and immutable
    - discovered services must have minimal metadata until registered
    """
    service_id: str  # Business identifier (e.g., "checkout-service")
    metadata: dict = field(default_factory=dict)
    criticality: Criticality = Criticality.MEDIUM
    team: Optional[str] = None
    discovered: bool = False  # True if auto-created from unknown edge reference

    # Audit fields
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        if not self.service_id:
            raise ValueError("service_id cannot be empty")
        if self.discovered and not self.metadata:
            # Discovered services start with minimal metadata
            self.metadata = {"source": "auto_discovered"}

    def mark_as_registered(self, team: str, criticality: Criticality, metadata: dict):
        """Convert a discovered service to a registered one."""
        self.discovered = False
        self.team = team
        self.criticality = criticality
        self.metadata = metadata
        self.updated_at = datetime.utcnow()
```

#### 2. ServiceDependency Entity

```python
# src/domain/entities/service_dependency.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from enum import Enum

class CommunicationMode(str, Enum):
    SYNC = "sync"
    ASYNC = "async"

class DependencyCriticality(str, Enum):
    HARD = "hard"        # Service cannot function without this dependency
    SOFT = "soft"        # Service can degrade gracefully
    DEGRADED = "degraded" # Service runs in degraded mode without this

class DiscoverySource(str, Enum):
    MANUAL = "manual"
    OTEL_SERVICE_GRAPH = "otel_service_graph"
    KUBERNETES = "kubernetes"
    SERVICE_MESH = "service_mesh"

@dataclass
class RetryConfig:
    max_retries: int = 3
    backoff_strategy: str = "exponential"  # exponential, linear, constant

    def __post_init__(self):
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")

@dataclass
class ServiceDependency:
    """
    Represents a directed edge from source service to target service.

    Domain invariants:
    - source and target must reference valid Service entities
    - confidence_score must be in [0.0, 1.0]
    - timeout_ms must be positive if specified
    """
    source_service_id: UUID  # FK to services.id
    target_service_id: UUID  # FK to services.id
    communication_mode: CommunicationMode
    criticality: DependencyCriticality = DependencyCriticality.HARD
    protocol: Optional[str] = None  # grpc, http, kafka, etc.
    timeout_ms: Optional[int] = None
    retry_config: Optional[RetryConfig] = None
    discovery_source: DiscoverySource = DiscoverySource.MANUAL
    confidence_score: float = 1.0  # 0.0 to 1.0

    # Staleness tracking
    last_observed_at: datetime = field(default_factory=datetime.utcnow)
    is_stale: bool = False

    # Audit fields
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        if not (0.0 <= self.confidence_score <= 1.0):
            raise ValueError("confidence_score must be between 0.0 and 1.0")
        if self.timeout_ms is not None and self.timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")
        if self.source_service_id == self.target_service_id:
            raise ValueError("Self-loops not allowed (source == target)")

    def mark_as_stale(self):
        """Mark this edge as stale (not observed recently)."""
        self.is_stale = True
        self.updated_at = datetime.utcnow()

    def refresh(self):
        """Refresh this edge (observed again)."""
        self.is_stale = False
        self.last_observed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
```

#### 3. CircularDependencyAlert Entity

```python
# src/domain/entities/circular_dependency_alert.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import List
from uuid import UUID, uuid4
from enum import Enum

class AlertStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"

@dataclass
class CircularDependencyAlert:
    """
    Represents a detected circular dependency (strongly connected component).

    Domain invariants:
    - cycle_path must contain at least 2 service_ids
    - cycle_path must form a closed loop (first == last)
    """
    cycle_path: List[str]  # List of service_ids forming the cycle
    status: AlertStatus = AlertStatus.OPEN
    acknowledged_by: Optional[str] = None
    resolution_notes: Optional[str] = None

    # Audit fields
    id: UUID = field(default_factory=uuid4)
    detected_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        if len(self.cycle_path) < 2:
            raise ValueError("Cycle path must contain at least 2 services")
        # Validate that it's actually a cycle (first should equal last in expanded form)
        # Note: We store minimal cycle representation, so this check is semantic

    def acknowledge(self, acknowledger: str):
        """Mark this alert as acknowledged."""
        self.status = AlertStatus.ACKNOWLEDGED
        self.acknowledged_by = acknowledger

    def resolve(self, notes: str):
        """Mark this alert as resolved."""
        self.status = AlertStatus.RESOLVED
        self.resolution_notes = notes
```

### Domain Services

#### 1. GraphTraversalService

```python
# src/domain/services/graph_traversal_service.py

from typing import List, Tuple, Set
from uuid import UUID
from enum import Enum

class TraversalDirection(str, Enum):
    UPSTREAM = "upstream"      # Dependencies that call this service
    DOWNSTREAM = "downstream"  # Dependencies this service calls
    BOTH = "both"

class GraphTraversalService:
    """
    Domain service for graph traversal operations.
    Uses repository to execute recursive CTE queries.
    """

    async def get_subgraph(
        self,
        service_id: UUID,
        direction: TraversalDirection,
        max_depth: int = 3,
        include_stale: bool = False,
        repository: 'DependencyRepositoryInterface'
    ) -> Tuple[List['Service'], List['ServiceDependency']]:
        """
        Retrieve subgraph starting from service_id.

        Args:
            service_id: Starting point for traversal
            direction: Which edges to follow
            max_depth: Maximum traversal depth (default 3, max 10)
            include_stale: Whether to include stale edges
            repository: Dependency repository for data access

        Returns:
            Tuple of (nodes, edges) in the subgraph

        Raises:
            ValueError: If max_depth > 10
        """
        if max_depth > 10:
            raise ValueError("max_depth cannot exceed 10")

        # Delegate to repository's recursive CTE implementation
        return await repository.traverse_graph(
            service_id=service_id,
            direction=direction,
            max_depth=max_depth,
            include_stale=include_stale
        )
```

#### 2. CircularDependencyDetector

```python
# src/domain/services/circular_dependency_detector.py

from typing import List, Set, Dict, Tuple
from uuid import UUID
from collections import defaultdict

class CircularDependencyDetector:
    """
    Implements Tarjan's algorithm for finding strongly connected components.

    Complexity: O(V + E) where V = services, E = edges
    """

    def __init__(self):
        self.index_counter = 0
        self.stack: List[UUID] = []
        self.lowlinks: Dict[UUID, int] = {}
        self.index: Dict[UUID, int] = {}
        self.on_stack: Set[UUID] = set()
        self.sccs: List[List[UUID]] = []

    async def detect_cycles(
        self,
        adjacency_list: Dict[UUID, List[UUID]]
    ) -> List[List[str]]:
        """
        Detect all strongly connected components (cycles) in the graph.

        Args:
            adjacency_list: Map of service_id → list of target service_ids

        Returns:
            List of cycles, where each cycle is a list of service_ids
            Only returns SCCs with size > 1 (actual cycles, not single nodes)
        """
        for node in adjacency_list.keys():
            if node not in self.index:
                await self._strongconnect(node, adjacency_list)

        # Filter out trivial SCCs (single nodes)
        cycles = [scc for scc in self.sccs if len(scc) > 1]
        return cycles

    async def _strongconnect(
        self,
        node: UUID,
        adjacency_list: Dict[UUID, List[UUID]]
    ):
        """Recursive helper for Tarjan's algorithm."""
        self.index[node] = self.index_counter
        self.lowlinks[node] = self.index_counter
        self.index_counter += 1
        self.stack.append(node)
        self.on_stack.add(node)

        # Consider successors
        for successor in adjacency_list.get(node, []):
            if successor not in self.index:
                await self._strongconnect(successor, adjacency_list)
                self.lowlinks[node] = min(self.lowlinks[node], self.lowlinks[successor])
            elif successor in self.on_stack:
                self.lowlinks[node] = min(self.lowlinks[node], self.index[successor])

        # If node is a root node, pop the stack and generate an SCC
        if self.lowlinks[node] == self.index[node]:
            scc = []
            while True:
                successor = self.stack.pop()
                self.on_stack.remove(successor)
                scc.append(successor)
                if successor == node:
                    break
            self.sccs.append(scc)
```

#### 3. EdgeMergeService

```python
# src/domain/services/edge_merge_service.py

from typing import List, Dict
from uuid import UUID
from domain.entities.service_dependency import (
    ServiceDependency,
    DiscoverySource
)

class EdgeMergeService:
    """
    Domain service for merging edges from multiple discovery sources.

    Conflict resolution priority:
    1. MANUAL (highest)
    2. SERVICE_MESH
    3. OTEL_SERVICE_GRAPH
    4. KUBERNETES (lowest)
    """

    PRIORITY_MAP = {
        DiscoverySource.MANUAL: 4,
        DiscoverySource.SERVICE_MESH: 3,
        DiscoverySource.OTEL_SERVICE_GRAPH: 2,
        DiscoverySource.KUBERNETES: 1,
    }

    def merge_edges(
        self,
        existing_edges: Dict[Tuple[UUID, UUID], ServiceDependency],
        new_edges: List[ServiceDependency]
    ) -> Dict[str, List[ServiceDependency]]:
        """
        Merge new edges with existing edges, resolving conflicts.

        Args:
            existing_edges: Map of (source_id, target_id) → ServiceDependency
            new_edges: List of new edges to merge

        Returns:
            Dict with keys:
            - "upserted": Edges that were inserted or updated
            - "conflicts": Edges where conflict resolution occurred
        """
        upserted = []
        conflicts = []

        for new_edge in new_edges:
            edge_key = (new_edge.source_service_id, new_edge.target_service_id)

            if edge_key not in existing_edges:
                # New edge, no conflict
                upserted.append(new_edge)
            else:
                existing = existing_edges[edge_key]

                # Check if same discovery source (update) or conflict
                if existing.discovery_source == new_edge.discovery_source:
                    # Same source, update
                    new_edge.id = existing.id  # Preserve existing ID
                    new_edge.created_at = existing.created_at
                    new_edge.refresh()
                    upserted.append(new_edge)
                else:
                    # Conflict: choose higher priority source
                    winner = self._resolve_conflict(existing, new_edge)
                    winner.refresh()
                    conflicts.append({
                        "edge": winner,
                        "existing_source": existing.discovery_source.value,
                        "new_source": new_edge.discovery_source.value,
                        "resolution": "kept_higher_priority"
                    })
                    upserted.append(winner)

        return {
            "upserted": upserted,
            "conflicts": conflicts
        }

    def _resolve_conflict(
        self,
        existing: ServiceDependency,
        new: ServiceDependency
    ) -> ServiceDependency:
        """Return the edge with higher priority source."""
        existing_priority = self.PRIORITY_MAP[existing.discovery_source]
        new_priority = self.PRIORITY_MAP[new.discovery_source]

        if new_priority > existing_priority:
            # New edge has higher priority, use its attributes but keep existing ID
            new.id = existing.id
            new.created_at = existing.created_at
            return new
        else:
            # Existing edge wins
            return existing

    def compute_confidence_score(
        self,
        source: DiscoverySource,
        observation_count: int = 1
    ) -> float:
        """
        Compute confidence score based on discovery source and observations.

        Args:
            source: Discovery source
            observation_count: Number of times this edge has been observed

        Returns:
            Confidence score between 0.0 and 1.0
        """
        # Base confidence by source
        base_confidence = {
            DiscoverySource.MANUAL: 1.0,
            DiscoverySource.SERVICE_MESH: 0.95,
            DiscoverySource.OTEL_SERVICE_GRAPH: 0.85,
            DiscoverySource.KUBERNETES: 0.75,
        }

        # Boost confidence with multiple observations (logarithmic scaling)
        import math
        observation_boost = min(0.1, 0.02 * math.log(observation_count + 1))

        return min(1.0, base_confidence[source] + observation_boost)
```

### Repository Interfaces

```python
# src/domain/repositories/service_repository.py

from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID
from domain.entities.service import Service

class ServiceRepositoryInterface(ABC):
    """Repository interface for Service entity operations."""

    @abstractmethod
    async def get_by_id(self, service_id: UUID) -> Optional[Service]:
        """Get service by UUID."""
        pass

    @abstractmethod
    async def get_by_service_id(self, service_id: str) -> Optional[Service]:
        """Get service by business identifier (service_id string)."""
        pass

    @abstractmethod
    async def list_all(self, skip: int = 0, limit: int = 100) -> List[Service]:
        """List all services with pagination."""
        pass

    @abstractmethod
    async def create(self, service: Service) -> Service:
        """Create a new service."""
        pass

    @abstractmethod
    async def bulk_upsert(self, services: List[Service]) -> List[Service]:
        """Bulk upsert services. Returns list of upserted services."""
        pass

    @abstractmethod
    async def update(self, service: Service) -> Service:
        """Update existing service."""
        pass
```

```python
# src/domain/repositories/dependency_repository.py

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, Dict
from uuid import UUID
from domain.entities.service import Service
from domain.entities.service_dependency import ServiceDependency
from domain.services.graph_traversal_service import TraversalDirection

class DependencyRepositoryInterface(ABC):
    """Repository interface for ServiceDependency operations."""

    @abstractmethod
    async def get_by_id(self, dependency_id: UUID) -> Optional[ServiceDependency]:
        """Get dependency by UUID."""
        pass

    @abstractmethod
    async def list_by_source(self, source_service_id: UUID) -> List[ServiceDependency]:
        """Get all outgoing dependencies from a service."""
        pass

    @abstractmethod
    async def list_by_target(self, target_service_id: UUID) -> List[ServiceDependency]:
        """Get all incoming dependencies to a service."""
        pass

    @abstractmethod
    async def bulk_upsert(self, dependencies: List[ServiceDependency]) -> List[ServiceDependency]:
        """Bulk upsert dependencies. Returns list of upserted dependencies."""
        pass

    @abstractmethod
    async def traverse_graph(
        self,
        service_id: UUID,
        direction: TraversalDirection,
        max_depth: int,
        include_stale: bool
    ) -> Tuple[List[Service], List[ServiceDependency]]:
        """
        Execute recursive graph traversal using PostgreSQL CTE.
        Returns (nodes, edges) in the subgraph.
        """
        pass

    @abstractmethod
    async def get_adjacency_list(self) -> Dict[UUID, List[UUID]]:
        """
        Get full graph as adjacency list for cycle detection.
        Returns: Map of source_id → [target_id, ...]
        """
        pass

    @abstractmethod
    async def mark_stale_edges(self, staleness_threshold_hours: int = 168) -> int:
        """
        Mark edges as stale if not observed within threshold.
        Returns: Number of edges marked stale.
        """
        pass
```

---

## API Specifications

### Endpoint 1: POST /api/v1/services/dependencies

**Purpose:** Bulk upsert of dependency graph (nodes + edges)

**Request Schema:**
```json
{
  "source": "manual | otel_service_graph | kubernetes | service_mesh",
  "timestamp": "2026-02-14T10:00:00Z",
  "nodes": [
    {
      "service_id": "checkout-service",
      "metadata": {
        "team": "payments",
        "criticality": "high",
        "tier": 1,
        "namespace": "production",
        "runtime": "python3.12"
      }
    }
  ],
  "edges": [
    {
      "source": "checkout-service",
      "target": "payment-service",
      "attributes": {
        "communication_mode": "sync | async",
        "criticality": "hard | soft | degraded",
        "protocol": "grpc | http | kafka",
        "timeout_ms": 5000,
        "retry_config": {
          "max_retries": 3,
          "backoff_strategy": "exponential"
        }
      }
    }
  ]
}
```

**Response (202 Accepted):**
```json
{
  "ingestion_id": "uuid",
  "status": "processing | completed | failed",
  "nodes_received": 150,
  "edges_received": 420,
  "nodes_upserted": 148,
  "edges_upserted": 415,
  "circular_dependencies_detected": [
    {
      "cycle_path": ["service-a", "service-b", "service-c", "service-a"],
      "alert_id": "uuid"
    }
  ],
  "conflicts_resolved": [
    {
      "edge": {"source": "svc-a", "target": "svc-b"},
      "existing_source": "otel_service_graph",
      "new_source": "manual",
      "resolution": "kept_higher_priority"
    }
  ],
  "warnings": [
    "3 unknown services auto-created as placeholders"
  ],
  "estimated_completion_seconds": 15
}
```

**Error Responses:**

- **400 Bad Request:** Invalid schema, missing required fields, invalid enum values
  ```json
  {
    "type": "https://slo-engine.internal/errors/invalid-schema",
    "title": "Invalid Request Schema",
    "status": 400,
    "detail": "Field 'nodes[0].service_id' is required but missing",
    "instance": "/api/v1/services/dependencies"
  }
  ```

- **429 Too Many Requests:** Rate limit exceeded
  ```json
  {
    "type": "https://slo-engine.internal/errors/rate-limit-exceeded",
    "title": "Rate Limit Exceeded",
    "status": 429,
    "detail": "API rate limit of 10 req/min exceeded. Retry after 45 seconds.",
    "instance": "/api/v1/services/dependencies",
    "retry_after_seconds": 45
  }
  ```

- **500 Internal Server Error:** Database failure, unexpected exception
  ```json
  {
    "type": "https://slo-engine.internal/errors/internal-error",
    "title": "Internal Server Error",
    "status": 500,
    "detail": "An unexpected error occurred while processing the request",
    "instance": "/api/v1/services/dependencies"
  }
  ```

**Authentication:** API Key (X-API-Key header) or OAuth2 Bearer token
**Rate Limit:** 10 req/min per client
**Timeout:** 60 seconds

---

### Endpoint 2: GET /api/v1/services/{service-id}/dependencies

**Purpose:** Query dependency subgraph for a service

**Path Parameters:**
- `service-id`: Service business identifier (e.g., "checkout-service")

**Query Parameters:**
- `direction`: enum (`upstream`, `downstream`, `both`) - default: `both`
- `depth`: integer (1-10) - default: `3`
- `include_stale`: boolean - default: `false`
- `include_external`: boolean - default: `true`

**Response (200 OK):**
```json
{
  "service_id": "checkout-service",
  "direction": "both",
  "depth": 3,
  "nodes": [
    {
      "service_id": "checkout-service",
      "id": "uuid",
      "team": "payments",
      "criticality": "high",
      "metadata": {...}
    },
    {
      "service_id": "payment-service",
      "id": "uuid",
      "team": "payments",
      "criticality": "critical",
      "metadata": {...}
    }
  ],
  "edges": [
    {
      "source": "checkout-service",
      "target": "payment-service",
      "communication_mode": "sync",
      "criticality": "hard",
      "protocol": "grpc",
      "timeout_ms": 5000,
      "confidence_score": 0.95,
      "discovery_source": "otel_service_graph",
      "last_observed_at": "2026-02-14T09:45:00Z",
      "is_stale": false
    }
  ],
  "statistics": {
    "total_nodes": 15,
    "total_edges": 42,
    "upstream_services": 3,
    "downstream_services": 11,
    "max_depth_reached": 3
  }
}
```

**Error Responses:**

- **404 Not Found:** Service not registered
  ```json
  {
    "type": "https://slo-engine.internal/errors/service-not-found",
    "title": "Service Not Found",
    "status": 404,
    "detail": "Service with ID 'nonexistent-service' is not registered",
    "instance": "/api/v1/services/nonexistent-service/dependencies"
  }
  ```

- **400 Bad Request:** Invalid depth parameter
  ```json
  {
    "type": "https://slo-engine.internal/errors/invalid-parameter",
    "title": "Invalid Parameter",
    "status": 400,
    "detail": "Parameter 'depth' must be between 1 and 10. Received: 15",
    "instance": "/api/v1/services/checkout-service/dependencies"
  }
  ```

**Authentication:** API Key or OAuth2 Bearer token
**Rate Limit:** 60 req/min per client
**Timeout:** 30 seconds

---

## Database Design

### Schema Details

#### Table: services

```sql
CREATE TABLE services (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_id VARCHAR(255) UNIQUE NOT NULL,  -- Business identifier
    metadata JSONB NOT NULL DEFAULT '{}',
    criticality VARCHAR(20) NOT NULL DEFAULT 'medium'
        CHECK (criticality IN ('critical', 'high', 'medium', 'low')),
    team VARCHAR(255),
    discovered BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_services_service_id ON services(service_id);
CREATE INDEX idx_services_team ON services(team) WHERE team IS NOT NULL;
CREATE INDEX idx_services_criticality ON services(criticality);
CREATE INDEX idx_services_discovered ON services(discovered) WHERE discovered = true;

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_services_updated_at
    BEFORE UPDATE ON services
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

#### Table: service_dependencies

```sql
CREATE TABLE service_dependencies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_service_id UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    target_service_id UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    communication_mode VARCHAR(10) NOT NULL CHECK (communication_mode IN ('sync', 'async')),
    criticality VARCHAR(20) NOT NULL DEFAULT 'hard'
        CHECK (criticality IN ('hard', 'soft', 'degraded')),
    protocol VARCHAR(50),
    timeout_ms INTEGER CHECK (timeout_ms > 0),
    retry_config JSONB,
    discovery_source VARCHAR(50) NOT NULL
        CHECK (discovery_source IN ('manual', 'otel_service_graph', 'kubernetes', 'service_mesh')),
    confidence_score REAL NOT NULL DEFAULT 1.0 CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    last_observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_stale BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Unique constraint: same edge from same source (allow different sources)
    CONSTRAINT unique_edge_per_source UNIQUE (source_service_id, target_service_id, discovery_source),

    -- Prevent self-loops
    CONSTRAINT no_self_loops CHECK (source_service_id != target_service_id)
);

-- Indexes for graph traversal
CREATE INDEX idx_deps_source ON service_dependencies(source_service_id) WHERE is_stale = false;
CREATE INDEX idx_deps_target ON service_dependencies(target_service_id) WHERE is_stale = false;
CREATE INDEX idx_deps_source_target ON service_dependencies(source_service_id, target_service_id);
CREATE INDEX idx_deps_discovery_source ON service_dependencies(discovery_source);
CREATE INDEX idx_deps_last_observed ON service_dependencies(last_observed_at);
CREATE INDEX idx_deps_stale ON service_dependencies(is_stale) WHERE is_stale = true;

-- Trigger for updated_at
CREATE TRIGGER update_service_dependencies_updated_at
    BEFORE UPDATE ON service_dependencies
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

#### Table: circular_dependency_alerts

```sql
CREATE TABLE circular_dependency_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cycle_path JSONB NOT NULL,  -- Array of service_ids forming the cycle
    status VARCHAR(20) NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'acknowledged', 'resolved')),
    acknowledged_by VARCHAR(255),
    resolution_notes TEXT,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Prevent duplicate alerts for same cycle (using JSONB containment)
    CONSTRAINT unique_cycle UNIQUE (cycle_path)
);

-- Index for querying open alerts
CREATE INDEX idx_circular_deps_status ON circular_dependency_alerts(status)
    WHERE status IN ('open', 'acknowledged');
CREATE INDEX idx_circular_deps_detected_at ON circular_dependency_alerts(detected_at DESC);
```

### Data Access Patterns

#### Pattern 1: Recursive Graph Traversal (Downstream)

```sql
WITH RECURSIVE dependency_tree AS (
    -- Base case: direct dependencies
    SELECT
        sd.target_service_id,
        sd.source_service_id,
        1 AS depth,
        ARRAY[sd.source_service_id] AS path,
        sd.*
    FROM service_dependencies sd
    WHERE sd.source_service_id = :service_uuid
      AND sd.is_stale = false

    UNION ALL

    -- Recursive case: transitive dependencies
    SELECT
        sd.target_service_id,
        sd.source_service_id,
        dt.depth + 1,
        dt.path || sd.source_service_id,
        sd.*
    FROM service_dependencies sd
    INNER JOIN dependency_tree dt ON sd.source_service_id = dt.target_service_id
    WHERE dt.depth < :max_depth
      AND sd.is_stale = false
      AND NOT sd.target_service_id = ANY(dt.path)  -- Cycle prevention
)
SELECT DISTINCT ON (target_service_id) *
FROM dependency_tree
ORDER BY target_service_id, depth ASC;
```

**Performance:** Indexed on `source_service_id` and `is_stale`. Target: <100ms on 5000 nodes.

#### Pattern 2: Get Full Adjacency List for Tarjan's Algorithm

```sql
SELECT
    source_service_id,
    array_agg(target_service_id) AS targets
FROM service_dependencies
WHERE is_stale = false
GROUP BY source_service_id;
```

**Performance:** Full table scan with aggregation. Cached in application memory for cycle detection.

#### Pattern 3: Mark Stale Edges

```sql
UPDATE service_dependencies
SET is_stale = true, updated_at = NOW()
WHERE last_observed_at < NOW() - INTERVAL ':staleness_hours hours'
  AND is_stale = false
RETURNING id;
```

#### Pattern 4: Bulk Upsert Services

```sql
INSERT INTO services (service_id, metadata, criticality, team, discovered)
VALUES
    (:service_id_1, :metadata_1, :criticality_1, :team_1, :discovered_1),
    (:service_id_2, :metadata_2, :criticality_2, :team_2, :discovered_2)
ON CONFLICT (service_id)
DO UPDATE SET
    metadata = EXCLUDED.metadata,
    criticality = EXCLUDED.criticality,
    team = EXCLUDED.team,
    discovered = EXCLUDED.discovered,
    updated_at = NOW()
RETURNING *;
```

### Migration Strategy

**Tool:** Alembic (SQLAlchemy migration framework)

**Migration Files:**
1. `001_create_services_table.py` - Create `services` table with indexes and triggers
2. `002_create_service_dependencies_table.py` - Create `service_dependencies` table
3. `003_create_circular_dependency_alerts_table.py` - Create `circular_dependency_alerts` table

**Rollback Strategy:**
- All migrations must include reversible `downgrade()` functions
- Test downgrades in staging before production deployment
- Keep migration history in version control

**Zero-Downtime Approach:**
- Use `CONCURRENTLY` for index creation
- Avoid locking `ALTER TABLE` operations during peak hours
- For large tables, use background workers (pg_repack if needed)

---

## Algorithm & Logic Design

### Tarjan's Algorithm for Cycle Detection

**Pseudocode:**

```python
class TarjanSCC:
    def __init__(self):
        self.index = 0
        self.stack = []
        self.indices = {}
        self.lowlinks = {}
        self.on_stack = set()
        self.sccs = []

    def find_sccs(self, graph: Dict[Node, List[Node]]) -> List[List[Node]]:
        """
        Find all strongly connected components.

        Time Complexity: O(V + E)
        Space Complexity: O(V)
        """
        for node in graph.keys():
            if node not in self.indices:
                self._strongconnect(node, graph)

        # Return only non-trivial SCCs (size > 1)
        return [scc for scc in self.sccs if len(scc) > 1]

    def _strongconnect(self, node: Node, graph: Dict[Node, List[Node]]):
        # Set the depth index for node to the smallest unused index
        self.indices[node] = self.index
        self.lowlinks[node] = self.index
        self.index += 1
        self.stack.append(node)
        self.on_stack.add(node)

        # Consider successors of node
        for successor in graph.get(node, []):
            if successor not in self.indices:
                # Successor has not yet been visited; recurse on it
                self._strongconnect(successor, graph)
                self.lowlinks[node] = min(self.lowlinks[node], self.lowlinks[successor])
            elif successor in self.on_stack:
                # Successor is in stack and hence in the current SCC
                self.lowlinks[node] = min(self.lowlinks[node], self.indices[successor])

        # If node is a root node, pop the stack and generate an SCC
        if self.lowlinks[node] == self.indices[node]:
            scc = []
            while True:
                w = self.stack.pop()
                self.on_stack.remove(w)
                scc.append(w)
                if w == node:
                    break
            self.sccs.append(scc)
```

---

## Error Handling & Edge Cases

### Edge Case Matrix

| Edge Case | Detection | Handling | User Feedback |
|-----------|-----------|----------|---------------|
| **Circular dependency detected** | Tarjan's algorithm after ingestion | Store `circular_dependency_alerts`, continue ingestion | Return warning in API response with cycle path |
| **Unknown service_id in edge** | FK lookup during edge ingestion | Auto-create placeholder `Service` with `discovered=true` | Return info in `warnings` list |
| **Conflicting edges from multiple sources** | Compare `discovery_source` during merge | Apply priority hierarchy (manual > mesh > otel > k8s) | Return conflicts in `conflicts_resolved` list |
| **Self-loop (source == target)** | Check constraint validation | Reject edge, raise validation error | 400 error with clear message |
| **Graph depth exceeds limit** | Check `max_depth` parameter | Clamp to max=10, log warning | Return 400 if >10 requested |
| **Stale edge included in traversal** | Check `is_stale` flag during query | Exclude unless `include_stale=true` | Transparent to user (excluded by default) |
| **Database connection failure** | AsyncPG exception | Retry with exponential backoff (3 attempts), then fail | 500 error after retries exhausted |
| **Invalid enum value in request** | Pydantic validation | Reject immediately | 400 error with valid enum options |
| **Request body exceeds size limit** | FastAPI middleware | Reject with 413 Payload Too Large | 413 error with max size info |
| **Concurrent ingestions conflict** | PostgreSQL row-level locking | Use `ON CONFLICT` upsert, serialize conflicts | Last write wins, no user impact |

### Retry Strategy

**Database Operations:**
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True
)
async def db_operation_with_retry():
    # Database operation
    pass
```

**Prometheus Queries (out of scope for FR-1, but documented for consistency):**
- Circuit breaker pattern: 10 failures → 30s open → half-open
- Fallback: Return cached recommendations with `stale: true` flag

---

## Dependencies & Interfaces

### Internal Dependencies

| Component | Depends On | Interface |
|-----------|-----------|-----------|
| **API Routes** | Use Cases, DTOs | FastAPI router, Pydantic schemas |
| **Use Cases** | Domain Entities, Domain Services, Repository Interfaces | Async methods |
| **Domain Services** | Domain Entities, Repository Interfaces | Pure domain logic |
| **Repository Implementations** | Domain Entities, SQLAlchemy Models | Async repository interfaces |

### External Dependencies

| Library | Version | Purpose | Fallback |
|---------|---------|---------|----------|
| **FastAPI** | 0.115+ | API framework | None (core requirement) |
| **Pydantic** | 2.0+ | Validation, DTOs | None (bundled with FastAPI) |
| **SQLAlchemy** | 2.0+ | ORM, async DB access | None (core requirement) |
| **AsyncPG** | 0.29+ | PostgreSQL async driver | Psycopg3 (compatibility layer) |
| **Alembic** | 1.13+ | Database migrations | Manual SQL scripts (not recommended) |
| **Python** | 3.12+ | Runtime | None (language requirement) |

### Integration Points

**With FR-2 (SLO Recommendation Generation):**
- FR-2 will call `QueryDependencySubgraphUseCase` to get dependency graphs
- Interface: Use case returns domain entities, FR-2 maps to its own domain models

**With FR-4 (Impact Analysis):**
- FR-4 will use `GraphTraversalService` for upstream traversal
- Interface: Shared domain service, stateless operations

---

## Security Considerations

### Input Validation

**Layer 1: Pydantic Schema Validation**
```python
from pydantic import BaseModel, Field, field_validator
from typing import List
from enum import Enum

class EdgeAttributesDTO(BaseModel):
    communication_mode: CommunicationMode
    criticality: DependencyCriticality
    protocol: Optional[str] = Field(None, max_length=50)
    timeout_ms: Optional[int] = Field(None, gt=0, le=60000)

    @field_validator('protocol')
    def validate_protocol(cls, v):
        if v and not v.isalnum():
            raise ValueError("protocol must be alphanumeric")
        return v
```

**Layer 2: Domain Entity Validation**
```python
# In ServiceDependency.__post_init__
if self.source_service_id == self.target_service_id:
    raise ValueError("Self-loops not allowed")
if not (0.0 <= self.confidence_score <= 1.0):
    raise ValueError("confidence_score out of bounds")
```

**Layer 3: Database Constraints**
```sql
CHECK (source_service_id != target_service_id),
CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0)
```

### Authorization Checks

**RBAC Middleware:**
```python
# src/infrastructure/api/middleware/auth.py

from fastapi import Request, HTTPException, status
from typing import Optional

async def verify_api_key(request: Request) -> Optional[str]:
    """Extract and verify API key from X-API-Key header."""
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key"
        )

    # Verify against database (bcrypt hashed keys)
    # Implementation in Phase 2
    return api_key
```

**Endpoint-Level Authorization:**
```python
@router.post("/dependencies", dependencies=[Depends(verify_api_key)])
async def ingest_dependencies(...):
    # Only authenticated clients can ingest
    pass
```

### Data Sanitization

**JSONB Metadata Sanitization:**
```python
import re

def sanitize_metadata(metadata: dict) -> dict:
    """Remove potentially malicious content from metadata."""
    # Block script tags, SQL keywords, etc.
    dangerous_patterns = [
        r'<script.*?>.*?</script>',
        r'DROP\s+TABLE',
        r'DELETE\s+FROM',
    ]

    sanitized = {}
    for key, value in metadata.items():
        if isinstance(value, str):
            for pattern in dangerous_patterns:
                if re.search(pattern, value, re.IGNORECASE):
                    raise ValueError(f"Dangerous content detected in metadata: {key}")
        sanitized[key] = value

    return sanitized
```

### SQL Injection Prevention

**All queries via SQLAlchemy ORM or parameterized:**
```python
# SAFE: Parameterized query
result = await session.execute(
    select(Service).where(Service.service_id == service_id)
)

# UNSAFE (never do this):
query = f"SELECT * FROM services WHERE service_id = '{service_id}'"  # NO!
```

---

## Testing Strategy

### Unit Tests

**Coverage Target:** 90% line coverage for domain and application layers

**Test Pyramid:**
```
    E2E (5%)
     /\
    /  \
   /    \
  / Integ \
 /  (25%)  \
/__Unit_____\
   (70%)
```

**Example Unit Test:**
```python
# tests/unit/domain/test_service_entity.py

import pytest
from domain.entities.service import Service, Criticality

def test_service_creation_valid():
    service = Service(
        service_id="test-service",
        team="platform",
        criticality=Criticality.HIGH
    )
    assert service.service_id == "test-service"
    assert service.discovered is False

def test_service_creation_empty_service_id_raises():
    with pytest.raises(ValueError, match="service_id cannot be empty"):
        Service(service_id="")

def test_mark_as_registered():
    service = Service(service_id="svc", discovered=True)
    service.mark_as_registered(
        team="backend",
        criticality=Criticality.MEDIUM,
        metadata={"key": "value"}
    )
    assert service.discovered is False
    assert service.team == "backend"
```

**Example Domain Service Test:**
```python
# tests/unit/domain/services/test_circular_dependency_detector.py

import pytest
from domain.services.circular_dependency_detector import CircularDependencyDetector
from uuid import uuid4

@pytest.mark.asyncio
async def test_detect_simple_cycle():
    detector = CircularDependencyDetector()

    # Graph: A → B → C → A (cycle)
    a, b, c = uuid4(), uuid4(), uuid4()
    graph = {
        a: [b],
        b: [c],
        c: [a]
    }

    cycles = await detector.detect_cycles(graph)

    assert len(cycles) == 1
    assert set(cycles[0]) == {a, b, c}

@pytest.mark.asyncio
async def test_no_cycle_in_dag():
    detector = CircularDependencyDetector()

    # Graph: A → B → C (no cycle)
    a, b, c = uuid4(), uuid4(), uuid4()
    graph = {
        a: [b],
        b: [c],
        c: []
    }

    cycles = await detector.detect_cycles(graph)

    assert len(cycles) == 0
```

### Integration Tests

**Scope:** Repository implementations, database interactions, API endpoints

**Test Containers:** Use `testcontainers-python` to spin up PostgreSQL for tests

```python
# tests/integration/conftest.py

import pytest
from testcontainers.postgres import PostgresContainer
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

@pytest.fixture(scope="session")
async def postgres_container():
    with PostgresContainer("postgres:16") as postgres:
        yield postgres

@pytest.fixture
async def db_session(postgres_container):
    engine = create_async_engine(postgres_container.get_connection_url())
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Run migrations
    # ...

    async with async_session() as session:
        yield session
```

**Example Integration Test:**
```python
# tests/integration/infrastructure/test_dependency_repository.py

import pytest
from infrastructure.database.repositories.dependency_repository import DependencyRepository
from domain.entities.service import Service
from domain.entities.service_dependency import ServiceDependency, CommunicationMode

@pytest.mark.asyncio
async def test_bulk_upsert_dependencies(db_session):
    repo = DependencyRepository(db_session)

    # Create test services first
    service_a = Service(service_id="svc-a", team="test")
    service_b = Service(service_id="svc-b", team="test")
    # Save services...

    # Create dependency
    dep = ServiceDependency(
        source_service_id=service_a.id,
        target_service_id=service_b.id,
        communication_mode=CommunicationMode.SYNC,
        discovery_source=DiscoverySource.MANUAL
    )

    result = await repo.bulk_upsert([dep])

    assert len(result) == 1
    assert result[0].source_service_id == service_a.id
```

### End-to-End Tests

**Scope:** Full API workflows

```python
# tests/e2e/test_dependency_ingestion_flow.py

import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_full_ingestion_and_query_flow(async_client: AsyncClient):
    # Step 1: Ingest dependency graph
    ingest_payload = {
        "source": "manual",
        "timestamp": "2026-02-14T10:00:00Z",
        "nodes": [
            {"service_id": "svc-a", "metadata": {"team": "platform"}},
            {"service_id": "svc-b", "metadata": {"team": "platform"}}
        ],
        "edges": [
            {
                "source": "svc-a",
                "target": "svc-b",
                "attributes": {
                    "communication_mode": "sync",
                    "criticality": "hard"
                }
            }
        ]
    }

    response = await async_client.post(
        "/api/v1/services/dependencies",
        json=ingest_payload,
        headers={"X-API-Key": "test-key"}
    )

    assert response.status_code == 202
    data = response.json()
    assert data["nodes_upserted"] == 2
    assert data["edges_upserted"] == 1

    # Step 2: Query dependency subgraph
    response = await async_client.get(
        "/api/v1/services/svc-a/dependencies",
        params={"direction": "downstream", "depth": 1},
        headers={"X-API-Key": "test-key"}
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["edges"]) == 1
    assert data["edges"][0]["source"] == "svc-a"
    assert data["edges"][0]["target"] == "svc-b"
```

### Load Tests

**Tool:** k6 or Locust

**Scenario:** 200 concurrent users querying dependency subgraphs

```javascript
// load-tests/dependency-query.js

import http from 'k6/http';
import { check } from 'k6';

export let options = {
  vus: 200,
  duration: '10m',
};

export default function () {
  const response = http.get('http://localhost:8000/api/v1/services/checkout-service/dependencies', {
    headers: { 'X-API-Key': 'test-key' },
  });

  check(response, {
    'status is 200': (r) => r.status === 200,
    'response time < 500ms': (r) => r.timings.duration < 500,
  });
}
```

### Test Data Requirements

**Seed Data:**
- 500 services with realistic metadata
- 5,000 edges with mixed discovery sources
- 5 circular dependency cycles (for alert testing)
- Mix of stale and fresh edges

**Data Generation:**
```python
# tests/fixtures/test_data_generator.py

from faker import Faker
import random

fake = Faker()

def generate_test_services(count: int) -> List[dict]:
    teams = ["platform", "payments", "search", "data", "ml"]
    criticalities = ["critical", "high", "medium", "low"]

    return [
        {
            "service_id": f"service-{i}",
            "team": random.choice(teams),
            "criticality": random.choice(criticalities),
            "metadata": {
                "namespace": "production",
                "runtime": random.choice(["python3.12", "go1.21", "java17"])
            }
        }
        for i in range(count)
    ]
```

---

## Performance Considerations

### Expected Load Patterns

| Metric | Expected Load | Peak Load |
|--------|---------------|-----------|
| Graph ingestion frequency | 1 per hour (scheduled batch) | 10 per hour (manual updates) |
| Dependency query frequency | 100 req/min (Backstage polling) | 500 req/min (incident response) |
| Average graph size | 1000 nodes, 5000 edges | 5000 nodes, 50000 edges |
| Subgraph query depth | 3 hops (average) | 10 hops (max allowed) |

### Optimization Strategies

**1. Query Optimization:**
- **Partial indexes** on `is_stale = false` for hot path queries
- **Index-only scans** for traversal queries (source/target coverage)
- **EXPLAIN ANALYZE** all recursive CTEs in CI/CD

**2. Caching Strategy:**
- **Application-level cache** (Redis): Subgraph queries cached for 5 minutes
- **Cache key:** `subgraph:{service_id}:{direction}:{depth}`
- **Cache invalidation:** On dependency ingestion for affected services

```python
# src/infrastructure/cache/dependency_cache.py

from redis.asyncio import Redis
import json

class DependencyCache:
    def __init__(self, redis: Redis):
        self.redis = redis
        self.ttl = 300  # 5 minutes

    async def get_subgraph(self, service_id: str, direction: str, depth: int):
        key = f"subgraph:{service_id}:{direction}:{depth}"
        cached = await self.redis.get(key)
        return json.loads(cached) if cached else None

    async def set_subgraph(self, service_id: str, direction: str, depth: int, data: dict):
        key = f"subgraph:{service_id}:{direction}:{depth}"
        await self.redis.setex(key, self.ttl, json.dumps(data))

    async def invalidate_all(self):
        """
        Invalidate all cached subgraphs.

        Decision: Brute-force invalidation for MVP simplicity.
        Selective invalidation deferred until cache thrashing is
        observed in production (monitor cache_misses_total metric).
        """
        pattern = "subgraph:*"
        keys = await self.redis.keys(pattern)
        if keys:
            await self.redis.delete(*keys)
```

**3. Connection Pooling:**
```python
# src/infrastructure/database/config.py

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+asyncpg://user:pass@localhost/slo_engine"

engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,           # Max connections per instance
    max_overflow=10,        # Burst capacity
    pool_pre_ping=True,     # Validate connections before use
    pool_recycle=3600,      # Recycle connections every hour
    echo=False              # Disable SQL logging in production
)

async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)
```

**4. Bulk Operations:**
- Use `bulk_insert_mappings()` for large ingestions
- Batch size: 1000 records per transaction
- PostgreSQL `COPY` command for initial seed data

### Performance Monitoring

**Key Metrics to Track:**

> **Decision:** `service_id` is intentionally omitted from all metric labels to avoid
> high cardinality (5000+ services). Use exemplars for per-service sampling when debugging.

```python
# src/infrastructure/observability/metrics.py

from prometheus_client import Histogram, Counter, Gauge

# API latency — labels: method, endpoint, status (NO service_id)
api_request_duration = Histogram(
    'slo_engine_api_request_duration_seconds',
    'API request duration',
    ['method', 'endpoint', 'status']
)

# Graph traversal performance — labels: direction, depth (NO service_id)
graph_traversal_duration = Histogram(
    'slo_engine_graph_traversal_duration_seconds',
    'Graph traversal duration',
    ['direction', 'depth']
)

# Database connection pool
db_connections_active = Gauge(
    'slo_engine_db_connections_active',
    'Active database connections'
)

# Cache hit rate
cache_hits = Counter(
    'slo_engine_cache_hits_total',
    'Cache hits',
    ['cache_type']
)
cache_misses = Counter(
    'slo_engine_cache_misses_total',
    'Cache misses',
    ['cache_type']
)
```

---

## Implementation Phases

### Phase 1: Domain Foundation (Week 1)
**Objective:** Establish core domain model and business logic

**Tasks:**

* **Create Domain Entities** [Effort: M]
  - **Description**: Implement `Service`, `ServiceDependency`, `CircularDependencyAlert` entities with full validation
  - **Acceptance Criteria**:
      - [ ]  All entities have complete `__post_init__` validation
      - [ ]  Domain invariants enforced (no self-loops, confidence scores in [0,1], etc.)
      - [ ]  Unit tests achieve >90% coverage
  - **Files to Create/Modify**:
      - `src/domain/entities/service.py` - Service entity
      - `src/domain/entities/service_dependency.py` - ServiceDependency entity
      - `src/domain/entities/circular_dependency_alert.py` - CircularDependencyAlert entity
      - `tests/unit/domain/entities/` - Comprehensive unit tests
  - **Dependencies**: None
  - **Testing Requirements**: Unit tests with pytest, property-based testing with Hypothesis

* **Implement Domain Services** [Effort: L]
  - **Description**: Build `GraphTraversalService`, `CircularDependencyDetector` (Tarjan's), `EdgeMergeService`
  - **Acceptance Criteria**:
      - [ ]  Tarjan's algorithm correctly identifies all SCCs
      - [ ]  Edge merge service applies priority hierarchy correctly
      - [ ]  Confidence score calculation matches spec
      - [ ]  Unit tests validate all edge cases (cycles, conflicts, staleness)
  - **Files to Create/Modify**:
      - `src/domain/services/graph_traversal_service.py`
      - `src/domain/services/circular_dependency_detector.py`
      - `src/domain/services/edge_merge_service.py`
      - `tests/unit/domain/services/` - Test all algorithms
  - **Dependencies**: Domain entities
  - **Testing Requirements**: Unit tests with synthetic graphs, benchmark for Tarjan's on 10K nodes

* **Define Repository Interfaces** [Effort: S]
  - **Description**: Create abstract interfaces for all repositories
  - **Acceptance Criteria**:
      - [ ]  All repository methods defined with type hints
      - [ ]  Docstrings explain contracts and return values
      - [ ]  Async signatures throughout
  - **Files to Create/Modify**:
      - `src/domain/repositories/service_repository.py`
      - `src/domain/repositories/dependency_repository.py`
      - `src/domain/repositories/circular_dependency_alert_repository.py`
  - **Dependencies**: Domain entities
  - **Testing Requirements**: None (interfaces only)

**Phase Deliverables:**
- Complete domain layer (entities, services, repository interfaces)
- Unit test suite with >90% coverage
- Domain logic validated independently of infrastructure

---

### Phase 2: Infrastructure & Persistence (Week 2)
**Objective:** Implement database schema and repository layer

**Tasks:**

* **Database Schema & Migrations** [Effort: M]
  - **Description**: Create Alembic migrations for all tables, indexes, constraints, triggers
  - **Acceptance Criteria**:
      - [ ]  All tables created with correct types and constraints
      - [ ]  Indexes match data access patterns (source/target, staleness)
      - [ ]  Triggers for `updated_at` working
      - [ ]  Migrations are reversible (downgrade tested)
      - [ ]  Migration executes in <5s on empty database
  - **Files to Create/Modify**:
      - `alembic/versions/001_create_services_table.py`
      - `alembic/versions/002_create_service_dependencies_table.py`
      - `alembic/versions/003_create_circular_dependency_alerts_table.py`
      - `src/infrastructure/database/models.py` - SQLAlchemy models
  - **Dependencies**: None
  - **Testing Requirements**: Migration up/down testing in CI

* **Implement Repository Layer** [Effort: XL]
  - **Description**: Build PostgreSQL repository implementations with AsyncPG/SQLAlchemy
  - **Acceptance Criteria**:
      - [ ]  All repository interface methods implemented
      - [ ]  Recursive CTE traversal returns correct subgraph in <100ms
      - [ ]  Bulk upsert handles 1000 records in <2s
      - [ ]  Connection pooling configured (max 20 connections)
      - [ ]  All queries use parameterized inputs (no SQL injection risk)
      - [ ]  Integration tests pass with testcontainers
  - **Files to Create/Modify**:
      - `src/infrastructure/database/repositories/service_repository.py`
      - `src/infrastructure/database/repositories/dependency_repository.py`
      - `src/infrastructure/database/repositories/circular_dependency_alert_repository.py`
      - `src/infrastructure/database/session.py` - Database session management
      - `tests/integration/infrastructure/database/` - Integration tests
  - **Dependencies**: Database schema, domain interfaces
  - **Testing Requirements**: Integration tests with PostgreSQL testcontainer, load testing for bulk operations

* **Database Configuration & Connection Management** [Effort: S]
  - **Description**: Set up async engine, session factory, connection pooling
  - **Acceptance Criteria**:
      - [ ]  Environment-based configuration (dev/staging/prod)
      - [ ]  Connection pool size configurable via env vars
      - [ ]  Health check endpoint verifies DB connectivity
      - [ ]  Graceful shutdown closes connections cleanly
  - **Files to Create/Modify**:
      - `src/infrastructure/database/config.py`
      - `src/infrastructure/database/health.py`
      - `.env.example` - Example configuration
  - **Dependencies**: None
  - **Testing Requirements**: Unit tests for config parsing, integration test for health check

**Phase Deliverables:**
- Working PostgreSQL schema with migrations
- Repository layer with full CRUD operations
- Integration test suite passing
- Database connection pooling and health checks operational

---

### Phase 3: Application Layer & Use Cases (Week 3)
**Objective:** Implement business workflows and DTOs

**Tasks:**

* **Define Application DTOs** [Effort: M]
  - **Description**: Create Pydantic models for all API request/response schemas
  - **Acceptance Criteria**:
      - [ ]  All DTOs have complete validation rules
      - [ ]  Enum fields validated against allowed values
      - [ ]  Custom validators for complex rules (e.g., cycle path validation)
      - [ ]  DTOs generate OpenAPI schema correctly
      - [ ]  Example values provided for documentation
  - **Files to Create/Modify**:
      - `src/application/dtos/dependency_graph_dto.py` - Ingestion request/response
      - `src/application/dtos/dependency_subgraph_dto.py` - Query request/response
      - `src/application/dtos/common.py` - Shared DTOs (error responses, enums)
      - `tests/unit/application/dtos/` - DTO validation tests
  - **Dependencies**: None (Pydantic only)
  - **Testing Requirements**: Unit tests for validation edge cases

* **Implement IngestDependencyGraphUseCase** [Effort: XL]
  - **Description**: Orchestrate full ingestion workflow (validate → merge → detect cycles → persist)
  - **Acceptance Criteria**:
      - [ ]  Accepts bulk graph ingestion with nodes + edges
      - [ ]  Auto-creates placeholder services for unknown service_ids
      - [ ]  Merges edges from multiple sources with priority resolution
      - [ ]  Triggers Tarjan's cycle detection asynchronously
      - [ ]  Returns detailed response with stats and warnings
      - [ ]  Handles concurrent ingestions safely (database UPSERT)
      - [ ]  Completes 1000-node graph in <30s
  - **Files to Create/Modify**:
      - `src/application/use_cases/ingest_dependency_graph.py`
      - `tests/unit/application/use_cases/test_ingest_dependency_graph.py`
      - `tests/integration/application/test_ingest_dependency_graph_integration.py`
  - **Dependencies**: Repositories, domain services, DTOs
  - **Testing Requirements**: Unit tests with mocked repositories, integration tests with real DB

* **Implement QueryDependencySubgraphUseCase** [Effort: M]
  - **Description**: Query and return dependency subgraph (upstream/downstream/both)
  - **Acceptance Criteria**:
      - [ ]  Supports direction (upstream/downstream/both) and depth (1-10)
      - [ ]  Excludes stale edges by default (configurable)
      - [ ]  Returns nodes + edges + statistics
      - [ ]  Response time <500ms for 3-hop query on 5000-node graph
      - [ ]  Handles non-existent service_id gracefully (404)
  - **Files to Create/Modify**:
      - `src/application/use_cases/query_dependency_subgraph.py`
      - `tests/unit/application/use_cases/test_query_dependency_subgraph.py`
  - **Dependencies**: Repositories, domain services, DTOs
  - **Testing Requirements**: Unit tests, integration tests with realistic graph topology

* **Implement DetectCircularDependenciesUseCase** [Effort: M]
  - **Description**: Background task to detect cycles and create alerts
  - **Acceptance Criteria**:
      - [ ]  Runs Tarjan's algorithm on full graph
      - [ ]  Creates `CircularDependencyAlert` for each SCC
      - [ ]  Deduplicates alerts (same cycle not reported twice)
      - [ ]  Completes in <10s for 5000-node graph
  - **Files to Create/Modify**:
      - `src/application/use_cases/detect_circular_dependencies.py`
      - `tests/unit/application/use_cases/test_detect_circular_dependencies.py`
  - **Dependencies**: Repositories, CircularDependencyDetector
  - **Testing Requirements**: Unit tests with known cycles, performance benchmark

**Phase Deliverables:**
- All use cases implemented and tested
- Application DTOs defined with complete validation
- Unit and integration tests passing
- Use case layer ready for API integration

---

### Phase 4: API Layer (Week 4)
**Objective:** Build FastAPI REST endpoints with authentication

**Tasks:**

* **Implement API Routes** [Effort: L]
  - **Description**: Create FastAPI routers for dependency ingestion and querying
  - **Acceptance Criteria**:
      - [ ]  POST /api/v1/services/dependencies accepts ingestion requests
      - [ ]  GET /api/v1/services/{service-id}/dependencies returns subgraph
      - [ ]  Both endpoints return RFC 7807 Problem Details on errors
      - [ ]  OpenAPI spec auto-generated with examples
      - [ ]  Request validation handled by Pydantic
      - [ ]  Async handlers use dependency injection for use cases
  - **Files to Create/Modify**:
      - `src/infrastructure/api/routes/dependencies.py`
      - `src/infrastructure/api/main.py` - FastAPI app setup
      - `tests/e2e/test_dependency_api.py` - E2E tests
  - **Dependencies**: Use cases, DTOs
  - **Testing Requirements**: E2E tests with httpx AsyncClient

* **Authentication & Authorization** [Effort: M]
  - **Description**: Implement API key validation and rate limiting
  - **Acceptance Criteria**:
      - [ ]  X-API-Key header validated against database (bcrypt hashed)
      - [ ]  Missing/invalid API key returns 401 with clear message
      - [ ]  Rate limiting enforced (10 req/min for ingestion, 60 req/min for queries)
      - [ ]  Rate limit headers returned (X-RateLimit-Limit, X-RateLimit-Remaining)
      - [ ]  429 response when rate limit exceeded
  - **Files to Create/Modify**:
      - `src/infrastructure/api/middleware/auth.py`
      - `src/infrastructure/api/middleware/rate_limit.py`
      - `src/infrastructure/database/models/api_key.py` - API key model
      - `tests/integration/infrastructure/api/test_auth.py`
  - **Dependencies**: None (middleware layer)
  - **Testing Requirements**: Integration tests for auth flows, rate limiting behavior

* **Error Handling & Validation** [Effort: S]
  - **Description**: Global exception handlers, RFC 7807 error responses
  - **Acceptance Criteria**:
      - [ ]  All exceptions mapped to appropriate HTTP status codes
      - [ ]  Error responses follow RFC 7807 Problem Details format
      - [ ]  Validation errors include field-level detail
      - [ ]  500 errors logged with full stack trace (not exposed to client)
      - [ ]  Error responses include request correlation ID
  - **Files to Create/Modify**:
      - `src/infrastructure/api/middleware/error_handler.py`
      - `src/infrastructure/api/schemas/error_schema.py`
  - **Dependencies**: None
  - **Testing Requirements**: Unit tests for error response formatting

* **OpenAPI Documentation** [Effort: S]
  - **Description**: Enhance auto-generated OpenAPI spec with descriptions, examples
  - **Acceptance Criteria**:
      - [ ]  All endpoints have clear descriptions
      - [ ]  Request/response examples provided
      - [ ]  Error response schemas documented
      - [ ]  Swagger UI accessible at /docs
      - [ ]  ReDoc accessible at /redoc
  - **Files to Create/Modify**:
      - `src/infrastructure/api/main.py` - OpenAPI metadata
      - `src/application/dtos/` - Add schema examples to DTOs
  - **Dependencies**: API routes, DTOs
  - **Testing Requirements**: Manual verification of Swagger UI

**Phase Deliverables:**
- Complete REST API with two endpoints
- Authentication and rate limiting operational
- OpenAPI documentation auto-generated
- E2E test suite passing

---

### Phase 5: Observability & Operations (Week 5)
**Objective:** Add monitoring, logging, health checks

**Tasks:**

* **Prometheus Metrics** [Effort: M]
  - **Description**: Instrument API and database operations with Prometheus metrics
  - **Acceptance Criteria**:
      - [ ]  API request duration histogram per endpoint
      - [ ]  Graph traversal duration histogram
      - [ ]  Database connection pool gauge
      - [ ]  Cache hit/miss counters
      - [ ]  Metrics endpoint at /metrics
      - [ ]  All metrics have proper labels (endpoint, status_code, direction, etc.)
  - **Files to Create/Modify**:
      - `src/infrastructure/observability/metrics.py`
      - `src/infrastructure/api/middleware/metrics.py` - Middleware to track requests
      - `src/infrastructure/database/repositories/` - Instrument queries
  - **Dependencies**: None (prometheus_client library)
  - **Testing Requirements**: Integration tests verify metrics are recorded

* **Structured Logging** [Effort: S]
  - **Description**: JSON-formatted logs with correlation IDs, log levels
  - **Acceptance Criteria**:
      - [ ]  All logs output as JSON
      - [ ]  Request correlation ID propagated through layers
      - [ ]  Log levels used appropriately (ERROR for exceptions, INFO for ingestion, DEBUG for queries)
      - [ ]  Sensitive data (API keys) not logged
      - [ ]  Logs include timestamp, logger name, message, context
  - **Files to Create/Modify**:
      - `src/infrastructure/observability/logging.py`
      - `src/infrastructure/api/middleware/logging.py` - Request logging middleware
  - **Dependencies**: None (structlog library)
  - **Testing Requirements**: Unit tests verify log format, sensitive data exclusion

* **Health Checks** [Effort: S]
  - **Description**: Liveness and readiness probes for Kubernetes
  - **Acceptance Criteria**:
      - [ ]  GET /api/v1/health returns 200 if process alive
      - [ ]  GET /api/v1/health/ready returns 200 if DB connected and Prometheus reachable
      - [ ]  Readiness check fails gracefully if dependencies down (503)
      - [ ]  Health checks excluded from rate limiting
  - **Files to Create/Modify**:
      - `src/infrastructure/api/routes/health.py`
      - `tests/integration/infrastructure/api/test_health.py`
  - **Dependencies**: Database session, (future: Prometheus client)
  - **Testing Requirements**: Integration tests with mocked DB failures

* **Tracing (OpenTelemetry)** [Effort: M]
  - **Description**: Distributed tracing for request flows (optional but recommended)
  - **Acceptance Criteria**:
      - [ ]  Trace spans created for API requests, use cases, repository calls
      - [ ]  Trace context propagated across async boundaries
      - [ ]  Traces exported to Tempo/Jaeger (configurable)
      - [ ]  Trace sampling rate configurable (default 10%)
  - **Files to Create/Modify**:
      - `src/infrastructure/observability/tracing.py`
      - `src/infrastructure/api/middleware/tracing.py`
  - **Dependencies**: None (opentelemetry-api, opentelemetry-sdk)
  - **Testing Requirements**: Manual verification in Jaeger UI

**Phase Deliverables:**
- Prometheus metrics exported
- Structured JSON logging operational
- Health checks for Kubernetes readiness/liveness
- (Optional) Distributed tracing configured

---

### Phase 6: Integration & Deployment (Week 6)
**Objective:** Integrate with external systems, deploy to staging

**Tasks:**

* **OpenTelemetry Service Graph Integration** [Effort: L]
  - **Description**: Poll OTel Service Graph Connector metrics from Prometheus, ingest as dependency edges
  - **Acceptance Criteria**:
      - [ ]  Background job queries `traces_service_graph_request_total` metric
      - [ ]  Converts metric labels to dependency edges (source → target)
      - [ ]  Ingests edges with `discovery_source=otel_service_graph`
      - [ ]  Runs every 15 minutes (configurable)
      - [ ]  Handles Prometheus unavailability gracefully (retry with backoff)
  - **Files to Create/Modify**:
      - `src/infrastructure/integrations/otel_service_graph.py`
      - `src/infrastructure/tasks/ingest_otel_graph.py` - Scheduled task
      - `tests/integration/infrastructure/integrations/test_otel_service_graph.py`
  - **Dependencies**: Prometheus client (from TRD FR-6)
  - **Testing Requirements**: Integration tests with mocked Prometheus responses

* **Scheduled Background Tasks** [Effort: M]
  - **Description**: Set up task scheduler (APScheduler or Celery) for periodic jobs
  - **Acceptance Criteria**:
      - [ ]  OTel graph ingestion task runs every 15 minutes
      - [ ]  Stale edge detection task runs daily
      - [ ]  Circular dependency detection runs after each ingestion
      - [ ]  Task failures logged and alerted (Sentry integration)
      - [ ]  Tasks can be triggered manually via admin API (future)
  - **Files to Create/Modify**:
      - `src/infrastructure/tasks/scheduler.py`
      - `src/infrastructure/tasks/mark_stale_edges.py`
      - `docker-compose.yml` - Add worker service
  - **Dependencies**: APScheduler or Celery
  - **Testing Requirements**: Integration tests verify tasks execute

* **Docker & Docker Compose** [Effort: S]
  - **Description**: Containerize application, create docker-compose for local dev
  - **Acceptance Criteria**:
      - [ ]  Multi-stage Dockerfile (builder + runtime)
      - [ ]  Image size optimized (<500MB)
      - [ ]  docker-compose.yml includes API, worker, PostgreSQL, Redis
      - [ ]  Environment variables configurable via .env file
      - [ ]  `docker-compose up` starts full stack
  - **Files to Create/Modify**:
      - `Dockerfile`
      - `docker-compose.yml`
      - `.dockerignore`
  - **Dependencies**: None
  - **Testing Requirements**: Manual verification of docker-compose stack

* **CI/CD Pipeline** [Effort: M]
  - **Description**: GitHub Actions workflow for testing, linting, building
  - **Acceptance Criteria**:
      - [ ]  Linting (ruff), type checking (mypy --strict)
      - [ ]  Unit + integration tests run on every PR
      - [ ]  Code coverage report generated (codecov)
      - [ ]  Docker image built and pushed to registry on main merge
      - [ ]  Deployment to staging triggered on successful build
  - **Files to Create/Modify**:
      - `.github/workflows/ci.yml`
      - `.github/workflows/deploy-staging.yml`
  - **Dependencies**: None
  - **Testing Requirements**: Validate CI pipeline with dummy PR

* **Deployment to Staging** [Effort: M]
  - **Description**: Deploy to Kubernetes staging environment
  - **Acceptance Criteria**:
      - [ ]  Helm chart created for API and worker deployments
      - [ ]  ConfigMaps and Secrets for configuration
      - [ ]  PostgreSQL and Redis provisioned (or managed service)
      - [ ]  Ingress configured with TLS
      - [ ]  Monitoring (Prometheus) and logging (Loki) integrated
      - [ ]  Smoke tests pass in staging
  - **Files to Create/Modify**:
      - `helm/slo-engine/` - Helm chart
      - `k8s/staging/` - Staging-specific overrides
  - **Dependencies**: Docker image, Kubernetes cluster
  - **Testing Requirements**: Smoke tests in staging, health check validation

**Phase Deliverables:**
- OTel Service Graph integration operational
- Background tasks scheduled and running
- Full Docker Compose local dev stack
- CI/CD pipeline operational
- Application deployed to staging environment

---

## Decisions & Clarifications

### All Decisions (Finalized)

✅ **Database:** PostgreSQL with recursive CTEs (not Neo4j)
✅ **Async Pattern:** Full async/await throughout
✅ **Discovery Sources:** Manual + OTel Service Graph (K8s/Service Mesh deferred)
✅ **Circular Dependency Handling:** Non-blocking (store alert, allow ingestion)
✅ **Staleness Threshold:** Global threshold (7 days) for all discovery sources. Single `STALE_EDGE_THRESHOLD_HOURS` env var (default: 168). Per-source thresholds deferred to Phase 3+ if needed.
✅ **API Key Management:** CLI tool only for MVP (`slo-cli api-keys create --name backstage`). Admin API endpoint deferred to Phase 3.
✅ **Background Task Queue:** APScheduler (in-process) for MVP. Migration trigger: task volume > 100/min or need for distributed execution across multiple workers.
✅ **Prometheus Metric Labels:** Omit `service_id` from metric labels to avoid high cardinality (5000 services). Use only aggregated labels (`direction`, `depth`, `method`, `endpoint`, `status_code`). Use exemplars for per-service sampling if granularity is needed for debugging.
✅ **Cache Invalidation:** Invalidate all cached subgraphs on any graph update (brute force). Optimization to selective invalidation deferred until cache thrashing is observed in production metrics.

### Technical Debt to Track

| Item | Description | Priority | Mitigation |
|------|-------------|----------|------------|
| **Neo4j Migration Path** | PostgreSQL CTE sufficient for MVP, but Neo4j may be needed for advanced graph analytics (PageRank, centrality) | P3 | Abstract repository interface to enable future swap |
| **Kubernetes/Service Mesh Integration** | Deferred to post-MVP, but design should not preclude it | P2 | Keep `DiscoverySource` enum extensible, ensure EdgeMergeService priority is configurable |
| **Real-Time Graph Updates** | MVP uses batch ingestion; real-time streaming (Kafka) deferred | P3 | Design use cases to be idempotent (safe to replay) |
| **Multi-Region Topology** | Single-region assumption for MVP | P2 | Ensure service metadata includes region tag for future use |

---

## Next Steps

1. **Review this plan** with the team and stakeholders
2. **Set up project board** with tasks from implementation phases
3. **Assign Phase 1 tasks** to backend engineers
4. **Schedule daily standups** during active development (Weeks 1-6)
5. **Create feature branch:** `feature/fr1-dependency-graph`
6. **Begin Phase 1:** Domain Foundation (Week 1)

---

**End of Technical Requirements Specification**
