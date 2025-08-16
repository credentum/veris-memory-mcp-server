"""
Webhook management tools for MCP server.

Provides tools for webhook subscription management and
event notifications through the MCP interface.
"""

from typing import Any, Dict, List

from ..client.veris_client import VerisMemoryClient, VerisMemoryClientError
from ..protocol.schemas import Tool
from ..tools.base import BaseTool, ToolError, ToolResult
from .events import EventType
from .manager import WebhookManager


class WebhookManagementTool(BaseTool):
    """
    Tool for managing webhook subscriptions and notifications.
    
    Allows users to register, update, and manage webhook endpoints
    for real-time event notifications.
    """
    
    name = "webhook_management"
    description = "Manage webhook subscriptions for real-time event notifications"
    
    def __init__(
        self,
        webhook_manager: WebhookManager,
        config: Dict[str, Any]
    ):
        """
        Initialize webhook management tool.
        
        Args:
            webhook_manager: Webhook manager instance
            config: Tool configuration
        """
        super().__init__(config)
        self.webhook_manager = webhook_manager
    
    def get_schema(self) -> Tool:
        """Get the tool schema definition."""
        return self._create_schema(
            parameters={
                "action": self._create_parameter(
                    "string",
                    "Action to perform on webhooks",
                    required=True,
                    enum=[
                        "register", 
                        "unregister", 
                        "update", 
                        "list", 
                        "get", 
                        "stats"
                    ],
                ),
                "webhook_id": self._create_parameter(
                    "string",
                    "Webhook ID for update/unregister/get operations",
                    required=False,
                ),
                "url": self._create_parameter(
                    "string",
                    "Webhook URL for register/update operations",
                    required=False,
                ),
                "event_types": self._create_parameter(
                    "array",
                    "List of event types to subscribe to (empty for all events)",
                    required=False,
                ),
                "headers": self._create_parameter(
                    "object",
                    "Additional HTTP headers for webhook delivery",
                    required=False,
                ),
                "signing_secret": self._create_parameter(
                    "string",
                    "Secret for webhook signature verification",
                    required=False,
                ),
                "description": self._create_parameter(
                    "string",
                    "Description for the webhook subscription",
                    required=False,
                ),
                "active": self._create_parameter(
                    "boolean",
                    "Whether the webhook is active (update only)",
                    required=False,
                ),
            },
            required=["action"],
        )
    
    async def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Execute webhook management operation.
        
        Args:
            arguments: Tool arguments containing action and parameters
            
        Returns:
            Tool result with operation outcome
        """
        action = arguments["action"]
        
        try:
            if action == "register":
                return await self._register_webhook(arguments)
            elif action == "unregister":
                return await self._unregister_webhook(arguments)
            elif action == "update":
                return await self._update_webhook(arguments)
            elif action == "list":
                return await self._list_webhooks()
            elif action == "get":
                return await self._get_webhook(arguments)
            elif action == "stats":
                return await self._get_stats()
            else:
                raise ToolError(f"Unknown action: {action}", code="invalid_action")
                
        except ToolError:
            raise
        except Exception as e:
            self.logger.error("Webhook management error", error=str(e), exc_info=True)
            raise ToolError(
                f"Webhook management failed: {str(e)}",
                code="internal_error",
            )
    
    async def _register_webhook(self, arguments: Dict[str, Any]) -> ToolResult:
        """Register a new webhook subscription."""
        url = arguments.get("url")
        if not url:
            raise ToolError("URL is required for webhook registration", code="missing_url")
        
        event_types = arguments.get("event_types", [])
        headers = arguments.get("headers", {})
        signing_secret = arguments.get("signing_secret")
        description = arguments.get("description")
        
        try:
            webhook_id = await self.webhook_manager.register_webhook(
                url=url,
                event_types=event_types,
                headers=headers,
                signing_secret=signing_secret,
                description=description,
            )
            
            return ToolResult.success(
                text=f"Webhook registered successfully with ID: {webhook_id}",
                data={
                    "webhook_id": webhook_id,
                    "url": url,
                    "event_types": event_types,
                    "description": description,
                },
                metadata={
                    "operation": "webhook_register",
                    "webhook_id": webhook_id,
                },
            )
            
        except ValueError as e:
            raise ToolError(str(e), code="registration_failed")
    
    async def _unregister_webhook(self, arguments: Dict[str, Any]) -> ToolResult:
        """Unregister a webhook subscription."""
        webhook_id = arguments.get("webhook_id")
        if not webhook_id:
            raise ToolError("webhook_id is required for unregistration", code="missing_webhook_id")
        
        success = await self.webhook_manager.unregister_webhook(webhook_id)
        
        if success:
            return ToolResult.success(
                text=f"Webhook {webhook_id} unregistered successfully",
                data={"webhook_id": webhook_id, "unregistered": True},
                metadata={"operation": "webhook_unregister"},
            )
        else:
            return ToolResult.error(
                f"Webhook {webhook_id} not found",
                error_code="webhook_not_found",
            )
    
    async def _update_webhook(self, arguments: Dict[str, Any]) -> ToolResult:
        """Update an existing webhook subscription."""
        webhook_id = arguments.get("webhook_id")
        if not webhook_id:
            raise ToolError("webhook_id is required for update", code="missing_webhook_id")
        
        update_params = {}
        for param in ["url", "event_types", "headers", "active", "description"]:
            if param in arguments:
                update_params[param] = arguments[param]
        
        if not update_params:
            raise ToolError("At least one parameter must be provided for update", code="no_update_params")
        
        try:
            success = await self.webhook_manager.update_webhook(
                webhook_id=webhook_id,
                **update_params
            )
            
            if success:
                return ToolResult.success(
                    text=f"Webhook {webhook_id} updated successfully",
                    data={
                        "webhook_id": webhook_id,
                        "updated_fields": list(update_params.keys()),
                        **update_params
                    },
                    metadata={"operation": "webhook_update"},
                )
            else:
                return ToolResult.error(
                    f"Webhook {webhook_id} not found",
                    error_code="webhook_not_found",
                )
                
        except ValueError as e:
            raise ToolError(str(e), code="update_failed")
    
    async def _list_webhooks(self) -> ToolResult:
        """List all webhook subscriptions."""
        subscriptions = self.webhook_manager.get_subscriptions()
        
        return ToolResult.success(
            text=f"Found {len(subscriptions)} webhook subscriptions",
            data={
                "subscriptions": subscriptions,
                "total_count": len(subscriptions),
            },
            metadata={"operation": "webhook_list"},
        )
    
    async def _get_webhook(self, arguments: Dict[str, Any]) -> ToolResult:
        """Get details of a specific webhook."""
        webhook_id = arguments.get("webhook_id")
        if not webhook_id:
            raise ToolError("webhook_id is required", code="missing_webhook_id")
        
        subscription = self.webhook_manager.get_subscription(webhook_id)
        
        if subscription:
            return ToolResult.success(
                text=f"Webhook {webhook_id} details",
                data=subscription,
                metadata={"operation": "webhook_get"},
            )
        else:
            return ToolResult.error(
                f"Webhook {webhook_id} not found",
                error_code="webhook_not_found",
            )
    
    async def _get_stats(self) -> ToolResult:
        """Get webhook system statistics."""
        stats = self.webhook_manager.get_stats()
        
        return ToolResult.success(
            text="Webhook system statistics",
            data=stats,
            metadata={"operation": "webhook_stats"},
        )


class EventNotificationTool(BaseTool):
    """
    Tool for manually triggering event notifications.
    
    Allows testing of webhook delivery and custom event
    emission for debugging and validation.
    """
    
    name = "event_notification"
    description = "Manually trigger event notifications for testing and debugging"
    
    def __init__(
        self,
        webhook_manager: WebhookManager,
        config: Dict[str, Any]
    ):
        """
        Initialize event notification tool.
        
        Args:
            webhook_manager: Webhook manager instance
            config: Tool configuration
        """
        super().__init__(config)
        self.webhook_manager = webhook_manager
    
    def get_schema(self) -> Tool:
        """Get the tool schema definition."""
        available_event_types = [et.value for et in EventType]
        
        return self._create_schema(
            parameters={
                "event_type": self._create_parameter(
                    "string",
                    "Type of event to emit",
                    required=True,
                    enum=available_event_types,
                ),
                "event_data": self._create_parameter(
                    "object",
                    "Event-specific data payload",
                    required=False,
                ),
                "event_metadata": self._create_parameter(
                    "object",
                    "Additional event metadata",
                    required=False,
                ),
                "test_mode": self._create_parameter(
                    "boolean",
                    "Whether this is a test event (adds test prefix to event_id)",
                    required=False,
                    default=True,
                ),
            },
            required=["event_type"],
        )
    
    async def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Execute event notification.
        
        Args:
            arguments: Tool arguments containing event details
            
        Returns:
            Tool result with notification outcome
        """
        try:
            # Parse event type
            event_type_str = arguments["event_type"]
            try:
                event_type = EventType(event_type_str)
            except ValueError:
                raise ToolError(f"Invalid event type: {event_type_str}", code="invalid_event_type")
            
            # Get event data and metadata
            event_data = arguments.get("event_data", {})
            event_metadata = arguments.get("event_metadata", {})
            test_mode = arguments.get("test_mode", True)
            
            # Create event
            import uuid
            from .events import Event
            
            event_id = str(uuid.uuid4())
            if test_mode:
                event_id = f"test-{event_id}"
            
            event = Event(
                event_type=event_type,
                event_id=event_id,
                data=event_data,
                metadata=event_metadata,
            )
            
            # Emit event
            await self.webhook_manager.emit_event(event)
            
            # Get matching subscriptions for feedback
            matching_count = 0
            for subscription in self.webhook_manager.get_subscriptions():
                if not subscription["active"]:
                    continue
                    
                subscription_event_types = {EventType(et) for et in subscription["event_types"]}
                if not subscription_event_types or event_type in subscription_event_types:
                    matching_count += 1
            
            return ToolResult.success(
                text=f"Event {event_type.value} emitted successfully to {matching_count} webhooks",
                data={
                    "event_id": event_id,
                    "event_type": event_type.value,
                    "test_mode": test_mode,
                    "matching_webhooks": matching_count,
                    "event_data": event_data,
                    "event_metadata": event_metadata,
                },
                metadata={
                    "operation": "event_emit",
                    "event_id": event_id,
                },
            )
            
        except ToolError:
            raise
        except Exception as e:
            self.logger.error("Event notification error", error=str(e), exc_info=True)
            raise ToolError(
                f"Event notification failed: {str(e)}",
                code="internal_error",
            )