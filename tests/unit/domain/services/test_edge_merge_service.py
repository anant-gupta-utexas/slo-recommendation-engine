"""Unit tests for EdgeMergeService."""

import pytest
from uuid import uuid4

from src.domain.services.edge_merge_service import EdgeMergeService
from src.domain.entities.service_dependency import (
    ServiceDependency,
    CommunicationMode,
    DiscoverySource,
)


class TestEdgeMergeService:
    """Test cases for EdgeMergeService."""

    @pytest.fixture
    def service(self):
        """Fixture for creating EdgeMergeService instance."""
        return EdgeMergeService()

    @pytest.fixture
    def source_id(self):
        """Fixture for source service UUID."""
        return uuid4()

    @pytest.fixture
    def target_id(self):
        """Fixture for target service UUID."""
        return uuid4()

    def test_priority_map_ordering(self, service):
        """Test that priority map has correct ordering."""
        assert service.PRIORITY_MAP[DiscoverySource.MANUAL] == 4
        assert service.PRIORITY_MAP[DiscoverySource.SERVICE_MESH] == 3
        assert service.PRIORITY_MAP[DiscoverySource.OTEL_SERVICE_GRAPH] == 2
        assert service.PRIORITY_MAP[DiscoverySource.KUBERNETES] == 1

        # Verify ordering: MANUAL > SERVICE_MESH > OTEL > KUBERNETES
        assert (
            service.PRIORITY_MAP[DiscoverySource.MANUAL]
            > service.PRIORITY_MAP[DiscoverySource.SERVICE_MESH]
        )
        assert (
            service.PRIORITY_MAP[DiscoverySource.SERVICE_MESH]
            > service.PRIORITY_MAP[DiscoverySource.OTEL_SERVICE_GRAPH]
        )
        assert (
            service.PRIORITY_MAP[DiscoverySource.OTEL_SERVICE_GRAPH]
            > service.PRIORITY_MAP[DiscoverySource.KUBERNETES]
        )

    def test_merge_edges_new_edge_no_conflict(self, service, source_id, target_id):
        """Test merging a new edge with no existing edge (no conflict)."""
        existing_edges = {}
        new_edge = ServiceDependency(
            source_service_id=source_id,
            target_service_id=target_id,
            communication_mode=CommunicationMode.SYNC,
            discovery_source=DiscoverySource.MANUAL,
        )

        result = service.merge_edges(existing_edges, [new_edge])

        assert len(result["upserted"]) == 1
        assert len(result["conflicts"]) == 0
        assert result["upserted"][0] == new_edge

    def test_merge_edges_same_source_update(self, service, source_id, target_id):
        """Test merging edge from same source (update, not conflict)."""
        existing_edge = ServiceDependency(
            source_service_id=source_id,
            target_service_id=target_id,
            communication_mode=CommunicationMode.SYNC,
            discovery_source=DiscoverySource.MANUAL,
        )
        existing_edges = {(source_id, target_id): existing_edge}

        # New edge from same source with updated attributes
        new_edge = ServiceDependency(
            source_service_id=source_id,
            target_service_id=target_id,
            communication_mode=CommunicationMode.ASYNC,
            discovery_source=DiscoverySource.MANUAL,
            protocol="kafka",
        )

        result = service.merge_edges(existing_edges, [new_edge])

        assert len(result["upserted"]) == 1
        assert len(result["conflicts"]) == 0

        # Verify attributes were updated
        upserted = result["upserted"][0]
        assert upserted.communication_mode == CommunicationMode.ASYNC
        assert upserted.protocol == "kafka"
        # Verify ID and created_at were preserved
        assert upserted.id == existing_edge.id
        assert upserted.created_at == existing_edge.created_at
        # Verify edge was refreshed
        assert not upserted.is_stale

    def test_merge_edges_conflict_manual_wins_over_otel(
        self, service, source_id, target_id
    ):
        """Test conflict resolution: MANUAL beats OTEL_SERVICE_GRAPH."""
        existing_edge = ServiceDependency(
            source_service_id=source_id,
            target_service_id=target_id,
            communication_mode=CommunicationMode.SYNC,
            discovery_source=DiscoverySource.OTEL_SERVICE_GRAPH,
        )
        existing_edges = {(source_id, target_id): existing_edge}

        # New edge from higher priority source (MANUAL)
        new_edge = ServiceDependency(
            source_service_id=source_id,
            target_service_id=target_id,
            communication_mode=CommunicationMode.ASYNC,
            discovery_source=DiscoverySource.MANUAL,
        )

        result = service.merge_edges(existing_edges, [new_edge])

        assert len(result["upserted"]) == 1
        assert len(result["conflicts"]) == 1

        # Verify new edge won
        winner = result["upserted"][0]
        assert winner.discovery_source == DiscoverySource.MANUAL
        assert winner.communication_mode == CommunicationMode.ASYNC

        # Verify conflict details
        conflict = result["conflicts"][0]
        assert conflict["existing_source"] == "otel_service_graph"
        assert conflict["new_source"] == "manual"
        assert conflict["resolution"] == "kept_higher_priority"

    def test_merge_edges_conflict_existing_wins_over_lower_priority(
        self, service, source_id, target_id
    ):
        """Test conflict resolution: existing MANUAL beats new KUBERNETES."""
        existing_edge = ServiceDependency(
            source_service_id=source_id,
            target_service_id=target_id,
            communication_mode=CommunicationMode.SYNC,
            discovery_source=DiscoverySource.MANUAL,
        )
        existing_edges = {(source_id, target_id): existing_edge}

        # New edge from lower priority source (KUBERNETES)
        new_edge = ServiceDependency(
            source_service_id=source_id,
            target_service_id=target_id,
            communication_mode=CommunicationMode.ASYNC,
            discovery_source=DiscoverySource.KUBERNETES,
        )

        result = service.merge_edges(existing_edges, [new_edge])

        assert len(result["upserted"]) == 1
        assert len(result["conflicts"]) == 1

        # Verify existing edge won
        winner = result["upserted"][0]
        assert winner.discovery_source == DiscoverySource.MANUAL
        assert winner.communication_mode == CommunicationMode.SYNC

        # Verify conflict details
        conflict = result["conflicts"][0]
        assert conflict["existing_source"] == "manual"
        assert conflict["new_source"] == "kubernetes"

    def test_merge_edges_multiple_new_edges(self, service):
        """Test merging multiple new edges at once."""
        # Create 3 pairs of services with edges
        edges = []
        for i in range(3):
            source_id = uuid4()
            target_id = uuid4()
            edges.append(
                ServiceDependency(
                    source_service_id=source_id,
                    target_service_id=target_id,
                    communication_mode=CommunicationMode.SYNC,
                    discovery_source=DiscoverySource.MANUAL,
                )
            )

        result = service.merge_edges({}, edges)

        assert len(result["upserted"]) == 3
        assert len(result["conflicts"]) == 0

    def test_merge_edges_mixed_scenarios(self, service):
        """Test merging with mix of new edges, updates, and conflicts."""
        # Edge 1: Existing OTEL edge
        source1, target1 = uuid4(), uuid4()
        existing1 = ServiceDependency(
            source_service_id=source1,
            target_service_id=target1,
            communication_mode=CommunicationMode.SYNC,
            discovery_source=DiscoverySource.OTEL_SERVICE_GRAPH,
        )

        # Edge 2: Existing MANUAL edge
        source2, target2 = uuid4(), uuid4()
        existing2 = ServiceDependency(
            source_service_id=source2,
            target_service_id=target2,
            communication_mode=CommunicationMode.SYNC,
            discovery_source=DiscoverySource.MANUAL,
        )

        existing_edges = {
            (source1, target1): existing1,
            (source2, target2): existing2,
        }

        # New edge 1: MANUAL (conflicts with existing OTEL, MANUAL wins)
        new1 = ServiceDependency(
            source_service_id=source1,
            target_service_id=target1,
            communication_mode=CommunicationMode.ASYNC,
            discovery_source=DiscoverySource.MANUAL,
        )

        # New edge 2: MANUAL update (same source, update)
        new2 = ServiceDependency(
            source_service_id=source2,
            target_service_id=target2,
            communication_mode=CommunicationMode.ASYNC,
            discovery_source=DiscoverySource.MANUAL,
        )

        # New edge 3: Completely new edge
        source3, target3 = uuid4(), uuid4()
        new3 = ServiceDependency(
            source_service_id=source3,
            target_service_id=target3,
            communication_mode=CommunicationMode.SYNC,
            discovery_source=DiscoverySource.KUBERNETES,
        )

        result = service.merge_edges(existing_edges, [new1, new2, new3])

        assert len(result["upserted"]) == 3
        assert len(result["conflicts"]) == 1  # Only new1 conflicted

    def test_compute_confidence_score_manual_source(self, service):
        """Test confidence score for MANUAL source."""
        score = service.compute_confidence_score(DiscoverySource.MANUAL)
        assert score == 1.0

    def test_compute_confidence_score_service_mesh(self, service):
        """Test confidence score for SERVICE_MESH source."""
        score = service.compute_confidence_score(DiscoverySource.SERVICE_MESH)
        # Allow small floating point tolerance due to observation boost
        assert 0.95 <= score < 0.97

    def test_compute_confidence_score_otel(self, service):
        """Test confidence score for OTEL_SERVICE_GRAPH source."""
        score = service.compute_confidence_score(DiscoverySource.OTEL_SERVICE_GRAPH)
        # Allow small floating point tolerance due to observation boost
        assert 0.85 <= score < 0.87

    def test_compute_confidence_score_kubernetes(self, service):
        """Test confidence score for KUBERNETES source."""
        score = service.compute_confidence_score(DiscoverySource.KUBERNETES)
        # Allow small floating point tolerance due to observation boost
        assert 0.75 <= score < 0.77

    def test_compute_confidence_score_with_observations(self, service):
        """Test confidence score increases with observation count."""
        base_score = service.compute_confidence_score(
            DiscoverySource.OTEL_SERVICE_GRAPH, observation_count=1
        )
        higher_score = service.compute_confidence_score(
            DiscoverySource.OTEL_SERVICE_GRAPH, observation_count=10
        )

        assert higher_score > base_score
        assert higher_score <= 1.0  # Never exceeds 1.0

    def test_compute_confidence_score_observation_boost_capped(self, service):
        """Test that observation boost is capped at 0.1."""
        # Even with many observations, boost shouldn't exceed 0.1
        score = service.compute_confidence_score(
            DiscoverySource.KUBERNETES, observation_count=1000
        )

        # Base is 0.75, max boost is 0.1, so max is 0.85
        assert score <= 0.85
        # But should be close to the cap
        assert score > 0.84

    def test_compute_confidence_score_never_exceeds_one(self, service):
        """Test that confidence score never exceeds 1.0."""
        # Manual starts at 1.0, observation boost shouldn't push it higher
        score = service.compute_confidence_score(
            DiscoverySource.MANUAL, observation_count=100
        )
        assert score == 1.0

    def test_resolve_conflict_preserves_existing_id(self, service, source_id, target_id):
        """Test that conflict resolution preserves the existing edge's ID."""
        existing = ServiceDependency(
            source_service_id=source_id,
            target_service_id=target_id,
            communication_mode=CommunicationMode.SYNC,
            discovery_source=DiscoverySource.OTEL_SERVICE_GRAPH,
        )

        new = ServiceDependency(
            source_service_id=source_id,
            target_service_id=target_id,
            communication_mode=CommunicationMode.ASYNC,
            discovery_source=DiscoverySource.MANUAL,
        )

        winner = service._resolve_conflict(existing, new)

        # New edge won (higher priority), but should have existing ID
        assert winner.discovery_source == DiscoverySource.MANUAL
        assert winner.id == existing.id
        assert winner.created_at == existing.created_at

    def test_merge_edges_refreshes_edges(self, service, source_id, target_id):
        """Test that merged edges are refreshed (not stale)."""
        existing = ServiceDependency(
            source_service_id=source_id,
            target_service_id=target_id,
            communication_mode=CommunicationMode.SYNC,
            discovery_source=DiscoverySource.MANUAL,
        )
        existing.mark_as_stale()
        assert existing.is_stale

        existing_edges = {(source_id, target_id): existing}

        new = ServiceDependency(
            source_service_id=source_id,
            target_service_id=target_id,
            communication_mode=CommunicationMode.SYNC,
            discovery_source=DiscoverySource.MANUAL,
        )

        result = service.merge_edges(existing_edges, [new])

        # Edge should be refreshed
        upserted = result["upserted"][0]
        assert not upserted.is_stale
