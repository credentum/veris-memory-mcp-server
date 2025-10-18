"""
Unit tests for MCP protocol implementation.
"""

import pytest
from unittest.mock import AsyncMock

from veris_memory_mcp_server.protocol.handlers import MCPHandler
from veris_memory_mcp_server.protocol.schemas import (
    MCPInitializeRequest,
    MCPListToolsRequest,
    MCPCallToolRequest,
    Tool,
    ToolSchema,
    ToolParameter,
)


class TestMCPHandler:
    """Test MCP protocol handler."""

    @pytest.fixture
    def handler(self):
        """Create MCP handler instance."""
        return MCPHandler()

    @pytest.fixture
    def sample_tool(self):
        """Create a sample tool for testing."""
        return Tool(
            name="test_tool",
            description="A test tool",
            inputSchema=ToolSchema(
                type="object",
                properties={"message": ToolParameter(type="string", description="Test message")},
                required=["message"],
            ),
        )

    @pytest.mark.asyncio
    async def test_handle_initialize(self, handler):
        """Test initialize request handling."""
        request = MCPInitializeRequest(
            id="test-1",
            params={
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "test-client", "version": "1.0.0"},
                "capabilities": {},
            },
        )

        response = await handler.handle_request(request)

        assert response.id == "test-1"
        assert response.result is not None
        assert response.result["protocolVersion"] == "2024-11-05"
        assert response.result["serverInfo"]["name"] == "veris-memory-mcp-server"
        assert handler.initialized

    @pytest.mark.asyncio
    async def test_handle_list_tools_before_init(self, handler):
        """Test list tools before initialization."""
        request = MCPListToolsRequest(id="test-1")

        response = await handler.handle_request(request)

        assert response.error is not None
        assert response.error["code"] == -32002  # Not initialized

    @pytest.mark.asyncio
    async def test_handle_list_tools_after_init(self, handler, sample_tool):
        """Test list tools after initialization."""
        # Initialize first
        init_request = MCPInitializeRequest(
            id="init-1",
            params={
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "test", "version": "1.0"},
                "capabilities": {},
            },
        )
        await handler.handle_request(init_request)

        # Register a tool
        mock_executor = AsyncMock(return_value={"content": [{"type": "text", "text": "Success"}]})
        handler.register_tool(sample_tool, mock_executor)

        # List tools
        request = MCPListToolsRequest(id="test-1")
        response = await handler.handle_request(request)

        assert response.result is not None
        assert len(response.result["tools"]) == 1
        assert response.result["tools"][0]["name"] == "test_tool"

    @pytest.mark.asyncio
    async def test_handle_call_tool(self, handler, sample_tool):
        """Test tool call handling."""
        # Initialize
        init_request = MCPInitializeRequest(
            id="init-1",
            params={
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "test", "version": "1.0"},
                "capabilities": {},
            },
        )
        await handler.handle_request(init_request)

        # Register tool with mock executor
        mock_executor = AsyncMock(
            return_value={"content": [{"type": "text", "text": "Tool executed"}]}
        )
        handler.register_tool(sample_tool, mock_executor)

        # Call tool
        request = MCPCallToolRequest(
            id="test-1",
            params={
                "name": "test_tool",
                "arguments": {"message": "hello"},
            },
        )

        response = await handler.handle_request(request)

        assert response.result is not None
        assert response.result["content"][0]["text"] == "Tool executed"
        assert not response.result["isError"]

        # Verify executor was called with correct arguments
        mock_executor.assert_called_once_with({"message": "hello"})

    @pytest.mark.asyncio
    async def test_handle_unknown_method(self, handler):
        """Test handling of unknown method."""
        from veris_memory_mcp_server.protocol.schemas import MCPRequest

        request = MCPRequest(
            id="test-1",
            method="unknown_method",
            params={},
        )

        response = await handler.handle_request(request)

        assert response.error is not None
        assert response.error["code"] == -32601  # Method not found
        assert "unknown_method" in response.error["message"]
