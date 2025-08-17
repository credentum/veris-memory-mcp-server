"""
MCP Protocol message handlers.

Implements the core logic for handling MCP protocol messages,
routing them to appropriate handlers, and managing the protocol lifecycle.
"""

from typing import Dict, List, Optional, Union

import structlog

from .schemas import (
    MCPCallToolRequest,
    MCPCallToolResponse,
    MCPError,
    MCPInitializeRequest,
    MCPInitializeResponse,
    MCPListToolsRequest,
    MCPListToolsResponse,
    MCPMethodNotFoundError,
    MCPRequest,
    MCPResponse,
    ServerInfo,
    Tool,
)

logger = structlog.get_logger(__name__)


class MCPHandler:
    """
    Main handler for MCP protocol messages.

    Routes incoming requests to appropriate handlers and manages
    the protocol state and capabilities.
    """

    def __init__(self, server_info: Optional[ServerInfo] = None):
        self.server_info = server_info or ServerInfo()
        self._initialized = False
        self._tools: Dict[str, Tool] = {}
        self._tool_executors: Dict[str, callable] = {}

        # Protocol capabilities
        self._capabilities = {
            "tools": {},
            "resources": {},
            "prompts": {},
        }

    def register_tool(self, tool: Tool, executor: callable) -> None:
        """
        Register a tool with its executor function.

        Args:
            tool: Tool definition
            executor: Async function to execute the tool
        """
        self._tools[tool.name] = tool
        self._tool_executors[tool.name] = executor
        logger.info("Registered tool", tool_name=tool.name)

    def unregister_tool(self, tool_name: str) -> None:
        """Unregister a tool."""
        self._tools.pop(tool_name, None)
        self._tool_executors.pop(tool_name, None)
        logger.info("Unregistered tool", tool_name=tool_name)

    async def handle_request(self, request: MCPRequest) -> MCPResponse:
        """
        Handle incoming MCP request.

        Args:
            request: Incoming request

        Returns:
            Response to send back to client
        """
        logger.debug(
            "Handling request",
            method=request.method,
            request_id=request.id,
        )

        try:
            # Route to appropriate handler
            if request.method == "initialize":
                return await self._handle_initialize(request)
            elif request.method == "tools/list":
                return await self._handle_list_tools(request)
            elif request.method == "tools/call":
                return await self._handle_call_tool(request)
            else:
                raise MCPMethodNotFoundError(request.method)

        except MCPError as e:
            logger.warning(
                "MCP error handling request",
                method=request.method,
                request_id=request.id,
                error_code=e.code,
                error_message=e.message,
            )
            return MCPResponse(
                id=request.id,
                error=e.to_dict(),
            )

        except Exception as e:
            logger.error(
                "Unexpected error handling request",
                method=request.method,
                request_id=request.id,
                error=str(e),
                exc_info=True,
            )
            return MCPResponse(
                id=request.id,
                error={
                    "code": -32603,
                    "message": "Internal error",
                    "data": {"details": str(e)},
                },
            )

    async def _handle_initialize(self, request: MCPRequest) -> MCPInitializeResponse:
        """Handle initialize request."""
        try:
            init_request = MCPInitializeRequest(**request.dict())
        except Exception as e:
            raise MCPError(f"Invalid initialize request: {e}", code=-32602)

        logger.info(
            "Initializing MCP session",
            protocol_version=init_request.protocol_version,
            client_info=init_request.client_info,
        )

        # Validate protocol version
        supported_versions = ["2024-11-05", "2025-06-18"]
        if init_request.protocol_version not in supported_versions:
            logger.warning(
                "Unsupported protocol version",
                requested=init_request.protocol_version,
                supported=supported_versions,
            )
            # Continue anyway - be liberal in what we accept

        # Mark as initialized
        self._initialized = True

        # Return initialize response
        return MCPInitializeResponse(
            request_id=request.id,
            protocol_version=init_request.protocol_version,
            server_info=self.server_info,
            capabilities=self._capabilities,
        )

    async def _handle_list_tools(self, request: MCPRequest) -> MCPListToolsResponse:
        """Handle list tools request."""
        if not self._initialized:
            raise MCPError("Session not initialized", code=-32002)

        try:
            # Validate request format
            MCPListToolsRequest(**request.dict())
        except Exception as e:
            raise MCPError(f"Invalid list tools request: {e}", code=-32602)

        logger.info("Listing tools", tool_count=len(self._tools))

        # Return available tools
        tools = list(self._tools.values())
        return MCPListToolsResponse(request.id, tools)

    async def _handle_call_tool(self, request: MCPRequest) -> MCPCallToolResponse:
        """Handle call tool request."""
        if not self._initialized:
            raise MCPError("Session not initialized", code=-32002)

        try:
            call_request = MCPCallToolRequest(**request.dict())
        except Exception as e:
            raise MCPError(f"Invalid call tool request: {e}", code=-32602)

        tool_name = call_request.tool_name
        arguments = call_request.tool_arguments

        logger.info(
            "Calling tool",
            tool_name=tool_name,
            arguments=arguments,
        )

        # Check if tool exists
        if tool_name not in self._tool_executors:
            raise MCPError(f"Unknown tool: {tool_name}", code=-32601)

        # Execute tool
        try:
            executor = self._tool_executors[tool_name]
            logger.error(f"!!!!! EXECUTOR TYPE: {type(executor)} !!!!!")
            logger.error(f"!!!!! EXECUTOR VALUE: {executor} !!!!!")
            logger.error(f"!!!!! CALLING EXECUTOR WITH: {arguments} !!!!!")
            result = await executor(arguments)
            logger.error(f"!!!!! RESULT: {result} !!!!!")
            logger.error(f"!!!!! RESULT TYPE: {type(result)} !!!!!")

            # Import ToolResult to check for it
            from ..tools.base import ToolResult
            
            # Format result for MCP response
            if isinstance(result, ToolResult):
                # Convert ToolResult to dict format
                result_dict = result.to_dict()
                content = result_dict["content"]
                is_error = result_dict.get("isError", False)
            elif isinstance(result, dict) and "content" in result:
                # Already properly formatted as dict
                content = result["content"]
                is_error = result.get("isError", False)
            else:
                # Wrap in content format
                content = [
                    {
                        "type": "text",
                        "text": str(result) if not isinstance(result, str) else result,
                    }
                ]
                is_error = False

            logger.info(
                "Tool execution completed",
                tool_name=tool_name,
                success=not is_error,
            )

            return MCPCallToolResponse(
                request_id=request.id,
                content=content,
                is_error=is_error,
            )

        except Exception as e:
            logger.error(
                "Tool execution failed",
                tool_name=tool_name,
                error=str(e),
                exc_info=True,
            )

            # Return error as tool result
            error_content = [
                {
                    "type": "text",
                    "text": f"Tool execution failed: {str(e)}",
                }
            ]

            return MCPCallToolResponse(
                request_id=request.id,
                content=error_content,
                is_error=True,
            )

    @property
    def initialized(self) -> bool:
        """Check if the handler is initialized."""
        return self._initialized

    @property
    def tools(self) -> List[Tool]:
        """Get list of registered tools."""
        return list(self._tools.values())

    def get_tool(self, name: str) -> Optional[Tool]:
        """Get tool by name."""
        return self._tools.get(name)
