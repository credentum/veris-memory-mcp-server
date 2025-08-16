# Claude CLI Integration Guide

This guide shows how to integrate the Veris Memory MCP Server with Claude CLI for seamless context management.

## Prerequisites

1. **Claude CLI installed** - Install the latest Claude CLI
2. **Veris Memory credentials** - API key and user ID
3. **Python 3.10+** - Required for the MCP server

## Installation

### Option 1: Install from PyPI (Coming Soon)

```bash
pip install veris-memory-mcp-server
```

### Option 2: Install from Source

```bash
# Clone the repository
git clone https://github.com/credentum/veris-memory-mcp-server.git
cd veris-memory-mcp-server

# Install in development mode
pip install -e .
```

### Option 3: Install from GitHub

```bash
pip install git+https://github.com/credentum/veris-memory-mcp-server.git
```

## Configuration

### 1. Set Environment Variables

```bash
# Required: Your Veris Memory API credentials
export VERIS_MEMORY_API_KEY="your-api-key-here"
export VERIS_MEMORY_USER_ID="your-user-id-here"

# Optional: Custom server URL (defaults to https://api.verismemory.com)
export VERIS_MEMORY_API_URL="https://your-custom-server.com"
```

### 2. Generate Configuration File (Optional)

```bash
# Create default configuration
veris-memory-mcp-server init --config veris-config.json

# Edit the configuration as needed
```

### 3. Add to Claude CLI

```bash
# Add Veris Memory MCP server to Claude CLI
claude mcp add veris-memory \
  --env VERIS_MEMORY_API_KEY \
  --env VERIS_MEMORY_USER_ID \
  -- veris-memory-mcp-server
```

### 4. Verify Installation

```bash
# Check that the server is registered
claude mcp list

# Test the connection (this will start a session with tools available)
claude
```

## Usage Examples

Once integrated, you can use Veris Memory directly in your Claude conversations:

### Storing Context

```
User: Store this architectural decision: We've decided to use PostgreSQL 
      as our primary database because of its ACID compliance, JSON support, 
      and strong ecosystem. This decision affects the user service and 
      analytics platform.

Claude: I'll store that architectural decision in Veris Memory for future reference.

[Claude uses store_context tool]

✅ Successfully stored decision context with ID: arch_db_20240101_001
```

### Retrieving Context

```
User: What database decisions have we made previously?

Claude: Let me search for previous database-related decisions in Veris Memory.

[Claude uses retrieve_context tool]

Found 3 relevant contexts:
1. [decision] PostgreSQL Selection (arch_db_20240101_001)
2. [decision] Redis Caching Layer (arch_cache_20231215_003) 
3. [analysis] Database Performance Review (perf_db_20231201_002)

Would you like me to show details for any of these decisions?
```

### Advanced Search

```
User: Find all high-priority decisions from the last quarter

Claude: I'll search for high-priority decisions with date filtering.

[Claude uses search_context tool with filters]

Found 8 high-priority decisions from the last quarter:
• API Gateway Implementation (priority: high, date: 2023-12-15)
• Security Framework Upgrade (priority: high, date: 2023-11-20)
• Database Migration Strategy (priority: high, date: 2023-10-30)
...
```

### Context Types Discovery

```
User: What types of information can I store?

Claude: [Claude uses list_context_types tool]

Available context types:
• decision: Architectural decisions, design choices, and strategic determinations
• knowledge: Documentation, procedures, best practices, and learning materials
• analysis: Data analysis, performance reviews, and analytical insights
• meeting_notes: Meeting summaries, action items, and discussion records
• issue: Bug reports, problems, and their resolutions
• requirement: System requirements, specifications, and functional needs
• research: Investigation results, findings, and research notes
```

## Advanced Configuration

### Custom Configuration File

Create a `veris-config.json` file:

```json
{
  "version": "0.1.0",
  "veris_memory": {
    "api_url": "https://api.verismemory.com",
    "api_key": "${VERIS_MEMORY_API_KEY}",
    "user_id": "${VERIS_MEMORY_USER_ID}",
    "timeout_ms": 30000,
    "max_retries": 3
  },
  "server": {
    "log_level": "INFO",
    "max_concurrent_requests": 10,
    "cache_enabled": true,
    "cache_ttl_seconds": 300
  },
  "tools": {
    "store_context": {
      "enabled": true,
      "max_content_size": 1048576,
      "allowed_context_types": ["*"]
    },
    "retrieve_context": {
      "enabled": true,
      "max_results": 100,
      "default_limit": 10
    },
    "search_context": {
      "enabled": true,
      "max_results": 100,
      "default_limit": 10
    },
    "delete_context": {
      "enabled": false
    },
    "list_context_types": {
      "enabled": true
    }
  }
}
```

Use custom configuration:

```bash
claude mcp add veris-memory \
  --env VERIS_MEMORY_API_KEY \
  --env VERIS_MEMORY_USER_ID \
  --env VERIS_MCP_CONFIG_PATH=/path/to/veris-config.json \
  -- veris-memory-mcp-server
```

### Tool-Specific Configuration

#### Restrict Context Types

```json
{
  "tools": {
    "store_context": {
      "allowed_context_types": ["decision", "knowledge", "analysis"]
    }
  }
}
```

#### Disable Dangerous Operations

```json
{
  "tools": {
    "delete_context": {
      "enabled": false
    }
  }
}
```

#### Adjust Performance Settings

```json
{
  "server": {
    "cache_enabled": true,
    "cache_ttl_seconds": 600,
    "max_concurrent_requests": 20
  },
  "veris_memory": {
    "timeout_ms": 60000,
    "max_retries": 5
  }
}
```

## Troubleshooting

### Common Issues

#### Server Not Starting

**Error**: `VERIS_MEMORY_API_KEY environment variable is required`

**Solution**: Ensure environment variables are set:
```bash
echo $VERIS_MEMORY_API_KEY  # Should show your API key
echo $VERIS_MEMORY_USER_ID  # Should show your user ID
```

#### Connection Issues

**Error**: `Failed to connect to Veris Memory: Connection refused`

**Solutions**:
1. Check API URL: `export VERIS_MEMORY_API_URL="https://your-server.com"`
2. Verify credentials are valid
3. Check network connectivity: `curl https://api.verismemory.com/health`

#### Tool Timeouts

**Error**: `HTTP timeout for tool store_context`

**Solutions**:
1. Increase timeout in config:
   ```json
   {
     "veris_memory": {
       "timeout_ms": 60000
     }
   }
   ```
2. Check network latency to Veris Memory API
3. Reduce content size if storing large contexts

### Debug Mode

Enable debug logging:

```bash
export VERIS_MCP_LOG_LEVEL=DEBUG
claude mcp add veris-memory --env VERIS_MCP_LOG_LEVEL -- veris-memory-mcp-server
```

Check logs in stderr (the server logs to stderr to avoid interfering with MCP protocol on stdout).

### Verify MCP Integration

Test the server independently:

```bash
# Test server startup
veris-memory-mcp-server --help

# Test with mock configuration
python examples/basic_usage.py
```

## Performance Tips

### Caching

Enable caching for better performance:

```json
{
  "server": {
    "cache_enabled": true,
    "cache_ttl_seconds": 300
  }
}
```

### Concurrent Requests

Adjust based on your usage:

```json
{
  "server": {
    "max_concurrent_requests": 20
  }
}
```

### Connection Pooling

The server automatically manages connections to Veris Memory with proper pooling and retry logic.

## Security Considerations

1. **API Keys**: Store in environment variables, never in code
2. **User Scoping**: All operations are scoped to your user ID
3. **Content Size**: Default limit is 1MB per context
4. **Rate Limiting**: Server respects Veris Memory API rate limits

## Next Steps

1. **Explore Context Types**: Use `list_context_types` to see available schemas
2. **Organize with Metadata**: Use consistent metadata for better retrieval
3. **Set Up Workflows**: Create patterns for storing different types of contexts
4. **Monitor Usage**: Check logs for performance and error patterns

For more advanced usage and API details, see the [GitHub repository](https://github.com/credentum/veris-memory-mcp-server).