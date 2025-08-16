#!/usr/bin/env python3
"""
Basic usage example for Veris Memory MCP Server.

This example demonstrates how to manually test the MCP server
without Claude CLI for development and debugging purposes.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add the src directory to the path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from veris_memory_mcp_server.config.settings import Config
from veris_memory_mcp_server.server import VerisMemoryMCPServer
from veris_memory_mcp_server.protocol.schemas import (
    MCPInitializeRequest,
    MCPListToolsRequest,
    MCPCallToolRequest,
)


async def main():
    """Run basic MCP server test."""
    print("🚀 Starting Veris Memory MCP Server Test")
    
    # Create test configuration
    config = Config(
        veris_memory={
            "api_url": "http://localhost:8000",  # Mock server
            "api_key": "test-api-key",
            "user_id": "test-user",
            "timeout_ms": 5000,
        },
        server={
            "log_level": "DEBUG",
        },
    )
    
    # Create server instance
    server = VerisMemoryMCPServer(config)
    
    try:
        # Start server (this would normally be done by stdio transport)
        await server.start()
        print("✅ Server started successfully")
        
        # Test 1: Initialize protocol
        print("\n📋 Test 1: Initialize Protocol")
        init_request = MCPInitializeRequest(
            id="test-init",
            params={
                "protocolVersion": "2024-11-05",
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                },
                "capabilities": {}
            }
        )
        
        response = await server.mcp_handler.handle_request(init_request)
        print(f"   Status: {'✅ Success' if response.result else '❌ Failed'}")
        if response.result:
            print(f"   Server: {response.result['serverInfo']['name']} v{response.result['serverInfo']['version']}")
        
        # Test 2: List available tools
        print("\n🔧 Test 2: List Available Tools")
        list_request = MCPListToolsRequest(id="test-list")
        
        response = await server.mcp_handler.handle_request(list_request)
        if response.result:
            tools = response.result["tools"]
            print(f"   Found {len(tools)} tools:")
            for tool in tools:
                print(f"   • {tool['name']}: {tool['description']}")
        else:
            print("   ❌ Failed to list tools")
        
        # Test 3: Test store_context tool (would fail without real Veris Memory)
        print("\n💾 Test 3: Test Store Context Tool")
        store_request = MCPCallToolRequest(
            id="test-store",
            params={
                "name": "store_context",
                "arguments": {
                    "context_type": "test",
                    "content": {
                        "text": "This is a test context",
                        "details": "Testing the MCP server functionality"
                    },
                    "metadata": {
                        "source": "basic_usage_example",
                        "timestamp": "2024-01-01T00:00:00Z"
                    }
                }
            }
        )
        
        response = await server.mcp_handler.handle_request(store_request)
        if response.result and not response.result.get("isError"):
            print("   ✅ Store context tool executed successfully")
            print(f"   Result: {response.result['content'][0]['text']}")
        else:
            print("   ⚠️  Store context failed (expected without real Veris Memory)")
            if response.result:
                print(f"   Error: {response.result['content'][0]['text']}")
        
        # Test 4: Health check
        print("\n🏥 Test 4: Health Check")
        health_status = await server.health_check()
        print(f"   Server Running: {'✅' if health_status['server_running'] else '❌'}")
        print(f"   MCP Initialized: {'✅' if health_status['mcp_initialized'] else '❌'}")
        print(f"   Tools Registered: {health_status['tools_registered']}")
        print(f"   Enabled Tools: {', '.join(health_status['enabled_tools'])}")
        
        print("\n🎉 All tests completed!")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean shutdown
        await server.stop()
        print("🛑 Server stopped")


if __name__ == "__main__":
    # Set up environment for testing
    import os
    os.environ.setdefault("VERIS_MEMORY_API_KEY", "test-key")
    os.environ.setdefault("VERIS_MEMORY_USER_ID", "test-user")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        sys.exit(1)