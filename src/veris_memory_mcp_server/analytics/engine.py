"""
Analytics engine for usage insights and performance analysis.

Provides high-level analytics capabilities, usage statistics,
and performance insights for operational intelligence.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field

# datetime imports removed - not used
from typing import Any, Dict, List, Optional, Tuple

import structlog

from .collector import MetricPoint, MetricsCollector

logger = structlog.get_logger(__name__)


@dataclass
class UsageStats:
    """Usage statistics for a specific time period."""

    timeframe: str
    start_time: float
    end_time: float

    # Operation statistics
    total_operations: int = 0
    successful_operations: int = 0
    failed_operations: int = 0

    # Performance statistics
    avg_response_time_ms: float = 0.0
    p95_response_time_ms: float = 0.0
    p99_response_time_ms: float = 0.0

    # Context operations
    contexts_stored: int = 0
    contexts_retrieved: int = 0
    contexts_searched: int = 0
    contexts_deleted: int = 0

    # Search statistics
    search_queries: int = 0
    avg_search_results: float = 0.0

    # Streaming statistics
    streaming_operations: int = 0
    total_chunks_streamed: int = 0

    # Webhook statistics
    webhooks_delivered: int = 0
    webhook_failures: int = 0

    # Error breakdown
    error_breakdown: Dict[str, int] = field(default_factory=dict)

    # Top operations
    top_operations: List[Tuple[str, int]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        success_rate = (self.successful_operations / max(self.total_operations, 1)) * 100

        return {
            "timeframe": self.timeframe,
            "period": {
                "start_time": self.start_time,
                "end_time": self.end_time,
                "duration_seconds": self.end_time - self.start_time,
            },
            "operations": {
                "total": self.total_operations,
                "successful": self.successful_operations,
                "failed": self.failed_operations,
                "success_rate_percent": round(success_rate, 2),
            },
            "performance": {
                "avg_response_time_ms": round(self.avg_response_time_ms, 2),
                "p95_response_time_ms": round(self.p95_response_time_ms, 2),
                "p99_response_time_ms": round(self.p99_response_time_ms, 2),
            },
            "context_operations": {
                "stored": self.contexts_stored,
                "retrieved": self.contexts_retrieved,
                "searched": self.contexts_searched,
                "deleted": self.contexts_deleted,
            },
            "search": {
                "total_queries": self.search_queries,
                "avg_results_per_query": round(self.avg_search_results, 2),
            },
            "streaming": {
                "operations": self.streaming_operations,
                "total_chunks": self.total_chunks_streamed,
            },
            "webhooks": {
                "delivered": self.webhooks_delivered,
                "failed": self.webhook_failures,
                "success_rate_percent": (
                    round(
                        (
                            self.webhooks_delivered
                            / max(self.webhooks_delivered + self.webhook_failures, 1)
                        )
                        * 100,
                        2,
                    )
                ),
            },
            "errors": {
                "breakdown": self.error_breakdown,
                "total_errors": sum(self.error_breakdown.values()),
            },
            "top_operations": self.top_operations[:10],  # Top 10
        }


@dataclass
class PerformanceInsights:
    """Performance insights and recommendations."""

    timeframe: str
    insights: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    performance_score: float = 0.0

    def add_insight(
        self,
        category: str,
        title: str,
        description: str,
        severity: str = "info",
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a performance insight."""
        self.insights.append(
            {
                "category": category,
                "title": title,
                "description": description,
                "severity": severity,
                "data": data or {},
                "timestamp": time.time(),
            }
        )

    def add_recommendation(
        self,
        title: str,
        description: str,
        impact: str,
        effort: str,
        priority: int = 1,
        action_items: Optional[List[str]] = None,
    ) -> None:
        """Add a performance recommendation."""
        self.recommendations.append(
            {
                "title": title,
                "description": description,
                "impact": impact,
                "effort": effort,
                "priority": priority,
                "action_items": action_items or [],
                "timestamp": time.time(),
            }
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "timeframe": self.timeframe,
            "performance_score": round(self.performance_score, 2),
            "insights": self.insights,
            "recommendations": sorted(
                self.recommendations,
                key=lambda r: r["priority"],
                reverse=True,
            ),
            "summary": {
                "total_insights": len(self.insights),
                "total_recommendations": len(self.recommendations),
                "high_priority_recommendations": len(
                    [r for r in self.recommendations if r["priority"] >= 8]
                ),
            },
        }


class AnalyticsEngine:
    """
    Advanced analytics engine for usage insights and performance analysis.

    Provides comprehensive analytics capabilities including usage statistics,
    performance insights, and operational recommendations.
    """

    def __init__(self, metrics_collector: MetricsCollector):
        """
        Initialize analytics engine.

        Args:
            metrics_collector: Metrics collector instance
        """
        self.metrics_collector = metrics_collector
        self._cached_stats: Dict[str, Tuple[float, UsageStats]] = {}
        self._cache_ttl_seconds = 300  # 5 minutes

    async def get_usage_stats(
        self,
        timeframe: str = "1h",
        use_cache: bool = True,
    ) -> UsageStats:
        """
        Get usage statistics for specified timeframe.

        Args:
            timeframe: Time period (1h, 6h, 24h, 7d, 30d)
            use_cache: Whether to use cached results

        Returns:
            Usage statistics for the timeframe
        """
        # Check cache first
        if use_cache and timeframe in self._cached_stats:
            cached_time, cached_stats = self._cached_stats[timeframe]
            if time.time() - cached_time < self._cache_ttl_seconds:
                return cached_stats

        # Calculate time range
        end_time = time.time()
        start_time = self._get_start_time(timeframe, end_time)

        # Create stats object
        stats = UsageStats(
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
        )

        # Get metrics for timeframe
        metrics = self.metrics_collector.get_metrics(since=start_time)

        # Analyze metrics
        await self._analyze_operations(metrics, stats)
        await self._analyze_performance(metrics, stats)
        await self._analyze_context_operations(metrics, stats)
        await self._analyze_search_operations(metrics, stats)
        await self._analyze_streaming(metrics, stats)
        await self._analyze_webhooks(metrics, stats)
        await self._analyze_errors(metrics, stats)

        # Cache results
        self._cached_stats[timeframe] = (time.time(), stats)

        logger.info(
            "Usage stats calculated",
            timeframe=timeframe,
            total_operations=stats.total_operations,
            success_rate=(stats.successful_operations / max(stats.total_operations, 1)) * 100,
        )

        return stats

    async def get_performance_insights(
        self,
        timeframe: str = "1h",
    ) -> PerformanceInsights:
        """
        Generate performance insights and recommendations.

        Args:
            timeframe: Time period to analyze

        Returns:
            Performance insights and recommendations
        """
        insights = PerformanceInsights(timeframe=timeframe)

        # Get usage stats for analysis
        stats = await self.get_usage_stats(timeframe)

        # Generate insights
        await self._generate_performance_insights(stats, insights)
        await self._generate_error_insights(stats, insights)
        await self._generate_usage_insights(stats, insights)
        await self._generate_recommendations(stats, insights)

        # Calculate performance score
        insights.performance_score = self._calculate_performance_score(stats)

        logger.info(
            "Performance insights generated",
            timeframe=timeframe,
            performance_score=insights.performance_score,
            insights_count=len(insights.insights),
            recommendations_count=len(insights.recommendations),
        )

        return insights

    async def get_real_time_metrics(self) -> Dict[str, Any]:
        """Get real-time operational metrics."""
        current_time = time.time()
        last_5_minutes = current_time - 300

        recent_metrics = self.metrics_collector.get_metrics(since=last_5_minutes)

        # Calculate real-time stats
        total_ops = len([m for m in recent_metrics if m.name == "operation_total"])

        recent_durations = [m.value for m in recent_metrics if m.name == "operation_duration_ms"]

        avg_duration = sum(recent_durations) / len(recent_durations) if recent_durations else 0

        # Error rate
        errors = len(
            [
                m
                for m in recent_metrics
                if m.name == "operation_total" and m.labels.get("success") == "false"
            ]
        )
        error_rate = (errors / max(total_ops, 1)) * 100

        return {
            "timestamp": current_time,
            "window_seconds": 300,
            "operations_per_minute": total_ops / 5,
            "avg_response_time_ms": round(avg_duration, 2),
            "error_rate_percent": round(error_rate, 2),
            "active_operations": len(self.metrics_collector._active_operations),
            "collector_stats": self.metrics_collector.get_stats(),
        }

    async def _analyze_operations(self, metrics: List[MetricPoint], stats: UsageStats) -> None:
        """Analyze operation metrics."""
        operation_counts: defaultdict[str, int] = defaultdict(int)
        successful_ops = 0
        failed_ops = 0

        for metric in metrics:
            if metric.name == "operation_total":
                operation = metric.labels.get("operation", "unknown")
                operation_counts[operation] += int(metric.value)

                if metric.labels.get("success") == "true":
                    successful_ops += int(metric.value)
                else:
                    failed_ops += int(metric.value)

        stats.total_operations = successful_ops + failed_ops
        stats.successful_operations = successful_ops
        stats.failed_operations = failed_ops
        stats.top_operations = sorted(
            operation_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )

    async def _analyze_performance(self, metrics: List[MetricPoint], stats: UsageStats) -> None:
        """Analyze performance metrics."""
        durations = [m.value for m in metrics if m.name == "operation_duration_ms"]

        if durations:
            stats.avg_response_time_ms = sum(durations) / len(durations)
            sorted_durations = sorted(durations)
            stats.p95_response_time_ms = self._percentile(sorted_durations, 0.95)
            stats.p99_response_time_ms = self._percentile(sorted_durations, 0.99)

    async def _analyze_context_operations(
        self,
        metrics: List[MetricPoint],
        stats: UsageStats,
    ) -> None:
        """Analyze context operation metrics."""
        for metric in metrics:
            if metric.name == "operation_total":
                operation = metric.labels.get("operation", "")
                if operation == "store_context":
                    stats.contexts_stored += int(metric.value)
                elif operation == "retrieve_context":
                    stats.contexts_retrieved += int(metric.value)
                elif operation in ("search_context", "streaming_search"):
                    stats.contexts_searched += int(metric.value)
                elif operation == "delete_context":
                    stats.contexts_deleted += int(metric.value)

    async def _analyze_search_operations(
        self,
        metrics: List[MetricPoint],
        stats: UsageStats,
    ) -> None:
        """Analyze search operation metrics."""
        search_results = []

        for metric in metrics:
            if metric.name == "search_results_count":
                search_results.append(metric.value)
                stats.search_queries += 1

        if search_results:
            stats.avg_search_results = sum(search_results) / len(search_results)

    async def _analyze_streaming(self, metrics: List[MetricPoint], stats: UsageStats) -> None:
        """Analyze streaming metrics."""
        for metric in metrics:
            if metric.name == "stream_chunks_delivered":
                stats.total_chunks_streamed += int(metric.value)
            elif metric.name == "operation_total" and "streaming" in metric.labels.get(
                "operation", ""
            ):
                stats.streaming_operations += int(metric.value)

    async def _analyze_webhooks(self, metrics: List[MetricPoint], stats: UsageStats) -> None:
        """Analyze webhook metrics."""
        for metric in metrics:
            if metric.name == "webhook_delivery":
                if metric.labels.get("status") == "success":
                    stats.webhooks_delivered += int(metric.value)
                else:
                    stats.webhook_failures += int(metric.value)

    async def _analyze_errors(self, metrics: List[MetricPoint], stats: UsageStats) -> None:
        """Analyze error metrics."""
        for metric in metrics:
            if metric.name == "operation_total" and metric.labels.get("success") == "false":
                error_type = metric.labels.get("error_type", "unknown")
                stats.error_breakdown[error_type] = stats.error_breakdown.get(error_type, 0) + int(
                    metric.value
                )

    async def _generate_performance_insights(
        self,
        stats: UsageStats,
        insights: PerformanceInsights,
    ) -> None:
        """Generate performance-related insights."""
        # High response time insight
        if stats.avg_response_time_ms > 1000:
            insights.add_insight(
                category="performance",
                title="High Average Response Time",
                description=f"Average response time is {stats.avg_response_time_ms:.0f}ms, which is above recommended thresholds",
                severity="warning",
                data={"avg_response_time_ms": stats.avg_response_time_ms},
            )

        # P99 latency insight
        if stats.p99_response_time_ms > 5000:
            insights.add_insight(
                category="performance",
                title="High P99 Latency",
                description=f"99th percentile response time is {stats.p99_response_time_ms:.0f}ms",
                severity="critical",
                data={"p99_response_time_ms": stats.p99_response_time_ms},
            )

        # Operation volume insight
        if stats.total_operations > 1000:
            insights.add_insight(
                category="usage",
                title="High Operation Volume",
                description=f"Processed {stats.total_operations} operations in {stats.timeframe}",
                severity="info",
                data={"total_operations": stats.total_operations},
            )

    async def _generate_error_insights(
        self,
        stats: UsageStats,
        insights: PerformanceInsights,
    ) -> None:
        """Generate error-related insights."""
        error_rate = (stats.failed_operations / max(stats.total_operations, 1)) * 100

        if error_rate > 5:
            insights.add_insight(
                category="reliability",
                title="High Error Rate",
                description=f"Error rate is {error_rate:.1f}%, which exceeds recommended threshold of 5%",
                severity="critical" if error_rate > 10 else "warning",
                data={
                    "error_rate_percent": error_rate,
                    "failed_operations": stats.failed_operations,
                    "total_operations": stats.total_operations,
                },
            )

        # Top error types
        if stats.error_breakdown:
            top_error = max(stats.error_breakdown.items(), key=lambda x: x[1])
            if top_error[1] > 10:
                insights.add_insight(
                    category="reliability",
                    title="Frequent Error Type",
                    description=f"'{top_error[0]}' errors occurred {top_error[1]} times",
                    severity="warning",
                    data={"error_type": top_error[0], "count": top_error[1]},
                )

    async def _generate_usage_insights(
        self,
        stats: UsageStats,
        insights: PerformanceInsights,
    ) -> None:
        """Generate usage-related insights."""
        # Search efficiency
        if stats.search_queries > 0 and stats.avg_search_results < 1:
            insights.add_insight(
                category="usage",
                title="Low Search Result Rate",
                description=f"Search queries return an average of {stats.avg_search_results:.1f} results",
                severity="info",
                data={"avg_search_results": stats.avg_search_results},
            )

        # Webhook delivery issues
        if stats.webhook_failures > 0:
            failure_rate = (
                stats.webhook_failures / max(stats.webhooks_delivered + stats.webhook_failures, 1)
            ) * 100

            if failure_rate > 10:
                insights.add_insight(
                    category="webhooks",
                    title="Webhook Delivery Issues",
                    description=f"Webhook failure rate is {failure_rate:.1f}%",
                    severity="warning",
                    data={
                        "failure_rate_percent": failure_rate,
                        "failed_deliveries": stats.webhook_failures,
                    },
                )

    async def _generate_recommendations(
        self,
        stats: UsageStats,
        insights: PerformanceInsights,
    ) -> None:
        """Generate actionable recommendations."""
        # Performance recommendations
        if stats.avg_response_time_ms > 1000:
            insights.add_recommendation(
                title="Optimize Response Times",
                description="Response times are higher than optimal. Consider caching and performance tuning.",
                impact="high",
                effort="medium",
                priority=8,
                action_items=[
                    "Enable response caching",
                    "Review database query performance",
                    "Consider connection pooling",
                    "Monitor resource utilization",
                ],
            )

        # Error rate recommendations
        error_rate = (stats.failed_operations / max(stats.total_operations, 1)) * 100
        if error_rate > 5:
            insights.add_recommendation(
                title="Reduce Error Rate",
                description="High error rate indicates reliability issues that need attention.",
                impact="critical",
                effort="high",
                priority=9,
                action_items=[
                    "Investigate top error types",
                    "Improve error handling",
                    "Add retry mechanisms",
                    "Enhance monitoring and alerting",
                ],
            )

        # Usage optimization
        if stats.streaming_operations == 0 and stats.total_operations > 100:
            insights.add_recommendation(
                title="Consider Streaming for Large Operations",
                description="High operation volume could benefit from streaming capabilities.",
                impact="medium",
                effort="low",
                priority=6,
                action_items=[
                    "Enable streaming search for large result sets",
                    "Use batch operations for bulk processing",
                ],
            )

    def _calculate_performance_score(self, stats: UsageStats) -> float:
        """Calculate overall performance score (0-100)."""
        score = 100.0

        # Response time penalty
        if stats.avg_response_time_ms > 500:
            score -= min(30, (stats.avg_response_time_ms - 500) / 100 * 5)

        # Error rate penalty
        error_rate = (stats.failed_operations / max(stats.total_operations, 1)) * 100
        score -= min(40, error_rate * 4)

        # P99 latency penalty
        if stats.p99_response_time_ms > 2000:
            score -= min(20, (stats.p99_response_time_ms - 2000) / 1000 * 5)

        # Webhook delivery penalty
        if stats.webhooks_delivered + stats.webhook_failures > 0:
            webhook_failure_rate = (
                stats.webhook_failures / (stats.webhooks_delivered + stats.webhook_failures)
            ) * 100
            score -= min(10, webhook_failure_rate)

        return max(0, score)

    def _get_start_time(self, timeframe: str, end_time: float) -> float:
        """Calculate start time for given timeframe."""
        timeframe_map = {
            "5m": 300,
            "15m": 900,
            "1h": 3600,
            "6h": 21600,
            "24h": 86400,
            "7d": 604800,
            "30d": 2592000,
        }

        seconds = timeframe_map.get(timeframe, 3600)
        return end_time - seconds

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
