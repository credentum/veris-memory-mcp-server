"""
Metrics collection system for comprehensive operational monitoring.

Collects, aggregates, and stores metrics for performance analysis
and operational insights.
"""

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import structlog

logger = structlog.get_logger(__name__)


class MetricType(str, Enum):
    """Types of metrics that can be collected."""

    # Performance metrics
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"

    # Business metrics
    OPERATION = "operation"
    USAGE = "usage"
    ERROR = "error"


@dataclass
class MetricPoint:
    """Individual metric data point."""

    name: str
    value: Union[int, float]
    metric_type: MetricType
    timestamp: float = field(default_factory=time.time)
    labels: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "name": self.name,
            "value": self.value,
            "type": self.metric_type.value,
            "timestamp": self.timestamp,
            "labels": self.labels,
            "metadata": self.metadata,
        }


@dataclass
class OperationMetrics:
    """Metrics for a specific operation execution."""

    operation: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    success: bool = True
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def complete(self, success: bool = True, error: Optional[Exception] = None) -> None:
        """Mark operation as complete and calculate duration."""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.success = success

        if error:
            self.error_type = type(error).__name__
            self.error_message = str(error)

    def to_metric_points(self) -> List[MetricPoint]:
        """Convert to metric points for collection."""
        base_labels = {
            "operation": self.operation,
            "success": str(self.success).lower(),
        }

        if self.error_type:
            base_labels["error_type"] = self.error_type

        points = []

        # Duration metric
        if self.duration_ms is not None:
            points.append(
                MetricPoint(
                    name="operation_duration_ms",
                    value=self.duration_ms,
                    metric_type=MetricType.HISTOGRAM,
                    labels=base_labels,
                    metadata=self.metadata,
                )
            )

        # Counter metric
        points.append(
            MetricPoint(
                name="operation_total",
                value=1,
                metric_type=MetricType.COUNTER,
                labels=base_labels,
                metadata=self.metadata,
            )
        )

        return points


class MetricsCollector:
    """
    Comprehensive metrics collection system.

    Collects, aggregates, and manages various types of metrics
    for performance monitoring and operational insights.
    """

    def __init__(
        self,
        retention_seconds: int = 3600,  # 1 hour
        max_points_per_metric: int = 10000,
        aggregation_interval_seconds: int = 60,
    ):
        """
        Initialize metrics collector.

        Args:
            retention_seconds: How long to keep metric data
            max_points_per_metric: Maximum points to store per metric
            aggregation_interval_seconds: Interval for metric aggregation
        """
        self.retention_seconds = retention_seconds
        self.max_points_per_metric = max_points_per_metric
        self.aggregation_interval_seconds = aggregation_interval_seconds

        # Storage for raw metric points
        self._raw_metrics: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=max_points_per_metric)
        )

        # Aggregated metrics storage
        self._aggregated_metrics: Dict[str, Dict[str, Any]] = {}

        # Operation tracking
        self._active_operations: Dict[str, OperationMetrics] = {}

        # Background tasks
        self._aggregation_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

        # Statistics
        self._total_points_collected = 0
        self._start_time = time.time()

    async def start(self) -> None:
        """Start the metrics collector background tasks."""
        if self._running:
            return

        self._running = True

        # Start background aggregation
        self._aggregation_task = asyncio.create_task(self._aggregation_loop())

        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info(
            "Metrics collector started",
            retention_seconds=self.retention_seconds,
            aggregation_interval=self.aggregation_interval_seconds,
        )

    async def stop(self) -> None:
        """Stop the metrics collector and cleanup resources."""
        if not self._running:
            return

        self._running = False

        # Cancel background tasks
        if self._aggregation_task:
            self._aggregation_task.cancel()
            try:
                await self._aggregation_task
            except asyncio.CancelledError:
                pass

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info(
            "Metrics collector stopped",
            total_points_collected=self._total_points_collected,
        )

    def record_metric(self, metric: MetricPoint) -> None:
        """Record a single metric point."""
        metric_key = self._get_metric_key(metric.name, metric.labels)
        self._raw_metrics[metric_key].append(metric)
        self._total_points_collected += 1

        logger.debug(
            "Metric recorded",
            name=metric.name,
            value=metric.value,
            type=metric.metric_type.value,
            labels=metric.labels,
        )

    def record_counter(
        self,
        name: str,
        value: Union[int, float] = 1,
        labels: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a counter metric."""
        metric = MetricPoint(
            name=name,
            value=value,
            metric_type=MetricType.COUNTER,
            labels=labels or {},
            metadata=metadata or {},
        )
        self.record_metric(metric)

    def record_gauge(
        self,
        name: str,
        value: Union[int, float],
        labels: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a gauge metric."""
        metric = MetricPoint(
            name=name,
            value=value,
            metric_type=MetricType.GAUGE,
            labels=labels or {},
            metadata=metadata or {},
        )
        self.record_metric(metric)

    def record_histogram(
        self,
        name: str,
        value: Union[int, float],
        labels: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a histogram metric."""
        metric = MetricPoint(
            name=name,
            value=value,
            metric_type=MetricType.HISTOGRAM,
            labels=labels or {},
            metadata=metadata or {},
        )
        self.record_metric(metric)

    def start_operation(
        self,
        operation: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Start tracking an operation.

        Args:
            operation: Operation name
            metadata: Additional metadata

        Returns:
            Operation ID for completion tracking
        """
        import uuid

        operation_id = str(uuid.uuid4())

        self._active_operations[operation_id] = OperationMetrics(
            operation=operation,
            start_time=time.time(),
            metadata=metadata or {},
        )

        return operation_id

    def complete_operation(
        self,
        operation_id: str,
        success: bool = True,
        error: Optional[Exception] = None,
    ) -> None:
        """Complete operation tracking and record metrics."""
        if operation_id not in self._active_operations:
            logger.warning("Unknown operation ID", operation_id=operation_id)
            return

        operation_metrics = self._active_operations.pop(operation_id)
        operation_metrics.complete(success=success, error=error)

        # Record operation metrics
        for point in operation_metrics.to_metric_points():
            self.record_metric(point)

        logger.debug(
            "Operation completed",
            operation=operation_metrics.operation,
            duration_ms=operation_metrics.duration_ms,
            success=operation_metrics.success,
        )

    def get_metrics(
        self,
        name_pattern: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None,
        since: Optional[float] = None,
    ) -> List[MetricPoint]:
        """
        Get collected metrics with optional filtering.

        Args:
            name_pattern: Filter by metric name pattern
            labels: Filter by labels
            since: Filter by timestamp (Unix timestamp)

        Returns:
            List of matching metric points
        """
        results = []

        for metric_key, points in self._raw_metrics.items():
            for point in points:
                # Apply filters
                if name_pattern and name_pattern not in point.name:
                    continue

                if since and point.timestamp < since:
                    continue

                if labels:
                    if not all(point.labels.get(k) == v for k, v in labels.items()):
                        continue

                results.append(point)

        # Sort by timestamp
        results.sort(key=lambda p: p.timestamp)
        return results

    def get_aggregated_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get aggregated metrics data."""
        return self._aggregated_metrics.copy()

    def get_stats(self) -> Dict[str, Any]:
        """Get collector statistics."""
        uptime_seconds = time.time() - self._start_time

        return {
            "running": self._running,
            "uptime_seconds": uptime_seconds,
            "total_points_collected": self._total_points_collected,
            "unique_metrics": len(self._raw_metrics),
            "active_operations": len(self._active_operations),
            "aggregated_metrics": len(self._aggregated_metrics),
            "configuration": {
                "retention_seconds": self.retention_seconds,
                "max_points_per_metric": self.max_points_per_metric,
                "aggregation_interval_seconds": self.aggregation_interval_seconds,
            },
        }

    async def _aggregation_loop(self) -> None:
        """Background task for metric aggregation."""
        logger.info("Started metrics aggregation loop")

        while self._running:
            try:
                await self._perform_aggregation()
                await asyncio.sleep(self.aggregation_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Error in metrics aggregation",
                    error=str(e),
                    exc_info=True,
                )
                await asyncio.sleep(5)  # Brief pause on errors

    async def _cleanup_loop(self) -> None:
        """Background task for cleaning up old metrics."""
        logger.info("Started metrics cleanup loop")

        while self._running:
            try:
                await self._cleanup_old_metrics()
                await asyncio.sleep(self.retention_seconds // 4)  # Check 4x per retention period
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Error in metrics cleanup",
                    error=str(e),
                    exc_info=True,
                )
                await asyncio.sleep(60)  # Pause on errors

    async def _perform_aggregation(self) -> None:
        """Perform metric aggregation."""
        current_time = time.time()
        window_start = current_time - self.aggregation_interval_seconds

        aggregations = {}

        for metric_key, points in self._raw_metrics.items():
            # Get points in current window
            window_points = [p for p in points if p.timestamp >= window_start]

            if not window_points:
                continue

            # Group by metric type for aggregation
            by_type = defaultdict(list)
            for point in window_points:
                by_type[point.metric_type].append(point)

            # Perform aggregation by type
            metric_aggregation = {}

            for metric_type, type_points in by_type.items():
                values = [p.value for p in type_points]

                if metric_type == MetricType.COUNTER:
                    metric_aggregation["sum"] = sum(values)
                    metric_aggregation["count"] = len(values)
                elif metric_type == MetricType.GAUGE:
                    metric_aggregation["current"] = values[-1] if values else 0
                    metric_aggregation["min"] = min(values) if values else 0
                    metric_aggregation["max"] = max(values) if values else 0
                    metric_aggregation["avg"] = sum(values) / len(values) if values else 0
                elif metric_type in (MetricType.HISTOGRAM, MetricType.TIMER):
                    if values:
                        sorted_values = sorted(values)
                        metric_aggregation.update(
                            {
                                "count": len(values),
                                "sum": sum(values),
                                "min": min(values),
                                "max": max(values),
                                "avg": sum(values) / len(values),
                                "p50": self._percentile(sorted_values, 0.5),
                                "p95": self._percentile(sorted_values, 0.95),
                                "p99": self._percentile(sorted_values, 0.99),
                            }
                        )

                metric_aggregation["type"] = metric_type.value
                metric_aggregation["window_start"] = window_start
                metric_aggregation["window_end"] = current_time

            aggregations[metric_key] = metric_aggregation

        # Store aggregations
        self._aggregated_metrics = aggregations

        logger.debug(
            "Metrics aggregated",
            metrics_count=len(aggregations),
            window_seconds=self.aggregation_interval_seconds,
        )

    async def _cleanup_old_metrics(self) -> None:
        """Clean up old metric points."""
        cutoff_time = time.time() - self.retention_seconds
        cleaned_count = 0

        for metric_key in list(self._raw_metrics.keys()):
            points = self._raw_metrics[metric_key]

            # Remove old points
            while points and points[0].timestamp < cutoff_time:
                points.popleft()
                cleaned_count += 1

            # Remove empty metric entries
            if not points:
                del self._raw_metrics[metric_key]

        if cleaned_count > 0:
            logger.debug(
                "Cleaned up old metrics",
                cleaned_points=cleaned_count,
                cutoff_time=cutoff_time,
            )

    def _get_metric_key(self, name: str, labels: Dict[str, str]) -> str:
        """Generate a unique key for a metric with labels."""
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}[{label_str}]" if label_str else name

    def _percentile(self, sorted_values: List[float], percentile: float) -> float:
        """Calculate percentile from sorted values."""
        if not sorted_values:
            return 0.0

        index = percentile * (len(sorted_values) - 1)
        lower_index = int(index)
        upper_index = min(lower_index + 1, len(sorted_values) - 1)

        if lower_index == upper_index:
            return sorted_values[lower_index]

        # Linear interpolation
        weight = index - lower_index
        return sorted_values[lower_index] * (1 - weight) + sorted_values[upper_index] * weight
