"""
Update Scratchpad tool for Veris Memory MCP Server.

Implements the update_scratchpad tool that allows Claude CLI to
maintain temporary working memory for ongoing tasks.
"""

from typing import Any, Dict

from ..client.veris_client import VerisMemoryClient, VerisMemoryClientError
from ..protocol.schemas import Tool
from .base import BaseTool, ToolError, ToolResult


class UpdateScratchpadTool(BaseTool):
    """
    Tool for updating the agent scratchpad in Veris Memory.

    Allows Claude CLI to maintain temporary working memory
    for ongoing tasks and intermediate results.
    """

    name = "update_scratchpad"
    description = "Update the agent's temporary scratchpad memory in Veris Memory"

    def __init__(self, veris_client: VerisMemoryClient, config: Dict[str, Any]):
        """
        Initialize update scratchpad tool.

        Args:
            veris_client: Veris Memory client instance
            config: Tool configuration
        """
        super().__init__(config)
        self.veris_client = veris_client
        self.max_content_size = config.get("max_content_size", 65536)  # 64KB default

    def get_schema(self) -> Tool:
        """Get the tool schema definition."""
        return self._create_schema(
            parameters={
                "content": self._create_parameter(
                    "object",
                    "Content to store in the scratchpad (replaces existing content)",
                    required=True,
                ),
                "agent_id": self._create_parameter(
                    "string",
                    "Agent ID for the scratchpad (optional, uses default if not provided)",
                    required=False,
                ),
                "merge": self._create_parameter(
                    "boolean",
                    "Whether to merge with existing content or replace (default: false)",
                    required=False,
                ),
            },
            required=["content"],
        )

    async def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Execute update scratchpad operation.

        Args:
            arguments: Tool arguments containing content, agent_id, etc.

        Returns:
            Tool result with confirmation of update
        """
        content = arguments["content"]
        agent_id = arguments.get("agent_id")
        merge = arguments.get("merge", False)

        try:
            # Validate content
            if content is None:
                raise ToolError(
                    "Content cannot be null",
                    code="invalid_content",
                )

            # Check content size
            content_str = str(content)
            if len(content_str.encode("utf-8")) > self.max_content_size:
                raise ToolError(
                    f"Content size exceeds maximum of {self.max_content_size} bytes",
                    code="content_too_large",
                    details={"max_size": self.max_content_size},
                )

            # Update scratchpad via Veris Memory client
            result = await self.veris_client.update_scratchpad(
                content=content,
                agent_id=agent_id,
                merge=merge,
            )

            updated_at = result.get("updated_at")
            scratchpad_id = result.get("scratchpad_id")

            # Format success response
            action = "Merged into" if merge else "Updated"
            success_message = f"{action} scratchpad"
            if scratchpad_id:
                success_message += f" ({scratchpad_id})"

            return ToolResult.success(
                text=success_message,
                data={
                    "scratchpad_id": scratchpad_id,
                    "updated_at": updated_at,
                    "agent_id": agent_id,
                    "merge": merge,
                },
                metadata={
                    "operation": "update_scratchpad",
                    "merge": merge,
                    "success": True,
                },
            )

        except VerisMemoryClientError as e:
            self.logger.error("Veris Memory API error", error=str(e))
            return ToolResult.error(
                f"Failed to update scratchpad: {e.message}",
                error_code="veris_memory_error",
                details={"original_error": str(e.original_error) if e.original_error else None},
            )

        except ToolError:
            # Re-raise tool errors as-is
            raise

        except Exception as e:
            self.logger.error("Unexpected error updating scratchpad", error=str(e), exc_info=True)
            raise ToolError(
                f"Unexpected error updating scratchpad: {str(e)}",
                code="internal_error",
            )
