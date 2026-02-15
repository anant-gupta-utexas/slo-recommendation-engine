"""Edge merge service module.

This module defines the EdgeMergeService for merging edges from multiple
discovery sources with conflict resolution.
"""

import math
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from src.domain.entities.service_dependency import (
        DiscoverySource,
        ServiceDependency,
    )


class EdgeMergeService:
    """Domain service for merging edges from multiple discovery sources.

    Conflict resolution priority:
    1. MANUAL (highest)
    2. SERVICE_MESH
    3. OTEL_SERVICE_GRAPH
    4. KUBERNETES (lowest)
    """

    # Import at runtime to avoid circular dependency issues
    from src.domain.entities.service_dependency import DiscoverySource

    PRIORITY_MAP = {
        DiscoverySource.MANUAL: 4,
        DiscoverySource.SERVICE_MESH: 3,
        DiscoverySource.OTEL_SERVICE_GRAPH: 2,
        DiscoverySource.KUBERNETES: 1,
    }

    def merge_edges(
        self,
        existing_edges: dict[tuple[UUID, UUID], "ServiceDependency"],
        new_edges: list["ServiceDependency"],
    ) -> dict[str, list["ServiceDependency"] | list[dict]]:
        """Merge new edges with existing edges, resolving conflicts.

        Args:
            existing_edges: Map of (source_id, target_id) → ServiceDependency
            new_edges: List of new edges to merge

        Returns:
            Dict with keys:
            - "upserted": Edges that were inserted or updated
            - "conflicts": Edges where conflict resolution occurred
        """
        upserted: list["ServiceDependency"] = []
        conflicts: list[dict] = []

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
                    conflicts.append(
                        {
                            "edge": winner,
                            "existing_source": existing.discovery_source.value,
                            "new_source": new_edge.discovery_source.value,
                            "resolution": "kept_higher_priority",
                        }
                    )
                    upserted.append(winner)

        return {"upserted": upserted, "conflicts": conflicts}

    def _resolve_conflict(
        self, existing: "ServiceDependency", new: "ServiceDependency"
    ) -> "ServiceDependency":
        """Return the edge with higher priority source.

        Args:
            existing: Existing edge in database
            new: New edge being merged

        Returns:
            The edge with higher priority source
        """
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
        self, source: "DiscoverySource", observation_count: int = 1
    ) -> float:
        """Compute confidence score based on discovery source and observations.

        Args:
            source: Discovery source
            observation_count: Number of times this edge has been observed

        Returns:
            Confidence score between 0.0 and 1.0
        """
        from src.domain.entities.service_dependency import DiscoverySource

        # Base confidence by source
        base_confidence = {
            DiscoverySource.MANUAL: 1.0,
            DiscoverySource.SERVICE_MESH: 0.95,
            DiscoverySource.OTEL_SERVICE_GRAPH: 0.85,
            DiscoverySource.KUBERNETES: 0.75,
        }

        # Boost confidence with multiple observations (logarithmic scaling)
        observation_boost = min(0.1, 0.02 * math.log(observation_count + 1))

        return min(1.0, base_confidence[source] + observation_boost)
