"""
Forget Context tool for Veris Memory MCP Server.

Implements the forget_context tool that allows Claude CLI to soft-delete
or archive context from Veris Memory.
"""

from typing import Any, Dict

from ..client.veris_client import VerisMemoryClient, VerisMemoryClientError
from ..protocol.schemas import Tool
from .base import BaseTool, ToolError, ToolResult


class ForgetContextTool(BaseTool):
    """
    Tool for forgetting (soft-deleting) context in Veris Memory.

    Allows Claude CLI to mark context as forgotten without permanently
    deleting it, supporting GDPR compliance and user privacy.
    """

    name = "forget_context"
    description = "Soft-delete or archive context in Veris Memory (marks as forgotten)"

    def __init__(self, veris_client: VerisMemoryClient, config: Dict[str, Any]):
        """
        Initialize forget context tool.

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
                "context_id": self._create_parameter(
                    "string",
                    "ID of the context to forget",
                    required=True,
                ),
                "reason": self._create_parameter(
                    "string",
                    "Reason for forgetting the context (for audit trail)",
                    required=False,
                ),
            },
            required=["context_id"],
        )

    async def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Execute forget context operation.

        Args:
            arguments: Tool arguments containing context_id, reason, etc.

        Returns:
            Tool result with confirmation of forgetting
        """
        context_id = arguments["context_id"]
        reason = arguments.get("reason")

        try:
            # Validate context_id
            if not context_id or not context_id.strip():
                raise ToolError(
                    "Context ID cannot be empty",
                    code="invalid_context_id",
                )

            # Forget context via Veris Memory client
            result = await self.veris_client.forget_context(
                context_id=context_id.strip(),
                reason=reason,
            )

            success = result.get("success", False)
            forgotten_at = result.get("forgotten_at")

            if not success:
                return ToolResult.error(
                    f"Failed to forget context: {result.get('error', 'Unknown error')}",
                    error_code="forget_failed",
                    details={"context_id": context_id},
                )

            # Format success response
            success_message = f"Successfully forgot context {context_id}"
            if reason:
                success_message += f" (reason: {reason})"

            return ToolResult.success(
                text=success_message,
                data={
                    "context_id": context_id,
                    "forgotten_at": forgotten_at,
                    "reason": reason,
                },
                metadata={
                    "operation": "forget_context",
                    "success": True,
                },
            )

        except VerisMemoryClientError as e:
            self.logger.error("Veris Memory API error", error=str(e))
            return ToolResult.error(
                f"Failed to forget context: {e.message}",
                error_code="veris_memory_error",
                details={"original_error": str(e.original_error) if e.original_error else None},
            )

        except ToolError:
            # Re-raise tool errors as-is
            raise

        except Exception as e:
            self.logger.error("Unexpected error forgetting context", error=str(e), exc_info=True)
            raise ToolError(
                f"Unexpected error forgetting context: {str(e)}",
                code="internal_error",
            )
