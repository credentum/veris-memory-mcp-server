"""
Upsert Fact tool for Veris Memory MCP Server.

Implements the upsert_fact tool that allows Claude CLI to create or update
user facts in Veris Memory.
"""

from typing import Any, Dict

from ..client.veris_client import VerisMemoryClient, VerisMemoryClientError
from ..protocol.schemas import Tool
from .base import BaseTool, ToolError, ToolResult


class UpsertFactTool(BaseTool):
    """
    Tool for creating or updating user facts in Veris Memory.

    Allows Claude CLI to store persistent facts about users that can be
    retrieved later for personalization and context.
    """

    name = "upsert_fact"
    description = "Create or update a user fact in Veris Memory"

    def __init__(self, veris_client: VerisMemoryClient, config: Dict[str, Any]):
        """
        Initialize upsert fact tool.

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
                "fact_key": self._create_parameter(
                    "string",
                    "Key identifying the fact (e.g., 'preferred_language', 'timezone')",
                    required=True,
                ),
                "fact_value": self._create_parameter(
                    "string",
                    "Value of the fact",
                    required=True,
                ),
                "user_id": self._create_parameter(
                    "string",
                    "User ID to associate the fact with (optional, uses default if not provided)",
                    required=False,
                ),
                "metadata": self._create_parameter(
                    "object",
                    "Optional metadata for the fact (e.g., source, confidence)",
                    required=False,
                ),
                "create_relationships": self._create_parameter(
                    "boolean",
                    "Whether to create relationships with existing entities",
                    required=False,
                ),
            },
            required=["fact_key", "fact_value"],
        )

    async def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Execute upsert fact operation.

        Args:
            arguments: Tool arguments containing fact_key, fact_value, etc.

        Returns:
            Tool result with fact ID and storage confirmation
        """
        fact_key = arguments["fact_key"]
        fact_value = arguments["fact_value"]
        user_id = arguments.get("user_id")
        metadata = arguments.get("metadata", {})
        create_relationships = arguments.get("create_relationships", False)

        try:
            # Validate fact key
            if not fact_key or not fact_key.strip():
                raise ToolError(
                    "Fact key cannot be empty",
                    code="invalid_fact_key",
                )

            # Validate fact value
            if not fact_value or not fact_value.strip():
                raise ToolError(
                    "Fact value cannot be empty",
                    code="invalid_fact_value",
                )

            # Upsert fact via Veris Memory client
            result = await self.veris_client.upsert_fact(
                fact_key=fact_key.strip(),
                fact_value=fact_value.strip(),
                user_id=user_id,
                metadata=metadata,
                create_relationships=create_relationships,
            )

            fact_id = result.get("fact_id")
            graph_id = result.get("graph_id")
            is_update = result.get("is_update", False)

            # Format success response
            action = "Updated" if is_update else "Created"
            success_message = f"{action} fact '{fact_key}'"
            if fact_id:
                success_message += f" with ID: {fact_id}"

            return ToolResult.success(
                text=success_message,
                data={
                    "fact_id": fact_id,
                    "graph_id": graph_id,
                    "fact_key": fact_key,
                    "fact_value": fact_value,
                    "is_update": is_update,
                    "user_id": user_id,
                },
                metadata={
                    "operation": "upsert_fact",
                    "is_update": is_update,
                    "success": True,
                },
            )

        except VerisMemoryClientError as e:
            self.logger.error("Veris Memory API error", error=str(e))
            return ToolResult.error(
                f"Failed to upsert fact: {e.message}",
                error_code="veris_memory_error",
                details={"original_error": str(e.original_error) if e.original_error else None},
            )

        except ToolError:
            # Re-raise tool errors as-is
            raise

        except Exception as e:
            self.logger.error("Unexpected error upserting fact", error=str(e), exc_info=True)
            raise ToolError(
                f"Unexpected error upserting fact: {str(e)}",
                code="internal_error",
            )
