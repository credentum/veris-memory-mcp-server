"""
MCP Protocol implementation for Veris Memory MCP Server.

This module provides the core Model Context Protocol implementation,
including message handling, transport, and schema definitions.
"""

from .handlers import MCPHandler
from .schemas import (
    MCPCallToolRequest,
    MCPCallToolResponse,
    MCPError,
    MCPInitializeRequest,
    MCPInitializeResponse,
    MCPListToolsRequest,
    MCPListToolsResponse,
    MCPRequest,
    MCPResponse,
)
from .transport import StdioTransport

__all__ = [
    "MCPHandler",
    "StdioTransport",
    "MCPError",
    "MCPInitializeRequest",
    "MCPInitializeResponse",
    "MCPListToolsRequest",
    "MCPListToolsResponse",
    "MCPCallToolRequest",
    "MCPCallToolResponse",
    "MCPRequest",
    "MCPResponse",
]
