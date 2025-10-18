"""
Analytics tools for MCP server.

Provides tools for accessing usage analytics, performance metrics,
and operational insights through the MCP interface.
"""

from typing import Any, Dict

from ..protocol.schemas import Tool
from ..tools.base import BaseTool, ToolError, ToolResult
from ..client.veris_client import VerisMemoryClient


class AnalyticsTool(BaseTool):
    """
    Tool for accessing usage analytics and performance insights.

    Provides comprehensive analytics capabilities including usage statistics,
    performance insights, and operational recommendations.
    """

    name = "analytics"
    description = "Get usage analytics, performance insights, and operational statistics"

    def __init__(self, veris_client: VerisMemoryClient, config: Dict[str, Any]):
        """
        Initialize analytics tool.

        Args:
            veris_client: Veris Memory client instance
            config: Tool configuration
        """
        super().__init__(config)
        self.veris_client = veris_client

    def get_schema(self) -> Tool:
        """Get the tool schema definition."""
        return self._create_schema(
            parameters={
                "type": self._create_parameter(
                    "string",
                    "Type of analytics to retrieve",
                    required=True,
                    enum=["usage_stats", "performance_insights", "real_time_metrics", "summary"],
                ),
                "timeframe": self._create_parameter(
                    "string",
                    "Time period for analytics (usage_stats and performance_insights only)",
                    required=False,
                    enum=["5m", "15m", "1h", "6h", "24h", "7d", "30d"],
                    default="1h",
                ),
                "include_recommendations": self._create_parameter(
                    "boolean",
                    "Include performance recommendations (performance_insights only)",
                    required=False,
                    default=True,
                ),
            },
            required=["type"],
        )

    async def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Execute analytics request.

        Args:
            arguments: Tool arguments containing analytics type and parameters

        Returns:
            Tool result with analytics data
        """
        analytics_type = arguments["type"]
        timeframe = arguments.get("timeframe", "1h")
        include_recommendations = arguments.get("include_recommendations", True)

        try:
            if analytics_type == "usage_stats":
                return await self._get_usage_stats(timeframe)
            elif analytics_type == "performance_insights":
                return await self._get_performance_insights(timeframe, include_recommendations)
            elif analytics_type == "real_time_metrics":
                return await self._get_real_time_metrics()
            elif analytics_type == "summary":
                return await self._get_analytics_summary(timeframe)
            else:
                raise ToolError(f"Unknown analytics type: {analytics_type}", code="invalid_type")

        except ToolError:
            raise
        except Exception as e:
            self.logger.error("Analytics request failed", error=str(e), exc_info=True)
            raise ToolError(
                f"Analytics request failed: {str(e)}",
                code="internal_error",
            )

    async def _get_usage_stats(self, timeframe: str) -> ToolResult:
        """Get usage statistics for timeframe."""
        stats_data = await self.veris_client.get_analytics("usage_stats", timeframe)

        # Create summary text from API data
        operations = stats_data.get("operations", {})
        context_ops = stats_data.get("context_operations", {})

        summary_lines = [
            f"Usage Statistics for {timeframe}:",
            f"• Total Operations: {operations.get('total', 0):,}",
            f"• Success Rate: {operations.get('success_rate_percent', 0):.1f}%",
            f"• Average Response Time: {stats_data.get('performance', {}).get('avg_response_time_ms', 0):.0f}ms",
        ]

        if context_ops.get("stored", 0) > 0:
            summary_lines.append(f"• Contexts Stored: {context_ops.get('stored', 0):,}")
        if context_ops.get("retrieved", 0) > 0:
            summary_lines.append(f"• Contexts Retrieved: {context_ops.get('retrieved', 0):,}")
        if stats_data.get("search", {}).get("total_queries", 0) > 0:
            summary_lines.append(
                f"• Search Queries: {stats_data.get('search', {}).get('total_queries', 0):,}"
            )

        return ToolResult.success(
            text="\n".join(summary_lines),
            data=stats_data,
            metadata={
                "operation": "usage_stats",
                "timeframe": timeframe,
            },
        )

    async def _get_performance_insights(
        self,
        timeframe: str,
        include_recommendations: bool,
    ) -> ToolResult:
        """Get performance insights and recommendations."""
        insights_data = await self.veris_client.get_analytics(
            "performance_insights", timeframe, include_recommendations
        )

        # Create summary text from API data
        performance_score = insights_data.get("performance_score", 0)
        insights_list = insights_data.get("insights", [])
        recommendations = insights_data.get("recommendations", [])

        summary_lines = [
            f"Performance Insights for {timeframe}:",
            f"• Performance Score: {performance_score:.1f}/100",
            f"• Total Insights: {len(insights_list)}",
        ]

        if include_recommendations:
            summary_lines.append(f"• Recommendations: {len(recommendations)}")

            high_priority = [r for r in recommendations if r.get("priority", 0) >= 8]
            if high_priority:
                summary_lines.append(f"• High Priority Actions: {len(high_priority)}")

        # Add top insights
        if insights_list:
            summary_lines.append("\nTop Insights:")
            for insight in insights_list[:3]:
                summary_lines.append(
                    f"• {insight.get('title', '')} ({insight.get('severity', 'info')})"
                )

        # Add top recommendations
        if include_recommendations and recommendations:
            summary_lines.append("\nTop Recommendations:")
            for rec in recommendations[:3]:
                summary_lines.append(
                    f"• {rec.get('title', '')} (Priority: {rec.get('priority', 0)})"
                )

        data = insights_data.copy()
        if not include_recommendations:
            data.pop("recommendations", None)

        return ToolResult.success(
            text="\n".join(summary_lines),
            data=data,
            metadata={
                "operation": "performance_insights",
                "timeframe": timeframe,
                "performance_score": performance_score,
            },
        )

    async def _get_real_time_metrics(self) -> ToolResult:
        """Get real-time operational metrics."""
        metrics_data = await self.veris_client.get_analytics("real_time_metrics")

        summary_lines = [
            "Real-time Metrics (Last 5 minutes):",
            f"• Operations/min: {metrics_data.get('operations_per_minute', 0):.1f}",
            f"• Avg Response Time: {metrics_data.get('avg_response_time_ms', 0):.0f}ms",
            f"• Error Rate: {metrics_data.get('error_rate_percent', 0):.1f}%",
            f"• Active Operations: {metrics_data.get('active_operations', 0)}",
        ]

        return ToolResult.success(
            text="\n".join(summary_lines),
            data=metrics_data,
            metadata={
                "operation": "real_time_metrics",
                "window_seconds": metrics_data.get("window_seconds", 300),
            },
        )

    async def _get_analytics_summary(self, timeframe: str) -> ToolResult:
        """Get comprehensive analytics summary."""
        # Get comprehensive summary from API
        summary_data = await self.veris_client.get_analytics("summary", timeframe)

        # Extract data from API response
        usage_stats = summary_data.get("usage_stats", {})
        performance_insights = summary_data.get("performance_insights", {})
        real_time_metrics = summary_data.get("real_time_metrics", {})

        operations = usage_stats.get("operations", {})
        context_ops = usage_stats.get("context_operations", {})
        performance = usage_stats.get("performance", {})

        success_rate = operations.get("success_rate_percent", 0)

        summary_lines = [
            f"Analytics Summary for {timeframe}:",
            "",
            "📊 Operations:",
            f"• Total: {operations.get('total', 0):,} operations",
            f"• Success Rate: {success_rate:.1f}%",
            f"• Current Rate: {real_time_metrics.get('operations_per_minute', 0):.1f}/min",
            "",
            "⚡ Performance:",
            f"• Score: {performance_insights.get('performance_score', 0):.1f}/100",
            f"• Avg Response: {performance.get('avg_response_time_ms', 0):.0f}ms",
            f"• P99 Latency: {performance.get('p99_response_time_ms', 0):.0f}ms",
            "",
            "🔍 Context Operations:",
            f"• Stored: {context_ops.get('stored', 0):,}",
            f"• Retrieved: {context_ops.get('retrieved', 0):,}",
            f"• Searched: {context_ops.get('searched', 0):,}",
        ]

        streaming = usage_stats.get("streaming", {})
        if streaming.get("operations", 0) > 0:
            summary_lines.extend(
                [
                    "",
                    "🌊 Streaming:",
                    f"• Operations: {streaming.get('operations', 0):,}",
                    f"• Chunks: {streaming.get('total_chunks', 0):,}",
                ]
            )

        webhooks = usage_stats.get("webhooks", {})
        if webhooks.get("delivered", 0) + webhooks.get("failed", 0) > 0:
            summary_lines.extend(
                [
                    "",
                    "🔔 Webhooks:",
                    f"• Delivered: {webhooks.get('delivered', 0):,}",
                    f"• Success Rate: {webhooks.get('success_rate_percent', 0):.1f}%",
                ]
            )

        recommendations = performance_insights.get("recommendations", [])
        if recommendations:
            high_priority = [r for r in recommendations if r.get("priority", 0) >= 8]
            summary_lines.extend(
                [
                    "",
                    "💡 Recommendations:",
                    f"• Total: {len(recommendations)}",
                    f"• High Priority: {len(high_priority)}",
                ]
            )

            if high_priority:
                summary_lines.append("")
                for rec in high_priority[:2]:
                    summary_lines.append(f"• {rec.get('title', '')}")

        return ToolResult.success(
            text="\n".join(summary_lines),
            data=summary_data,
            metadata={
                "operation": "analytics_summary",
                "timeframe": timeframe,
                "performance_score": performance_insights.get("performance_score", 0),
            },
        )


class MetricsTool(BaseTool):
    """
    Tool for accessing raw metrics and collector statistics.

    Provides direct access to collected metrics data and
    metrics collector operational information.
    """

    name = "metrics"
    description = "Access raw metrics data and collector statistics"

    def __init__(self, veris_client: VerisMemoryClient, config: Dict[str, Any]):
        """
        Initialize metrics tool.

        Args:
            veris_client: Veris Memory client instance
            config: Tool configuration
        """
        super().__init__(config)
        self.veris_client = veris_client

    def get_schema(self) -> Tool:
        """Get the tool schema definition."""
        return self._create_schema(
            parameters={
                "action": self._create_parameter(
                    "string",
                    "Action to perform",
                    required=True,
                    enum=["list_metrics", "get_metrics", "collector_stats", "aggregated_metrics"],
                ),
                "metric_name": self._create_parameter(
                    "string",
                    "Metric name pattern to filter by (get_metrics only)",
                    required=False,
                ),
                "labels": self._create_parameter(
                    "object",
                    "Label filters (get_metrics only)",
                    required=False,
                ),
                "since_minutes": self._create_parameter(
                    "integer",
                    "Get metrics from last N minutes (get_metrics only)",
                    required=False,
                    default=60,
                ),
                "limit": self._create_parameter(
                    "integer",
                    "Maximum number of metric points to return",
                    required=False,
                    default=1000,
                ),
            },
            required=["action"],
        )

    async def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Execute metrics request.

        Args:
            arguments: Tool arguments containing action and parameters

        Returns:
            Tool result with metrics data
        """
        action = arguments["action"]

        try:
            if action == "list_metrics":
                return await self._list_metrics()
            elif action == "get_metrics":
                return await self._get_metrics(arguments)
            elif action == "collector_stats":
                return await self._get_collector_stats()
            elif action == "aggregated_metrics":
                return await self._get_aggregated_metrics()
            else:
                raise ToolError(f"Unknown action: {action}", code="invalid_action")

        except ToolError:
            raise
        except Exception as e:
            self.logger.error("Metrics request failed", error=str(e), exc_info=True)
            raise ToolError(
                f"Metrics request failed: {str(e)}",
                code="internal_error",
            )

    async def _list_metrics(self) -> ToolResult:
        """List available metric names."""
        # Get metrics list from API
        metrics_data = await self.veris_client.get_metrics("list_metrics")

        metric_names = metrics_data.get("metrics", [])
        count = metrics_data.get("count", len(metric_names))

        summary_lines = [f"Available Metrics ({count} unique names):", ""]

        for name in sorted(metric_names):
            summary_lines.append(f"• {name}")

        return ToolResult.success(
            text="\n".join(summary_lines),
            data=metrics_data,
            metadata={"operation": "list_metrics"},
        )

    async def _get_metrics(self, arguments: Dict[str, Any]) -> ToolResult:
        """Get metrics with filtering."""
        metric_name = arguments.get("metric_name")
        labels = arguments.get("labels", {})
        since_minutes = arguments.get("since_minutes", 60)
        limit = arguments.get("limit", 1000)

        # Get metrics from API
        metrics_data = await self.veris_client.get_metrics(
            action="get_metrics",
            metric_name=metric_name,
            labels=labels,
            since_minutes=since_minutes,
            limit=limit,
        )

        metrics_list = metrics_data.get("metrics", [])
        count = metrics_data.get("count", len(metrics_list))

        summary_lines = [
            f"Retrieved {count} metric points",
            f"Time Range: Last {since_minutes} minutes",
        ]

        if metric_name:
            summary_lines.append(f"Metric Pattern: {metric_name}")
        if labels:
            summary_lines.append(f"Labels: {labels}")

        return ToolResult.success(
            text="\n".join(summary_lines),
            data={
                "metrics": metrics_list,
                "count": count,
                "filters": {
                    "metric_name": metric_name,
                    "labels": labels,
                    "since_minutes": since_minutes,
                    "limit": limit,
                },
            },
            metadata={"operation": "get_metrics"},
        )

    async def _get_collector_stats(self) -> ToolResult:
        """Get metrics collector statistics."""
        stats_data = await self.veris_client.get_metrics("collector_stats")

        summary_lines = [
            "Metrics Collector Statistics:",
            f"• Status: {'Running' if stats_data.get('running', False) else 'Stopped'}",
            f"• Uptime: {stats_data.get('uptime_seconds', 0):.0f} seconds",
            f"• Total Points: {stats_data.get('total_points_collected', 0):,}",
            f"• Unique Metrics: {stats_data.get('unique_metrics', 0)}",
            f"• Active Operations: {stats_data.get('active_operations', 0)}",
            f"• Aggregated Metrics: {stats_data.get('aggregated_metrics', 0)}",
        ]

        return ToolResult.success(
            text="\n".join(summary_lines),
            data=stats_data,
            metadata={"operation": "collector_stats"},
        )

    async def _get_aggregated_metrics(self) -> ToolResult:
        """Get aggregated metrics data."""
        aggregated_data = await self.veris_client.get_metrics("aggregated_metrics")

        aggregated = aggregated_data.get("data", {})
        count = len(aggregated) if isinstance(aggregated, dict) else 0

        summary_lines = [f"Aggregated Metrics ({count} metrics):", ""]

        if isinstance(aggregated, dict):
            for metric_key, data in list(aggregated.items())[:10]:  # Show top 10
                if isinstance(data, dict):
                    metric_type = data.get("type", "unknown")
                    if metric_type == "counter":
                        summary_lines.append(f"• {metric_key}: {data.get('sum', 0)} total")
                    elif metric_type == "gauge":
                        summary_lines.append(f"• {metric_key}: {data.get('current', 0)} current")
                    elif metric_type in ("histogram", "timer"):
                        avg = data.get("avg", 0)
                        summary_lines.append(f"• {metric_key}: {avg:.2f} avg")
                else:
                    summary_lines.append(f"• {metric_key}: {data}")

            if count > 10:
                summary_lines.append(f"... and {count - 10} more")

        return ToolResult.success(
            text="\n".join(summary_lines),
            data=aggregated_data,
            metadata={"operation": "aggregated_metrics"},
        )
