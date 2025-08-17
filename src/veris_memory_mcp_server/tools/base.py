"""
Base classes for MCP tools.

Provides common functionality and interfaces for all Veris Memory tools,
including validation, error handling, and result formatting.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import structlog
from pydantic import BaseModel, ValidationError

from ..protocol.schemas import Tool, ToolParameter, ToolSchema

logger = structlog.get_logger(__name__)


class ToolError(Exception):
    """Base exception for tool execution errors."""

    def __init__(
        self, message: str, code: str = "tool_error", details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class ToolValidationError(ToolError):
    """Error for invalid tool arguments."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="validation_error", details=details)


class ToolExecutionError(ToolError):
    """Error during tool execution."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="execution_error", details=details)


class ToolResult:
    """Standardized tool result format."""

    def __init__(
        self,
        content: List[Dict[str, Any]],
        is_error: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.content = content
        self.is_error = is_error
        self.metadata = metadata or {}

    @classmethod
    def success(
        cls,
        text: str,
        data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ToolResult":
        """Create a successful result with text content."""
        # MCP specification: content should be text only for tool responses
        content = [{"type": "text", "text": text}]
        
        # If there's structured data, include it in the text response as JSON
        if data:
            import json
            data_text = f"\n\nStructured Data:\n```json\n{json.dumps(data, indent=2)}\n```"
            content[0]["text"] += data_text

        return cls(content=content, is_error=False, metadata=metadata)

    @classmethod
    def error(
        cls,
        message: str,
        error_code: str = "tool_error",
        details: Optional[Dict[str, Any]] = None,
    ) -> "ToolResult":
        """Create an error result."""
        error_text = f"Error: {message}"
        
        # Include details in the text response if provided
        if details:
            import json
            details_text = f"\n\nError Details:\n```json\n{json.dumps({'error_code': error_code, 'details': details}, indent=2)}\n```"
            error_text += details_text
            
        content = [{"type": "text", "text": error_text}]
        return cls(content=content, is_error=True)

    @classmethod
    def data(
        cls,
        data: Dict[str, Any],
        description: str = "Tool execution result",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ToolResult":
        """Create a result with structured data."""
        import json
        data_text = f"{description}\n\n```json\n{json.dumps(data, indent=2)}\n```"
        content = [{"type": "text", "text": data_text}]
        return cls(content=content, is_error=False, metadata=metadata)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for MCP response."""
        result = {
            "content": self.content,
            "isError": self.is_error,
        }

        if self.metadata:
            result["metadata"] = self.metadata

        return result


class BaseTool(ABC):
    """
    Base class for all MCP tools.

    Provides common functionality including argument validation,
    error handling, and result formatting.
    """

    # Tool metadata (must be defined by subclasses)
    name: str = ""
    description: str = ""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize tool with configuration.

        Args:
            config: Tool-specific configuration
        """
        self.config = config or {}
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Set up tool-specific logging."""
        self.logger = logger.bind(tool=self.name)

    @abstractmethod
    def get_schema(self) -> Tool:
        """
        Get the tool schema definition.

        Returns:
            Tool schema for MCP protocol
        """
        pass

    @abstractmethod
    async def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Execute the tool with given arguments.

        Args:
            arguments: Tool arguments from MCP request

        Returns:
            Tool execution result

        Raises:
            ToolError: If execution fails
        """
        pass

    async def __call__(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make tool callable for MCP handler integration.

        Args:
            arguments: Tool arguments

        Returns:
            Formatted result dictionary
        """
        try:
            self.logger.info("Executing tool", arguments=arguments)

            # Validate arguments
            self._validate_arguments(arguments)

            # Execute tool
            result = await self.execute(arguments)

            self.logger.info(
                "Tool execution completed",
                success=not result.is_error,
                result_type=type(result.content).__name__ if result.content else None,
            )

            return result.to_dict()

        except ToolError as e:
            self.logger.warning(
                "Tool execution failed",
                error_code=e.code,
                error_message=e.message,
                details=e.details,
            )
            return ToolResult.error(e.message, e.code, e.details).to_dict()

        except Exception as e:
            self.logger.error(
                "Unexpected tool error",
                error=str(e),
                exc_info=True,
            )
            return ToolResult.error(
                "Internal tool error",
                "internal_error",
                {"exception": str(e)},
            ).to_dict()

    def _validate_arguments(self, arguments: Dict[str, Any]) -> None:
        """
        Validate tool arguments against schema.

        Args:
            arguments: Arguments to validate

        Raises:
            ToolValidationError: If validation fails
        """
        schema = self.get_schema()

        # Check required parameters
        for required_param in schema.inputSchema.required:
            if required_param not in arguments:
                raise ToolValidationError(
                    f"Missing required parameter: {required_param}",
                    details={"missing_parameter": required_param},
                )

        # Validate parameter types and constraints
        for param_name, param_value in arguments.items():
            if param_name in schema.inputSchema.properties:
                param_def = schema.inputSchema.properties[param_name]
                self._validate_parameter(param_name, param_value, param_def)

    def _validate_parameter(
        self,
        name: str,
        value: Any,
        definition: ToolParameter,
    ) -> None:
        """
        Validate a single parameter.

        Args:
            name: Parameter name
            value: Parameter value
            definition: Parameter definition

        Raises:
            ToolValidationError: If validation fails
        """
        # Type validation
        if definition.type == "string" and not isinstance(value, str):
            raise ToolValidationError(
                f"Parameter '{name}' must be a string",
                details={
                    "parameter": name,
                    "expected_type": "string",
                    "actual_type": type(value).__name__,
                },
            )
        elif definition.type == "number" and not isinstance(value, (int, float)):
            raise ToolValidationError(
                f"Parameter '{name}' must be a number",
                details={
                    "parameter": name,
                    "expected_type": "number",
                    "actual_type": type(value).__name__,
                },
            )
        elif definition.type == "integer" and not isinstance(value, int):
            raise ToolValidationError(
                f"Parameter '{name}' must be an integer",
                details={
                    "parameter": name,
                    "expected_type": "integer",
                    "actual_type": type(value).__name__,
                },
            )
        elif definition.type == "boolean" and not isinstance(value, bool):
            raise ToolValidationError(
                f"Parameter '{name}' must be a boolean",
                details={
                    "parameter": name,
                    "expected_type": "boolean",
                    "actual_type": type(value).__name__,
                },
            )
        elif definition.type == "object" and not isinstance(value, dict):
            raise ToolValidationError(
                f"Parameter '{name}' must be an object",
                details={
                    "parameter": name,
                    "expected_type": "object",
                    "actual_type": type(value).__name__,
                },
            )
        elif definition.type == "array" and not isinstance(value, list):
            raise ToolValidationError(
                f"Parameter '{name}' must be an array",
                details={
                    "parameter": name,
                    "expected_type": "array",
                    "actual_type": type(value).__name__,
                },
            )

        # Enum validation
        if definition.enum and value not in definition.enum:
            raise ToolValidationError(
                f"Parameter '{name}' must be one of: {definition.enum}",
                details={
                    "parameter": name,
                    "allowed_values": definition.enum,
                    "actual_value": value,
                },
            )

    def _create_parameter(
        self,
        param_type: str,
        description: str,
        required: bool = False,
        enum: Optional[List[str]] = None,
        default: Optional[Any] = None,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Helper to create JSON Schema parameter definitions."""
        param = {
            "type": param_type,
            "description": description,
        }
        
        if enum is not None:
            param["enum"] = enum
        if default is not None:
            param["default"] = default
        if minimum is not None:
            param["minimum"] = minimum
        if maximum is not None:
            param["maximum"] = maximum
            
        return param

    def _create_schema(
        self,
        parameters: Dict[str, Any],
        required: List[str],
    ) -> Tool:
        """Helper to create tool schema with proper JSON Schema format."""
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema=ToolSchema(
                type="object",
                properties=parameters,
                required=required,
                additionalProperties=False,
            ),
        )
