"""
Analytics tools for MCP server.

Provides tools for accessing usage analytics, performance metrics,
and operational insights through the MCP interface.
"""

import time
from typing import Any, Dict, List

from ..protocol.schemas import Tool
from ..tools.base import BaseTool, ToolError, ToolResult
from .engine import AnalyticsEngine
from .collector import MetricsCollector


class AnalyticsTool(BaseTool):
    """
    Tool for accessing usage analytics and performance insights.
    
    Provides comprehensive analytics capabilities including usage statistics,
    performance insights, and operational recommendations.
    """
    
    name = "analytics"
    description = "Get usage analytics, performance insights, and operational statistics"
    
    def __init__(
        self,
        analytics_engine: AnalyticsEngine,
        config: Dict[str, Any]
    ):
        """
        Initialize analytics tool.
        
        Args:
            analytics_engine: Analytics engine instance
            config: Tool configuration
        """
        super().__init__(config)
        self.analytics_engine = analytics_engine
    
    def get_schema(self) -> Tool:
        """Get the tool schema definition."""
        return self._create_schema(
            parameters={
                "type": self._create_parameter(
                    "string",
                    "Type of analytics to retrieve",
                    required=True,
                    enum=[
                        "usage_stats",
                        "performance_insights", 
                        "real_time_metrics",
                        "summary"
                    ],
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
        stats = await self.analytics_engine.get_usage_stats(timeframe)
        
        # Create summary text
        summary_lines = [
            f"Usage Statistics for {timeframe}:",
            f"• Total Operations: {stats.total_operations:,}",
            f"• Success Rate: {(stats.successful_operations / max(stats.total_operations, 1)) * 100:.1f}%",
            f"• Average Response Time: {stats.avg_response_time_ms:.0f}ms",
        ]
        
        if stats.contexts_stored > 0:
            summary_lines.append(f"• Contexts Stored: {stats.contexts_stored:,}")
        if stats.contexts_searched > 0:
            summary_lines.append(f"• Search Queries: {stats.search_queries:,}")
        if stats.streaming_operations > 0:
            summary_lines.append(f"• Streaming Operations: {stats.streaming_operations:,}")
        
        return ToolResult.success(
            text="\n".join(summary_lines),
            data=stats.to_dict(),
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
        insights = await self.analytics_engine.get_performance_insights(timeframe)
        
        # Create summary text
        summary_lines = [
            f"Performance Insights for {timeframe}:",
            f"• Performance Score: {insights.performance_score:.1f}/100",
            f"• Total Insights: {len(insights.insights)}",
        ]
        
        if include_recommendations:
            summary_lines.append(f"• Recommendations: {len(insights.recommendations)}")
            
            high_priority = [r for r in insights.recommendations if r["priority"] >= 8]
            if high_priority:
                summary_lines.append(f"• High Priority Actions: {len(high_priority)}")
        
        # Add top insights
        if insights.insights:
            summary_lines.append("\nTop Insights:")
            for insight in insights.insights[:3]:
                summary_lines.append(f"• {insight['title']} ({insight['severity']})")
        
        # Add top recommendations
        if include_recommendations and insights.recommendations:
            summary_lines.append("\nTop Recommendations:")
            for rec in insights.recommendations[:3]:
                summary_lines.append(f"• {rec['title']} (Priority: {rec['priority']})")
        
        data = insights.to_dict()
        if not include_recommendations:
            data.pop("recommendations", None)
        
        return ToolResult.success(
            text="\n".join(summary_lines),
            data=data,
            metadata={
                "operation": "performance_insights",
                "timeframe": timeframe,
                "performance_score": insights.performance_score,
            },
        )
    
    async def _get_real_time_metrics(self) -> ToolResult:
        """Get real-time operational metrics."""
        metrics = await self.analytics_engine.get_real_time_metrics()
        
        summary_lines = [
            "Real-time Metrics (Last 5 minutes):",
            f"• Operations/min: {metrics['operations_per_minute']:.1f}",
            f"• Avg Response Time: {metrics['avg_response_time_ms']:.0f}ms",
            f"• Error Rate: {metrics['error_rate_percent']:.1f}%",
            f"• Active Operations: {metrics['active_operations']}",
        ]
        
        return ToolResult.success(
            text="\n".join(summary_lines),
            data=metrics,
            metadata={
                "operation": "real_time_metrics",
                "window_seconds": metrics["window_seconds"],
            },
        )
    
    async def _get_analytics_summary(self, timeframe: str) -> ToolResult:
        """Get comprehensive analytics summary."""
        # Get both usage stats and performance insights
        stats = await self.analytics_engine.get_usage_stats(timeframe)
        insights = await self.analytics_engine.get_performance_insights(timeframe)
        real_time = await self.analytics_engine.get_real_time_metrics()
        
        # Create comprehensive summary
        success_rate = (stats.successful_operations / max(stats.total_operations, 1)) * 100
        
        summary_lines = [
            f"Analytics Summary for {timeframe}:",
            "",
            "📊 Operations:",
            f"• Total: {stats.total_operations:,} operations",
            f"• Success Rate: {success_rate:.1f}%",
            f"• Current Rate: {real_time['operations_per_minute']:.1f}/min",
            "",
            "⚡ Performance:",
            f"• Score: {insights.performance_score:.1f}/100",
            f"• Avg Response: {stats.avg_response_time_ms:.0f}ms",
            f"• P99 Latency: {stats.p99_response_time_ms:.0f}ms",
            "",
            "🔍 Context Operations:",
            f"• Stored: {stats.contexts_stored:,}",
            f"• Retrieved: {stats.contexts_retrieved:,}",
            f"• Searched: {stats.contexts_searched:,}",
        ]
        
        if stats.streaming_operations > 0:
            summary_lines.extend([
                "",
                "🌊 Streaming:",
                f"• Operations: {stats.streaming_operations:,}",
                f"• Chunks: {stats.total_chunks_streamed:,}",
            ])
        
        if stats.webhooks_delivered + stats.webhook_failures > 0:
            webhook_success = (
                stats.webhooks_delivered / 
                max(stats.webhooks_delivered + stats.webhook_failures, 1)
            ) * 100
            summary_lines.extend([
                "",
                "🔔 Webhooks:",
                f"• Delivered: {stats.webhooks_delivered:,}",
                f"• Success Rate: {webhook_success:.1f}%",
            ])
        
        if insights.recommendations:
            high_priority = [r for r in insights.recommendations if r["priority"] >= 8]
            summary_lines.extend([
                "",
                "💡 Recommendations:",
                f"• Total: {len(insights.recommendations)}",
                f"• High Priority: {len(high_priority)}",
            ])
            
            if high_priority:
                summary_lines.append("")
                for rec in high_priority[:2]:
                    summary_lines.append(f"• {rec['title']}")
        
        return ToolResult.success(
            text="\n".join(summary_lines),
            data={
                "usage_stats": stats.to_dict(),
                "performance_insights": insights.to_dict(),
                "real_time_metrics": real_time,
                "summary": {
                    "timeframe": timeframe,
                    "performance_score": insights.performance_score,
                    "success_rate_percent": success_rate,
                    "operations_per_minute": real_time["operations_per_minute"],
                },
            },
            metadata={
                "operation": "analytics_summary",
                "timeframe": timeframe,
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
    
    def __init__(
        self,
        metrics_collector: MetricsCollector,
        config: Dict[str, Any]
    ):
        """
        Initialize metrics tool.
        
        Args:
            metrics_collector: Metrics collector instance
            config: Tool configuration
        """
        super().__init__(config)
        self.metrics_collector = metrics_collector
    
    def get_schema(self) -> Tool:
        """Get the tool schema definition."""
        return self._create_schema(
            parameters={
                "action": self._create_parameter(
                    "string",
                    "Action to perform",
                    required=True,
                    enum=[
                        "list_metrics",
                        "get_metrics",
                        "collector_stats",
                        "aggregated_metrics"
                    ],
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
        # Get unique metric names from recent data
        recent_metrics = self.metrics_collector.get_metrics(
            since=time.time() - 3600  # Last hour
        )
        
        metric_info = {}
        for metric in recent_metrics:
            if metric.name not in metric_info:
                metric_info[metric.name] = {
                    "type": metric.metric_type.value,
                    "count": 0,
                    "labels": set(),
                }
            
            metric_info[metric.name]["count"] += 1
            metric_info[metric.name]["labels"].update(metric.labels.keys())
        
        # Convert sets to lists for JSON serialization
        for info in metric_info.values():
            info["labels"] = sorted(list(info["labels"]))
        
        summary_lines = [
            f"Available Metrics ({len(metric_info)} unique names):",
            ""
        ]
        
        for name, info in sorted(metric_info.items()):
            summary_lines.append(
                f"• {name} ({info['type']}) - {info['count']} points"
            )
        
        return ToolResult.success(
            text="\n".join(summary_lines),
            data={
                "metrics": metric_info,
                "total_unique_metrics": len(metric_info),
            },
            metadata={"operation": "list_metrics"},
        )
    
    async def _get_metrics(self, arguments: Dict[str, Any]) -> ToolResult:
        """Get metrics with filtering."""
        metric_name = arguments.get("metric_name")
        labels = arguments.get("labels", {})
        since_minutes = arguments.get("since_minutes", 60)
        limit = arguments.get("limit", 1000)
        
        since_timestamp = time.time() - (since_minutes * 60)
        
        metrics = self.metrics_collector.get_metrics(
            name_pattern=metric_name,
            labels=labels,
            since=since_timestamp,
        )
        
        # Limit results
        if len(metrics) > limit:
            metrics = metrics[-limit:]  # Get most recent
        
        # Convert to dict format
        metrics_data = [metric.to_dict() for metric in metrics]
        
        summary_lines = [
            f"Retrieved {len(metrics_data)} metric points",
            f"Time Range: Last {since_minutes} minutes",
        ]
        
        if metric_name:
            summary_lines.append(f"Metric Pattern: {metric_name}")
        if labels:
            summary_lines.append(f"Labels: {labels}")
        
        return ToolResult.success(
            text="\n".join(summary_lines),
            data={
                "metrics": metrics_data,
                "count": len(metrics_data),
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
        stats = self.metrics_collector.get_stats()
        
        summary_lines = [
            "Metrics Collector Statistics:",
            f"• Status: {'Running' if stats['running'] else 'Stopped'}",
            f"• Uptime: {stats['uptime_seconds']:.0f} seconds",
            f"• Total Points: {stats['total_points_collected']:,}",
            f"• Unique Metrics: {stats['unique_metrics']}",
            f"• Active Operations: {stats['active_operations']}",
            f"• Aggregated Metrics: {stats['aggregated_metrics']}",
        ]
        
        return ToolResult.success(
            text="\n".join(summary_lines),
            data=stats,
            metadata={"operation": "collector_stats"},
        )
    
    async def _get_aggregated_metrics(self) -> ToolResult:
        """Get aggregated metrics data."""
        aggregated = self.metrics_collector.get_aggregated_metrics()
        
        summary_lines = [
            f"Aggregated Metrics ({len(aggregated)} metrics):",
            ""
        ]
        
        for metric_key, data in list(aggregated.items())[:10]:  # Show top 10
            metric_type = data.get("type", "unknown")
            if metric_type == "counter":
                summary_lines.append(f"• {metric_key}: {data.get('sum', 0)} total")
            elif metric_type == "gauge":
                summary_lines.append(f"• {metric_key}: {data.get('current', 0)} current")
            elif metric_type in ("histogram", "timer"):
                avg = data.get("avg", 0)
                summary_lines.append(f"• {metric_key}: {avg:.2f} avg")
        
        if len(aggregated) > 10:
            summary_lines.append(f"... and {len(aggregated) - 10} more")
        
        return ToolResult.success(
            text="\n".join(summary_lines),
            data={
                "aggregated_metrics": aggregated,
                "count": len(aggregated),
            },
            metadata={"operation": "aggregated_metrics"},
        )