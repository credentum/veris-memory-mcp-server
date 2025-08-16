"""
Webhook delivery system for reliable event notifications.

Handles HTTP delivery of webhook events with retries,
backoff, and delivery tracking.
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import aiohttp
import structlog

from .events import Event

logger = structlog.get_logger(__name__)


class DeliveryStatus(str, Enum):
    """Status of webhook delivery attempts."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    ABANDONED = "abandoned"


@dataclass
class DeliveryAttempt:
    """Record of a single delivery attempt."""

    attempt_number: int
    timestamp: float
    status_code: Optional[int] = None
    response_time_ms: float = 0.0
    error: Optional[str] = None
    response_body: Optional[str] = None


@dataclass
class DeliveryResult:
    """Result of webhook delivery including all attempts."""

    webhook_id: str
    event_id: str
    url: str
    final_status: DeliveryStatus
    attempts: List[DeliveryAttempt] = field(default_factory=list)
    total_duration_ms: float = 0.0
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    @property
    def attempt_count(self) -> int:
        """Number of delivery attempts."""
        return len(self.attempts)

    @property
    def is_successful(self) -> bool:
        """Whether delivery was successful."""
        return self.final_status == DeliveryStatus.SUCCESS

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "webhook_id": self.webhook_id,
            "event_id": self.event_id,
            "url": self.url,
            "final_status": self.final_status.value,
            "attempt_count": self.attempt_count,
            "total_duration_ms": self.total_duration_ms,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "attempts": [
                {
                    "attempt_number": attempt.attempt_number,
                    "timestamp": attempt.timestamp,
                    "status_code": attempt.status_code,
                    "response_time_ms": attempt.response_time_ms,
                    "error": attempt.error,
                    "response_body": attempt.response_body[:500] if attempt.response_body else None,
                }
                for attempt in self.attempts
            ],
        }


class WebhookDelivery:
    """
    Webhook delivery engine with retry logic and backoff.

    Handles reliable delivery of webhook events with configurable
    retry policies and delivery tracking.
    """

    def __init__(
        self,
        max_retries: int = 3,
        initial_backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 60.0,
        backoff_multiplier: float = 2.0,
        timeout_seconds: float = 30.0,
        max_concurrent_deliveries: int = 100,
    ):
        """
        Initialize webhook delivery system.

        Args:
            max_retries: Maximum number of retry attempts
            initial_backoff_seconds: Initial backoff delay
            max_backoff_seconds: Maximum backoff delay
            backoff_multiplier: Backoff multiplier for exponential backoff
            timeout_seconds: HTTP request timeout
            max_concurrent_deliveries: Maximum concurrent delivery attempts
        """
        self.max_retries = max_retries
        self.initial_backoff_seconds = initial_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.backoff_multiplier = backoff_multiplier
        self.timeout_seconds = timeout_seconds

        # Concurrency control
        self._delivery_semaphore = asyncio.Semaphore(max_concurrent_deliveries)

        # Delivery tracking
        self._active_deliveries: Dict[str, asyncio.Task] = {}
        self._delivery_history: List[DeliveryResult] = []
        self._max_history_size = 10000

    async def deliver_event(
        self,
        webhook_id: str,
        url: str,
        event: Event,
        headers: Optional[Dict[str, str]] = None,
        signing_secret: Optional[str] = None,
    ) -> DeliveryResult:
        """
        Deliver event to webhook URL with retry logic.

        Args:
            webhook_id: Unique identifier for the webhook
            url: Target webhook URL
            event: Event to deliver
            headers: Additional HTTP headers
            signing_secret: Secret for webhook signature

        Returns:
            Delivery result with attempt history
        """
        async with self._delivery_semaphore:
            delivery_result = DeliveryResult(
                webhook_id=webhook_id,
                event_id=event.event_id,
                url=url,
                final_status=DeliveryStatus.PENDING,
            )

            try:
                start_time = time.time()

                # Prepare payload and headers
                payload = event.to_webhook_payload(signing_secret)
                delivery_headers = self._prepare_headers(headers)

                logger.info(
                    "Starting webhook delivery",
                    webhook_id=webhook_id,
                    event_id=event.event_id,
                    event_type=event.event_type.value,
                    url=url,
                )

                # Attempt delivery with retries
                success = await self._attempt_delivery_with_retries(
                    delivery_result, url, payload, delivery_headers
                )

                # Update final status
                delivery_result.final_status = (
                    DeliveryStatus.SUCCESS if success else DeliveryStatus.FAILED
                )
                delivery_result.completed_at = time.time()
                delivery_result.total_duration_ms = (
                    delivery_result.completed_at - start_time
                ) * 1000

                # Store in history
                self._add_to_history(delivery_result)

                logger.info(
                    "Webhook delivery completed",
                    webhook_id=webhook_id,
                    event_id=event.event_id,
                    final_status=delivery_result.final_status.value,
                    attempt_count=delivery_result.attempt_count,
                    total_duration_ms=delivery_result.total_duration_ms,
                )

                return delivery_result

            except Exception as e:
                logger.error(
                    "Webhook delivery failed with exception",
                    webhook_id=webhook_id,
                    event_id=event.event_id,
                    error=str(e),
                    exc_info=True,
                )

                delivery_result.final_status = DeliveryStatus.FAILED
                delivery_result.completed_at = time.time()

                # Add error attempt if no attempts recorded
                if not delivery_result.attempts:
                    delivery_result.attempts.append(
                        DeliveryAttempt(
                            attempt_number=1,
                            timestamp=time.time(),
                            error=f"Delivery exception: {str(e)}",
                        )
                    )

                self._add_to_history(delivery_result)
                return delivery_result

    async def _attempt_delivery_with_retries(
        self,
        delivery_result: DeliveryResult,
        url: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> bool:
        """Attempt delivery with exponential backoff retries."""
        for attempt_num in range(1, self.max_retries + 2):  # +1 for initial attempt
            attempt_start = time.time()

            try:
                # Perform HTTP request
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)
                ) as session:
                    async with session.post(
                        url,
                        json=payload,
                        headers=headers,
                    ) as response:
                        response_time_ms = (time.time() - attempt_start) * 1000
                        response_body = await response.text()

                        # Create attempt record
                        attempt = DeliveryAttempt(
                            attempt_number=attempt_num,
                            timestamp=attempt_start,
                            status_code=response.status,
                            response_time_ms=response_time_ms,
                            response_body=response_body[:1000],  # Truncate long responses
                        )

                        delivery_result.attempts.append(attempt)

                        # Check if delivery was successful
                        if 200 <= response.status < 300:
                            logger.debug(
                                "Webhook delivery successful",
                                attempt=attempt_num,
                                status_code=response.status,
                                response_time_ms=response_time_ms,
                            )
                            return True

                        # Log non-success status
                        logger.warning(
                            "Webhook delivery failed",
                            attempt=attempt_num,
                            status_code=response.status,
                            response_time_ms=response_time_ms,
                        )

                        # Don't retry on client errors (4xx)
                        if 400 <= response.status < 500:
                            logger.info(
                                "Abandoning webhook delivery due to client error",
                                status_code=response.status,
                            )
                            delivery_result.final_status = DeliveryStatus.ABANDONED
                            return False

            except asyncio.TimeoutError:
                response_time_ms = (time.time() - attempt_start) * 1000
                attempt = DeliveryAttempt(
                    attempt_number=attempt_num,
                    timestamp=attempt_start,
                    response_time_ms=response_time_ms,
                    error="Request timeout",
                )
                delivery_result.attempts.append(attempt)

                logger.warning(
                    "Webhook delivery timed out",
                    attempt=attempt_num,
                    timeout_seconds=self.timeout_seconds,
                )

            except Exception as e:
                response_time_ms = (time.time() - attempt_start) * 1000
                attempt = DeliveryAttempt(
                    attempt_number=attempt_num,
                    timestamp=attempt_start,
                    response_time_ms=response_time_ms,
                    error=str(e),
                )
                delivery_result.attempts.append(attempt)

                logger.warning(
                    "Webhook delivery attempt failed",
                    attempt=attempt_num,
                    error=str(e),
                )

            # Calculate backoff delay for next attempt
            if attempt_num <= self.max_retries:
                backoff_delay = min(
                    self.initial_backoff_seconds * (self.backoff_multiplier ** (attempt_num - 1)),
                    self.max_backoff_seconds,
                )

                logger.debug(
                    "Retrying webhook delivery",
                    attempt=attempt_num,
                    next_attempt_in_seconds=backoff_delay,
                )

                delivery_result.final_status = DeliveryStatus.RETRYING
                await asyncio.sleep(backoff_delay)

        return False

    def _prepare_headers(
        self, additional_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """Prepare HTTP headers for webhook delivery."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Veris-Memory-MCP-Server/1.0",
            "X-Webhook-Delivery": f"veris-mcp-{int(time.time())}",
        }

        if additional_headers:
            headers.update(additional_headers)

        return headers

    def _add_to_history(self, delivery_result: DeliveryResult) -> None:
        """Add delivery result to history with size management."""
        self._delivery_history.append(delivery_result)

        # Maintain history size limit
        if len(self._delivery_history) > self._max_history_size:
            self._delivery_history = self._delivery_history[-self._max_history_size :]

    def get_delivery_stats(self) -> Dict[str, Any]:
        """Get delivery statistics and metrics."""
        if not self._delivery_history:
            return {
                "total_deliveries": 0,
                "success_rate": 0.0,
                "average_response_time_ms": 0.0,
                "active_deliveries": len(self._active_deliveries),
            }

        total_deliveries = len(self._delivery_history)
        successful_deliveries = sum(1 for result in self._delivery_history if result.is_successful)

        # Calculate average response time from successful attempts
        successful_attempts = [
            attempt
            for result in self._delivery_history
            if result.is_successful
            for attempt in result.attempts
            if attempt.status_code and 200 <= attempt.status_code < 300
        ]

        avg_response_time = (
            (
                sum(attempt.response_time_ms for attempt in successful_attempts)
                / len(successful_attempts)
            )
            if successful_attempts
            else 0.0
        )

        return {
            "total_deliveries": total_deliveries,
            "successful_deliveries": successful_deliveries,
            "failed_deliveries": total_deliveries - successful_deliveries,
            "success_rate": (successful_deliveries / total_deliveries) * 100,
            "average_response_time_ms": avg_response_time,
            "active_deliveries": len(self._active_deliveries),
            "configuration": {
                "max_retries": self.max_retries,
                "timeout_seconds": self.timeout_seconds,
                "max_concurrent_deliveries": self._delivery_semaphore._value,
            },
        }

    def get_recent_deliveries(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent delivery history."""
        recent = self._delivery_history[-limit:] if self._delivery_history else []
        return [result.to_dict() for result in reversed(recent)]

    async def cancel_active_deliveries(self) -> int:
        """Cancel all active deliveries."""
        cancelled_count = 0
        for task in self._active_deliveries.values():
            if not task.done():
                task.cancel()
                cancelled_count += 1

        self._active_deliveries.clear()
        return cancelled_count
