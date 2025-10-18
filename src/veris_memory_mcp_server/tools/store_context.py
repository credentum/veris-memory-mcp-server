"""
Store Context tool for Veris Memory MCP Server.

Implements the store_context tool that allows Claude CLI to store
context data in Veris Memory with metadata and categorization.
"""

from typing import Any, Dict

from ..client.veris_client import VerisMemoryClient, VerisMemoryClientError
from ..protocol.schemas import Tool
from .base import BaseTool, ToolError, ToolResult


class StoreContextTool(BaseTool):
    """
    Tool for storing context data in Veris Memory.

    Allows Claude CLI to store decisions, knowledge, analysis,
    and other contextual information with structured metadata.
    """

    name = "store_context"
    description = "Store context data in Veris Memory with optional metadata for future retrieval"

    def __init__(self, veris_client: VerisMemoryClient, config: Dict[str, Any]):
        """
        Initialize store context tool.

        Args:
            veris_client: Veris Memory client instance
            config: Tool configuration
        """
        super().__init__(config)
        self.veris_client = veris_client
        self.max_content_size = config.get("max_content_size", 1048576)  # 1MB
        self.allowed_context_types = config.get("allowed_context_types", ["*"])

    def get_schema(self) -> Tool:
        """Get the tool schema definition."""
        return self._create_schema(
            parameters={
                "context_type": self._create_parameter(
                    "string",
                    "Type of context being stored (e.g., 'decision', 'knowledge', 'analysis', 'meeting_notes')",  # noqa: E501
                    required=True,
                    enum=None if "*" in self.allowed_context_types else self.allowed_context_types,
                ),
                "content": self._create_parameter(
                    "object",
                    "The actual context content with structured data",
                    required=True,
                ),
                "metadata": self._create_parameter(
                    "object",
                    "Optional metadata for categorization and search (e.g., project, priority, tags)",  # noqa: E501
                    required=False,
                ),
                "title": self._create_parameter(
                    "string",
                    "Optional title for the context",
                    required=False,
                ),
            },
            required=["context_type", "content"],
        )

    async def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Execute store context operation.

        Args:
            arguments: Tool arguments containing context_type, content, metadata, etc.

        Returns:
            Tool result with context ID and storage confirmation
        """
        context_type = arguments["context_type"]
        content = arguments["content"]
        metadata = arguments.get("metadata", {})
        title = arguments.get("title")

        try:
            # Validate context type if restricted
            if (
                "*" not in self.allowed_context_types
                and context_type not in self.allowed_context_types
            ):
                raise ToolError(
                    f"Context type '{context_type}' not allowed. "
                    f"Allowed types: {self.allowed_context_types}",
                    code="invalid_context_type",
                )

            # Validate content structure
            self._validate_content(content)

            # Add title to content if provided
            if title:
                if isinstance(content, dict):
                    content = content.copy()
                    content["title"] = title
                else:
                    content = {"title": title, "data": content}

            # Ensure content is a dictionary with required fields
            if not isinstance(content, dict):
                content = {"text": str(content)}

            # Add text field if missing (required by Veris Memory)
            if "text" not in content:
                # Try to extract text from common fields
                text_content = self._extract_text_content(content)
                content["text"] = text_content

            # Store context via Veris Memory client
            result = await self.veris_client.store_context(
                context_type=context_type,
                content=content,
                metadata=metadata,
            )

            context_id = result.get("context_id")

            # Format success response
            success_message = f"Successfully stored {context_type} context"
            if context_id:
                success_message += f" with ID: {context_id}"

            return ToolResult.success(
                text=success_message,
                data={
                    "context_id": context_id,
                    "context_type": context_type,
                    "timestamp": result.get("created_at"),
                    "metadata": metadata,
                },
                metadata={
                    "operation": "store_context",
                    "context_type": context_type,
                    "success": True,
                },
            )

        except VerisMemoryClientError as e:
            self.logger.error("Veris Memory API error", error=str(e))
            return ToolResult.error(
                f"Failed to store context: {e.message}",
                error_code="veris_memory_error",
                details={"original_error": str(e.original_error) if e.original_error else None},
            )

        except ToolError:
            # Re-raise tool errors as-is
            raise

        except Exception as e:
            self.logger.error("Unexpected error storing context", error=str(e), exc_info=True)
            raise ToolError(
                f"Unexpected error storing context: {str(e)}",
                code="internal_error",
            )

    def _validate_content(self, content: Any) -> None:
        """
        Validate content structure and size.

        Args:
            content: Content to validate

        Raises:
            ToolError: If content is invalid
        """
        # Check content size (rough approximation)
        content_str = str(content)
        if len(content_str.encode("utf-8")) > self.max_content_size:
            raise ToolError(
                f"Content size exceeds maximum of {self.max_content_size} bytes",
                code="content_too_large",
                details={"max_size": self.max_content_size},
            )

        # Validate content has meaningful data
        if not content or (isinstance(content, dict) and not any(content.values())):
            raise ToolError(
                "Content cannot be empty",
                code="empty_content",
            )

    def _extract_text_content(self, content: Dict[str, Any]) -> str:
        """
        Extract text content from structured data.

        Args:
            content: Content dictionary

        Returns:
            Extracted text content
        """
        # Try common text fields
        text_fields = ["text", "description", "summary", "content", "message", "notes"]

        for field in text_fields:
            if field in content and isinstance(content[field], str) and content[field].strip():
                return content[field].strip()

        # Try to extract from title + other fields
        parts = []

        if "title" in content:
            parts.append(str(content["title"]))

        # Add other string values
        for key, value in content.items():
            if key not in ["title"] and isinstance(value, str) and value.strip():
                parts.append(f"{key}: {value}")

        if parts:
            return " | ".join(parts)

        # Fallback to string representation
        return str(content)
