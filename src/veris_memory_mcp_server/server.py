"""
Main Veris Memory MCP Server implementation.

Coordinates all components to provide MCP protocol support for
Claude CLI integration with Veris Memory.
"""

import asyncio
import signal
import sys
from typing import Optional

import structlog

from .client.veris_client import VerisMemoryClient
from .config.settings import Config
from .protocol.handlers import MCPHandler
from .protocol.schemas import ServerInfo
from .protocol.transport import StdioTransport
from .tools.store_context import StoreContextTool
from .tools.retrieve_context import RetrieveContextTool
from .tools.search_context import SearchContextTool
from .tools.delete_context import DeleteContextTool
from .tools.list_context_types import ListContextTypesTool
from .utils.cache import MemoryCache, CachedVerisClient
from .utils.health import (
    HealthChecker,
    create_veris_memory_health_checks,
    create_veris_client_health_check,
    create_cache_health_check,
)


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
        self._tools = {}
        
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
            self.mcp_handler.register_tool(store_tool.get_schema(), store_tool)
            logger.debug("Registered store_context tool")
        
        # Retrieve Context Tool
        if self.config.tools.retrieve_context.enabled:
            retrieve_tool = RetrieveContextTool(
                client_to_use,
                self.config.tools.retrieve_context.dict(),
            )
            self._tools["retrieve_context"] = retrieve_tool
            self.mcp_handler.register_tool(retrieve_tool.get_schema(), retrieve_tool)
            logger.debug("Registered retrieve_context tool")
        
        # Search Context Tool
        if self.config.tools.search_context.enabled:
            search_tool = SearchContextTool(
                client_to_use,
                self.config.tools.search_context.dict(),
            )
            self._tools["search_context"] = search_tool
            self.mcp_handler.register_tool(search_tool.get_schema(), search_tool)
            logger.debug("Registered search_context tool")
        
        # Delete Context Tool
        if self.config.tools.delete_context.enabled:
            delete_tool = DeleteContextTool(
                client_to_use,
                self.config.tools.delete_context.dict(),
            )
            self._tools["delete_context"] = delete_tool
            self.mcp_handler.register_tool(delete_tool.get_schema(), delete_tool)
            logger.debug("Registered delete_context tool")
        
        # List Context Types Tool
        if self.config.tools.list_context_types.enabled:
            list_tool = ListContextTypesTool(
                client_to_use,
                self.config.tools.list_context_types.dict(),
            )
            self._tools["list_context_types"] = list_tool
            self.mcp_handler.register_tool(list_tool.get_schema(), list_tool)
            logger.debug("Registered list_context_types tool")
        
        logger.info(
            "Tools registered successfully",
            enabled_tools=list(self._tools.keys()),
            total_tools=len(self._tools),
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
        
        # Combine with detailed health checks
        return {
            **basic_status,
            "health_status": health_status.to_dict(),
        }