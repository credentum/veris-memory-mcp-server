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

from .delivery import DeliveryResult, WebhookDelivery
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
        return self.active and (not self.event_types or event.event_type in self.event_types)

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
                if self.delivery_count > 0
                else 100.0
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
            if not url or not url.startswith(("http://", "https://")):
                raise ValueError("Invalid webhook URL - must start with http:// or https://")

            # Convert event types
            parsed_event_types = set()
            if event_types:
                for et in event_types:
                    if isinstance(et, str):
                        try:
                            parsed_event_types.add(EventType(et))
                        except ValueError:
                            raise ValueError(f"Invalid event type: {et}")
                    elif isinstance(et, EventType):
                        parsed_event_types.add(et)
                    else:
                        raise ValueError(f"Event type must be string or EventType, got {type(et)}")

            # Create subscription
            subscription = WebhookSubscription(
                webhook_id=webhook_id,
                url=url,
                event_types=parsed_event_types,
                headers=headers or {},
                signing_secret=signing_secret,
                description=description,
            )

            self._subscriptions[webhook_id] = subscription

            logger.info(
                "Webhook registered",
                webhook_id=webhook_id,
                url=url,
                event_types=[et.value for et in parsed_event_types],
                description=description,
            )

            return webhook_id

    async def unregister_webhook(self, webhook_id: str) -> bool:
        """Unregister a webhook subscription."""
        async with self._subscription_lock:
            subscription = self._subscriptions.pop(webhook_id, None)
            if subscription:
                logger.info(
                    "Webhook unregistered",
                    webhook_id=webhook_id,
                    url=subscription.url,
                )
                return True
            return False

    async def update_webhook(
        self,
        webhook_id: str,
        url: Optional[str] = None,
        event_types: Optional[List[Union[EventType, str]]] = None,
        headers: Optional[Dict[str, str]] = None,
        active: Optional[bool] = None,
        description: Optional[str] = None,
    ) -> bool:
        """Update an existing webhook subscription."""
        async with self._subscription_lock:
            subscription = self._subscriptions.get(webhook_id)
            if not subscription:
                return False

            # Update fields
            if url is not None:
                if not url.startswith(("http://", "https://")):
                    raise ValueError("Invalid webhook URL")
                subscription.url = url

            if event_types is not None:
                parsed_event_types = set()
                for et in event_types:
                    if isinstance(et, str):
                        parsed_event_types.add(EventType(et))
                    elif isinstance(et, EventType):
                        parsed_event_types.add(et)
                subscription.event_types = parsed_event_types

            if headers is not None:
                subscription.headers = headers

            if active is not None:
                subscription.active = active

            if description is not None:
                subscription.description = description

            logger.info(
                "Webhook updated",
                webhook_id=webhook_id,
                url=subscription.url,
                active=subscription.active,
            )

            return True

    async def emit_event(self, event: Event) -> None:
        """Emit an event to registered webhooks."""
        if not self._is_running:
            logger.warning(
                "Dropping event - webhook manager not running",
                event_id=event.event_id,
                event_type=event.event_type.value,
            )
            return

        try:
            # Add event to processing queue
            await self._event_queue.put(event)
            self._events_processed += 1

            logger.debug(
                "Event queued for webhook delivery",
                event_id=event.event_id,
                event_type=event.event_type.value,
                queue_size=self._event_queue.qsize(),
            )

        except asyncio.QueueFull:
            logger.error(
                "Event queue full - dropping event",
                event_id=event.event_id,
                event_type=event.event_type.value,
                queue_size=self._event_queue.qsize(),
            )

    async def _process_events(self) -> None:
        """Background task to process events and deliver to webhooks."""
        logger.info("Started webhook event processing")

        while self._is_running:
            try:
                # Get next event from queue
                event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)

                # Find matching subscriptions
                matching_subscriptions = []
                async with self._subscription_lock:
                    for subscription in self._subscriptions.values():
                        if subscription.matches_event(event):
                            matching_subscriptions.append(subscription)

                if not matching_subscriptions:
                    logger.debug(
                        "No matching webhooks for event",
                        event_id=event.event_id,
                        event_type=event.event_type.value,
                    )
                    continue

                # Deliver to all matching webhooks concurrently
                delivery_tasks = []
                for subscription in matching_subscriptions:
                    task = asyncio.create_task(self._deliver_to_webhook(subscription, event))
                    delivery_tasks.append(task)

                # Wait for all deliveries to complete
                delivery_results = await asyncio.gather(*delivery_tasks, return_exceptions=True)

                # Update statistics
                for result in delivery_results:
                    if isinstance(result, Exception):
                        self._events_failed += 1
                        logger.error(
                            "Webhook delivery task failed",
                            error=str(result),
                        )
                    elif isinstance(result, DeliveryResult):
                        if result.is_successful:
                            self._events_delivered += 1
                        else:
                            self._events_failed += 1

                logger.debug(
                    "Event delivered to webhooks",
                    event_id=event.event_id,
                    webhook_count=len(matching_subscriptions),
                )

            except asyncio.TimeoutError:
                # Timeout waiting for events is normal
                continue

            except Exception as e:
                logger.error(
                    "Error processing webhook event",
                    error=str(e),
                    exc_info=True,
                )
                await asyncio.sleep(0.1)  # Brief pause on errors

    async def _deliver_to_webhook(
        self,
        subscription: WebhookSubscription,
        event: Event,
    ) -> DeliveryResult:
        """Deliver event to a specific webhook subscription."""
        try:
            # Perform delivery
            result = await self.delivery_engine.deliver_event(
                webhook_id=subscription.webhook_id,
                url=subscription.url,
                event=event,
                headers=subscription.headers,
                signing_secret=subscription.signing_secret,
            )

            # Update subscription statistics
            async with self._subscription_lock:
                if subscription.webhook_id in self._subscriptions:
                    subscription.delivery_count += 1
                    subscription.last_delivery_at = time.time()

                    if not result.is_successful:
                        subscription.failure_count += 1

            return result

        except Exception as e:
            logger.error(
                "Failed to deliver webhook",
                webhook_id=subscription.webhook_id,
                url=subscription.url,
                error=str(e),
                exc_info=True,
            )

            # Update failure count
            async with self._subscription_lock:
                if subscription.webhook_id in self._subscriptions:
                    subscription.delivery_count += 1
                    subscription.failure_count += 1

            raise

    def get_subscriptions(self) -> List[Dict[str, Any]]:
        """Get list of all webhook subscriptions."""
        return [sub.to_dict() for sub in self._subscriptions.values()]

    def get_subscription(self, webhook_id: str) -> Optional[Dict[str, Any]]:
        """Get details of a specific webhook subscription."""
        subscription = self._subscriptions.get(webhook_id)
        return subscription.to_dict() if subscription else None

    def get_stats(self) -> Dict[str, Any]:
        """Get webhook manager statistics."""
        uptime_seconds = time.time() - self._start_time

        return {
            "is_running": self._is_running,
            "uptime_seconds": uptime_seconds,
            "total_subscriptions": len(self._subscriptions),
            "active_subscriptions": sum(1 for sub in self._subscriptions.values() if sub.active),
            "events_processed": self._events_processed,
            "events_delivered": self._events_delivered,
            "events_failed": self._events_failed,
            "events_pending": self._event_queue.qsize(),
            "success_rate": ((self._events_delivered / max(self._events_processed, 1)) * 100),
            "delivery_stats": self.delivery_engine.get_delivery_stats(),
            "configuration": {
                "max_subscriptions": self.max_subscriptions,
                "event_buffer_size": self.event_buffer_size,
            },
        }
