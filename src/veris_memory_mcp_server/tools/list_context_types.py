"""
List Context Types tool for Veris Memory MCP Server.

Provides discovery of available context types and their schemas.
"""

from typing import Any, Dict

from ..client.veris_client import VerisMemoryClient, VerisMemoryClientError
from ..protocol.schemas import Tool
from .base import BaseTool, ToolError, ToolResult


class ListContextTypesTool(BaseTool):
    """Tool for listing available context types."""

    name = "list_context_types"
    description = "Get available context types and their descriptions"

    def __init__(self, veris_client: VerisMemoryClient, config: Dict[str, Any]):
        super().__init__(config)
        self.veris_client = veris_client

    def get_schema(self) -> Tool:
        return self._create_schema(
            parameters={
                "include_descriptions": self._create_parameter(
                    "boolean",
                    "Include detailed descriptions of each context type",
                    required=False,
                    default=True,
                ),
            },
            required=[],
        )

    async def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        include_descriptions = arguments.get("include_descriptions", True)

        try:
            context_types = await self.veris_client.list_context_types()

            # Format response based on include_descriptions flag
            if include_descriptions:
                # Provide detailed information about each context type
                type_info = {
                    "decision": "Architectural decisions, design choices, and strategic determinations",  # noqa: E501
                    "knowledge": "Documentation, procedures, best practices, and learning materials",  # noqa: E501
                    "analysis": "Data analysis, performance reviews, and analytical insights",
                    "meeting_notes": "Meeting summaries, action items, and discussion records",
                    "issue": "Bug reports, problems, and their resolutions",
                    "requirement": "System requirements, specifications, and functional needs",
                    "research": "Investigation results, findings, and research notes",
                }

                formatted_types = []
                for ctx_type in context_types:
                    formatted_types.append(
                        {
                            "type": ctx_type,
                            "description": type_info.get(ctx_type, "Custom context type"),
                        }
                    )

                summary = f"Found {len(context_types)} available context types:"
                for info in formatted_types:
                    summary += f"\n• {info['type']}: {info['description']}"

                return ToolResult.success(
                    text=summary,
                    data={
                        "context_types": formatted_types,
                        "count": len(context_types),
                    },
                )
            else:
                # Simple list
                return ToolResult.success(
                    text=f"Available context types: {', '.join(context_types)}",
                    data={
                        "context_types": context_types,
                        "count": len(context_types),
                    },
                )

        except VerisMemoryClientError as e:
            return ToolResult.error(
                f"Failed to list context types: {e.message}", "veris_memory_error"
            )
        except Exception as e:
            raise ToolError(f"Error listing context types: {str(e)}", "internal_error")
