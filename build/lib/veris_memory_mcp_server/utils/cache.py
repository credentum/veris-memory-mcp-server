"""
Caching utilities for Veris Memory MCP Server.

Provides response caching to improve performance and reduce
API calls to the Veris Memory backend.
"""

import asyncio
import hashlib
import json
import time
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger(__name__)


class CacheItem:
    """Individual cache item with expiration."""

    def __init__(self, value: Any, ttl_seconds: int):
        self.value = value
        self.created_at = time.time()
        self.ttl_seconds = ttl_seconds

    @property
    def is_expired(self) -> bool:
        """Check if cache item has expired."""
        return time.time() - self.created_at > self.ttl_seconds

    @property
    def age_seconds(self) -> float:
        """Get age of cache item in seconds."""
        return time.time() - self.created_at


class MemoryCache:
    """
    In-memory cache with TTL support.

    Provides basic caching functionality for tool responses
    to reduce API calls and improve performance.
    """

    def __init__(self, default_ttl_seconds: int = 300, max_size: int = 1000):
        """
        Initialize memory cache.

        Args:
            default_ttl_seconds: Default TTL for cache items
            max_size: Maximum number of items in cache
        """
        self.default_ttl_seconds = default_ttl_seconds
        self.max_size = max_size
        self._cache: Dict[str, CacheItem] = {}
        self._access_order: list = []  # For LRU eviction
        self._lock = asyncio.Lock()

    def _generate_key(self, operation: str, **kwargs: Any) -> str:
        """
        Generate cache key from operation and parameters.

        Args:
            operation: Operation name (e.g., 'retrieve_context')
            **kwargs: Operation parameters

        Returns:
            Cache key string
        """
        # Create deterministic key from operation and sorted parameters
        params_str = json.dumps(kwargs, sort_keys=True, default=str)
        key_content = f"{operation}:{params_str}"
        return hashlib.sha256(key_content.encode()).hexdigest()[:16]

    async def get(self, operation: str, **kwargs: Any) -> Optional[Any]:
        """
        Get cached value for operation.

        Args:
            operation: Operation name
            **kwargs: Operation parameters

        Returns:
            Cached value or None if not found/expired
        """
        key = self._generate_key(operation, **kwargs)

        async with self._lock:
            if key not in self._cache:
                return None

            item = self._cache[key]

            # Check if expired
            if item.is_expired:
                logger.debug("Cache item expired", key=key, age=item.age_seconds)
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                return None

            # Update access order for LRU
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)

            logger.debug(
                "Cache hit",
                key=key,
                operation=operation,
                age=item.age_seconds,
            )

            return item.value

    async def set(
        self, operation: str, value: Any, ttl_seconds: Optional[int] = None, **kwargs: Any
    ) -> None:
        """
        Set cached value for operation.

        Args:
            operation: Operation name
            value: Value to cache
            ttl_seconds: TTL override (uses default if None)
            **kwargs: Operation parameters
        """
        key = self._generate_key(operation, **kwargs)
        ttl = ttl_seconds or self.default_ttl_seconds

        async with self._lock:
            # Evict if at max size
            if len(self._cache) >= self.max_size and key not in self._cache:
                await self._evict_lru()

            # Store item
            self._cache[key] = CacheItem(value, ttl)

            # Update access order
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)

            logger.debug(
                "Cache set",
                key=key,
                operation=operation,
                ttl=ttl,
                cache_size=len(self._cache),
            )

    async def invalidate(self, operation: str, **kwargs: Any) -> bool:
        """
        Invalidate cached value for operation.

        Args:
            operation: Operation name
            **kwargs: Operation parameters

        Returns:
            True if item was found and removed
        """
        key = self._generate_key(operation, **kwargs)

        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)

                logger.debug("Cache invalidated", key=key, operation=operation)
                return True

            return False

    async def clear(self) -> None:
        """Clear all cached items."""
        async with self._lock:
            self._cache.clear()
            self._access_order.clear()
            logger.info("Cache cleared")

    async def cleanup_expired(self) -> int:
        """
        Remove expired items from cache.

        Returns:
            Number of items removed
        """
        removed_count = 0

        async with self._lock:
            expired_keys = [key for key, item in self._cache.items() if item.is_expired]

            for key in expired_keys:
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                removed_count += 1

            if removed_count > 0:
                logger.debug(
                    "Cleaned up expired cache items",
                    removed_count=removed_count,
                    remaining_count=len(self._cache),
                )

        return removed_count

    async def _evict_lru(self) -> None:
        """Evict least recently used item."""
        if not self._access_order:
            return

        lru_key = self._access_order.pop(0)
        if lru_key in self._cache:
            del self._cache[lru_key]
            logger.debug("Evicted LRU cache item", key=lru_key)

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        async with self._lock:
            total_items = len(self._cache)
            expired_items = sum(1 for item in self._cache.values() if item.is_expired)

            return {
                "total_items": total_items,
                "expired_items": expired_items,
                "active_items": total_items - expired_items,
                "max_size": self.max_size,
                "default_ttl_seconds": self.default_ttl_seconds,
            }


class CachedVerisClient:
    """
    Caching wrapper for Veris Memory client.

    Provides transparent caching for expensive operations
    like context retrieval and search.
    """

    def __init__(self, client, cache: MemoryCache):
        """
        Initialize cached client wrapper.

        Args:
            client: VerisMemoryClient instance to wrap
            cache: Cache instance to use
        """
        self.client = client
        self.cache = cache

        # Operations that should be cached
        self._cacheable_operations = {
            "retrieve_context": 300,  # 5 minutes
            "search_context": 300,  # 5 minutes
            "list_context_types": 900,  # 15 minutes
        }

    def __getattr__(self, name: str):
        """Delegate to wrapped client with caching for eligible operations."""
        attr = getattr(self.client, name)

        if name in self._cacheable_operations and callable(attr):
            return self._create_cached_method(name, attr)

        return attr

    def _create_cached_method(self, operation: str, method):
        """Create cached version of a method."""

        async def cached_method(*args, **kwargs):
            # Try cache first
            cached_result = await self.cache.get(operation, args=args, kwargs=kwargs)
            if cached_result is not None:
                return cached_result

            # Call actual method
            result = await method(*args, **kwargs)

            # Cache result
            ttl = self._cacheable_operations[operation]
            await self.cache.set(operation, result, ttl, args=args, kwargs=kwargs)

            return result

        return cached_method

    async def invalidate_context_cache(self, context_id: Optional[str] = None) -> None:
        """
        Invalidate context-related cache entries.

        Called after operations that modify contexts (store, delete).

        Args:
            context_id: Specific context ID to invalidate (if applicable)
        """
        # For now, clear all retrieve/search cache since we don't have
        # fine-grained cache invalidation
        operations_to_clear = ["retrieve_context", "search_context"]

        for operation in operations_to_clear:
            # Since we can't easily identify all cache keys for an operation,
            # we'll need to implement a more sophisticated cache invalidation
            # strategy in the future. For now, log the intent.
            logger.debug(
                "Context cache invalidation needed",
                operation=operation,
                context_id=context_id,
            )
