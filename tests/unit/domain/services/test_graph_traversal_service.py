"""Unit tests for GraphTraversalService."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from src.domain.services.graph_traversal_service import (
    GraphTraversalService,
    TraversalDirection,
)
from src.domain.entities.service import Service
from src.domain.entities.service_dependency import (
    ServiceDependency,
    CommunicationMode,
)


class TestTraversalDirection:
    """Test cases for TraversalDirection enum."""

    def test_traversal_direction_values(self):
        """Test that all expected traversal directions exist."""
        assert TraversalDirection.UPSTREAM.value == "upstream"
        assert TraversalDirection.DOWNSTREAM.value == "downstream"
        assert TraversalDirection.BOTH.value == "both"


class TestGraphTraversalService:
    """Test cases for GraphTraversalService."""

    @pytest.fixture
    def service(self):
        """Fixture for creating GraphTraversalService instance."""
        return GraphTraversalService()

    @pytest.fixture
    def mock_repository(self):
        """Fixture for mock repository."""
        repo = MagicMock()
        repo.traverse_graph = AsyncMock()
        return repo

    @pytest.fixture
    def service_id(self):
        """Fixture for service UUID."""
        return uuid4()

    @pytest.mark.asyncio
    async def test_get_subgraph_with_valid_params(
        self, service, mock_repository, service_id
    ):
        """Test get_subgraph with valid parameters."""
        # Setup mock response
        expected_nodes = [Service(service_id="test-service")]
        expected_edges = [
            ServiceDependency(
                source_service_id=service_id,
                target_service_id=uuid4(),
                communication_mode=CommunicationMode.SYNC,
            )
        ]
        mock_repository.traverse_graph.return_value = (expected_nodes, expected_edges)

        # Call method
        nodes, edges = await service.get_subgraph(
            service_id=service_id,
            direction=TraversalDirection.DOWNSTREAM,
            repository=mock_repository,
            max_depth=3,
            include_stale=False,
        )

        # Verify repository was called correctly
        mock_repository.traverse_graph.assert_called_once_with(
            service_id=service_id,
            direction=TraversalDirection.DOWNSTREAM,
            max_depth=3,
            include_stale=False,
        )

        # Verify results
        assert nodes == expected_nodes
        assert edges == expected_edges

    @pytest.mark.asyncio
    async def test_get_subgraph_max_depth_exceeds_limit_raises(
        self, service, mock_repository, service_id
    ):
        """Test that max_depth > 10 raises ValueError."""
        with pytest.raises(ValueError, match="max_depth cannot exceed 10"):
            await service.get_subgraph(
                service_id=service_id,
                direction=TraversalDirection.DOWNSTREAM,
                repository=mock_repository,
                max_depth=11,
            )

        # Repository should not be called
        mock_repository.traverse_graph.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_subgraph_max_depth_too_low_raises(
        self, service, mock_repository, service_id
    ):
        """Test that max_depth < 1 raises ValueError."""
        with pytest.raises(ValueError, match="max_depth must be at least 1"):
            await service.get_subgraph(
                service_id=service_id,
                direction=TraversalDirection.DOWNSTREAM,
                repository=mock_repository,
                max_depth=0,
            )

        # Repository should not be called
        mock_repository.traverse_graph.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_subgraph_with_max_depth_1(
        self, service, mock_repository, service_id
    ):
        """Test get_subgraph with minimum depth of 1."""
        mock_repository.traverse_graph.return_value = ([], [])

        await service.get_subgraph(
            service_id=service_id,
            direction=TraversalDirection.DOWNSTREAM,
            repository=mock_repository,
            max_depth=1,
        )

        mock_repository.traverse_graph.assert_called_once()
        call_kwargs = mock_repository.traverse_graph.call_args.kwargs
        assert call_kwargs["max_depth"] == 1

    @pytest.mark.asyncio
    async def test_get_subgraph_with_max_depth_10(
        self, service, mock_repository, service_id
    ):
        """Test get_subgraph with maximum allowed depth of 10."""
        mock_repository.traverse_graph.return_value = ([], [])

        await service.get_subgraph(
            service_id=service_id,
            direction=TraversalDirection.DOWNSTREAM,
            repository=mock_repository,
            max_depth=10,
        )

        mock_repository.traverse_graph.assert_called_once()
        call_kwargs = mock_repository.traverse_graph.call_args.kwargs
        assert call_kwargs["max_depth"] == 10

    @pytest.mark.asyncio
    async def test_get_subgraph_with_default_depth(
        self, service, mock_repository, service_id
    ):
        """Test get_subgraph uses default depth of 3."""
        mock_repository.traverse_graph.return_value = ([], [])

        await service.get_subgraph(
            service_id=service_id,
            direction=TraversalDirection.DOWNSTREAM,
            repository=mock_repository,
        )

        call_kwargs = mock_repository.traverse_graph.call_args.kwargs
        assert call_kwargs["max_depth"] == 3

    @pytest.mark.asyncio
    async def test_get_subgraph_with_include_stale_true(
        self, service, mock_repository, service_id
    ):
        """Test get_subgraph with include_stale=True."""
        mock_repository.traverse_graph.return_value = ([], [])

        await service.get_subgraph(
            service_id=service_id,
            direction=TraversalDirection.DOWNSTREAM,
            repository=mock_repository,
            include_stale=True,
        )

        call_kwargs = mock_repository.traverse_graph.call_args.kwargs
        assert call_kwargs["include_stale"] is True

    @pytest.mark.asyncio
    async def test_get_subgraph_with_include_stale_false(
        self, service, mock_repository, service_id
    ):
        """Test get_subgraph with include_stale=False (default)."""
        mock_repository.traverse_graph.return_value = ([], [])

        await service.get_subgraph(
            service_id=service_id,
            direction=TraversalDirection.DOWNSTREAM,
            repository=mock_repository,
        )

        call_kwargs = mock_repository.traverse_graph.call_args.kwargs
        assert call_kwargs["include_stale"] is False

    @pytest.mark.asyncio
    async def test_get_subgraph_with_all_directions(
        self, service, mock_repository, service_id
    ):
        """Test get_subgraph with all traversal directions."""
        mock_repository.traverse_graph.return_value = ([], [])

        for direction in TraversalDirection:
            mock_repository.traverse_graph.reset_mock()

            await service.get_subgraph(
                service_id=service_id,
                direction=direction,
                repository=mock_repository,
            )

            call_kwargs = mock_repository.traverse_graph.call_args.kwargs
            assert call_kwargs["direction"] == direction

    @pytest.mark.asyncio
    async def test_get_subgraph_delegates_to_repository(
        self, service, mock_repository, service_id
    ):
        """Test that get_subgraph properly delegates to repository."""
        expected_result = ([Service(service_id="test")], [])
        mock_repository.traverse_graph.return_value = expected_result

        result = await service.get_subgraph(
            service_id=service_id,
            direction=TraversalDirection.BOTH,
            repository=mock_repository,
            max_depth=5,
            include_stale=True,
        )

        # Verify exact delegation
        assert result == expected_result
        mock_repository.traverse_graph.assert_called_once_with(
            service_id=service_id,
            direction=TraversalDirection.BOTH,
            max_depth=5,
            include_stale=True,
        )
