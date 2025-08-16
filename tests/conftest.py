"""
Pytest configuration and fixtures for Veris Memory MCP Server tests.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from veris_memory_mcp_server.config.settings import Config, VerisMemoryConfig, ServerConfig, ToolsConfig
from veris_memory_mcp_server.client.veris_client import VerisMemoryClient


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_config():
    """Create a test configuration."""
    return Config(
        version="0.1.0-test",
        veris_memory=VerisMemoryConfig(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            user_id="test-user",
            timeout_ms=5000,
            max_retries=1,
        ),
        server=ServerConfig(
            log_level="DEBUG",
            max_concurrent_requests=5,
            cache_enabled=False,
        ),
        tools=ToolsConfig(),
    )


@pytest.fixture
def mock_veris_client():
    """Create a mock Veris Memory client."""
    client = AsyncMock(spec=VerisMemoryClient)
    client.connected = True
    
    # Mock typical responses
    client.store_context.return_value = {
        "context_id": "test-context-123",
        "created_at": "2024-01-01T00:00:00Z",
    }
    
    client.retrieve_context.return_value = [
        {
            "id": "ctx-1",
            "context_type": "decision",
            "content": {"title": "Test Decision", "text": "We decided to use Python"},
            "metadata": {"project": "test"},
            "created_at": "2024-01-01T00:00:00Z",
            "relevance_score": 0.9,
        }
    ]
    
    client.search_context.return_value = {
        "results": [],
        "total": 0,
        "query": "test",
    }
    
    client.delete_context.return_value = {
        "deleted": True,
        "context_id": "test-context-123",
    }
    
    client.list_context_types.return_value = [
        "decision",
        "knowledge", 
        "analysis",
    ]
    
    return client


@pytest.fixture
async def mock_transport():
    """Create a mock transport."""
    transport = MagicMock()
    transport.send_response = AsyncMock()
    transport.send_notification = AsyncMock()
    return transport