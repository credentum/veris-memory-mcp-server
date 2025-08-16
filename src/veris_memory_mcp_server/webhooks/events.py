"""
Event definitions for webhook system.

Defines event types and data structures for
context operations and system notifications.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class EventType(str, Enum):
    """Event types for webhook notifications."""

    # Context events
    CONTEXT_STORED = "context.stored"
    CONTEXT_RETRIEVED = "context.retrieved"
    CONTEXT_UPDATED = "context.updated"
    CONTEXT_DELETED = "context.deleted"
    CONTEXT_SEARCHED = "context.searched"

    # Batch operation events
    BATCH_OPERATION_STARTED = "batch.operation.started"
    BATCH_OPERATION_COMPLETED = "batch.operation.completed"
    BATCH_OPERATION_FAILED = "batch.operation.failed"

    # Streaming events
    STREAM_STARTED = "stream.started"
    STREAM_CHUNK_DELIVERED = "stream.chunk.delivered"
    STREAM_COMPLETED = "stream.completed"
    STREAM_FAILED = "stream.failed"

    # System events
    SERVER_STARTED = "server.started"
    SERVER_STOPPING = "server.stopping"
    HEALTH_CHECK_FAILED = "health.check.failed"
    CACHE_EVICTION = "cache.eviction"

    # Security events
    AUTHENTICATION_FAILED = "auth.failed"
    RATE_LIMIT_EXCEEDED = "rate_limit.exceeded"
    SUSPICIOUS_ACTIVITY = "security.suspicious_activity"


@dataclass
class Event:
    """Base event structure for webhook notifications."""

    event_type: EventType
    event_id: str
    timestamp: float = field(default_factory=time.time)
    source: str = "veris-memory-mcp-server"
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary format."""
        return {
            "event_type": self.event_type.value,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "data": self.data,
            "metadata": self.metadata,
        }

    def to_webhook_payload(self, signing_secret: Optional[str] = None) -> Dict[str, Any]:
        """Convert to webhook payload format with optional signing."""
        payload = self.to_dict()

        if signing_secret:
            import hashlib
            import hmac
            import json

            # Create signature for webhook verification
            payload_str = json.dumps(payload, sort_keys=True)
            signature = hmac.new(
                signing_secret.encode(), payload_str.encode(), hashlib.sha256
            ).hexdigest()

            payload["signature"] = f"sha256={signature}"

        return payload


@dataclass
class ContextEvent(Event):
    """Event for context-related operations."""

    def __init__(
        self,
        event_type: EventType,
        event_id: str,
        context_id: str,
        context_type: str,
        operation_details: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(event_type, event_id, **kwargs)
        self.data.update(
            {
                "context_id": context_id,
                "context_type": context_type,
                "operation_details": operation_details or {},
            }
        )


@dataclass
class BatchEvent(Event):
    """Event for batch operations."""

    def __init__(
        self,
        event_type: EventType,
        event_id: str,
        batch_id: str,
        operation: str,
        total_items: int,
        progress: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(event_type, event_id, **kwargs)
        self.data.update(
            {
                "batch_id": batch_id,
                "operation": operation,
                "total_items": total_items,
                "progress": progress or {},
            }
        )


@dataclass
class StreamEvent(Event):
    """Event for streaming operations."""

    def __init__(
        self,
        event_type: EventType,
        event_id: str,
        stream_id: str,
        operation: str,
        chunk_info: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(event_type, event_id, **kwargs)
        self.data.update(
            {
                "stream_id": stream_id,
                "operation": operation,
                "chunk_info": chunk_info or {},
            }
        )


@dataclass
class SystemEvent(Event):
    """Event for system-level notifications."""

    def __init__(
        self,
        event_type: EventType,
        event_id: str,
        component: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(event_type, event_id, **kwargs)
        self.data.update(
            {
                "component": component,
                "status": status,
                "details": details or {},
            }
        )


@dataclass
class SecurityEvent(Event):
    """Event for security-related notifications."""

    def __init__(
        self,
        event_type: EventType,
        event_id: str,
        security_level: str,  # "info", "warning", "critical"
        client_info: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(event_type, event_id, **kwargs)
        self.data.update(
            {
                "security_level": security_level,
                "client_info": client_info or {},
            }
        )


def create_context_stored_event(
    context_id: str,
    context_type: str,
    content_size: int,
    storage_duration_ms: float,
    event_id: Optional[str] = None,
) -> ContextEvent:
    """Create a context stored event."""
    import uuid

    return ContextEvent(
        event_type=EventType.CONTEXT_STORED,
        event_id=event_id or str(uuid.uuid4()),
        context_id=context_id,
        context_type=context_type,
        operation_details={
            "content_size_bytes": content_size,
            "storage_duration_ms": storage_duration_ms,
        },
    )


def create_context_searched_event(
    query: str,
    results_count: int,
    search_duration_ms: float,
    filters: Optional[Dict[str, Any]] = None,
    event_id: Optional[str] = None,
) -> Event:
    """Create a context searched event."""
    import uuid

    return Event(
        event_type=EventType.CONTEXT_SEARCHED,
        event_id=event_id or str(uuid.uuid4()),
        data={
            "query": query,
            "results_count": results_count,
            "search_duration_ms": search_duration_ms,
            "filters": filters or {},
        },
    )


def create_batch_operation_event(
    event_type: EventType,
    batch_id: str,
    operation: str,
    total_items: int,
    progress: Optional[Dict[str, Any]] = None,
    event_id: Optional[str] = None,
) -> BatchEvent:
    """Create a batch operation event."""
    import uuid

    return BatchEvent(
        event_type=event_type,
        event_id=event_id or str(uuid.uuid4()),
        batch_id=batch_id,
        operation=operation,
        total_items=total_items,
        progress=progress,
    )


def create_stream_event(
    event_type: EventType,
    stream_id: str,
    operation: str,
    chunk_info: Optional[Dict[str, Any]] = None,
    event_id: Optional[str] = None,
) -> StreamEvent:
    """Create a streaming event."""
    import uuid

    return StreamEvent(
        event_type=event_type,
        event_id=event_id or str(uuid.uuid4()),
        stream_id=stream_id,
        operation=operation,
        chunk_info=chunk_info,
    )


def create_system_event(
    event_type: EventType,
    component: str,
    status: str,
    details: Optional[Dict[str, Any]] = None,
    event_id: Optional[str] = None,
) -> SystemEvent:
    """Create a system event."""
    import uuid

    return SystemEvent(
        event_type=event_type,
        event_id=event_id or str(uuid.uuid4()),
        component=component,
        status=status,
        details=details,
    )


def create_security_event(
    event_type: EventType,
    security_level: str,
    client_info: Optional[Dict[str, Any]] = None,
    event_id: Optional[str] = None,
) -> SecurityEvent:
    """Create a security event."""
    import uuid

    return SecurityEvent(
        event_type=event_type,
        event_id=event_id or str(uuid.uuid4()),
        security_level=security_level,
        client_info=client_info,
    )
