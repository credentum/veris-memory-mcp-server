"""
Webhook management system for event subscriptions and delivery.

Manages webhook registrations, event filtering, and
coordinated delivery of notifications.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Union

import structlog

from .delivery import WebhookDelivery, DeliveryResult
from .events import Event, EventType


logger = structlog.get_logger(__name__)


@dataclass
class WebhookSubscription:
    """Webhook subscription configuration."""
    
    webhook_id: str
    url: str
    event_types: Set[EventType]
    active: bool = True
    headers: Dict[str, str] = field(default_factory=dict)
    signing_secret: Optional[str] = None
    description: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_delivery_at: Optional[float] = None
    delivery_count: int = 0
    failure_count: int = 0
    
    def matches_event(self, event: Event) -> bool:
        """Check if this subscription should receive the event."""
        return (
            self.active and
            (not self.event_types or event.event_type in self.event_types)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "webhook_id": self.webhook_id,
            "url": self.url,
            "event_types": [et.value for et in self.event_types],
            "active": self.active,
            "headers": self.headers,
            "description": self.description,
            "created_at": self.created_at,
            "last_delivery_at": self.last_delivery_at,
            "delivery_count": self.delivery_count,
            "failure_count": self.failure_count,
            "success_rate": (
                ((self.delivery_count - self.failure_count) / self.delivery_count * 100)
                if self.delivery_count > 0 else 100.0
            ),
        }


class WebhookManager:
    """
    Central webhook management system.
    
    Manages webhook subscriptions, event routing, and delivery
    coordination for real-time notifications.
    """
    
    def __init__(
        self,
        delivery_engine: Optional[WebhookDelivery] = None,
        max_subscriptions: int = 1000,
        event_buffer_size: int = 10000,
    ):
        """
        Initialize webhook manager.
        
        Args:
            delivery_engine: Webhook delivery engine (creates default if None)
            max_subscriptions: Maximum number of webhook subscriptions
            event_buffer_size: Size of event buffer for reliability
        """
        self.delivery_engine = delivery_engine or WebhookDelivery()
        self.max_subscriptions = max_subscriptions
        self.event_buffer_size = event_buffer_size
        
        # Subscription management
        self._subscriptions: Dict[str, WebhookSubscription] = {}
        self._subscription_lock = asyncio.Lock()
        
        # Event processing
        self._event_queue: asyncio.Queue = asyncio.Queue(maxsize=event_buffer_size)
        self._processing_task: Optional[asyncio.Task] = None
        self._is_running = False
        
        # Statistics
        self._events_processed = 0
        self._events_delivered = 0
        self._events_failed = 0
        self._start_time = time.time()
    
    async def start(self) -> None:
        """Start the webhook manager event processing."""
        if self._is_running:
            return
        
        self._is_running = True
        self._processing_task = asyncio.create_task(self._process_events())
        
        logger.info(
            "Webhook manager started",
            max_subscriptions=self.max_subscriptions,
            event_buffer_size=self.event_buffer_size,
        )
    
    async def stop(self) -> None:
        """Stop the webhook manager and cleanup resources."""
        if not self._is_running:
            return
        
        self._is_running = False
        
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
        
        # Cancel any active deliveries
        cancelled = await self.delivery_engine.cancel_active_deliveries()
        
        logger.info(
            "Webhook manager stopped",
            cancelled_deliveries=cancelled,
            total_events_processed=self._events_processed,
        )
    
    async def register_webhook(
        self,
        url: str,
        event_types: Optional[List[Union[EventType, str]]] = None,
        headers: Optional[Dict[str, str]] = None,
        signing_secret: Optional[str] = None,
        description: Optional[str] = None,
        webhook_id: Optional[str] = None,
    ) -> str:
        """
        Register a new webhook subscription.
        
        Args:
            url: Webhook URL to deliver events to
            event_types: List of event types to subscribe to (all if None)
            headers: Additional HTTP headers for delivery
            signing_secret: Secret for webhook signature verification
            description: Optional description for the webhook
            webhook_id: Optional custom webhook ID
            
        Returns:
            Webhook ID for managing the subscription
            
        Raises:
            ValueError: If subscription limit exceeded or invalid parameters
        """
        async with self._subscription_lock:
            # Check subscription limit
            if len(self._subscriptions) >= self.max_subscriptions:
                raise ValueError(f"Maximum subscriptions limit ({self.max_subscriptions}) exceeded")
            
            # Generate webhook ID
            webhook_id = webhook_id or str(uuid.uuid4())
            
            # Validate URL
            if not url or not url.startswith(('http://', 'https://')):\n                raise ValueError(\"Invalid webhook URL - must start with http:// or https://\")\n            \n            # Convert event types\n            parsed_event_types = set()\n            if event_types:\n                for et in event_types:\n                    if isinstance(et, str):\n                        try:\n                            parsed_event_types.add(EventType(et))\n                        except ValueError:\n                            raise ValueError(f\"Invalid event type: {et}\")\n                    elif isinstance(et, EventType):\n                        parsed_event_types.add(et)\n                    else:\n                        raise ValueError(f\"Event type must be string or EventType, got {type(et)}\")\n            \n            # Create subscription\n            subscription = WebhookSubscription(\n                webhook_id=webhook_id,\n                url=url,\n                event_types=parsed_event_types,\n                headers=headers or {},\n                signing_secret=signing_secret,\n                description=description,\n            )\n            \n            self._subscriptions[webhook_id] = subscription\n            \n            logger.info(\n                \"Webhook registered\",\n                webhook_id=webhook_id,\n                url=url,\n                event_types=[et.value for et in parsed_event_types],\n                description=description,\n            )\n            \n            return webhook_id\n    \n    async def unregister_webhook(self, webhook_id: str) -> bool:\n        \"\"\"Unregister a webhook subscription.\"\"\"\n        async with self._subscription_lock:\n            subscription = self._subscriptions.pop(webhook_id, None)\n            if subscription:\n                logger.info(\n                    \"Webhook unregistered\",\n                    webhook_id=webhook_id,\n                    url=subscription.url,\n                )\n                return True\n            return False\n    \n    async def update_webhook(\n        self,\n        webhook_id: str,\n        url: Optional[str] = None,\n        event_types: Optional[List[Union[EventType, str]]] = None,\n        headers: Optional[Dict[str, str]] = None,\n        active: Optional[bool] = None,\n        description: Optional[str] = None,\n    ) -> bool:\n        \"\"\"Update an existing webhook subscription.\"\"\"\n        async with self._subscription_lock:\n            subscription = self._subscriptions.get(webhook_id)\n            if not subscription:\n                return False\n            \n            # Update fields\n            if url is not None:\n                if not url.startswith(('http://', 'https://')):\n                    raise ValueError(\"Invalid webhook URL\")\n                subscription.url = url\n            \n            if event_types is not None:\n                parsed_event_types = set()\n                for et in event_types:\n                    if isinstance(et, str):\n                        parsed_event_types.add(EventType(et))\n                    elif isinstance(et, EventType):\n                        parsed_event_types.add(et)\n                subscription.event_types = parsed_event_types\n            \n            if headers is not None:\n                subscription.headers = headers\n            \n            if active is not None:\n                subscription.active = active\n            \n            if description is not None:\n                subscription.description = description\n            \n            logger.info(\n                \"Webhook updated\",\n                webhook_id=webhook_id,\n                url=subscription.url,\n                active=subscription.active,\n            )\n            \n            return True\n    \n    async def emit_event(self, event: Event) -> None:\n        \"\"\"Emit an event to registered webhooks.\"\"\"\n        if not self._is_running:\n            logger.warning(\n                \"Dropping event - webhook manager not running\",\n                event_id=event.event_id,\n                event_type=event.event_type.value,\n            )\n            return\n        \n        try:\n            # Add event to processing queue\n            await self._event_queue.put(event)\n            self._events_processed += 1\n            \n            logger.debug(\n                \"Event queued for webhook delivery\",\n                event_id=event.event_id,\n                event_type=event.event_type.value,\n                queue_size=self._event_queue.qsize(),\n            )\n            \n        except asyncio.QueueFull:\n            logger.error(\n                \"Event queue full - dropping event\",\n                event_id=event.event_id,\n                event_type=event.event_type.value,\n                queue_size=self._event_queue.qsize(),\n            )\n    \n    async def _process_events(self) -> None:\n        \"\"\"Background task to process events and deliver to webhooks.\"\"\"\n        logger.info(\"Started webhook event processing\")\n        \n        while self._is_running:\n            try:\n                # Get next event from queue\n                event = await asyncio.wait_for(\n                    self._event_queue.get(),\n                    timeout=1.0\n                )\n                \n                # Find matching subscriptions\n                matching_subscriptions = []\n                async with self._subscription_lock:\n                    for subscription in self._subscriptions.values():\n                        if subscription.matches_event(event):\n                            matching_subscriptions.append(subscription)\n                \n                if not matching_subscriptions:\n                    logger.debug(\n                        \"No matching webhooks for event\",\n                        event_id=event.event_id,\n                        event_type=event.event_type.value,\n                    )\n                    continue\n                \n                # Deliver to all matching webhooks concurrently\n                delivery_tasks = []\n                for subscription in matching_subscriptions:\n                    task = asyncio.create_task(\n                        self._deliver_to_webhook(subscription, event)\n                    )\n                    delivery_tasks.append(task)\n                \n                # Wait for all deliveries to complete\n                delivery_results = await asyncio.gather(\n                    *delivery_tasks,\n                    return_exceptions=True\n                )\n                \n                # Update statistics\n                for result in delivery_results:\n                    if isinstance(result, Exception):\n                        self._events_failed += 1\n                        logger.error(\n                            \"Webhook delivery task failed\",\n                            error=str(result),\n                        )\n                    elif isinstance(result, DeliveryResult):\n                        if result.is_successful:\n                            self._events_delivered += 1\n                        else:\n                            self._events_failed += 1\n                \n                logger.debug(\n                    \"Event delivered to webhooks\",\n                    event_id=event.event_id,\n                    webhook_count=len(matching_subscriptions),\n                )\n                \n            except asyncio.TimeoutError:\n                # Timeout waiting for events is normal\n                continue\n            \n            except Exception as e:\n                logger.error(\n                    \"Error processing webhook event\",\n                    error=str(e),\n                    exc_info=True,\n                )\n                await asyncio.sleep(0.1)  # Brief pause on errors\n    \n    async def _deliver_to_webhook(\n        self,\n        subscription: WebhookSubscription,\n        event: Event,\n    ) -> DeliveryResult:\n        \"\"\"Deliver event to a specific webhook subscription.\"\"\"\n        try:\n            # Perform delivery\n            result = await self.delivery_engine.deliver_event(\n                webhook_id=subscription.webhook_id,\n                url=subscription.url,\n                event=event,\n                headers=subscription.headers,\n                signing_secret=subscription.signing_secret,\n            )\n            \n            # Update subscription statistics\n            async with self._subscription_lock:\n                if subscription.webhook_id in self._subscriptions:\n                    subscription.delivery_count += 1\n                    subscription.last_delivery_at = time.time()\n                    \n                    if not result.is_successful:\n                        subscription.failure_count += 1\n            \n            return result\n            \n        except Exception as e:\n            logger.error(\n                \"Failed to deliver webhook\",\n                webhook_id=subscription.webhook_id,\n                url=subscription.url,\n                error=str(e),\n                exc_info=True,\n            )\n            \n            # Update failure count\n            async with self._subscription_lock:\n                if subscription.webhook_id in self._subscriptions:\n                    subscription.delivery_count += 1\n                    subscription.failure_count += 1\n            \n            raise\n    \n    def get_subscriptions(self) -> List[Dict[str, Any]]:\n        \"\"\"Get list of all webhook subscriptions.\"\"\"\n        return [sub.to_dict() for sub in self._subscriptions.values()]\n    \n    def get_subscription(self, webhook_id: str) -> Optional[Dict[str, Any]]:\n        \"\"\"Get details of a specific webhook subscription.\"\"\"\n        subscription = self._subscriptions.get(webhook_id)\n        return subscription.to_dict() if subscription else None\n    \n    def get_stats(self) -> Dict[str, Any]:\n        \"\"\"Get webhook manager statistics.\"\"\"\n        uptime_seconds = time.time() - self._start_time\n        \n        return {\n            \"is_running\": self._is_running,\n            \"uptime_seconds\": uptime_seconds,\n            \"total_subscriptions\": len(self._subscriptions),\n            \"active_subscriptions\": sum(\n                1 for sub in self._subscriptions.values() if sub.active\n            ),\n            \"events_processed\": self._events_processed,\n            \"events_delivered\": self._events_delivered,\n            \"events_failed\": self._events_failed,\n            \"events_pending\": self._event_queue.qsize(),\n            \"success_rate\": (\n                (self._events_delivered / max(self._events_processed, 1)) * 100\n            ),\n            \"delivery_stats\": self.delivery_engine.get_delivery_stats(),\n            \"configuration\": {\n                \"max_subscriptions\": self.max_subscriptions,\n                \"event_buffer_size\": self.event_buffer_size,\n            },\n        }"