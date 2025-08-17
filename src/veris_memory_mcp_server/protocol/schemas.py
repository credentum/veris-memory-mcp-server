"""
MCP Protocol message schemas and data structures.

Defines the JSON-RPC 2.0 message formats for the Model Context Protocol,
including requests, responses, and error handling.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class MCPError(Exception):
    """Base exception for MCP protocol errors."""

    def __init__(
        self,
        message: str,
        code: int = -32000,
        data: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.data = data or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to JSON-RPC error format."""
        error_dict = {
            "code": self.code,
            "message": self.message,
        }
        if self.data:
            error_dict["data"] = self.data
        return error_dict


class MCPValidationError(MCPError):
    """Error for invalid request parameters."""

    def __init__(self, message: str, data: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=-32602, data=data)


class MCPMethodNotFoundError(MCPError):
    """Error for unknown method calls."""

    def __init__(self, method: str):
        super().__init__(f"Method not found: {method}", code=-32601)


class MCPInternalError(MCPError):
    """Error for internal server issues."""

    def __init__(self, message: str, data: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=-32603, data=data)


# Base message types
class MCPMessage(BaseModel, ABC):
    """Base class for all MCP messages."""

    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")

    class Config:
        extra = "forbid"


class MCPRequest(MCPMessage):
    """Base class for MCP requests."""

    id: Union[str, int] = Field(description="Request ID")
    method: str = Field(description="Method name")
    params: Optional[Dict[str, Any]] = Field(default=None, description="Method parameters")


class MCPResponse(MCPMessage):
    """Base class for MCP responses."""

    id: Union[str, int] = Field(description="Request ID")
    result: Optional[Dict[str, Any]] = Field(default=None, description="Response result")
    error: Optional[Dict[str, Any]] = Field(default=None, description="Error information")

    def dict(self, **kwargs) -> Dict[str, Any]:
        """Override dict to properly handle JSON-RPC 2.0 response format."""
        # Get base dict with exclude_unset=False to keep jsonrpc field
        result = super().dict(exclude_unset=False, **kwargs)
        
        # JSON-RPC 2.0: Response must have either result OR error, never both
        if self.error is not None:
            # Error response - remove result field
            result.pop("result", None)
        else:
            # Success response - remove error field
            result.pop("error", None)
            
        return result


class MCPNotification(MCPMessage):
    """Base class for MCP notifications (no response expected)."""

    method: str = Field(description="Method name")
    params: Optional[Dict[str, Any]] = Field(default=None, description="Method parameters")


# Client info structures
class ClientInfo(BaseModel):
    """Information about the MCP client."""

    name: str = Field(description="Client name")
    version: str = Field(description="Client version")


class ServerInfo(BaseModel):
    """Information about the MCP server."""

    name: str = Field(default="veris-memory-mcp-server", description="Server name")
    version: str = Field(default="0.1.0", description="Server version")


# Tool structures
class ToolParameter(BaseModel):
    """Tool parameter definition."""

    type: str = Field(description="Parameter type")
    description: Optional[str] = Field(default=None, description="Parameter description")
    enum: Optional[List[str]] = Field(default=None, description="Allowed values")
    default: Optional[Any] = Field(default=None, description="Default value")


class ToolSchema(BaseModel):
    """Tool input schema definition."""

    type: str = Field(default="object", description="Schema type")
    properties: Dict[str, ToolParameter] = Field(description="Tool parameters")
    required: List[str] = Field(default_factory=list, description="Required parameters")


class Tool(BaseModel):
    """Tool definition."""

    name: str = Field(description="Tool name")
    description: str = Field(description="Tool description")
    inputSchema: ToolSchema = Field(description="Tool input schema")


# Initialize protocol
class MCPInitializeRequest(MCPRequest):
    """Initialize request from client."""

    method: str = Field(default="initialize", frozen=True)
    params: Dict[str, Any] = Field(description="Initialize parameters")

    @property
    def protocol_version(self) -> str:
        """Get protocol version from params."""
        version = self.params.get("protocolVersion", "2025-06-18")
        return str(version)

    @property
    def client_info(self) -> Optional[ClientInfo]:
        """Get client info from params."""
        client_data = self.params.get("clientInfo")
        return ClientInfo(**client_data) if client_data else None

    @property
    def capabilities(self) -> Dict[str, Any]:
        """Get client capabilities from params."""
        caps = self.params.get("capabilities", {})
        return caps if isinstance(caps, dict) else {}


class MCPInitializeResponse(MCPResponse):
    """Initialize response to client."""

    def __init__(
        self,
        request_id: Union[str, int],
        protocol_version: str = "2025-06-18",
        server_info: Optional[ServerInfo] = None,
        capabilities: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            id=request_id,
            result={
                "protocolVersion": protocol_version,
                "serverInfo": (server_info or ServerInfo()).dict(),
                "capabilities": capabilities
                or {
                    "tools": {},
                    "resources": {},
                    "prompts": {},
                },
            },
        )


# List tools
class MCPListToolsRequest(MCPRequest):
    """List tools request from client."""

    method: str = Field(default="tools/list", frozen=True)


class MCPListToolsResponse(MCPResponse):
    """List tools response to client."""

    def __init__(self, request_id: Union[str, int], tools: List[Tool]):
        super().__init__(
            id=request_id,
            result={"tools": [tool.dict() for tool in tools]},
        )


# Call tool
class MCPCallToolRequest(MCPRequest):
    """Call tool request from client."""

    method: str = Field(default="tools/call", frozen=True)

    @property
    def tool_name(self) -> str:
        """Get tool name from params."""
        name = self.params.get("name", "")
        return str(name) if name is not None else ""

    @property
    def tool_arguments(self) -> Dict[str, Any]:
        """Get tool arguments from params."""
        args = self.params.get("arguments", {})
        return args if isinstance(args, dict) else {}


class ToolResult(BaseModel):
    """Result of tool execution."""

    content: List[Dict[str, Any]] = Field(description="Tool result content")
    isError: bool = Field(default=False, description="Whether result is an error")


class MCPCallToolResponse(MCPResponse):
    """Call tool response to client."""

    def __init__(
        self,
        request_id: Union[str, int],
        content: List[Dict[str, Any]],
        is_error: bool = False,
    ):
        super().__init__(
            id=request_id,
            result={
                "content": content,
                "isError": is_error,
            },
        )


# Logging notification
class MCPLogNotification(MCPNotification):
    """Log notification to client."""

    method: str = Field(default="notifications/log", frozen=True)

    def __init__(self, level: str, message: str, data: Optional[Dict[str, Any]] = None):
        super().__init__(
            method="notifications/log",
            params={
                "level": level,
                "message": message,
                "data": data or {},
            },
        )


# Progress notification
class MCPProgressNotification(MCPNotification):
    """Progress notification to client."""

    method: str = Field(default="notifications/progress", frozen=True)

    def __init__(
        self,
        progress_token: Union[str, int],
        progress: int,
        total: Optional[int] = None,
    ):
        super().__init__(
            params={
                "progressToken": progress_token,
                "progress": progress,
                "total": total,
            }
        )
