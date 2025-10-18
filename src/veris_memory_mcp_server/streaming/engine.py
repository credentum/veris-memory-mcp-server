"""
Streaming engine for handling large context operations.

Provides efficient streaming interfaces for large datasets and
batch processing capabilities for bulk operations.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

import structlog

from ..client.veris_client import VerisMemoryClient, VerisMemoryClientError

logger = structlog.get_logger(__name__)


@dataclass
class StreamChunk:
    """Individual chunk of streamed data."""

    sequence: int
    data: Dict[str, Any]
    is_final: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "sequence": self.sequence,
            "data": self.data,
            "is_final": self.is_final,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


@dataclass
class BatchResult:
    """Result of batch operation."""

    total_items: int
    successful_items: int
    failed_items: int
    execution_time_ms: float
    results: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_items == 0:
            return 100.0
        return (self.successful_items / self.total_items) * 100.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "total_items": self.total_items,
            "successful_items": self.successful_items,
            "failed_items": self.failed_items,
            "success_rate": self.success_rate,
            "execution_time_ms": self.execution_time_ms,
            "results": self.results,
            "errors": self.errors,
        }


class StreamingEngine:
    """
    Engine for handling streaming and batch operations.

    Provides efficient processing of large datasets through streaming
    and optimized batch operations for bulk context management.
    """

    def __init__(
        self,
        client: VerisMemoryClient,
        chunk_size: int = 1024,
        max_concurrent_streams: int = 10,
        buffer_size: int = 8192,
    ):
        """
        Initialize streaming engine.

        Args:
            client: Veris Memory client instance
            chunk_size: Size of each stream chunk
            max_concurrent_streams: Maximum concurrent streaming operations
            buffer_size: Internal buffer size for streaming
        """
        self.client = client
        self.chunk_size = chunk_size
        self.max_concurrent_streams = max_concurrent_streams
        self.buffer_size = buffer_size

        # Stream management
        self._active_streams: Dict[str, asyncio.Task] = {}
        self._stream_semaphore = asyncio.Semaphore(max_concurrent_streams)

    async def stream_search_results(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        max_results: int = 1000,
        stream_id: Optional[str] = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream search results for large datasets.

        Args:
            query: Search query
            filters: Optional search filters
            max_results: Maximum number of results to stream
            stream_id: Optional stream identifier

        Yields:
            StreamChunk objects containing batched results
        """
        stream_id = stream_id or f"search_{int(time.time())}"

        async with self._stream_semaphore:
            logger.info(
                "Starting streaming search",
                stream_id=stream_id,
                query=query,
                max_results=max_results,
            )

            try:
                # Start with initial batch
                offset = 0
                sequence = 0
                total_results = 0

                while offset < max_results:
                    # Calculate batch size for this chunk
                    batch_size = min(self.chunk_size, max_results - offset)

                    # Perform search with pagination
                    search_filters = filters.copy() if filters else {}
                    search_filters.update(
                        {
                            "offset": offset,
                            "limit": batch_size,
                        }
                    )

                    try:
                        # Get batch of results
                        results = await self.client.search_context(
                            query=query,
                            filters=search_filters,
                            limit=batch_size,
                        )

                        batch_results = results.get("results", [])

                        if not batch_results:
                            break  # No more results

                        total_results += len(batch_results)

                        # Create stream chunk
                        chunk = StreamChunk(
                            sequence=sequence,
                            data={
                                "results": batch_results,
                                "batch_info": {
                                    "offset": offset,
                                    "batch_size": len(batch_results),
                                    "total_so_far": total_results,
                                },
                            },
                            is_final=False,
                            metadata={
                                "stream_id": stream_id,
                                "query": query,
                                "batch_number": sequence + 1,
                            },
                        )

                        yield chunk

                        # Move to next batch
                        offset += batch_size
                        sequence += 1

                        # Check if we got fewer results than requested (end of data)
                        if len(batch_results) < batch_size:
                            break

                        # Small delay to prevent overwhelming the backend
                        await asyncio.sleep(0.01)

                    except Exception as e:
                        logger.error(
                            "Error in streaming search batch",
                            stream_id=stream_id,
                            sequence=sequence,
                            error=str(e),
                        )

                        # Yield error chunk
                        error_chunk = StreamChunk(
                            sequence=sequence,
                            data={
                                "error": str(e),
                                "batch_info": {
                                    "offset": offset,
                                    "failed": True,
                                },
                            },
                            is_final=False,
                            metadata={
                                "stream_id": stream_id,
                                "error": True,
                            },
                        )
                        yield error_chunk
                        break

                # Send final chunk
                final_chunk = StreamChunk(
                    sequence=sequence,
                    data={
                        "summary": {
                            "total_results": total_results,
                            "total_chunks": sequence,
                            "query": query,
                        }
                    },
                    is_final=True,
                    metadata={
                        "stream_id": stream_id,
                        "completed": True,
                    },
                )
                yield final_chunk

                logger.info(
                    "Streaming search completed",
                    stream_id=stream_id,
                    total_results=total_results,
                    total_chunks=sequence + 1,
                )

            except Exception as e:
                logger.error(
                    "Streaming search failed",
                    stream_id=stream_id,
                    error=str(e),
                    exc_info=True,
                )

                # Send error final chunk
                error_final = StreamChunk(
                    sequence=sequence,
                    data={"error": f"Streaming failed: {str(e)}"},
                    is_final=True,
                    metadata={
                        "stream_id": stream_id,
                        "error": True,
                    },
                )
                yield error_final

    async def batch_store_contexts(
        self,
        contexts: List[Dict[str, Any]],
        batch_size: Optional[int] = None,
        max_retries: int = 3,
    ) -> BatchResult:
        """
        Store multiple contexts efficiently in batches.

        Args:
            contexts: List of context data to store
            batch_size: Size of each batch (uses chunk_size if None)
            max_retries: Maximum retries for failed items

        Returns:
            BatchResult with operation summary
        """
        batch_size = batch_size or self.chunk_size
        start_time = time.time()

        logger.info(
            "Starting batch context storage",
            total_contexts=len(contexts),
            batch_size=batch_size,
        )

        successful_results = []
        failed_results = []

        # Process contexts in batches
        for i in range(0, len(contexts), batch_size):
            batch = contexts[i : i + batch_size]
            batch_number = (i // batch_size) + 1

            logger.debug(
                "Processing batch",
                batch_number=batch_number,
                batch_size=len(batch),
            )

            # Process batch items concurrently
            batch_tasks = []
            for j, context in enumerate(batch):
                task = self._store_single_context_with_retry(context, max_retries, i + j)
                batch_tasks.append(task)

            # Wait for batch completion
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            # Categorize results
            for idx, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    failed_results.append(
                        {
                            "index": i + idx,
                            "context": batch[idx],
                            "error": str(result),
                        }
                    )
                else:
                    successful_results.append(
                        {
                            "index": i + idx,
                            "result": result,
                        }
                    )

            # Small delay between batches to prevent overwhelming
            if i + batch_size < len(contexts):
                await asyncio.sleep(0.05)

        execution_time = (time.time() - start_time) * 1000

        batch_result = BatchResult(
            total_items=len(contexts),
            successful_items=len(successful_results),
            failed_items=len(failed_results),
            execution_time_ms=execution_time,
            results=successful_results,
            errors=failed_results,
        )

        logger.info(
            "Batch storage completed",
            total_items=batch_result.total_items,
            successful=batch_result.successful_items,
            failed=batch_result.failed_items,
            success_rate=batch_result.success_rate,
            execution_time_ms=batch_result.execution_time_ms,
        )

        return batch_result

    async def _store_single_context_with_retry(
        self,
        context: Dict[str, Any],
        max_retries: int,
        index: int,
    ) -> Dict[str, Any]:
        """Store single context with retry logic."""
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                result = await self.client.store_context(
                    context_type=context.get("context_type", "unknown"),
                    content=context.get("content", {}),
                    metadata=context.get("metadata", {}),
                )

                return result

            except VerisMemoryClientError as e:
                last_error = e
                if attempt < max_retries:
                    # Exponential backoff
                    delay = (2**attempt) * 0.1
                    await asyncio.sleep(delay)
                    logger.debug(
                        "Retrying context storage",
                        index=index,
                        attempt=attempt + 1,
                        delay=delay,
                    )
                else:
                    logger.warning(
                        "Context storage failed after retries",
                        index=index,
                        attempts=attempt + 1,
                        error=str(e),
                    )

        raise last_error or Exception("Storage failed")

    async def batch_update_contexts(
        self,
        updates: List[Dict[str, Any]],
        batch_size: Optional[int] = None,
    ) -> BatchResult:
        """
        Update multiple contexts efficiently.

        Args:
            updates: List of context updates (must include context_id)
            batch_size: Size of each batch

        Returns:
            BatchResult with operation summary
        """
        batch_size = batch_size or self.chunk_size
        start_time = time.time()

        logger.info(
            "Starting batch context updates",
            total_updates=len(updates),
            batch_size=batch_size,
        )

        successful_results = []
        failed_results = []

        # Process updates in batches
        for i in range(0, len(updates), batch_size):
            batch = updates[i : i + batch_size]

            # Process batch items concurrently
            update_tasks = []
            for j, update in enumerate(batch):
                # For now, simulate update operation
                # In real implementation, this would call the backend
                task = self._simulate_update_context(update, i + j)
                update_tasks.append(task)

            # Wait for batch completion
            batch_results = await asyncio.gather(*update_tasks, return_exceptions=True)

            # Categorize results
            for idx, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    failed_results.append(
                        {
                            "index": i + idx,
                            "update": batch[idx],
                            "error": str(result),
                        }
                    )
                else:
                    successful_results.append(
                        {
                            "index": i + idx,
                            "result": result,
                        }
                    )

        execution_time = (time.time() - start_time) * 1000

        return BatchResult(
            total_items=len(updates),
            successful_items=len(successful_results),
            failed_items=len(failed_results),
            execution_time_ms=execution_time,
            results=successful_results,
            errors=failed_results,
        )

    async def _simulate_update_context(self, update: Dict[str, Any], index: int) -> Dict[str, Any]:
        """Simulate context update operation."""
        # Add small random delay to simulate real operation
        await asyncio.sleep(0.01 + (index % 10) * 0.001)

        if "context_id" not in update:
            raise ValueError("context_id is required for updates")

        return {
            "context_id": update["context_id"],
            "updated": True,
            "timestamp": time.time(),
        }

    def get_stream_status(self, stream_id: str) -> Optional[Dict[str, Any]]:
        """Get status of active stream."""
        if stream_id in self._active_streams:
            task = self._active_streams[stream_id]
            return {
                "stream_id": stream_id,
                "active": not task.done(),
                "cancelled": task.cancelled(),
                "exception": str(task.exception()) if task.done() and task.exception() else None,
            }
        return None

    async def cancel_stream(self, stream_id: str) -> bool:
        """Cancel active stream."""
        if stream_id in self._active_streams:
            task = self._active_streams[stream_id]
            if not task.done():
                task.cancel()
                logger.info("Stream cancelled", stream_id=stream_id)
                return True
        return False

    def get_engine_stats(self) -> Dict[str, Any]:
        """Get streaming engine statistics."""
        active_streams = sum(1 for task in self._active_streams.values() if not task.done())

        return {
            "chunk_size": self.chunk_size,
            "max_concurrent_streams": self.max_concurrent_streams,
            "buffer_size": self.buffer_size,
            "active_streams": active_streams,
            "total_registered_streams": len(self._active_streams),
        }
