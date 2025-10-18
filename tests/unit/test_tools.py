"""
Unit tests for MCP tools.
"""

import pytest

from veris_memory_mcp_server.tools.base import ToolError
from veris_memory_mcp_server.tools.retrieve_context import RetrieveContextTool
from veris_memory_mcp_server.tools.store_context import StoreContextTool


class TestStoreContextTool:
    """Test store context tool."""

    @pytest.fixture
    def store_tool(self, mock_veris_client):
        """Create store context tool instance."""
        config = {
            "max_content_size": 1000,
            "allowed_context_types": ["*"],
        }
        return StoreContextTool(mock_veris_client, config)

    def test_get_schema(self, store_tool):
        """Test schema generation."""
        schema = store_tool.get_schema()
        assert schema.name == "store_context"
        assert "context_type" in schema.inputSchema.properties
        assert "content" in schema.inputSchema.properties
        assert "context_type" in schema.inputSchema.required
        assert "content" in schema.inputSchema.required

    @pytest.mark.asyncio
    async def test_execute_success(self, store_tool, mock_veris_client):
        """Test successful context storage."""
        arguments = {
            "context_type": "decision",
            "content": {"text": "Test decision", "details": "Some details"},
            "metadata": {"project": "test"},
        }

        result = await store_tool.execute(arguments)

        assert not result.is_error
        assert "Successfully stored decision context" in result.content[0]["text"]

        # Verify client was called correctly
        mock_veris_client.store_context.assert_called_once_with(
            context_type="decision",
            content={"text": "Test decision", "details": "Some details"},
            metadata={"project": "test"},
        )

    @pytest.mark.asyncio
    async def test_execute_empty_content(self, store_tool):
        """Test handling of empty content."""
        arguments = {
            "context_type": "decision",
            "content": {},
        }

        with pytest.raises(ToolError) as exc_info:
            await store_tool.execute(arguments)

        assert exc_info.value.code == "empty_content"

    @pytest.mark.asyncio
    async def test_execute_content_too_large(self, store_tool):
        """Test handling of oversized content."""
        large_content = {"text": "x" * 2000}  # Exceeds 1000 byte limit
        arguments = {
            "context_type": "decision",
            "content": large_content,
        }

        with pytest.raises(ToolError) as exc_info:
            await store_tool.execute(arguments)

        assert exc_info.value.code == "content_too_large"


class TestRetrieveContextTool:
    """Test retrieve context tool."""

    @pytest.fixture
    def retrieve_tool(self, mock_veris_client):
        """Create retrieve context tool instance."""
        config = {
            "max_results": 50,
            "default_limit": 5,
        }
        return RetrieveContextTool(mock_veris_client, config)

    def test_get_schema(self, retrieve_tool):
        """Test schema generation."""
        schema = retrieve_tool.get_schema()
        assert schema.name == "retrieve_context"
        assert "query" in schema.inputSchema.properties
        assert "limit" in schema.inputSchema.properties
        assert "query" in schema.inputSchema.required

    @pytest.mark.asyncio
    async def test_execute_success(self, retrieve_tool, mock_veris_client):
        """Test successful context retrieval."""
        arguments = {
            "query": "test decision",
            "limit": 5,
        }

        result = await retrieve_tool.execute(arguments)

        assert not result.is_error
        assert "Found 1 context" in result.content[0]["text"]

        # Verify client was called correctly
        mock_veris_client.retrieve_context.assert_called_once_with(
            query="test decision",
            limit=5,
            context_type=None,
            metadata_filters=None,
        )

    @pytest.mark.asyncio
    async def test_execute_empty_query(self, retrieve_tool):
        """Test handling of empty query."""
        arguments = {
            "query": "",
        }

        with pytest.raises(ToolError) as exc_info:
            await retrieve_tool.execute(arguments)

        assert exc_info.value.code == "empty_query"

    @pytest.mark.asyncio
    async def test_execute_invalid_limit(self, retrieve_tool):
        """Test handling of invalid limit."""
        arguments = {
            "query": "test",
            "limit": 100,  # Exceeds max_results of 50
        }

        with pytest.raises(ToolError) as exc_info:
            await retrieve_tool.execute(arguments)

        assert exc_info.value.code == "invalid_limit"
