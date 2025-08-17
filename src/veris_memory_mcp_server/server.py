"""
Main Veris Memory MCP Server implementation.

Coordinates all components to provide MCP protocol support for
Claude CLI integration with Veris Memory.
"""

import asyncio
import signal
import sys
from typing import Any, Dict, Optional

import structlog

from .analytics.collector import MetricsCollector
from .analytics.engine import AnalyticsEngine
from .analytics.tools import AnalyticsTool, MetricsTool
from .client.veris_client import VerisMemoryClient
from .config.settings import Config
from .protocol.handlers import MCPHandler
from .protocol.schemas import ServerInfo
from .protocol.transport import StdioTransport
from .streaming.engine import StreamingEngine
from .streaming.tools import BatchOperationsTool, StreamingSearchTool
from .tools.delete_context import DeleteContextTool
from .tools.list_context_types import ListContextTypesTool
from .tools.retrieve_context import RetrieveContextTool
from .tools.search_context import SearchContextTool
from .tools.store_context import StoreContextTool
from .utils.cache import CachedVerisClient, MemoryCache
from .utils.health import (
    HealthChecker,
    create_cache_health_check,
    create_veris_client_health_check,
    create_veris_memory_health_checks,
)
from .webhooks.delivery import WebhookDelivery
from .webhooks.manager import WebhookManager
from .webhooks.tools import EventNotificationTool, WebhookManagementTool

logger = structlog.get_logger(__name__)


class VerisMemoryMCPServer:
    """
    Main MCP server for Veris Memory integration.

    Coordinates protocol handling, tool registration, and transport
    to provide Claude CLI with access to Veris Memory capabilities.
    """

    def __init__(self, config: Config):
        """
        Initialize the MCP server.

        Args:
            config: Server configuration
        """
        self.config = config
        self._running = False
        self._shutdown_event = asyncio.Event()

        # Initialize components
        self.veris_client = VerisMemoryClient(config)

        # Initialize caching if enabled
        self.cache = None
        self.cached_client = self.veris_client
        if config.server.cache_enabled:
            self.cache = MemoryCache(
                default_ttl_seconds=config.server.cache_ttl_seconds,
                max_size=1000,
            )
            self.cached_client = CachedVerisClient(self.veris_client, self.cache)

        # Initialize streaming engine if enabled
        self.streaming_engine = None
        if config.streaming.enabled:
            self.streaming_engine = StreamingEngine(
                client=self.cached_client,
                chunk_size=config.streaming.chunk_size,
                max_concurrent_streams=config.streaming.max_concurrent_streams,
                buffer_size=config.streaming.buffer_size,
            )

        # Initialize analytics system if enabled
        self.metrics_collector = None
        self.analytics_engine = None
        if config.analytics.enabled:
            self.metrics_collector = MetricsCollector(
                retention_seconds=config.analytics.retention_seconds,
                max_points_per_metric=config.analytics.max_points_per_metric,
                aggregation_interval_seconds=config.analytics.aggregation_interval_seconds,
            )
            self.analytics_engine = AnalyticsEngine(self.metrics_collector)

        # Initialize webhook system if enabled
        self.webhook_manager = None
        if config.webhooks.enabled:
            webhook_delivery = WebhookDelivery(
                max_retries=config.webhooks.max_retries,
                initial_backoff_seconds=config.webhooks.initial_backoff_seconds,
                max_backoff_seconds=config.webhooks.max_backoff_seconds,
                timeout_seconds=config.webhooks.timeout_seconds,
                max_concurrent_deliveries=config.webhooks.max_concurrent_deliveries,
            )
            self.webhook_manager = WebhookManager(
                delivery_engine=webhook_delivery,
                max_subscriptions=config.webhooks.max_subscriptions,
                event_buffer_size=config.webhooks.event_buffer_size,
            )

        # Initialize health monitoring
        self.health_checker = create_veris_memory_health_checks()

        self.mcp_handler = MCPHandler(
            server_info=ServerInfo(
                name="veris-memory-mcp-server",
                version=config.version,
            )
        )
        self.transport = StdioTransport()

        # Tool instances
        self._tools: Dict[str, Any] = {}

        # Set up signal handlers
        self._setup_signal_handlers()

    async def start(self) -> None:
        """Start the MCP server."""
        if self._running:
            return

        logger.info("Starting Veris Memory MCP Server")

        try:
            # Connect to Veris Memory
            await self.veris_client.connect()

            # Start metrics collector if enabled
            if self.metrics_collector:
                await self.metrics_collector.start()
                logger.debug("Metrics collector started")

            # Start webhook manager if enabled
            if self.webhook_manager:
                await self.webhook_manager.start()
                logger.debug("Webhook manager started")

            # Set up health checks
            await self._setup_health_checks()

            # Register tools
            await self._register_tools()

            # Set up transport
            self.transport.set_message_handler(self.mcp_handler.handle_request)

            self._running = True

            logger.info(
                "Server started successfully",
                tools_registered=len(self._tools),
                veris_connected=self.veris_client.connected,
                cache_enabled=self.cache is not None,
                streaming_enabled=self.streaming_engine is not None,
                webhooks_enabled=self.webhook_manager is not None,
                analytics_enabled=self.analytics_engine is not None,
                health_checks=len(self.health_checker.get_registered_checks()),
            )

        except Exception as e:
            logger.error("Failed to start server", error=str(e), exc_info=True)
            await self.stop()
            raise

    async def stop(self) -> None:
        """Stop the MCP server."""
        if not self._running:
            return

        logger.info("Stopping Veris Memory MCP Server")

        self._running = False
        self._shutdown_event.set()

        # Stop transport
        await self.transport.stop()

        # Stop webhook manager if enabled
        if self.webhook_manager:
            await self.webhook_manager.stop()
            logger.debug("Webhook manager stopped")

        # Stop metrics collector if enabled
        if self.metrics_collector:
            await self.metrics_collector.stop()
            logger.debug("Metrics collector stopped")

        # Disconnect from Veris Memory
        await self.veris_client.disconnect()

        logger.info("Server stopped")

    async def run_stdio(self) -> None:
        """
        Run the server with stdio transport for Claude CLI.

        This is the main entry point for Claude CLI integration.
        """
        try:
            await self.start()

            # Start transport in background
            transport_task = asyncio.create_task(self.transport.start())

            # Wait for shutdown signal
            try:
                await self._shutdown_event.wait()
            except asyncio.CancelledError:
                logger.info("Server operation cancelled")

            # Clean shutdown
            transport_task.cancel()
            try:
                await transport_task
            except asyncio.CancelledError:
                pass

        except Exception as e:
            logger.error("Server error", error=str(e), exc_info=True)
            raise
        finally:
            await self.stop()

    async def _register_tools(self) -> None:
        """Register all available tools with the MCP handler."""
        logger.info("Registering tools")

        # Use cached client for tools to improve performance
        client_to_use = self.cached_client

        # Store Context Tool
        if self.config.tools.store_context.enabled:
            store_tool = StoreContextTool(
                client_to_use,
                self.config.tools.store_context.dict(),
            )
            self._tools["store_context"] = store_tool
            self.mcp_handler.register_tool(store_tool.get_schema(), store_tool.execute)
            logger.debug("Registered store_context tool")

        # Retrieve Context Tool
        if self.config.tools.retrieve_context.enabled:
            retrieve_tool = RetrieveContextTool(
                client_to_use,
                self.config.tools.retrieve_context.dict(),
            )
            self._tools["retrieve_context"] = retrieve_tool
            logger.error(f"!!!!! REGISTERING RETRIEVE TOOL: {type(retrieve_tool)} !!!!!")
            logger.error(f"!!!!! REGISTERING EXECUTOR: {type(retrieve_tool.execute)} !!!!!")
            logger.error(f"!!!!! IS COROUTINE FUNCTION: {asyncio.iscoroutinefunction(retrieve_tool.execute)} !!!!!")
            self.mcp_handler.register_tool(retrieve_tool.get_schema(), retrieve_tool.execute)
            logger.debug("Registered retrieve_context tool")

        # Search Context Tool
        if self.config.tools.search_context.enabled:
            search_tool = SearchContextTool(
                client_to_use,
                self.config.tools.search_context.dict(),
            )
            self._tools["search_context"] = search_tool
            self.mcp_handler.register_tool(search_tool.get_schema(), search_tool.execute)
            logger.debug("Registered search_context tool")

        # Delete Context Tool
        if self.config.tools.delete_context.enabled:
            delete_tool = DeleteContextTool(
                client_to_use,
                self.config.tools.delete_context.dict(),
            )
            self._tools["delete_context"] = delete_tool
            self.mcp_handler.register_tool(delete_tool.get_schema(), delete_tool.execute)
            logger.debug("Registered delete_context tool")

        # List Context Types Tool
        if self.config.tools.list_context_types.enabled:
            list_tool = ListContextTypesTool(
                client_to_use,
                self.config.tools.list_context_types.dict(),
            )
            self._tools["list_context_types"] = list_tool
            self.mcp_handler.register_tool(list_tool.get_schema(), list_tool.execute)
            logger.debug("Registered list_context_types tool")

        # Advanced streaming tools
        if self.streaming_engine:
            # Streaming Search Tool
            if self.config.tools.streaming_search.enabled:
                streaming_search_tool = StreamingSearchTool(
                    client_to_use,
                    self.streaming_engine,
                    self.config.tools.streaming_search.dict(),
                )
                self._tools["streaming_search"] = streaming_search_tool
                self.mcp_handler.register_tool(
                    streaming_search_tool.get_schema(), streaming_search_tool.execute
                )
                logger.debug("Registered streaming_search tool")

            # Batch Operations Tool
            if self.config.tools.batch_operations.enabled:
                batch_ops_tool = BatchOperationsTool(
                    client_to_use,
                    self.streaming_engine,
                    self.config.tools.batch_operations.dict(),
                )
                self._tools["batch_operations"] = batch_ops_tool
                self.mcp_handler.register_tool(batch_ops_tool.get_schema(), batch_ops_tool.execute)
                logger.debug("Registered batch_operations tool")

        # Webhook management tools
        if self.webhook_manager:
            # Webhook Management Tool
            if self.config.tools.webhook_management.enabled:
                webhook_mgmt_tool = WebhookManagementTool(
                    self.webhook_manager,
                    self.config.tools.webhook_management.dict(),
                )
                self._tools["webhook_management"] = webhook_mgmt_tool
                self.mcp_handler.register_tool(webhook_mgmt_tool.get_schema(), webhook_mgmt_tool.execute)
                logger.debug("Registered webhook_management tool")

            # Event Notification Tool
            if self.config.tools.event_notification.enabled:
                event_notif_tool = EventNotificationTool(
                    self.webhook_manager,
                    self.config.tools.event_notification.dict(),
                )
                self._tools["event_notification"] = event_notif_tool
                self.mcp_handler.register_tool(event_notif_tool.get_schema(), event_notif_tool.execute)
                logger.debug("Registered event_notification tool")

        # Analytics tools
        if self.analytics_engine:
            # Analytics Tool
            if self.config.tools.analytics.enabled:
                analytics_tool = AnalyticsTool(
                    self.analytics_engine,
                    self.config.tools.analytics.dict(),
                )
                self._tools["analytics"] = analytics_tool
                self.mcp_handler.register_tool(analytics_tool.get_schema(), analytics_tool.execute)
                logger.debug("Registered analytics tool")

            # Metrics Tool
            if self.config.tools.metrics.enabled:
                metrics_tool = MetricsTool(
                    self.metrics_collector,
                    self.config.tools.metrics.dict(),
                )
                self._tools["metrics"] = metrics_tool
                self.mcp_handler.register_tool(metrics_tool.get_schema(), metrics_tool.execute)
                logger.debug("Registered metrics tool")

        logger.info(
            "Tools registered successfully",
            enabled_tools=list(self._tools.keys()),
            total_tools=len(self._tools),
            advanced_features={
                "streaming": self.streaming_engine is not None,
                "webhooks": self.webhook_manager is not None,
                "analytics": self.analytics_engine is not None,
            },
        )

    async def _setup_health_checks(self) -> None:
        """Set up health monitoring checks."""
        logger.info("Setting up health checks")

        # Register Veris Memory client health check
        veris_health_check = create_veris_client_health_check(self.veris_client)
        self.health_checker.register_check(
            "veris_connection",
            veris_health_check,
            timeout_seconds=10.0,
            critical=True,
        )

        # Register cache health check if caching is enabled
        if self.cache:
            cache_health_check = create_cache_health_check(self.cache)
            self.health_checker.register_check(
                "cache",
                cache_health_check,
                timeout_seconds=2.0,
                critical=False,  # Cache issues are not critical
            )

        logger.debug(
            "Health checks configured",
            registered_checks=self.health_checker.get_registered_checks(),
        )

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        if sys.platform != "win32":
            # Unix-like systems
            loop = asyncio.get_event_loop()

            def signal_handler(signum: int) -> None:
                logger.info(f"Received signal {signum}, initiating shutdown")
                if self._running:
                    loop.create_task(self.stop())

            signal.signal(signal.SIGINT, lambda s, f: signal_handler(s))
            signal.signal(signal.SIGTERM, lambda s, f: signal_handler(s))

    @property
    def running(self) -> bool:
        """Check if server is running."""
        return self._running

    @property
    def tools(self) -> dict:
        """Get registered tools."""
        return self._tools.copy()

    async def health_check(self) -> dict:
        """
        Perform comprehensive health check of server components.

        Returns:
            Health status information
        """
        # Run all health checks
        health_status = await self.health_checker.run_all_checks()

        # Basic server status
        basic_status = {
            "server_running": self._running,
            "veris_connected": self.veris_client.connected,
            "mcp_initialized": self.mcp_handler.initialized,
            "tools_registered": len(self._tools),
            "enabled_tools": list(self._tools.keys()),
            "cache_enabled": self.cache is not None,
        }

        # Add cache stats if available
        if self.cache:
            basic_status["cache_stats"] = await self.cache.get_stats()

        # Add streaming stats if available
        if self.streaming_engine:
            basic_status["streaming_stats"] = self.streaming_engine.get_engine_stats()

        # Add webhook stats if available
        if self.webhook_manager:
            basic_status["webhook_stats"] = self.webhook_manager.get_stats()

        # Add analytics stats if available
        if self.analytics_engine:
            basic_status["analytics_stats"] = {
                "metrics_collector": self.metrics_collector.get_stats(),
                "real_time_metrics": await self.analytics_engine.get_real_time_metrics(),
            }

        # Combine with detailed health checks
        return {
            **basic_status,
            "health_status": health_status.to_dict(),
        }
