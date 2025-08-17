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
