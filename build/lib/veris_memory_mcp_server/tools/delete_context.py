"""
Delete Context tool for Veris Memory MCP Server.

Implements context deletion with proper authorization checks.
"""

from typing import Any, Dict

from ..client.veris_client import VerisMemoryClient, VerisMemoryClientError
from ..protocol.schemas import Tool
from .base import BaseTool, ToolError, ToolResult


class DeleteContextTool(BaseTool):
    """Tool for deleting contexts with authorization."""

    name = "delete_context"
    description = "Delete a context from Veris Memory (requires authorization)"

    def __init__(self, veris_client: VerisMemoryClient, config: Dict[str, Any]):
        super().__init__(config)
        self.veris_client = veris_client

    def get_schema(self) -> Tool:
        return self._create_schema(
            parameters={
                "context_id": self._create_parameter(
                    "string",
                    "ID of the context to delete",
                    required=True,
                ),
                "confirm": self._create_parameter(
                    "boolean",
                    "Confirmation that you want to delete this context",
                    required=True,
                ),
            },
            required=["context_id", "confirm"],
        )

    async def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        context_id = arguments["context_id"]
        confirm = arguments.get("confirm", False)

        try:
            if not context_id or not context_id.strip():
                raise ToolError("Context ID cannot be empty", code="empty_context_id")

            if not confirm:
                raise ToolError("Deletion requires explicit confirmation", code="not_confirmed")

            result = await self.veris_client.delete_context(context_id.strip())

            return ToolResult.success(
                text=f"Successfully deleted context: {context_id}",
                data=result,
                metadata={
                    "operation": "delete_context",
                    "context_id": context_id,
                    "success": True,
                },
            )

        except VerisMemoryClientError as e:
            return ToolResult.error(f"Deletion failed: {e.message}", "veris_memory_error")
        except Exception as e:
            raise ToolError(f"Deletion error: {str(e)}", "internal_error")
