"""
Get User Facts tool for Veris Memory MCP Server.

Implements the get_user_facts tool that allows Claude CLI to retrieve
all facts stored for a specific user.
"""

from typing import Any, Dict, List

from ..client.veris_client import VerisMemoryClient, VerisMemoryClientError
from ..protocol.schemas import Tool
from .base import BaseTool, ToolError, ToolResult


class GetUserFactsTool(BaseTool):
    """
    Tool for retrieving user facts from Veris Memory.

    Allows Claude CLI to get all facts stored for a user,
    useful for personalization and context retrieval.
    """

    name = "get_user_facts"
    description = "Retrieve all facts stored for a user from Veris Memory"

    def __init__(self, veris_client: VerisMemoryClient, config: Dict[str, Any]):
        """
        Initialize get user facts tool.

        Args:
            veris_client: Veris Memory client instance
            config: Tool configuration
        """
        super().__init__(config)
        self.veris_client = veris_client
        self.default_limit = config.get("default_limit", 100)
        self.max_limit = config.get("max_limit", 1000)

    def get_schema(self) -> Tool:
        """Get the tool schema definition."""
        return self._create_schema(
            parameters={
                "user_id": self._create_parameter(
                    "string",
                    "User ID to retrieve facts for (optional, uses default if not provided)",
                    required=False,
                ),
                "limit": self._create_parameter(
                    "integer",
                    f"Maximum number of facts to return (default: {self.default_limit})",
                    required=False,
                    minimum=1,
                    maximum=self.max_limit,
                ),
                "include_forgotten": self._create_parameter(
                    "boolean",
                    "Whether to include forgotten/archived facts (default: false)",
                    required=False,
                ),
            },
            required=[],
        )

    async def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Execute get user facts operation.

        Args:
            arguments: Tool arguments containing user_id, limit, etc.

        Returns:
            Tool result with list of user facts
        """
        user_id = arguments.get("user_id")
        limit = arguments.get("limit", self.default_limit)
        include_forgotten = arguments.get("include_forgotten", False)

        try:
            # Validate limit
            if limit < 1:
                limit = 1
            elif limit > self.max_limit:
                limit = self.max_limit

            # Get facts via Veris Memory client
            result = await self.veris_client.get_user_facts(
                user_id=user_id,
                limit=limit,
                include_forgotten=include_forgotten,
            )

            facts: List[Dict[str, Any]] = result.get("facts", [])
            total_count = result.get("total_count", len(facts))

            # Format success response
            if not facts:
                success_message = "No facts found for user"
            else:
                success_message = f"Retrieved {len(facts)} fact(s)"
                if total_count > len(facts):
                    success_message += f" (total: {total_count})"

            return ToolResult.success(
                text=success_message,
                data={
                    "facts": facts,
                    "count": len(facts),
                    "total_count": total_count,
                    "user_id": user_id,
                    "include_forgotten": include_forgotten,
                },
                metadata={
                    "operation": "get_user_facts",
                    "count": len(facts),
                    "success": True,
                },
            )

        except VerisMemoryClientError as e:
            self.logger.error("Veris Memory API error", error=str(e))
            return ToolResult.error(
                f"Failed to get user facts: {e.message}",
                error_code="veris_memory_error",
                details={"original_error": str(e.original_error) if e.original_error else None},
            )

        except ToolError:
            # Re-raise tool errors as-is
            raise

        except Exception as e:
            self.logger.error("Unexpected error getting user facts", error=str(e), exc_info=True)
            raise ToolError(
                f"Unexpected error getting user facts: {str(e)}",
                code="internal_error",
            )
