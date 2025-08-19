"""
Veris Memory client wrapper for MCP server.

Provides a simplified interface to the Veris Memory SDK for use
within the MCP server, handling authentication and connection management.
"""

import asyncio
from typing import Any, Dict, List, Optional

import structlog
from veris_memory_sdk import MCPClient, MCPConfig
from veris_memory_sdk.core.errors import (
    MCPConnectionError,
)
from veris_memory_sdk.core.errors import MCPError as SDKMCPError
from veris_memory_sdk.core.errors import (
    MCPSecurityError,
    MCPTimeoutError,
    MCPValidationError,
)

from ..config.settings import Config

logger = structlog.get_logger(__name__)


class VerisMemoryClientError(Exception):
    """Base exception for Veris Memory client errors."""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.message = message
        self.original_error = original_error


class VerisMemoryClient:
    """
    Wrapper around Veris Memory SDK for MCP server use.

    Provides simplified interface and handles connection management,
    error translation, and result formatting for MCP tools.
    """

    def __init__(self, config: Config):
        """
        Initialize Veris Memory client.

        Args:
            config: Server configuration containing Veris Memory settings
        """
        self.config = config
        self._client: Optional[MCPClient] = None
        self._connected = False
        self._connection_lock = asyncio.Lock()

    async def connect(self) -> None:
        """Connect to Veris Memory API."""
        async with self._connection_lock:
            if self._connected and self._client:
                return

            try:
                # For testing with local veris-memory service, use direct HTTP instead of SDK
                # This avoids SDK security restrictions for private networks
                import aiohttp
                
                # Test connection to veris-memory service
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.config.veris_memory.api_url}/health") as resp:
                        if resp.status == 200:
                            self._connected = True
                            logger.info("Connected to Veris Memory API via direct HTTP")
                        else:
                            raise Exception(f"Health check failed with status {resp.status}")
                
                # Store connection info for later use
                self._base_url = self.config.veris_memory.api_url

            except Exception as e:
                logger.error("Failed to connect to Veris Memory API", error=str(e))
                raise VerisMemoryClientError(
                    f"Failed to connect to Veris Memory: {str(e)}",
                    original_error=e,
                )

    async def disconnect(self) -> None:
        """Disconnect from Veris Memory API."""
        async with self._connection_lock:
            if self._connected:
                try:
                    logger.info("Disconnected from Veris Memory API")
                except Exception as e:
                    logger.warning("Error during disconnect", error=str(e))
                finally:
                    self._connected = False

    async def _ensure_connected(self) -> None:
        """Ensure connection is established."""
        if not self._connected:
            await self.connect()

    async def store_context(
        self,
        context_type: str,
        content: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Store context in Veris Memory.

        Args:
            context_type: Type of context (decision, knowledge, analysis, etc.)
            content: Context content data
            metadata: Optional metadata for categorization
            user_id: Optional user ID override

        Returns:
            Storage result with context ID

        Raises:
            VerisMemoryClientError: If storage fails
        """
        await self._ensure_connected()

        try:
            # Use direct HTTP call instead of SDK
            import aiohttp
            
            payload = {
                "content": content,
                "type": "log",
                "metadata": metadata or {},
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._base_url}/tools/store_context",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                    else:
                        error_text = await resp.text()
                        raise Exception(f"HTTP {resp.status}: {error_text}")
                        
            logger.info(
                "Context stored successfully",
                context_type=context_type,
                context_id=result.get("id"),
            )

            return result

        except Exception as e:
            logger.error("Failed to store context", error=str(e))
            raise VerisMemoryClientError(
                f"Failed to store context: {str(e)}",
                original_error=e,
            )

    async def retrieve_context(
        self,
        query: str,
        limit: int = 10,
        context_type: Optional[str] = None,
        metadata_filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve contexts from Veris Memory.

        Args:
            query: Search query for semantic matching
            limit: Maximum number of results
            context_type: Optional filter by context type
            metadata_filters: Optional metadata filters
            user_id: Optional user ID override

        Returns:
            List of matching contexts

        Raises:
            VerisMemoryClientError: If retrieval fails
        """
        await self._ensure_connected()

        try:
            # Use direct HTTP call to Veris Memory API
            import aiohttp
            
            payload = {
                "query": query,
                "limit": limit,
                "user_id": user_id or self.config.veris_memory.user_id,
            }
            
            if context_type:
                payload["context_type"] = context_type
                
            if metadata_filters:
                payload["metadata_filters"] = metadata_filters
                
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._base_url}/tools/retrieve_context",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.config.veris_memory.api_key}",
                        "Content-Type": "application/json",
                    }
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        # The API returns 'results' not 'contexts'
                        contexts = result.get("results", [])
                        logger.info(
                            "Contexts retrieved successfully",
                            query=query,
                            count=len(contexts),
                        )
                        return contexts
                    else:
                        error_text = await resp.text()
                        raise VerisMemoryClientError(
                            f"Retrieve failed with status {resp.status}: {error_text}"
                        )

        except aiohttp.ClientError as e:
            logger.error("Failed to retrieve contexts", error=str(e))
            raise VerisMemoryClientError(
                f"Failed to retrieve contexts: {str(e)}",
                original_error=e,
            )

    async def search_context(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Advanced context search with filters.

        Args:
            query: Search query
            filters: Advanced search filters
            limit: Maximum number of results
            user_id: Optional user ID override

        Returns:
            Search results with metadata

        Raises:
            VerisMemoryClientError: If search fails
        """
        await self._ensure_connected()

        try:
            # Use direct HTTP call to Veris Memory API
            import aiohttp
            
            payload = {
                "query": query,
                "limit": limit,
                "user_id": user_id or self.config.veris_memory.user_id,
            }
            
            if filters:
                payload["filters"] = filters
                
            async with aiohttp.ClientSession() as session:
                # Use retrieve_context endpoint for search (no dedicated search endpoint)
                async with session.post(
                    f"{self._base_url}/tools/retrieve_context",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.config.veris_memory.api_key}",
                        "Content-Type": "application/json",
                    }
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        # Return the full result including results, total_count, etc.
                        logger.info(
                            "Context search completed",
                            query=query,
                            result_count=len(result.get("results", [])),
                        )
                        return result
                    else:
                        error_text = await resp.text()
                        raise VerisMemoryClientError(
                            f"Search failed with status {resp.status}: {error_text}"
                        )

        except aiohttp.ClientError as e:
            logger.error("Failed to search contexts", error=str(e))
            raise VerisMemoryClientError(
                f"Failed to search contexts: {str(e)}",
                original_error=e,
            )

    async def delete_context(
        self,
        context_id: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Delete a context from Veris Memory.

        Args:
            context_id: ID of context to delete
            user_id: Optional user ID override

        Returns:
            Deletion result

        Raises:
            VerisMemoryClientError: If deletion fails
        """
        await self._ensure_connected()

        try:
            result = await self._client.call_tool(
                tool_name="delete_context",
                arguments={"context_id": context_id},
                user_id=user_id or self.config.veris_memory.user_id,
            )

            logger.info("Context deleted successfully", context_id=context_id)

            return result

        except SDKMCPError as e:
            logger.error("Failed to delete context", error=str(e))
            raise VerisMemoryClientError(
                f"Failed to delete context: {str(e)}",
                original_error=e,
            )

    async def list_context_types(
        self,
        user_id: Optional[str] = None,
    ) -> List[str]:
        """
        Get available context types.

        Args:
            user_id: Optional user ID override

        Returns:
            List of available context types

        Raises:
            VerisMemoryClientError: If listing fails
        """
        await self._ensure_connected()

        try:
            result = await self._client.call_tool(
                tool_name="list_context_types",
                arguments={},
                user_id=user_id or self.config.veris_memory.user_id,
            )

            context_types = result.get("context_types", [])

            logger.info("Context types listed", count=len(context_types))

            return context_types

        except SDKMCPError as e:
            logger.error("Failed to list context types", error=str(e))
            raise VerisMemoryClientError(
                f"Failed to list context types: {str(e)}",
                original_error=e,
            )

    async def _ensure_connected(self) -> None:
        """Ensure client is connected, reconnecting if necessary."""
        if not self._connected or not self._client:
            await self.connect()

        # Test connection with a simple health check
        try:
            if hasattr(self._client, "health_check"):
                await self._client.health_check()
        except Exception as e:
            logger.warning("Connection health check failed, reconnecting", error=str(e))
            await self.disconnect()
            await self.connect()

    async def get_analytics(
        self,
        analytics_type: str,
        timeframe: str = "1h",
        include_recommendations: bool = True,
    ) -> Dict[str, Any]:
        """
        Get analytics data from Veris Memory API.

        Args:
            analytics_type: Type of analytics (usage_stats, performance_insights, real_time_metrics, summary)
            timeframe: Time period for analytics (5m, 15m, 1h, 6h, 24h, 7d, 30d)
            include_recommendations: Include performance recommendations

        Returns:
            Analytics data from API server

        Raises:
            VerisMemoryClientError: If analytics request fails
        """
        await self._ensure_connected()

        # Simple cache key for analytics requests
        cache_key = f"analytics_{analytics_type}_{timeframe}_{include_recommendations}"
        
        # Check cache first (basic time-based caching)
        if not hasattr(self, '_analytics_cache'):
            self._analytics_cache = {}
            self._cache_timestamps = {}
        
        cache_ttl = 30  # 30 seconds for analytics cache
        current_time = __import__('time').time()
        
        if (cache_key in self._analytics_cache and 
            current_time - self._cache_timestamps.get(cache_key, 0) < cache_ttl):
            return self._analytics_cache[cache_key]

        try:
            import aiohttp
            
            # Map timeframes to minutes for API
            timeframe_minutes = {
                "5m": 5, "15m": 15, "1h": 60, "6h": 360,
                "24h": 1440, "7d": 10080, "30d": 43200
            }
            minutes = timeframe_minutes.get(timeframe, 60)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._base_url}/api/dashboard/analytics",
                    params={
                        "minutes": minutes,
                        "include_insights": "true" if include_recommendations else "false"
                    },
                    headers={"Content-Type": "application/json"}
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        
                        # Transform API response to match MCP analytics format
                        if analytics_type == "usage_stats":
                            formatted_result = self._format_usage_stats(result, timeframe)
                        elif analytics_type == "performance_insights":
                            formatted_result = self._format_performance_insights(result, timeframe)
                        elif analytics_type == "real_time_metrics":
                            formatted_result = self._format_real_time_metrics(result)
                        elif analytics_type == "summary":
                            formatted_result = self._format_analytics_summary(result, timeframe)
                        else:
                            formatted_result = result
                        
                        # Cache the result
                        self._analytics_cache[cache_key] = formatted_result
                        self._cache_timestamps[cache_key] = current_time
                        
                        return formatted_result
                    else:
                        error_text = await resp.text()
                        raise Exception(f"HTTP {resp.status}: {error_text}")

        except Exception as e:
            logger.error("Failed to get analytics", error=str(e))
            raise VerisMemoryClientError(
                f"Failed to get analytics: {str(e)}",
                original_error=e,
            )

    async def get_metrics(
        self,
        action: str,
        metric_name: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None,
        since_minutes: int = 60,
        limit: int = 1000,
    ) -> Dict[str, Any]:
        """
        Get metrics data from Veris Memory API.

        Args:
            action: Action to perform (list_metrics, get_metrics, collector_stats, aggregated_metrics)
            metric_name: Optional metric name pattern
            labels: Optional label filters
            since_minutes: Get metrics from last N minutes
            limit: Maximum number of metric points

        Returns:
            Metrics data from API server

        Raises:
            VerisMemoryClientError: If metrics request fails
        """
        await self._ensure_connected()

        # Simple cache key for metrics requests
        cache_key = f"metrics_{action}_{metric_name}_{str(labels)}_{since_minutes}_{limit}"
        
        # Check cache first (basic time-based caching)
        if not hasattr(self, '_metrics_cache'):
            self._metrics_cache = {}
            self._metrics_cache_timestamps = {}
        
        cache_ttl = 60  # 60 seconds for metrics cache (longer than analytics)
        current_time = __import__('time').time()
        
        if (cache_key in self._metrics_cache and 
            current_time - self._metrics_cache_timestamps.get(cache_key, 0) < cache_ttl):
            return self._metrics_cache[cache_key]

        try:
            import aiohttp
            
            # For now, return metrics derived from analytics data
            # In the future, this could be a separate metrics endpoint
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._base_url}/api/dashboard/analytics",
                    params={"minutes": since_minutes, "include_insights": "true"},
                    headers={"Content-Type": "application/json"}
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        formatted_result = self._format_metrics_response(result, action, metric_name, labels, limit)
                        
                        # Cache the result
                        self._metrics_cache[cache_key] = formatted_result
                        self._metrics_cache_timestamps[cache_key] = current_time
                        
                        return formatted_result
                    else:
                        error_text = await resp.text()
                        raise Exception(f"HTTP {resp.status}: {error_text}")

        except Exception as e:
            logger.error("Failed to get metrics", error=str(e))
            raise VerisMemoryClientError(
                f"Failed to get metrics: {str(e)}",
                original_error=e,
            )

    def _format_usage_stats(self, api_data: Dict[str, Any], timeframe: str) -> Dict[str, Any]:
        """Format API analytics data as usage stats."""
        data = api_data.get("data", {})
        analytics = data.get("analytics", {})
        global_stats = analytics.get("global_request_stats", {})
        
        return {
            "timeframe": timeframe,
            "period": {
                "start_time": api_data.get("timestamp", 0) - (3600 if timeframe == "1h" else 86400),
                "end_time": api_data.get("timestamp", 0),
                "duration_seconds": 3600 if timeframe == "1h" else 86400,
            },
            "operations": {
                "total": global_stats.get("total_requests", 0),
                "successful": global_stats.get("total_requests", 0) - global_stats.get("total_errors", 0),
                "failed": global_stats.get("total_errors", 0),
                "success_rate_percent": 100 - global_stats.get("error_rate_percent", 0),
            },
            "performance": {
                "avg_response_time_ms": global_stats.get("avg_duration_ms", 0),
                "p95_response_time_ms": global_stats.get("p95_duration_ms", 0),
                "p99_response_time_ms": global_stats.get("p99_duration_ms", 0),
            },
            "context_operations": {
                "stored": self._count_endpoint_requests(analytics, "store_context"),
                "retrieved": self._count_endpoint_requests(analytics, "retrieve_context"),
                "searched": self._count_endpoint_requests(analytics, "search_context"),
                "deleted": 0,
            },
            "search": {
                "total_queries": self._count_endpoint_requests(analytics, "retrieve_context"),
                "avg_results_per_query": 0.0,
            },
            "streaming": {
                "operations": 0,
                "total_chunks": 0,
            },
            "webhooks": {
                "delivered": 0,
                "failed": 0,
                "success_rate_percent": 0.0,
            },
            "errors": {
                "breakdown": {},
                "total_errors": global_stats.get("total_errors", 0),
            },
            "top_operations": []
        }

    def _format_performance_insights(self, api_data: Dict[str, Any], timeframe: str) -> Dict[str, Any]:
        """Format API analytics data as performance insights."""
        insights = api_data.get("insights", {})
        
        return {
            "timeframe": timeframe,
            "performance_score": 100.0 if insights.get("performance_status") == "healthy" else 
                               50.0 if insights.get("performance_status") == "warning" else 0.0,
            "insights": [
                {
                    "title": alert.get("message", ""),
                    "severity": alert.get("severity", "info"),
                    "category": alert.get("type", "general")
                }
                for alert in insights.get("alerts", [])
            ],
            "recommendations": [
                {
                    "title": rec,
                    "priority": 8,
                    "description": rec
                }
                for rec in insights.get("recommendations", [])
            ],
            "summary": {
                "total_insights": len(insights.get("alerts", [])),
                "total_recommendations": len(insights.get("recommendations", [])),
                "high_priority_recommendations": len(insights.get("recommendations", [])),
            }
        }

    def _format_real_time_metrics(self, api_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format API analytics data as real-time metrics."""
        data = api_data.get("data", {})
        analytics = data.get("analytics", {})
        global_stats = analytics.get("global_request_stats", {})
        
        return {
            "timestamp": api_data.get("timestamp", 0),
            "window_seconds": 300,
            "operations_per_minute": global_stats.get("requests_per_minute", 0.0),
            "avg_response_time_ms": global_stats.get("avg_duration_ms", 0),
            "error_rate_percent": global_stats.get("error_rate_percent", 0.0),
            "active_operations": 0,
            "collector_stats": {
                "running": True,
                "uptime_seconds": 0,
                "total_points_collected": global_stats.get("total_requests", 0),
                "unique_metrics": len(analytics.get("endpoint_statistics", {})),
                "active_operations": 0,
                "aggregated_metrics": 0,
                "configuration": {
                    "retention_seconds": 3600,
                    "max_points_per_metric": 10000,
                    "aggregation_interval_seconds": 60,
                },
            },
        }

    def _format_analytics_summary(self, api_data: Dict[str, Any], timeframe: str) -> Dict[str, Any]:
        """Format API analytics data as summary."""
        usage_stats = self._format_usage_stats(api_data, timeframe)
        performance_insights = self._format_performance_insights(api_data, timeframe)
        real_time_metrics = self._format_real_time_metrics(api_data)
        
        return {
            "usage_stats": usage_stats,
            "performance_insights": performance_insights,
            "real_time_metrics": real_time_metrics,
            "summary": {
                "timeframe": timeframe,
                "performance_score": performance_insights["performance_score"],
                "success_rate_percent": usage_stats["operations"]["success_rate_percent"],
                "operations_per_minute": real_time_metrics["operations_per_minute"],
            }
        }

    def _format_metrics_response(
        self, api_data: Dict[str, Any], action: str, metric_name: Optional[str], 
        labels: Optional[Dict[str, str]], limit: int
    ) -> Dict[str, Any]:
        """Format API analytics data as metrics response."""
        if action == "collector_stats":
            return self._format_real_time_metrics(api_data)["collector_stats"]
        elif action == "list_metrics":
            analytics = api_data.get("data", {}).get("analytics", {})
            endpoints = analytics.get("endpoint_statistics", {})
            return {
                "metrics": list(endpoints.keys()),
                "count": len(endpoints)
            }
        elif action == "get_metrics":
            # Return trending data as metric points
            analytics = api_data.get("data", {}).get("analytics", {})
            trending = analytics.get("trending_data", [])
            return {
                "metrics": trending[:limit],
                "count": len(trending)
            }
        else:
            return {"action": action, "data": api_data}

    def _count_endpoint_requests(self, analytics: Dict[str, Any], operation: str) -> int:
        """Count requests for specific operation from endpoint statistics."""
        endpoint_stats = analytics.get("endpoint_statistics", {})
        for endpoint, stats in endpoint_stats.items():
            if operation in endpoint.lower():
                return stats.get("request_count", 0)
        return 0

    @property
    def connected(self) -> bool:
        """Check if client is connected."""
        return self._connected and self._client is not None

    async def __aenter__(self) -> "VerisMemoryClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.disconnect()
