"""
Get Agent State tool for Veris Memory MCP Server.

Implements the get_agent_state tool that allows Claude CLI to
retrieve the current state and scratchpad of an agent.
"""

from typing import Any, Dict

from ..client.veris_client import VerisMemoryClient, VerisMemoryClientError
from ..protocol.schemas import Tool
from .base import BaseTool, ToolError, ToolResult


class GetAgentStateTool(BaseTool):
    """
    Tool for retrieving agent state from Veris Memory.

    Allows Claude CLI to get the current scratchpad and state
    information for an agent session.
    """

    name = "get_agent_state"
    description = "Retrieve the current agent state and scratchpad from Veris Memory"

    def __init__(self, veris_client: VerisMemoryClient, config: Dict[str, Any]):
        """
        Initialize get agent state tool.

        Args:
            veris_client: Veris Memory client instance
            config: Tool configuration
        """
        super().__init__(config)
        self.veris_client = veris_client

    def get_schema(self) -> Tool:
        """Get the tool schema definition."""
        return self._create_schema(
            parameters={
                "agent_id": self._create_parameter(
                    "string",
                    "Agent ID to retrieve state for (optional, uses default if not provided)",
                    required=False,
                ),
                "include_scratchpad": self._create_parameter(
                    "boolean",
                    "Whether to include the full scratchpad content (default: true)",
                    required=False,
                ),
            },
            required=[],
        )

    async def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Execute get agent state operation.

        Args:
            arguments: Tool arguments containing agent_id, include_scratchpad, etc.

        Returns:
            Tool result with agent state
        """
        agent_id = arguments.get("agent_id")
        include_scratchpad = arguments.get("include_scratchpad", True)

        try:
            # Get agent state via Veris Memory client
            result = await self.veris_client.get_agent_state(
                agent_id=agent_id,
                include_scratchpad=include_scratchpad,
            )

            state = result.get("state", {})
            scratchpad = result.get("scratchpad")
            last_updated = result.get("last_updated")

            # Format success response
            has_scratchpad = scratchpad is not None and scratchpad != {}
            if has_scratchpad:
                success_message = "Retrieved agent state with scratchpad"
            else:
                success_message = "Retrieved agent state (no scratchpad content)"

            response_data = {
                "agent_id": agent_id,
                "state": state,
                "last_updated": last_updated,
            }

            if include_scratchpad:
                response_data["scratchpad"] = scratchpad

            return ToolResult.success(
                text=success_message,
                data=response_data,
                metadata={
                    "operation": "get_agent_state",
                    "has_scratchpad": has_scratchpad,
                    "success": True,
                },
            )

        except VerisMemoryClientError as e:
            self.logger.error("Veris Memory API error", error=str(e))
            return ToolResult.error(
                f"Failed to get agent state: {e.message}",
                error_code="veris_memory_error",
                details={"original_error": str(e.original_error) if e.original_error else None},
            )

        except ToolError:
            # Re-raise tool errors as-is
            raise

        except Exception as e:
            self.logger.error("Unexpected error getting agent state", error=str(e), exc_info=True)
            raise ToolError(
                f"Unexpected error getting agent state: {str(e)}",
                code="internal_error",
            )
