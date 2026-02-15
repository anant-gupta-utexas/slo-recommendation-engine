"""Circular dependency detector module.

This module implements Tarjan's algorithm for finding strongly connected components
to detect circular dependencies in the service dependency graph.
"""

from uuid import UUID


class CircularDependencyDetector:
    """Implements Tarjan's algorithm for finding strongly connected components.

    Time Complexity: O(V + E) where V = services, E = edges
    Space Complexity: O(V)
    """

    def __init__(self):
        """Initialize the detector state."""
        self.index_counter = 0
        self.stack: list[UUID] = []
        self.lowlinks: dict[UUID, int] = {}
        self.index: dict[UUID, int] = {}
        self.on_stack: set[UUID] = set()
        self.sccs: list[list[UUID]] = []

    async def detect_cycles(
        self, adjacency_list: dict[UUID, list[UUID]]
    ) -> list[list[UUID]]:
        """Detect all strongly connected components (cycles) in the graph.

        Args:
            adjacency_list: Map of service_id → list of target service_ids

        Returns:
            List of cycles, where each cycle is a list of service UUIDs.
            Only returns SCCs with size > 1 (actual cycles, not single nodes)
        """
        for node in adjacency_list.keys():
            if node not in self.index:
                await self._strongconnect(node, adjacency_list)

        # Filter out trivial SCCs (single nodes)
        cycles = [scc for scc in self.sccs if len(scc) > 1]
        return cycles

    async def _strongconnect(
        self, node: UUID, adjacency_list: dict[UUID, list[UUID]]
    ):
        """Recursive helper for Tarjan's algorithm.

        Args:
            node: Current node being processed
            adjacency_list: Complete graph as adjacency list
        """
        # Set the depth index for node to the smallest unused index
        self.index[node] = self.index_counter
        self.lowlinks[node] = self.index_counter
        self.index_counter += 1
        self.stack.append(node)
        self.on_stack.add(node)

        # Consider successors of node
        for successor in adjacency_list.get(node, []):
            if successor not in self.index:
                # Successor has not yet been visited; recurse on it
                await self._strongconnect(successor, adjacency_list)
                self.lowlinks[node] = min(
                    self.lowlinks[node], self.lowlinks[successor]
                )
            elif successor in self.on_stack:
                # Successor is in stack and hence in the current SCC
                self.lowlinks[node] = min(self.lowlinks[node], self.index[successor])

        # If node is a root node, pop the stack and generate an SCC
        if self.lowlinks[node] == self.index[node]:
            scc = []
            while True:
                w = self.stack.pop()
                self.on_stack.remove(w)
                scc.append(w)
                if w == node:
                    break
            self.sccs.append(scc)
