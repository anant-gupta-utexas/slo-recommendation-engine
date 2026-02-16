"""Circular dependency detector module.

This module implements Tarjan's algorithm for finding strongly connected components
to detect circular dependencies in the service dependency graph.
"""

from uuid import UUID


class CircularDependencyDetector:
    """Implements Tarjan's algorithm for finding strongly connected components.

    Time Complexity: O(V + E) where V = services, E = edges
    Space Complexity: O(V)

    The detector is reusable: each call to detect_cycles() resets internal state.
    Uses an iterative implementation to avoid Python's recursion limit.
    """

    def __init__(self) -> None:
        """Initialize the detector."""
        pass

    def detect_cycles(
        self, adjacency_list: dict[UUID, list[UUID]]
    ) -> list[list[UUID]]:
        """Detect all strongly connected components (cycles) in the graph.

        Args:
            adjacency_list: Map of service_id -> list of target service_ids

        Returns:
            List of cycles, where each cycle is a list of service UUIDs.
            Only returns SCCs with size > 1 (actual cycles, not single nodes)
        """
        # Reset all state for each invocation (makes detector reusable)
        index_counter = 0
        stack: list[UUID] = []
        lowlinks: dict[UUID, int] = {}
        index: dict[UUID, int] = {}
        on_stack: set[UUID] = set()
        sccs: list[list[UUID]] = []

        # Iterative Tarjan's algorithm using an explicit call stack
        # Each frame is (node, successor_index, is_root_call)
        for start_node in adjacency_list.keys():
            if start_node in index:
                continue

            # Explicit call stack: each entry is (node, successor_iterator_index)
            call_stack: list[tuple[UUID, int]] = [(start_node, 0)]

            while call_stack:
                node, si = call_stack[-1]

                if si == 0 and node not in index:
                    # First visit: initialize this node
                    index[node] = index_counter
                    lowlinks[node] = index_counter
                    index_counter += 1
                    stack.append(node)
                    on_stack.add(node)

                successors = adjacency_list.get(node, [])

                if si < len(successors):
                    # Process next successor
                    call_stack[-1] = (node, si + 1)
                    successor = successors[si]

                    if successor not in index:
                        # Successor not yet visited: push it onto call stack
                        call_stack.append((successor, 0))
                    elif successor in on_stack:
                        # Successor is on stack: update lowlink
                        lowlinks[node] = min(lowlinks[node], index[successor])
                else:
                    # All successors processed: check if this is an SCC root
                    call_stack.pop()

                    if lowlinks[node] == index[node]:
                        # Node is root of an SCC: pop stack to get SCC members
                        scc: list[UUID] = []
                        while True:
                            w = stack.pop()
                            on_stack.remove(w)
                            scc.append(w)
                            if w == node:
                                break
                        sccs.append(scc)

                    # Update parent's lowlink
                    if call_stack:
                        parent = call_stack[-1][0]
                        lowlinks[parent] = min(lowlinks[parent], lowlinks[node])

        # Filter out trivial SCCs (single nodes)
        cycles = [scc for scc in sccs if len(scc) > 1]
        return cycles
