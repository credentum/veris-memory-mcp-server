"""
Retrieve Context tool for Veris Memory MCP Server.

Implements the retrieve_context tool that allows Claude CLI to search
and retrieve stored context data from Veris Memory.
"""

from typing import Any, Dict, List, Optional

from ..client.veris_client import VerisMemoryClient, VerisMemoryClientError
from ..protocol.schemas import Tool
from .base import BaseTool, ToolError, ToolResult


class RetrieveContextTool(BaseTool):
    """
    Tool for retrieving context data from Veris Memory.

    Allows Claude CLI to search for and retrieve previously stored
    contexts using semantic search and filtering.
    """

    name = "retrieve_context"
    description = "Search and retrieve context data from Veris Memory using semantic search"

    def __init__(self, veris_client: VerisMemoryClient, config: Dict[str, Any]):
        """
        Initialize retrieve context tool.

        Args:
            veris_client: Veris Memory client instance
            config: Tool configuration
        """
        super().__init__(config)
        self.veris_client = veris_client
        self.max_results = config.get("max_results", 100)
        self.default_limit = config.get("default_limit", 10)

    def get_schema(self) -> Tool:
        """Get the tool schema definition."""
        return self._create_schema(
            parameters={
                "query": self._create_parameter(
                    "string",
                    "Search query for semantic matching against stored contexts",
                    required=True,
                ),
                "limit": self._create_parameter(
                    "integer",
                    f"Maximum number of results to return (1-{self.max_results}, default: {self.default_limit})",
                    required=False,
                    default=self.default_limit,
                ),
                "context_type": self._create_parameter(
                    "string",
                    "Filter results by specific context type (e.g., 'decision', 'knowledge')",
                    required=False,
                ),
                "metadata_filters": self._create_parameter(
                    "object",
                    "Filter results by metadata key-value pairs (e.g., {'project': 'api-v2', 'priority': 'high'})",
                    required=False,
                ),
            },
            required=["query"],
        )

    async def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Execute retrieve context operation.

        Args:
            arguments: Tool arguments containing query, limit, filters, etc.

        Returns:
            Tool result with retrieved contexts
        """
        self.logger.error("!!!!! RETRIEVE_CONTEXT EXECUTE CALLED !!!!!")
        self.logger.error(f"!!!!! ARGUMENTS: {arguments} !!!!!")

        query = arguments["query"]
        limit = arguments.get("limit", self.default_limit)
        context_type = arguments.get("context_type")
        metadata_filters = arguments.get("metadata_filters")

        try:
            # Validate limit
            if not isinstance(limit, int) or limit < 1 or limit > self.max_results:
                raise ToolError(
                    f"Limit must be an integer between 1 and {self.max_results}",
                    code="invalid_limit",
                    details={"limit": limit, "max_results": self.max_results},
                )

            # Validate query
            if not query or not query.strip():
                raise ToolError(
                    "Query cannot be empty",
                    code="empty_query",
                )

            # Retrieve contexts via Veris Memory client
            contexts = await self.veris_client.retrieve_context(
                query=query.strip(),
                limit=limit,
                context_type=context_type,
                metadata_filters=metadata_filters,
            )

            # Format results
            if not contexts:
                return ToolResult.success(
                    text=f"No contexts found matching query: '{query}'",
                    data={
                        "query": query,
                        "results": [],
                        "count": 0,
                        "filters_applied": {
                            "context_type": context_type,
                            "metadata_filters": metadata_filters,
                        },
                    },
                    metadata={
                        "operation": "retrieve_context",
                        "query": query,
                        "result_count": 0,
                    },
                )

            # Format contexts for display
            formatted_contexts = self._format_contexts(contexts)

            # Create summary text
            summary_text = self._create_summary(query, contexts, context_type, metadata_filters)

            return ToolResult.success(
                text=summary_text,
                data={
                    "query": query,
                    "results": formatted_contexts,
                    "count": len(contexts),
                    "filters_applied": {
                        "context_type": context_type,
                        "metadata_filters": metadata_filters,
                    },
                },
                metadata={
                    "operation": "retrieve_context",
                    "query": query,
                    "result_count": len(contexts),
                },
            )

        except VerisMemoryClientError as e:
            self.logger.error("Veris Memory API error", error=str(e))
            return ToolResult.error(
                f"Failed to retrieve contexts: {e.message}",
                error_code="veris_memory_error",
                details={"original_error": str(e.original_error) if e.original_error else None},
            )

        except ToolError:
            # Re-raise tool errors as-is
            raise

        except Exception as e:
            import traceback

            tb = traceback.format_exc()
            self.logger.error(f"!!!!! UNEXPECTED ERROR !!!!!")
            self.logger.error(f"!!!!! ERROR TYPE: {type(e)} !!!!!")
            self.logger.error(f"!!!!! ERROR VALUE: {str(e)} !!!!!")
            self.logger.error(f"!!!!! FULL TRACEBACK:\n{tb}")
            raise ToolError(
                f"Unexpected error retrieving contexts: {str(e)}",
                code="internal_error",
                details={"traceback": tb},
            )

    def _format_contexts(self, contexts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Format contexts for display.

        Args:
            contexts: Raw contexts from Veris Memory

        Returns:
            Formatted contexts
        """
        formatted = []

        for context in contexts:
            # Extract type from content or use default
            content = context.get("content", {})
            context_type = content.get("type") if isinstance(content, dict) else "unknown"

            formatted_context = {
                "id": context.get("id", "unknown"),
                "type": context_type,
                "title": self._extract_title(context),
                "summary": self._extract_summary(context),
                "metadata": context.get("metadata", {}),
                "created_at": context.get("created_at"),
                "relevance_score": context.get("relevance_score", 0.0),
            }

            # Include full content if it's not too large
            content = context.get("content", {})
            if isinstance(content, dict):
                content_size = len(str(content))
                if content_size < 2000:  # Include full content if small
                    formatted_context["content"] = content
                else:
                    formatted_context["content_preview"] = str(content)[:500] + "..."

            formatted.append(formatted_context)

        # Sort by relevance score (descending)
        formatted.sort(key=lambda x: x.get("relevance_score", 0.0), reverse=True)

        return formatted

    def _extract_title(self, context: Dict[str, Any]) -> str:
        """Extract title from context."""
        content = context.get("content", {})

        # Try various title fields
        if isinstance(content, dict):
            for field in ["title", "name", "subject", "summary"]:
                if field in content and content[field]:
                    return str(content[field])[:100]  # Limit title length

        # Fallback to context type and ID
        # Try to get type from content.type since contexts don't have context_type field
        content_type = content.get("type", "Context") if isinstance(content, dict) else "Context"
        context_id = context.get("id", "unknown")
        # Handle the case where context_id might not be sliceable
        if isinstance(context_id, str) and len(context_id) > 8:
            context_id = context_id[:8]
        # Handle case where content_type might be None
        if content_type and isinstance(content_type, str):
            return f"{content_type.title()} ({context_id})"
        else:
            return f"Context ({context_id})"

    def _extract_summary(self, context: Dict[str, Any]) -> str:
        """Extract summary from context."""
        content = context.get("content", {})

        if isinstance(content, dict):
            # Try summary fields first
            for field in ["summary", "description", "text", "content"]:
                if field in content and content[field]:
                    text = str(content[field])
                    # Return first sentence or first 200 characters
                    if "." in text:
                        first_sentence = text.split(".")[0] + "."
                        if len(first_sentence) <= 200:
                            return first_sentence
                    return text[:200] + ("..." if len(text) > 200 else "")

        return "No summary available"

    def _create_summary(
        self,
        query: str,
        contexts: List[Dict[str, Any]],
        context_type: Optional[str] = None,
        metadata_filters: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create summary text for the results."""
        count = len(contexts)

        # Base message
        if count == 1:
            summary = f"Found 1 context matching '{query}'"
        else:
            summary = f"Found {count} contexts matching '{query}'"

        # Add filter information
        filters = []
        if context_type:
            filters.append(f"type: {context_type}")
        if metadata_filters:
            filter_strs = [f"{k}: {v}" for k, v in metadata_filters.items()]
            filters.append(f"metadata: {', '.join(filter_strs)}")

        if filters:
            summary += f" (filtered by {', '.join(filters)})"

        summary += ":"

        # Add brief descriptions of top results
        if contexts:
            for i, context in enumerate(contexts[:3]):  # Show top 3
                title = self._extract_title(context)
                # Get type from content.type field
                content = context.get("content", {})
                context_type = (
                    content.get("type", "unknown") if isinstance(content, dict) else "unknown"
                )
                summary += f"\n{i+1}. [{context_type}] {title}"

        if count > 3:
            summary += f"\n... and {count - 3} more results"

        return summary
