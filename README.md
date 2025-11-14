# Veris Memory MCP Server

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A Model Context Protocol (MCP) server that exposes Veris Memory capabilities to Claude CLI and other MCP-compatible hosts.

## Overview

This server implements the [Model Context Protocol](https://modelcontextprotocol.io/) specification to provide Claude CLI with direct access to Veris Memory's context storage and retrieval capabilities. It acts as a bridge between Claude and the Veris Memory backend API.

```
[Claude CLI] ←→ [Veris Memory MCP Server] ←→ [Veris Memory API]
     |                     |                        |
   JSON-RPC            MCP Protocol            veris-memory-mcp-sdk
   over stdio          Implementation             (Client SDK)
```

## Features

- **🔌 Claude CLI Integration**: Native MCP protocol support for seamless Claude CLI integration
- **📦 Complete Tool Set**: Store, retrieve, search, and manage contexts in Veris Memory
- **🚀 High Performance**: Async implementation with connection pooling and caching
- **🔒 Secure**: Proper authentication, input validation, and error handling
- **⚙️ Configurable**: Flexible configuration system supporting various deployment scenarios
- **📊 Observable**: Comprehensive logging and monitoring capabilities

## Available Tools

| Tool | Description | Use Case |
|------|-------------|----------|
| `store_context` | Store context data with metadata | Save decisions, knowledge, analysis |
| `retrieve_context` | Search and retrieve contexts | Find relevant past contexts |
| `search_context` | Advanced search with filters | Complex queries with metadata filters |
| `delete_context` | Remove contexts (with authorization) | Clean up outdated information |
| `list_context_types` | Get available context types | Discover schema options |

## Quick Start

### Installation

```bash
# Install from PyPI (coming soon)
pip install veris-memory-mcp-server

# Or install from source
git clone https://github.com/credentum/veris-memory-mcp-server.git
cd veris-memory-mcp-server
pip install -e .
```

### Configuration

#### Sprint 13: API Key Authentication

Sprint 13 introduces API key authentication for enhanced security. All API requests now require an `X-API-Key` header.

1. **Set up environment variables:**
   ```bash
   # Backend API URL
   export VERIS_MEMORY_API_URL="http://localhost:8000"

   # Sprint 13 API Key (required)
   # Format: vmk_{prefix}_{random}:user_id:role:is_agent
   export VERIS_MEMORY_API_KEY="vmk_writer_$(openssl rand -hex 16):mcp_server:writer:true"

   # User ID (optional)
   export VERIS_MEMORY_USER_ID="your-user-id"
   ```

   **Development**: Use the default test key (requires backend `ENVIRONMENT=development`):
   ```bash
   export VERIS_MEMORY_API_KEY="vmk_test_a1b2c3d4e5f6789012345678901234567890"
   ```

   **Production**: Generate a secure API key and add it to the backend's `.env` file:
   ```bash
   # Generate key
   KEY_SUFFIX=$(openssl rand -hex 16)
   export VERIS_MEMORY_API_KEY="vmk_writer_${KEY_SUFFIX}:mcp_server:writer:true"

   # Add to backend .env file
   echo "API_KEY_MCP=vmk_writer_${KEY_SUFFIX}:mcp_server:writer:true" >> backend/.env
   echo "AUTH_REQUIRED=true" >> backend/.env
   ```

2. **Add to Claude CLI:**
   ```bash
   claude mcp add veris-memory \
     --env VERIS_MEMORY_API_URL \
     --env VERIS_MEMORY_API_KEY \
     --env VERIS_MEMORY_USER_ID \
     -- veris-memory-mcp-server
   ```

3. **Test the integration:**
   ```bash
   # Claude CLI will now have access to Veris Memory tools
   # You can use them in conversations like:
   # "Store this decision in Veris Memory: We chose React for the frontend"
   # "Retrieve contexts about our API architecture decisions"
   ```

**📖 For detailed Sprint 13 setup instructions, see [docs/SPRINT_13_SETUP.md](docs/SPRINT_13_SETUP.md)**

## Usage Examples

### Storing Context with Claude

```
User: Store this architectural decision: We've decided to use PostgreSQL 
      as our primary database because of its ACID compliance and JSON support.

Claude: I'll store that architectural decision for you.

[Claude uses store_context tool]
✅ Stored context successfully with ID: arch_001
```

### Retrieving Context with Claude

```
User: What database decisions have we made previously?

Claude: Let me search for database-related decisions.

[Claude uses retrieve_context tool with query "database decisions"]

Found 3 relevant contexts:
1. PostgreSQL selection (arch_001) - Primary database choice
2. Redis caching (arch_005) - Caching layer decision  
3. MongoDB migration (arch_012) - Document store evaluation
```

## Configuration

### Configuration File

Create a `config.json` file:

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

| Variable | Description | Required |
|----------|-------------|----------|
| `VERIS_MEMORY_API_KEY` | API key for Veris Memory | Yes |
| `VERIS_MEMORY_USER_ID` | User ID for scoped operations | Yes |
| `VERIS_MCP_CONFIG_PATH` | Path to configuration file | No |
| `VERIS_MCP_LOG_LEVEL` | Logging level (DEBUG, INFO, WARN, ERROR) | No |
| `NEO4J_PASSWORD` | Neo4j database password | Yes (if using Docker) |
| `REDIS_PASSWORD` | Redis cache password | Yes (if using Docker) |

## Security

### Development Environment Security

**🔒 Secure by Default**: The `docker-compose.dev.yml` configuration uses security best practices:

- ✅ **All database ports bound to localhost (127.0.0.1)** - Prevents internet exposure
- ✅ **Redis password authentication required** - No unauthenticated access
- ✅ **Neo4j password authentication required** - Protected graph database
- ✅ **Health checks enabled** - Ensures services are running securely

### Quick Setup (Secure Development)

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Edit .env and set secure passwords
# Change NEO4J_PASSWORD and REDIS_PASSWORD

# 3. Start services with secure configuration
docker-compose -f docker-compose.dev.yml up -d

# 4. Verify services are only accessible locally
# These should all work:
curl http://localhost:6333/health  # Qdrant
curl http://localhost:7474         # Neo4j
redis-cli -a your-password ping    # Redis

# These should FAIL from external machine:
curl http://your-server-ip:6333/health  # Should timeout/refuse
```

### Port Binding Explained

**Development (docker-compose.dev.yml):**
```yaml
ports:
  - "127.0.0.1:6379:6379"  # ✅ Localhost only - Secure
```

**Insecure (DON'T DO THIS):**
```yaml
ports:
  - "6379:6379"  # ❌ Binds to 0.0.0.0 - EXPOSED TO INTERNET!
```

### Remote Access

If you need to access services running on a remote server:

**Option 1: SSH Tunnel (Recommended)**
```bash
# Forward remote Neo4j browser to your local machine
ssh -L 7474:localhost:7474 user@server

# Now access http://localhost:7474 in your browser
```

**Option 2: VPN/Tailscale**
```bash
# Install Tailscale on server and client
# Access services via Tailscale IP
```

### Security Checklist

Before deploying:

- [ ] Changed all default passwords in `.env`
- [ ] Verified ports are bound to `127.0.0.1` in compose file
- [ ] Tested external access is blocked (should fail)
- [ ] Tested local access works (should succeed)
- [ ] Added `.env` to `.gitignore` (already included)
- [ ] Never committed passwords to git

### Production Security

For production deployments:

1. **Use strong, unique passwords** (16+ characters)
2. **Use secrets management** (AWS Secrets Manager, HashiCorp Vault, etc.)
3. **Enable TLS/SSL** for all connections
4. **Use private networks** (VPC, VPN) for database access
5. **Implement rate limiting** on APIs
6. **Enable audit logging** for all operations
7. **Regular security updates** for all containers
8. **Network segmentation** between services

### Common Security Issues

❌ **Docker exposes ports despite firewall:**
- Docker bypasses UFW/iptables by default
- Solution: Bind to `127.0.0.1:PORT:PORT` instead of `PORT:PORT`

❌ **Redis accessible without password:**
- Default Redis has no authentication
- Solution: Use `--requirepass` flag (already configured in dev compose)

❌ **Databases exposed to internet:**
- Easy to accidentally expose with `0.0.0.0` binding
- Solution: Always use `127.0.0.1` for development

## Development

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/credentum/veris-memory-mcp-server.git
cd veris-memory-mcp-server

# Install development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/veris_memory_mcp_server --cov-report=html

# Run specific test types
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
```

### Code Quality

```bash
# Format code
black src tests
isort src tests

# Type checking
mypy src

# Linting
flake8 src tests

# Run all quality checks
pre-commit run --all-files
```

## Architecture

### Core Components

- **Server**: Main MCP server implementation with JSON-RPC handling
- **Protocol**: MCP protocol handlers and stdio transport
- **Tools**: Individual tool implementations (store, retrieve, search, etc.)
- **Client**: Wrapper around veris-memory-mcp-sdk for backend communication
- **Config**: Configuration management and validation

### Tool Implementation

Each tool follows a consistent pattern:

```python
from veris_memory_mcp_server.tools.base import BaseTool

class StoreContextTool(BaseTool):
    name = "store_context"
    description = "Store context data in Veris Memory"
    
    async def execute(self, arguments: dict) -> dict:
        # Validate input
        # Call Veris Memory API
        # Return result
```

## Troubleshooting

### Common Issues

**Server fails to start**
- Check that all required environment variables are set
- Verify Veris Memory API credentials
- Ensure Python 3.10+ is installed

**Tool calls timeout**
- Increase timeout in configuration
- Check network connectivity to Veris Memory API
- Verify API key has proper permissions

**Claude CLI doesn't see tools**
- Restart Claude CLI after adding the MCP server
- Check server logs for initialization errors
- Verify MCP server is configured correctly

### Debug Mode

Enable detailed logging:

```bash
export VERIS_MCP_LOG_LEVEL=DEBUG
veris-memory-mcp-server
```

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Documentation**: [GitHub Wiki](https://github.com/credentum/veris-memory-mcp-server/wiki)
- **Issues**: [GitHub Issues](https://github.com/credentum/veris-memory-mcp-server/issues)
- **Discussions**: [GitHub Discussions](https://github.com/credentum/veris-memory-mcp-server/discussions)

## Related Projects

- [veris-memory-mcp-sdk](https://github.com/credentum/veris-memory-mcp-sdk) - Python SDK for Veris Memory
- [Model Context Protocol](https://modelcontextprotocol.io/) - Official MCP specification
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) - Claude Code command line interface

---

Built with ❤️ by the Veris Memory Team