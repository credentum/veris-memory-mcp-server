"""
Search Context tool for Veris Memory MCP Server.

Implements advanced search capabilities with complex filtering options.
"""

from typing import Any, Dict

from ..client.veris_client import VerisMemoryClient, VerisMemoryClientError
from ..protocol.schemas import Tool
from .base import BaseTool, ToolError, ToolResult


class SearchContextTool(BaseTool):
    """Advanced context search with filtering capabilities."""

    name = "search_context"
    description = "Advanced search of contexts with complex filtering and sorting options"

    def __init__(self, veris_client: VerisMemoryClient, config: Dict[str, Any]):
        super().__init__(config)
        self.veris_client = veris_client
        self.max_results = config.get("max_results", 100)
        self.default_limit = config.get("default_limit", 10)

    def get_schema(self) -> Tool:
        return self._create_schema(
            parameters={
                "query": self._create_parameter("string", "Search query for semantic matching"),
                "filters": self._create_parameter(
                    "object", "Advanced search filters including date ranges, metadata, etc."
                ),
                "limit": self._create_parameter(
                    "integer",
                    f"Maximum results (1-{self.max_results})",
                    default=self.default_limit,
                    minimum=1,
                    maximum=self.max_results,
                ),
            },
            required=["query"],
        )

    async def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        query = arguments["query"]
        filters = arguments.get("filters", {})
        limit = arguments.get("limit", self.default_limit)

        try:
            if not query.strip():
                raise ToolError("Query cannot be empty", code="empty_query")

            if not isinstance(limit, int) or limit < 1 or limit > self.max_results:
                raise ToolError(f"Limit must be between 1 and {self.max_results}")

            result = await self.veris_client.search_context(
                query=query.strip(),
                filters=filters,
                limit=limit,
            )

            return ToolResult.success(
                text=f"Search completed for '{query}' with {len(result.get('results', []))} results",
                data=result,
                metadata={
                    "operation": "search_context",
                    "query": query,
                    "result_count": len(result.get("results", [])),
                },
            )

        except VerisMemoryClientError as e:
            return ToolResult.error(f"Search failed: {e.message}", "veris_memory_error")
        except Exception as e:
            raise ToolError(f"Search error: {str(e)}", "internal_error")
