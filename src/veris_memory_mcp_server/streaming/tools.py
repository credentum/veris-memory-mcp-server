"""
Streaming-enabled tools for Veris Memory MCP Server.

Implements tools that leverage streaming capabilities for
handling large datasets and batch operations efficiently.
"""

import json
from typing import Any, Dict

from ..client.veris_client import VerisMemoryClient, VerisMemoryClientError
from ..protocol.schemas import Tool
from ..tools.base import BaseTool, ToolError, ToolResult
from .engine import StreamingEngine


class StreamingSearchTool(BaseTool):
    """
    Advanced search tool with streaming capabilities for large result sets.
    
    Provides efficient handling of large search results through streaming
    interface, reducing memory usage and improving response times.
    """
    
    name = "streaming_search"
    description = "Stream large search results efficiently for big datasets and complex queries"
    
    def __init__(self, veris_client: VerisMemoryClient, streaming_engine: StreamingEngine, config: Dict[str, Any]):
        """
        Initialize streaming search tool.
        
        Args:
            veris_client: Veris Memory client instance
            streaming_engine: Streaming engine for large operations
            config: Tool configuration
        """
        super().__init__(config)
        self.veris_client = veris_client
        self.streaming_engine = streaming_engine
        self.max_results = config.get("max_results", 10000)
        self.default_chunk_size = config.get("default_chunk_size", 100)
    
    def get_schema(self) -> Tool:
        """Get the tool schema definition."""
        return self._create_schema(
            parameters={
                "query": self._create_parameter(
                    "string",
                    "Search query for semantic matching against stored contexts",
                    required=True,
                ),
                "filters": self._create_parameter(
                    "object",
                    "Advanced search filters (metadata, date ranges, context types, etc.)",
                    required=False,
                ),
                "max_results": self._create_parameter(
                    "integer",
                    f"Maximum number of results to return (1-{self.max_results})",
                    required=False,
                    default=1000,
                ),
                "streaming": self._create_parameter(
                    "boolean",
                    "Enable streaming mode for large result sets",
                    required=False,
                    default=True,
                ),
                "chunk_size": self._create_parameter(
                    "integer",
                    "Number of results per chunk in streaming mode",
                    required=False,
                    default=self.default_chunk_size,
                ),
            },
            required=["query"],
        )
    
    async def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Execute streaming search operation.
        
        Args:
            arguments: Tool arguments containing query, filters, streaming options
            
        Returns:
            Tool result with search results or streaming information
        """
        query = arguments["query"]
        filters = arguments.get("filters", {})
        max_results = arguments.get("max_results", 1000)
        streaming_enabled = arguments.get("streaming", True)
        chunk_size = arguments.get("chunk_size", self.default_chunk_size)
        
        try:
            # Validate inputs
            if not query.strip():
                raise ToolError("Query cannot be empty", code="empty_query")
            
            if not isinstance(max_results, int) or max_results < 1 or max_results > self.max_results:
                raise ToolError(
                    f"max_results must be between 1 and {self.max_results}",
                    code="invalid_max_results",
                )
            
            if not isinstance(chunk_size, int) or chunk_size < 1 or chunk_size > 1000:
                raise ToolError(
                    "chunk_size must be between 1 and 1000",
                    code="invalid_chunk_size",
                )
            
            # Decide between streaming and regular search
            if streaming_enabled and max_results > chunk_size:
                return await self._execute_streaming_search(
                    query, filters, max_results, chunk_size
                )
            else:
                return await self._execute_regular_search(query, filters, max_results)
        
        except VerisMemoryClientError as e:
            self.logger.error("Veris Memory API error", error=str(e))
            return ToolResult.error(
                f"Search failed: {e.message}",
                error_code="veris_memory_error",
                details={"original_error": str(e.original_error) if e.original_error else None},
            )
        
        except ToolError:
            raise
        
        except Exception as e:
            self.logger.error("Unexpected error in streaming search", error=str(e), exc_info=True)
            raise ToolError(
                f"Search error: {str(e)}",
                code="internal_error",
            )
    
    async def _execute_streaming_search(
        self,
        query: str,
        filters: Dict[str, Any],
        max_results: int,
        chunk_size: int,
    ) -> ToolResult:
        """Execute search with streaming for large result sets."""
        import uuid
        stream_id = str(uuid.uuid4())[:8]
        
        self.logger.info(
            "Starting streaming search",
            query=query,
            max_results=max_results,
            chunk_size=chunk_size,
            stream_id=stream_id,
        )
        
        # Collect all chunks from the stream
        chunks = []
        total_results = 0
        
        try:
            async for chunk in self.streaming_engine.stream_search_results(
                query=query,
                filters=filters,
                max_results=max_results,
                stream_id=stream_id,
            ):
                chunks.append(chunk.to_dict())
                
                # Count results from data chunks (not final summary)
                if not chunk.is_final and "results" in chunk.data:
                    total_results += len(chunk.data["results"])
                
                # Stop if we get the final chunk
                if chunk.is_final:
                    break
            
            # Format comprehensive response
            if chunks:
                # Extract all results from chunks
                all_results = []
                for chunk in chunks:
                    if not chunk["is_final"] and "results" in chunk["data"]:
                        all_results.extend(chunk["data"]["results"])
                
                # Create summary
                summary = f"Streaming search completed for '{query}'"
                if total_results > 0:
                    summary += f" - Found {total_results} results in {len(chunks)} chunks"
                else:
                    summary += " - No results found"
                
                return ToolResult.success(
                    text=summary,
                    data={
                        "query": query,
                        "streaming_mode": True,
                        "stream_id": stream_id,
                        "total_results": total_results,
                        "total_chunks": len(chunks),
                        "results": all_results[:100],  # Limit display results
                        "full_results_available": total_results > 100,
                        "streaming_summary": {
                            "chunks_processed": len(chunks),
                            "chunk_size": chunk_size,
                            "max_results": max_results,
                        }
                    },
                    metadata={
                        "operation": "streaming_search",
                        "stream_id": stream_id,
                        "total_results": total_results,
                    },
                )
            else:
                return ToolResult.error(
                    "Streaming search failed - no chunks received",
                    error_code="streaming_failed",
                )
        
        except Exception as e:
            self.logger.error(
                "Streaming search failed",
                stream_id=stream_id,
                error=str(e),
                exc_info=True,
            )
            return ToolResult.error(
                f"Streaming search failed: {str(e)}",
                error_code="streaming_error",
                details={"stream_id": stream_id},
            )
    
    async def _execute_regular_search(
        self,
        query: str,
        filters: Dict[str, Any],
        max_results: int,
    ) -> ToolResult:
        """Execute regular (non-streaming) search."""
        self.logger.info(
            "Starting regular search",
            query=query,
            max_results=max_results,
        )
        
        # Use existing search functionality
        result = await self.veris_client.search_context(
            query=query,
            filters=filters,
            limit=max_results,
        )
        
        results = result.get("results", [])
        
        return ToolResult.success(
            text=f"Search completed for '{query}' - Found {len(results)} results",
            data={
                "query": query,
                "streaming_mode": False,
                "results": results,
                "total_results": len(results),
                "search_metadata": result.get("metadata", {}),
            },
            metadata={
                "operation": "regular_search",
                "total_results": len(results),
            },
        )


class BatchOperationsTool(BaseTool):
    """
    Tool for efficient batch operations on multiple contexts.
    
    Provides bulk storage, updates, and deletions with
    optimized performance and comprehensive error handling.
    """
    
    name = "batch_operations"
    description = "Perform bulk operations on multiple contexts efficiently"
    
    def __init__(self, veris_client: VerisMemoryClient, streaming_engine: StreamingEngine, config: Dict[str, Any]):
        """
        Initialize batch operations tool.
        
        Args:
            veris_client: Veris Memory client instance
            streaming_engine: Streaming engine for batch processing
            config: Tool configuration
        """
        super().__init__(config)
        self.veris_client = veris_client
        self.streaming_engine = streaming_engine
        self.max_batch_size = config.get("max_batch_size", 1000)
        self.default_batch_size = config.get("default_batch_size", 50)
    
    def get_schema(self) -> Tool:
        """Get the tool schema definition."""
        return self._create_schema(
            parameters={
                "operation": self._create_parameter(
                    "string",
                    "Type of batch operation to perform",
                    required=True,
                    enum=["store", "update", "delete"],
                ),
                "items": self._create_parameter(
                    "array",
                    "Array of items to process in the batch operation",
                    required=True,
                ),
                "batch_size": self._create_parameter(
                    "integer",
                    f"Number of items to process per batch (1-{self.max_batch_size})",
                    required=False,
                    default=self.default_batch_size,
                ),
                "max_retries": self._create_parameter(
                    "integer",
                    "Maximum number of retries for failed items",
                    required=False,
                    default=3,
                ),
                "continue_on_error": self._create_parameter(
                    "boolean",
                    "Continue processing if some items fail",
                    required=False,
                    default=True,
                ),
            },
            required=["operation", "items"],
        )
    
    async def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Execute batch operation.
        
        Args:
            arguments: Tool arguments containing operation type and items
            
        Returns:
            Tool result with batch operation summary
        """
        operation = arguments["operation"]
        items = arguments["items"]
        batch_size = arguments.get("batch_size", self.default_batch_size)
        max_retries = arguments.get("max_retries", 3)
        continue_on_error = arguments.get("continue_on_error", True)
        
        try:
            # Validate inputs
            if operation not in ["store", "update", "delete"]:
                raise ToolError(
                    "Invalid operation. Must be 'store', 'update', or 'delete'",
                    code="invalid_operation",
                )
            
            if not isinstance(items, list) or len(items) == 0:
                raise ToolError(
                    "Items must be a non-empty array",
                    code="invalid_items",
                )
            
            if len(items) > self.max_batch_size:
                raise ToolError(
                    f"Batch size cannot exceed {self.max_batch_size} items",
                    code="batch_too_large",
                )
            
            if not isinstance(batch_size, int) or batch_size < 1 or batch_size > self.max_batch_size:
                raise ToolError(
                    f"batch_size must be between 1 and {self.max_batch_size}",
                    code="invalid_batch_size",
                )
            
            # Execute appropriate batch operation
            if operation == "store":
                result = await self._execute_batch_store(items, batch_size, max_retries)
            elif operation == "update":
                result = await self._execute_batch_update(items, batch_size)
            elif operation == "delete":
                result = await self._execute_batch_delete(items, batch_size)
            
            # Format response
            success_message = self._format_batch_result_message(operation, result)
            
            return ToolResult.success(
                text=success_message,
                data={
                    "operation": operation,
                    "batch_result": result.to_dict(),
                    "configuration": {
                        "batch_size": batch_size,
                        "max_retries": max_retries,
                        "continue_on_error": continue_on_error,
                    }
                },
                metadata={
                    "operation": f"batch_{operation}",
                    "total_items": result.total_items,
                    "success_rate": result.success_rate,
                },
            )
        
        except VerisMemoryClientError as e:
            self.logger.error("Veris Memory API error", error=str(e))
            return ToolResult.error(
                f"Batch {operation} failed: {e.message}",
                error_code="veris_memory_error",
                details={"original_error": str(e.original_error) if e.original_error else None},
            )
        
        except ToolError:
            raise
        
        except Exception as e:
            self.logger.error("Unexpected error in batch operation", error=str(e), exc_info=True)
            raise ToolError(
                f"Batch {operation} error: {str(e)}",
                code="internal_error",
            )
    
    async def _execute_batch_store(
        self,
        items: list,
        batch_size: int,
        max_retries: int,
    ):
        """Execute batch store operation."""
        self.logger.info(
            "Starting batch store operation",
            total_items=len(items),
            batch_size=batch_size,
        )
        
        # Validate each item has required fields
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                raise ToolError(f"Item {i} must be an object", code="invalid_item")
            
            if "context_type" not in item:
                raise ToolError(f"Item {i} missing context_type", code="missing_context_type")
            
            if "content" not in item:
                raise ToolError(f"Item {i} missing content", code="missing_content")
        
        # Use streaming engine for batch processing
        return await self.streaming_engine.batch_store_contexts(
            contexts=items,
            batch_size=batch_size,
            max_retries=max_retries,
        )
    
    async def _execute_batch_update(self, items: list, batch_size: int):
        """Execute batch update operation."""
        self.logger.info(
            "Starting batch update operation",
            total_items=len(items),
            batch_size=batch_size,
        )
        
        # Validate each item has context_id
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                raise ToolError(f"Item {i} must be an object", code="invalid_item")
            
            if "context_id" not in item:
                raise ToolError(f"Item {i} missing context_id", code="missing_context_id")
        
        # Use streaming engine for batch processing
        return await self.streaming_engine.batch_update_contexts(
            updates=items,
            batch_size=batch_size,
        )
    
    async def _execute_batch_delete(self, items: list, batch_size: int):
        """Execute batch delete operation."""
        # For demo purposes, simulate batch delete
        import time
        from ..streaming.engine import BatchResult
        
        start_time = time.time()
        
        self.logger.info(
            "Starting batch delete operation",
            total_items=len(items),
            batch_size=batch_size,
        )
        
        # Validate items are context IDs or objects with context_id
        context_ids = []
        for i, item in enumerate(items):
            if isinstance(item, str):
                context_ids.append(item)
            elif isinstance(item, dict) and "context_id" in item:
                context_ids.append(item["context_id"])
            else:
                raise ToolError(
                    f"Item {i} must be a context_id string or object with context_id",
                    code="invalid_delete_item",
                )
        
        # Simulate batch deletion
        successful = 0
        failed = 0
        results = []
        errors = []
        
        for context_id in context_ids:
            try:
                # Simulate delete operation
                await self.veris_client.delete_context(context_id)
                successful += 1
                results.append({"context_id": context_id, "deleted": True})
            except Exception as e:
                failed += 1
                errors.append({"context_id": context_id, "error": str(e)})
        
        execution_time = (time.time() - start_time) * 1000
        
        return BatchResult(
            total_items=len(context_ids),
            successful_items=successful,
            failed_items=failed,
            execution_time_ms=execution_time,
            results=results,
            errors=errors,
        )
    
    def _format_batch_result_message(self, operation: str, result) -> str:
        """Format batch result into human-readable message."""
        if result.total_items == 0:
            return f"No items to {operation}"
        
        message = f"Batch {operation} completed: "
        message += f"{result.successful_items}/{result.total_items} items successful"
        
        if result.failed_items > 0:
            message += f", {result.failed_items} failed"
        
        message += f" ({result.success_rate:.1f}% success rate)"
        message += f" in {result.execution_time_ms:.1f}ms"
        
        return message