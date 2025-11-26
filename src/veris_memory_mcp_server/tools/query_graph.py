"""
Query Graph tool for Veris Memory MCP Server.

Implements the query_graph tool that allows Claude CLI to execute
Cypher queries against the Neo4j graph database.
"""

from typing import Any, Dict, List

from ..client.veris_client import VerisMemoryClient, VerisMemoryClientError
from ..protocol.schemas import Tool
from .base import BaseTool, ToolError, ToolResult


class QueryGraphTool(BaseTool):
    """
    Tool for querying the Neo4j graph database in Veris Memory.

    Allows Claude CLI to execute Cypher queries for advanced
    graph traversal and relationship exploration.
    """

    name = "query_graph"
    description = "Execute a Cypher query against the Veris Memory graph database"

    def __init__(self, veris_client: VerisMemoryClient, config: Dict[str, Any]):
        """
        Initialize query graph tool.

        Args:
            veris_client: Veris Memory client instance
            config: Tool configuration
        """
        super().__init__(config)
        self.veris_client = veris_client
        self.max_results = config.get("max_results", 100)
        self.allowed_operations = config.get("allowed_operations", ["MATCH", "RETURN"])
        self.read_only = config.get("read_only", True)

    def get_schema(self) -> Tool:
        """Get the tool schema definition."""
        return self._create_schema(
            parameters={
                "query": self._create_parameter(
                    "string",
                    "Cypher query to execute (read-only operations only)",
                    required=True,
                ),
                "parameters": self._create_parameter(
                    "object",
                    "Optional parameters for the Cypher query",
                    required=False,
                ),
                "limit": self._create_parameter(
                    "integer",
                    f"Maximum number of results to return (default: {self.max_results})",
                    required=False,
                    minimum=1,
                    maximum=self.max_results,
                ),
            },
            required=["query"],
        )

    async def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Execute query graph operation.

        Args:
            arguments: Tool arguments containing query, parameters, etc.

        Returns:
            Tool result with query results
        """
        query = arguments["query"]
        parameters = arguments.get("parameters", {})
        limit = arguments.get("limit", self.max_results)

        try:
            # Validate query
            if not query or not query.strip():
                raise ToolError(
                    "Query cannot be empty",
                    code="invalid_query",
                )

            # Security check for read-only mode
            if self.read_only:
                query_upper = query.upper()
                dangerous_keywords = [
                    "CREATE",
                    "DELETE",
                    "SET",
                    "REMOVE",
                    "MERGE",
                    "DROP",
                    "DETACH",
                ]
                for keyword in dangerous_keywords:
                    if keyword in query_upper:
                        raise ToolError(
                            f"Write operations ({keyword}) not allowed in read-only mode",
                            code="write_not_allowed",
                            details={"keyword": keyword},
                        )

            # Execute query via Veris Memory client
            result = await self.veris_client.query_graph(
                query=query.strip(),
                parameters=parameters,
                limit=limit,
            )

            records: List[Dict[str, Any]] = result.get("records", [])
            columns = result.get("columns", [])

            # Format success response
            if not records:
                success_message = "Query returned no results"
            else:
                success_message = f"Query returned {len(records)} record(s)"

            return ToolResult.success(
                text=success_message,
                data={
                    "records": records,
                    "columns": columns,
                    "count": len(records),
                },
                metadata={
                    "operation": "query_graph",
                    "count": len(records),
                    "success": True,
                },
            )

        except VerisMemoryClientError as e:
            self.logger.error("Veris Memory API error", error=str(e))
            return ToolResult.error(
                f"Failed to execute query: {e.message}",
                error_code="veris_memory_error",
                details={"original_error": str(e.original_error) if e.original_error else None},
            )

        except ToolError:
            # Re-raise tool errors as-is
            raise

        except Exception as e:
            self.logger.error("Unexpected error executing query", error=str(e), exc_info=True)
            raise ToolError(
                f"Unexpected error executing query: {str(e)}",
                code="internal_error",
            )
