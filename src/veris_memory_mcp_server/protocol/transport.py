"""
Transport layer for MCP protocol communication.

Implements stdio transport for Claude CLI integration and other
transport mechanisms for MCP message exchange.
"""

import asyncio
import json
import sys
from typing import Any, Awaitable, AsyncIterator, Callable, Dict, Optional, Union

import structlog
from pydantic import ValidationError

from .schemas import MCPMessage, MCPNotification, MCPRequest, MCPResponse

logger = structlog.get_logger(__name__)


class TransportError(Exception):
    """Base exception for transport errors."""

    pass


class StdioTransport:
    """
    Stdio transport for MCP communication.

    Handles JSON-RPC message exchange over stdin/stdout for
    integration with Claude CLI and other stdio-based hosts.
    """

    def __init__(self):
        self._running = False
        self._message_handler: Optional[Union[
            Callable[[MCPRequest], MCPResponse],
            Callable[[MCPRequest], Awaitable[MCPResponse]]
        ]] = None

    def set_message_handler(self, handler: Union[
        Callable[[MCPRequest], MCPResponse],
        Callable[[MCPRequest], Awaitable[MCPResponse]]
    ]) -> None:
        """Set the message handler for incoming requests."""
        self._message_handler = handler

    async def start(self) -> None:
        """Start the stdio transport loop."""
        if self._running:
            raise TransportError("Transport is already running")

        if not self._message_handler:
            raise TransportError("Message handler not set")

        self._running = True
        logger.info("Starting stdio transport")

        try:
            await self._run_transport_loop()
        except Exception as e:
            logger.error("Transport loop error", error=str(e), exc_info=True)
            raise
        finally:
            self._running = False
            logger.info("Stdio transport stopped")

    async def stop(self) -> None:
        """Stop the stdio transport."""
        self._running = False

    async def send_message(self, message: MCPMessage) -> None:
        """
        Send a message via stdout.

        Args:
            message: Message to send
        """
        try:
            message_dict = message.dict(exclude_unset=False)
            message_json = json.dumps(message_dict, separators=(",", ":"))

            # Write to stdout with newline - ensure immediate flush
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._write_stdout_sync, message_json)

            logger.debug("Sent message", message_type=type(message).__name__)

        except Exception as e:
            logger.error("Failed to send message", error=str(e), exc_info=True)
            raise TransportError(f"Failed to send message: {e}")

    def _write_stdout_sync(self, message_json: str) -> None:
        """Synchronous stdout write with immediate flush."""
        sys.stdout.write(message_json + "\n")
        sys.stdout.flush()
        # Ensure OS-level flush
        import os
        os.fsync(sys.stdout.fileno())

    async def send_response(self, response: MCPResponse) -> None:
        """Send a response message."""
        logger.debug(
            "Sending MCP response",
            response_id=response.id,
            has_result=response.result is not None,
            has_error=response.error is not None,
        )
        await self.send_message(response)

    async def send_notification(self, notification: MCPNotification) -> None:
        """Send a notification message."""
        await self.send_message(notification)

    async def _run_transport_loop(self) -> None:
        """Main transport loop for processing stdin messages."""
        logger.debug("Starting transport loop")

        async for line in self._read_stdin_lines():
            if not self._running:
                break

            try:
                await self._process_line(line)
            except Exception as e:
                logger.error("Error processing line", error=str(e), line=line[:100])
                # Continue processing other messages

    async def _read_stdin_lines(self) -> AsyncIterator[str]:
        """Async generator for reading lines from stdin."""
        loop = asyncio.get_event_loop()

        while self._running:
            try:
                # Read line from stdin in a non-blocking way
                line = await loop.run_in_executor(None, sys.stdin.readline)

                if not line:  # EOF
                    logger.info("Received EOF on stdin")
                    break

                line = line.strip()
                if line:
                    yield line

            except Exception as e:
                logger.error("Error reading from stdin", error=str(e))
                break

    async def _process_line(self, line: str) -> None:
        """
        Process a single line from stdin.

        Args:
            line: JSON line to process
        """
        if not line.strip():
            return

        try:
            # Parse JSON
            message_data = json.loads(line)
            logger.debug("Received message", message_data=message_data)

            # Determine message type and handle
            if "method" in message_data:
                if "id" in message_data:
                    # Request
                    await self._handle_request(message_data)
                else:
                    # Notification
                    await self._handle_notification(message_data)
            else:
                # Response (shouldn't happen in server mode)
                logger.warning("Received response in server mode", message_data=message_data)

        except json.JSONDecodeError as e:
            logger.error("Invalid JSON received", error=str(e), line=line[:100])
            # Send error response if we can extract an ID
            await self._send_parse_error(line)

        except Exception as e:
            logger.error("Error processing message", error=str(e), line=line[:100])

    async def _handle_request(self, message_data: Dict[str, Any]) -> None:
        """Handle incoming request message."""
        try:
            # Create request object
            request = MCPRequest(**message_data)

            logger.info(
                "Processing request",
                method=request.method,
                request_id=request.id,
            )

            # Call message handler
            if self._message_handler:
                response = await self._safe_call_handler(request)
                await self.send_response(response)
            else:
                logger.error("No message handler set")
                error_response = self._create_error_response(
                    request.id, -32603, "Internal error: no message handler"
                )
                await self.send_response(error_response)

        except ValidationError as e:
            logger.error("Invalid request format", error=str(e))
            request_id = message_data.get("id", "unknown")
            error_response = self._create_error_response(
                request_id, -32602, f"Invalid request: {e}"
            )
            await self.send_response(error_response)

        except Exception as e:
            logger.error("Error handling request", error=str(e), exc_info=True)
            request_id = message_data.get("id", "unknown")
            error_response = self._create_error_response(request_id, -32603, "Internal error")
            await self.send_response(error_response)

    async def _handle_notification(self, message_data: Dict[str, Any]) -> None:
        """Handle incoming notification message."""
        try:
            notification = MCPNotification(**message_data)
            logger.info("Received notification", method=notification.method)

            # Notifications don't require responses
            # Could be extended to handle specific notification types

        except ValidationError as e:
            logger.error("Invalid notification format", error=str(e))
        except Exception as e:
            logger.error("Error handling notification", error=str(e))

    async def _safe_call_handler(self, request: MCPRequest) -> MCPResponse:
        """Safely call the message handler with error handling."""
        try:
            # Call handler (might be sync or async)
            logger.debug("Calling message handler", method=request.method, request_id=request.id)
            result = self._message_handler(request)
            
            if asyncio.iscoroutine(result):
                logger.debug("Handler returned coroutine, awaiting...")
                response = await result
                logger.debug(
                    "Handler completed",
                    response_id=getattr(response, 'id', 'unknown'),
                    response_type=type(response).__name__
                )
                return response
            else:
                logger.debug("Handler returned direct response")
                return result

        except Exception as e:
            logger.error("Handler error", error=str(e), exc_info=True)
            return self._create_error_response(request.id, -32603, f"Internal error: {str(e)}")

    def _create_error_response(
        self,
        request_id: Any,
        code: int,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> MCPResponse:
        """Create an error response."""
        return MCPResponse(
            id=request_id,
            error={
                "code": code,
                "message": message,
                "data": data or {},
            },
        )

    async def _send_parse_error(self, line: str) -> None:
        """Send parse error response."""
        error_response = self._create_error_response("unknown", -32700, "Parse error")
        await self.send_response(error_response)


class HttpTransport:
    """
    HTTP transport for MCP communication.

    Future implementation for HTTP-based MCP hosts.
    """

    def __init__(self, host: str = "localhost", port: int = 8000):
        self.host = host
        self.port = port
        self._app = None

    async def start(self) -> None:
        """Start HTTP server."""
        raise NotImplementedError("HTTP transport not yet implemented")

    async def stop(self) -> None:
        """Stop HTTP server."""
        raise NotImplementedError("HTTP transport not yet implemented")
