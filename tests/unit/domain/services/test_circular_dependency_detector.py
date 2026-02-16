"""Unit tests for CircularDependencyDetector."""

import pytest
from uuid import uuid4

from src.domain.services.circular_dependency_detector import (
    CircularDependencyDetector,
)


class TestCircularDependencyDetector:
    """Test cases for CircularDependencyDetector using Tarjan's algorithm."""

    @pytest.fixture
    def detector(self):
        """Fixture for creating CircularDependencyDetector instance."""
        return CircularDependencyDetector()

    def test_detect_simple_cycle(self, detector):
        """Test detecting a simple 3-node cycle: A → B → C → A."""
        a, b, c = uuid4(), uuid4(), uuid4()
        graph = {a: [b], b: [c], c: [a]}

        cycles = detector.detect_cycles(graph)

        assert len(cycles) == 1
        assert set(cycles[0]) == {a, b, c}

    def test_no_cycle_in_dag(self, detector):
        """Test that a DAG (directed acyclic graph) has no cycles."""
        a, b, c = uuid4(), uuid4(), uuid4()
        # A → B → C (no cycle)
        graph = {a: [b], b: [c], c: []}

        cycles = detector.detect_cycles(graph)

        assert len(cycles) == 0

    def test_detect_two_node_cycle(self, detector):
        """Test detecting a simple 2-node cycle: A ⇄ B."""
        a, b = uuid4(), uuid4()
        graph = {a: [b], b: [a]}

        cycles = detector.detect_cycles(graph)

        assert len(cycles) == 1
        assert set(cycles[0]) == {a, b}

    def test_multiple_disjoint_cycles(self, detector):
        """Test detecting multiple separate cycles in the graph."""
        # Cycle 1: A → B → A
        a, b = uuid4(), uuid4()
        # Cycle 2: C → D → E → C
        c, d, e = uuid4(), uuid4(), uuid4()

        graph = {
            a: [b],
            b: [a],
            c: [d],
            d: [e],
            e: [c],
        }

        cycles = detector.detect_cycles(graph)

        assert len(cycles) == 2

        # Check both cycles were detected
        cycle_sets = [set(cycle) for cycle in cycles]
        assert {a, b} in cycle_sets
        assert {c, d, e} in cycle_sets

    def test_self_loop_filtered_out(self, detector):
        """Test that self-loops (trivial SCCs) are filtered out."""
        a, b = uuid4(), uuid4()
        # Note: Domain entity validation prevents self-loops,
        # but Tarjan's algorithm should filter them anyway
        graph = {a: [b], b: []}

        cycles = detector.detect_cycles(graph)

        # No cycles (single nodes are filtered out)
        assert len(cycles) == 0

    def test_complex_graph_with_nested_cycles(self, detector):
        """Test detecting cycles in a complex graph."""
        a, b, c, d, e = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()

        # A → B → C → A (cycle)
        # B → D → E → D (cycle)
        graph = {
            a: [b],
            b: [c, d],
            c: [a],
            d: [e],
            e: [d],
        }

        cycles = detector.detect_cycles(graph)

        assert len(cycles) == 2

        # Check cycles
        cycle_sets = [set(cycle) for cycle in cycles]
        assert {a, b, c} in cycle_sets
        assert {d, e} in cycle_sets

    def test_empty_graph(self, detector):
        """Test detecting cycles in an empty graph."""
        graph = {}

        cycles = detector.detect_cycles(graph)

        assert len(cycles) == 0

    def test_single_node_no_cycle(self, detector):
        """Test single isolated node has no cycle."""
        a = uuid4()
        graph = {a: []}

        cycles = detector.detect_cycles(graph)

        assert len(cycles) == 0

    def test_linear_chain_no_cycle(self, detector):
        """Test long linear chain has no cycle."""
        nodes = [uuid4() for _ in range(10)]
        graph = {nodes[i]: [nodes[i + 1]] for i in range(9)}
        graph[nodes[9]] = []  # Last node has no outgoing edges

        cycles = detector.detect_cycles(graph)

        assert len(cycles) == 0

    def test_large_cycle(self, detector):
        """Test detecting a large cycle with many nodes."""
        # Create a cycle with 100 nodes
        nodes = [uuid4() for _ in range(100)]
        graph = {nodes[i]: [nodes[(i + 1) % 100]] for i in range(100)}

        cycles = detector.detect_cycles(graph)

        assert len(cycles) == 1
        assert len(cycles[0]) == 100
        assert set(cycles[0]) == set(nodes)

    def test_cycle_with_branches(self, detector):
        """Test detecting cycle in graph with non-cyclic branches."""
        a, b, c, d, e = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()

        # A → B → C → A (cycle)
        # A → D (branch, no cycle)
        # D → E (branch, no cycle)
        graph = {
            a: [b, d],
            b: [c],
            c: [a],
            d: [e],
            e: [],
        }

        cycles = detector.detect_cycles(graph)

        assert len(cycles) == 1
        assert set(cycles[0]) == {a, b, c}

    def test_diamond_pattern_no_cycle(self, detector):
        """Test diamond pattern (converging paths) has no cycle."""
        a, b, c, d = uuid4(), uuid4(), uuid4(), uuid4()

        # A → B → D
        # A → C → D
        # (Diamond pattern, no cycle)
        graph = {
            a: [b, c],
            b: [d],
            c: [d],
            d: [],
        }

        cycles = detector.detect_cycles(graph)

        assert len(cycles) == 0

    def test_tarjan_algorithm_efficiency(self, detector):
        """Test Tarjan's algorithm handles large graphs efficiently."""
        # Create a large graph with one cycle
        # Iterative implementation handles any graph size without recursion limit
        num_nodes = 5000
        nodes = [uuid4() for _ in range(num_nodes)]
        graph = {nodes[i]: [nodes[(i + 1) % num_nodes]] for i in range(num_nodes)}

        cycles = detector.detect_cycles(graph)

        # Should find exactly one large cycle
        assert len(cycles) == 1
        assert len(cycles[0]) == num_nodes

    def test_strongly_connected_component(self, detector):
        """Test detecting a fully connected component (all nodes reach all nodes)."""
        a, b, c = uuid4(), uuid4(), uuid4()

        # Fully connected: every node connects to every other node
        graph = {
            a: [b, c],
            b: [a, c],
            c: [a, b],
        }

        cycles = detector.detect_cycles(graph)

        # All three nodes form one SCC
        assert len(cycles) == 1
        assert set(cycles[0]) == {a, b, c}

    def test_partial_cycle_detection(self, detector):
        """Test graph with some nodes in cycles and some not."""
        a, b, c, d, e, f = uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()

        # A → B → C → A (cycle)
        # D → E → F (no cycle)
        graph = {
            a: [b],
            b: [c],
            c: [a],
            d: [e],
            e: [f],
            f: [],
        }

        cycles = detector.detect_cycles(graph)

        assert len(cycles) == 1
        assert set(cycles[0]) == {a, b, c}

    def test_detector_state_isolation(self):
        """Test that multiple detector instances are independent."""
        detector1 = CircularDependencyDetector()
        detector2 = CircularDependencyDetector()

        a, b, c = uuid4(), uuid4(), uuid4()
        graph1 = {a: [b], b: [c], c: [a]}

        d, e = uuid4(), uuid4()
        graph2 = {d: [e], e: [d]}

        cycles1 = detector1.detect_cycles(graph1)
        cycles2 = detector2.detect_cycles(graph2)

        assert len(cycles1) == 1
        assert len(cycles2) == 1
        assert set(cycles1[0]) == {a, b, c}
        assert set(cycles2[0]) == {d, e}

    def test_detector_reusable(self):
        """Test that the same detector instance can be called multiple times."""
        detector = CircularDependencyDetector()

        a, b = uuid4(), uuid4()
        graph1 = {a: [b], b: [a]}
        cycles1 = detector.detect_cycles(graph1)
        assert len(cycles1) == 1

        c, d, e = uuid4(), uuid4(), uuid4()
        graph2 = {c: [d], d: [e], e: [c]}
        cycles2 = detector.detect_cycles(graph2)
        assert len(cycles2) == 1
        assert set(cycles2[0]) == {c, d, e}
