# Veris Memory MCP Server Implementation Plan

## Overview

This plan outlines the implementation of a Model Context Protocol (MCP) server that exposes Veris Memory capabilities to Claude CLI and other MCP-compatible hosts.

## Architecture Overview

```
[Claude CLI] ←→ [Veris Memory MCP Server] ←→ [Veris Memory Backend API]
     |                     |                          |
   JSON-RPC            MCP Protocol               veris-memory-mcp-sdk
   over stdio          Implementation                (Client SDK)
```

## Core Components

### 1. MCP Protocol Layer
- **JSON-RPC 2.0** message handling
- **Stdio transport** for Claude CLI integration
- **Capability negotiation** during initialization
- **Error handling** with proper MCP error codes

### 2. Tool Definitions
- **store_context**: Store context data in Veris Memory
- **retrieve_context**: Search and retrieve contexts
- **search_context**: Advanced context search with filters
- **delete_context**: Remove contexts (with proper authorization)
- **list_context_types**: Get available context types

### 3. Backend Integration
- Uses existing **veris-memory-mcp-sdk** as client library
- Handles authentication to Veris Memory API
- Manages connection pooling and retry logic
- Provides caching for improved performance

## Technical Specifications

### MCP Server Implementation

#### Message Flow
```
1. Claude CLI starts server via stdio
2. Server sends initialization response with capabilities
3. Claude CLI requests tools list
4. Server provides tool definitions
5. Claude CLI invokes tools via JSON-RPC
6. Server translates to Veris Memory API calls
7. Server returns results to Claude CLI
```

#### Tool Schema Definitions
```json
{
  "tools": [
    {
      "name": "store_context",
      "description": "Store context data in Veris Memory with optional metadata",
      "inputSchema": {
        "type": "object",
        "properties": {
          "context_type": {
            "type": "string",
            "description": "Type of context (decision, knowledge, analysis, etc.)"
          },
          "content": {
            "type": "object",
            "description": "Context content as structured data",
            "properties": {
              "title": {"type": "string"},
              "text": {"type": "string"},
              "data": {"type": "object"}
            },
            "required": ["text"]
          },
          "metadata": {
            "type": "object",
            "description": "Optional metadata for categorization and search"
          }
        },
        "required": ["context_type", "content"]
      }
    },
    {
      "name": "retrieve_context",
      "description": "Search and retrieve contexts from Veris Memory",
      "inputSchema": {
        "type": "object",
        "properties": {
          "query": {
            "type": "string",
            "description": "Search query for semantic matching"
          },
          "limit": {
            "type": "number",
            "minimum": 1,
            "maximum": 100,
            "default": 10,
            "description": "Maximum number of results to return"
          },
          "context_type": {
            "type": "string",
            "description": "Filter by specific context type"
          },
          "metadata_filters": {
            "type": "object",
            "description": "Filter by metadata key-value pairs"
          }
        },
        "required": ["query"]
      }
    }
  ]
}
```

## Project Structure

```
veris-memory-mcp-server/
├── README.md
├── pyproject.toml
├── requirements.txt
├── setup.py
├── src/
│   └── veris_memory_mcp_server/
│       ├── __init__.py
│       ├── main.py                 # Entry point for Claude CLI
│       ├── server.py               # Core MCP server implementation
│       ├── protocol/
│       │   ├── __init__.py
│       │   ├── handlers.py         # JSON-RPC message handlers
│       │   ├── transport.py        # Stdio transport implementation
│       │   └── schemas.py          # MCP message schemas
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── base.py            # Base tool class
│       │   ├── store_context.py   # Store context tool
│       │   ├── retrieve_context.py # Retrieve context tool
│       │   ├── search_context.py  # Search context tool
│       │   └── delete_context.py  # Delete context tool
│       ├── client/
│       │   ├── __init__.py
│       │   └── veris_client.py    # Wrapper for veris-memory-mcp-sdk
│       ├── config/
│       │   ├── __init__.py
│       │   ├── settings.py        # Configuration management
│       │   └── auth.py            # Authentication handling
│       └── utils/
│           ├── __init__.py
│           ├── logging.py         # Logging configuration
│           └── validation.py      # Input validation
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # Pytest configuration
│   ├── test_server.py            # Server tests
│   ├── test_tools.py             # Tool tests
│   └── integration/
│       ├── __init__.py
│       └── test_claude_cli.py    # Claude CLI integration tests
├── examples/
│   ├── config.json.example       # Example configuration
│   └── test_with_claude.md       # How to test with Claude CLI
├── docs/
│   ├── installation.md           # Installation guide
│   ├── configuration.md          # Configuration reference
│   └── troubleshooting.md        # Common issues and solutions
└── scripts/
    ├── install.sh                # Installation script
    └── test_integration.sh       # Integration test script
```

## Implementation Phases

### Phase 1: Core MCP Protocol (Foundation)
**Goal**: Basic MCP server that can communicate with Claude CLI

**Components**:
- JSON-RPC 2.0 message handling
- Stdio transport implementation
- Basic server lifecycle (initialization, shutdown)
- Tool registration system
- Error handling framework

**Deliverables**:
- Working MCP server that responds to Claude CLI
- Basic tool registration (no actual Veris Memory integration yet)
- Comprehensive logging system
- Configuration system

**Success Criteria**:
- Claude CLI can connect and list available tools
- Server handles JSON-RPC messages correctly
- Proper error responses for invalid requests

### Phase 2: Veris Memory Integration
**Goal**: Connect MCP server to actual Veris Memory backend

**Components**:
- Integration with veris-memory-mcp-sdk
- Authentication management
- Connection pooling and retry logic
- Tool implementation (store_context, retrieve_context)

**Deliverables**:
- Working store_context and retrieve_context tools
- Authentication configuration
- Error mapping from Veris Memory API to MCP errors
- Basic caching for performance

**Success Criteria**:
- Claude CLI can store and retrieve contexts successfully
- Proper error handling for backend failures
- Authentication works with API keys

### Phase 3: Advanced Features
**Goal**: Full-featured MCP server with all capabilities

**Components**:
- Additional tools (search_context, delete_context, list_context_types)
- Advanced search and filtering
- Metadata handling
- Performance optimizations

**Deliverables**:
- Complete tool set
- Advanced search capabilities
- Metadata-based filtering
- Performance monitoring

**Success Criteria**:
- All tools work correctly with Claude CLI
- Advanced search queries return relevant results
- Server performs well under load

### Phase 4: Production Readiness
**Goal**: Production-ready server with monitoring and deployment

**Components**:
- Comprehensive testing suite
- Documentation and examples
- Deployment scripts
- Monitoring and observability

**Deliverables**:
- Complete test coverage
- Installation and configuration guides
- Docker support
- Monitoring integration

**Success Criteria**:
- >90% test coverage
- Easy installation process
- Production deployment ready

## Development Guidelines

### Code Quality Standards
- **Type hints**: Full type annotation using Python 3.10+ features
- **Testing**: Minimum 90% test coverage
- **Documentation**: Comprehensive docstrings and API documentation
- **Linting**: Black, isort, flake8, mypy compliance
- **Security**: Input validation and sanitization

### Performance Requirements
- **Startup time**: <2 seconds for Claude CLI integration
- **Response time**: <500ms for typical operations
- **Memory usage**: <100MB baseline memory consumption
- **Concurrent requests**: Support multiple simultaneous tool calls

### Security Considerations
- **Input validation**: All tool inputs validated against schemas
- **Authentication**: Secure API key management
- **Authorization**: User-scoped operations where applicable
- **Logging**: Security events logged appropriately
- **Error handling**: No sensitive data in error messages

## Configuration System

### Configuration File (config.json)
```json
{
  "veris_memory": {
    "api_url": "https://api.verismemory.com",
    "api_key": "${VERIS_MEMORY_API_KEY}",
    "user_id": "${VERIS_MEMORY_USER_ID}",
    "timeout_ms": 30000
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
    }
  }
}
```

### Environment Variables
- `VERIS_MEMORY_API_KEY`: API key for Veris Memory
- `VERIS_MEMORY_USER_ID`: User ID for scoped operations
- `VERIS_MCP_CONFIG_PATH`: Path to configuration file
- `VERIS_MCP_LOG_LEVEL`: Logging level override

## Testing Strategy

### Unit Tests
- Individual tool implementations
- Protocol handlers
- Configuration management
- Error handling

### Integration Tests
- End-to-end tool execution
- Veris Memory API integration
- Error scenarios and recovery

### Claude CLI Integration Tests
- Actual Claude CLI interaction
- Tool invocation workflows
- Error handling from Claude perspective

## Deployment Options

### Local Development
```bash
# Install from source
pip install -e .

# Run with Claude CLI
claude mcp add veris-memory -- python -m veris_memory_mcp_server
```

### Production Deployment
```bash
# Install from PyPI (future)
pip install veris-memory-mcp-server

# Configure
export VERIS_MEMORY_API_KEY="your-api-key"
export VERIS_MEMORY_USER_ID="your-user-id"

# Add to Claude CLI
claude mcp add veris-memory --env VERIS_MEMORY_API_KEY --env VERIS_MEMORY_USER_ID -- veris-memory-mcp-server
```

### Docker Support
```dockerfile
FROM python:3.11-slim
COPY . /app
WORKDIR /app
RUN pip install .
ENTRYPOINT ["python", "-m", "veris_memory_mcp_server"]
```

## Success Metrics

### Functionality
- [ ] Claude CLI can discover and invoke all tools
- [ ] All tool operations work correctly with Veris Memory backend
- [ ] Error handling provides helpful feedback to users
- [ ] Configuration system supports various deployment scenarios

### Performance
- [ ] Server startup time <2 seconds
- [ ] Tool invocation response time <500ms (95th percentile)
- [ ] Memory usage <100MB baseline
- [ ] No memory leaks during extended operation

### Quality
- [ ] >90% test coverage
- [ ] 100% type annotation coverage
- [ ] All linting checks pass
- [ ] Comprehensive documentation

### Usability
- [ ] Easy installation process
- [ ] Clear configuration documentation
- [ ] Helpful error messages
- [ ] Working examples and tutorials

## Next Steps

1. **Phase 1 Implementation**: Start with core MCP protocol implementation
2. **Early Testing**: Set up basic Claude CLI integration testing
3. **Iterative Development**: Implement tools incrementally with testing
4. **Documentation**: Create user guides and API documentation
5. **Community Feedback**: Share with Veris Memory users for testing and feedback

This implementation plan provides a comprehensive roadmap for creating a production-ready Veris Memory MCP Server that integrates seamlessly with Claude CLI and other MCP-compatible hosts.