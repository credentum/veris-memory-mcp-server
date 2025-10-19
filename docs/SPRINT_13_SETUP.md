# Sprint 13 Setup Guide

This guide explains how to configure the Veris Memory MCP Server to work with the Sprint 13 backend, which includes API key authentication.

## Overview

Sprint 13 introduces API key authentication to secure all Veris Memory API endpoints. The MCP server has been updated to support this authentication mechanism.

## What Changed in Sprint 13

1. **API Key Authentication**: All API requests now require an `X-API-Key` header
2. **Role-Based Access Control**: Different API keys have different permissions (admin, writer, reader, guest)
3. **Agent Detection**: API keys can be marked as `is_agent` to restrict destructive operations
4. **Audit Logging**: All operations are logged with API key attribution

## Configuration

### Environment Variables

Set the following environment variables to configure the MCP server:

```bash
# Required: Veris Memory API URL (Sprint 13 backend)
export VERIS_MEMORY_API_URL="http://localhost:8000"

# Required: API key for authentication
export VERIS_MEMORY_API_KEY="vmk_your_api_key_here"

# Optional: User ID for scoped operations
export VERIS_MEMORY_USER_ID="your_user_id"

# Optional: Log level
export VERIS_MCP_LOG_LEVEL="INFO"
```

### Obtaining an API Key

#### Development Environment

For local development with the default test key:

```bash
export VERIS_MEMORY_API_KEY="vmk_test_a1b2c3d4e5f6789012345678901234567890"
```

**⚠️ WARNING**: The default test key only works when the backend has `ENVIRONMENT=development`

#### Production Environment

For production, generate a secure API key:

```bash
# Generate secure random key
KEY_SUFFIX=$(openssl rand -hex 16)

# Format: vmk_writer_{random}:user_id:role:is_agent
export VERIS_MEMORY_API_KEY="vmk_writer_${KEY_SUFFIX}:mcp_server:writer:true"
```

Then add this API key to the backend's `.env` file:

```bash
# In the Veris Memory backend .env file
API_KEY_MCP=vmk_writer_{random}:mcp_server:writer:true
AUTH_REQUIRED=true
ENVIRONMENT=production
```

### API Key Roles

Choose the appropriate role for your MCP server:

| Role | Permissions | Use Case |
|------|-------------|----------|
| `admin` | Full access, can delete contexts | Administrative operations |
| `writer` | Create and read contexts | Normal MCP server operation (recommended) |
| `reader` | Read-only access | Query-only applications |
| `guest` | Limited read access | Public/demo access |

### Agent Flag

The `is_agent` flag indicates whether the API key is used by an AI agent:

- `is_agent=true`: AI agent (recommended for MCP server)
  - ✅ Can create contexts
  - ✅ Can read contexts
  - ✅ Can use forget_context (soft delete)
  - ❌ Cannot use delete_context (hard delete - human only)

- `is_agent=false`: Human user
  - ✅ Full permissions based on role
  - ✅ Can use delete_context (if admin)

## Claude CLI Integration

### Add MCP Server to Claude CLI

```bash
# Add the MCP server with environment variables
claude mcp add veris-memory \
  --env VERIS_MEMORY_API_URL \
  --env VERIS_MEMORY_API_KEY \
  --env VERIS_MEMORY_USER_ID \
  -- veris-memory-mcp-server
```

### Test the Connection

```bash
# Start Claude CLI
claude

# In Claude conversation:
# "Store this test context in Veris Memory: Sprint 13 authentication is working"
# Claude will use the store_context tool with authentication
```

## Configuration File (Optional)

Create a `config.json` file for advanced configuration:

```json
{
  "version": "0.1.0",
  "veris_memory": {
    "api_url": "http://localhost:8000",
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
  }
}
```

Then run with:

```bash
veris-memory-mcp-server --config config.json
```

## Verifying Authentication

### Check Logs

When the MCP server starts, you should see:

```
INFO: Connected to Veris Memory API with connection pooling
DEBUG: Added X-API-Key header for Sprint 13 authentication
```

### Test API Calls

The MCP server will automatically include the `X-API-Key` header in all requests:

```
POST /tools/store_context
Headers:
  Content-Type: application/json
  X-API-Key: vmk_writer_...
```

## Troubleshooting

### Error: "API key authentication required"

**Cause**: The backend requires authentication but no API key is configured

**Solution**: Set `VERIS_MEMORY_API_KEY` environment variable

```bash
export VERIS_MEMORY_API_KEY="your_api_key_here"
```

### Error: "Invalid or expired API key"

**Cause**: The API key is not recognized by the backend

**Solution**:
1. Verify the API key is added to the backend's `.env` file
2. Restart the backend service
3. Check the API key format: `vmk_{prefix}_{random}:user:role:is_agent`

### Error: "Insufficient permissions"

**Cause**: The API key role doesn't have permission for the requested operation

**Solution**: Use a key with appropriate role:
- For read-only: `reader` role
- For normal operations: `writer` role
- For admin operations: `admin` role

### Warning: "No API key configured"

**Cause**: `VERIS_MEMORY_API_KEY` is not set

**Solution**: This is OK for local development with `AUTH_REQUIRED=false`, but **required** for production

## Security Best Practices

1. **Never commit API keys to git**
   - Use environment variables
   - Add `.env` files to `.gitignore`

2. **Use unique API keys per service**
   - Don't share API keys between services
   - Generate fresh keys for each MCP server instance

3. **Rotate API keys regularly**
   - Update keys every 90 days
   - Remove old keys from backend configuration

4. **Use agent flag correctly**
   - Set `is_agent=true` for MCP server (prevents accidental hard deletes)
   - Set `is_agent=false` only for human-operated tools

5. **Monitor API key usage**
   - Check backend audit logs regularly
   - Watch for unusual access patterns

## Reference

For more information on Sprint 13:
- API Documentation: See `SPRINT_13_API_DOCUMENTATION.md` in the backend repo
- MCP Tool Contracts: See `context/mcp_contracts/` directory
- Environment Configuration: See `.env.sprint13.example` in the backend repo

## Quick Start Example

Complete setup for local development:

```bash
# 1. Set environment variables
export VERIS_MEMORY_API_URL="http://localhost:8000"
export VERIS_MEMORY_API_KEY="vmk_test_a1b2c3d4e5f6789012345678901234567890"
export VERIS_MEMORY_USER_ID="mcp_dev_user"

# 2. Add to Claude CLI
claude mcp add veris-memory \
  --env VERIS_MEMORY_API_URL \
  --env VERIS_MEMORY_API_KEY \
  --env VERIS_MEMORY_USER_ID \
  -- veris-memory-mcp-server

# 3. Test connection
veris-memory-mcp-server

# 4. Use from Claude CLI
claude
# Claude can now use Veris Memory tools with authentication!
```

## Support

If you encounter issues:
1. Check the MCP server logs: `VERIS_MCP_LOG_LEVEL=DEBUG`
2. Check the backend logs: `LOG_LEVEL=debug`
3. Verify API key configuration in backend `.env` file
4. Test the backend health endpoint: `curl http://localhost:8000/health`
