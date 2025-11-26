"""
Configuration management for Veris Memory MCP Server.

Handles loading, validation, and management of server configuration
from files and environment variables.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator


class VerisMemoryConfig(BaseModel):
    """Configuration for Veris Memory API connection."""

    api_url: str = Field(default="https://api.verismemory.com", description="Veris Memory API URL")
    api_key: Optional[str] = Field(default=None, description="API key for authentication")
    user_id: Optional[str] = Field(default=None, description="User ID for scoped operations")
    timeout_ms: int = Field(default=30000, description="Request timeout in milliseconds")
    max_retries: int = Field(default=3, description="Maximum number of retry attempts")

    @validator("api_key", pre=True)
    def resolve_api_key(cls, v: Optional[str]) -> Optional[str]:
        """Resolve API key from environment variable if needed."""
        if v is None:
            return os.getenv("VERIS_MEMORY_API_KEY")
        if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
            env_var = v[2:-1]
            return os.getenv(env_var)
        return v

    @validator("user_id", pre=True)
    def resolve_user_id(cls, v: Optional[str]) -> Optional[str]:
        """Resolve user ID from environment variable if needed."""
        if v is None:
            return os.getenv("VERIS_MEMORY_USER_ID")
        if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
            env_var = v[2:-1]
            return os.getenv(env_var)
        return v


class ServerConfig(BaseModel):
    """Configuration for MCP server behavior."""

    log_level: str = Field(default="INFO", description="Logging level")
    max_concurrent_requests: int = Field(default=10, description="Maximum concurrent requests")
    cache_enabled: bool = Field(default=True, description="Enable response caching")
    cache_ttl_seconds: int = Field(default=300, description="Cache TTL in seconds")
    request_timeout_ms: int = Field(default=30000, description="Request timeout in milliseconds")

    @validator("log_level")
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v_upper


class ToolConfig(BaseModel):
    """Configuration for individual tools."""

    enabled: bool = Field(default=True, description="Whether tool is enabled")
    max_content_size: int = Field(default=1048576, description="Maximum content size in bytes")
    allowed_context_types: List[str] = Field(default=["*"], description="Allowed context types")
    max_results: int = Field(default=100, description="Maximum results to return")
    default_limit: int = Field(default=10, description="Default result limit")


class WebhookConfig(BaseModel):
    """Configuration for webhook system."""

    enabled: bool = Field(default=True, description="Enable webhook notifications")
    max_subscriptions: int = Field(default=1000, description="Maximum webhook subscriptions")
    event_buffer_size: int = Field(default=10000, description="Event buffer size")
    max_retries: int = Field(default=3, description="Maximum delivery retries")
    timeout_seconds: float = Field(default=30.0, description="HTTP request timeout")
    initial_backoff_seconds: float = Field(default=1.0, description="Initial retry backoff")
    max_backoff_seconds: float = Field(default=60.0, description="Maximum retry backoff")
    max_concurrent_deliveries: int = Field(default=100, description="Max concurrent deliveries")
    signing_secret: Optional[str] = Field(
        default=None, description="Default webhook signing secret"
    )

    @validator("signing_secret", pre=True)
    def resolve_signing_secret(cls, v: Optional[str]) -> Optional[str]:
        """Resolve signing secret from environment variable if needed."""
        if v is None:
            return os.getenv("WEBHOOK_SIGNING_SECRET")
        if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
            env_var = v[2:-1]
            return os.getenv(env_var)
        return v


class StreamingConfig(BaseModel):
    """Configuration for streaming operations."""

    enabled: bool = Field(default=True, description="Enable streaming capabilities")
    chunk_size: int = Field(default=1024, description="Streaming chunk size")
    max_concurrent_streams: int = Field(default=10, description="Max concurrent streams")
    buffer_size: int = Field(default=8192, description="Stream buffer size")
    default_batch_size: int = Field(default=50, description="Default batch size")
    max_batch_size: int = Field(default=1000, description="Maximum batch size")


class AnalyticsConfig(BaseModel):
    """Configuration for analytics tools (API client mode)."""

    enabled: bool = Field(default=True, description="Enable analytics tools")
    cache_ttl_seconds: int = Field(default=300, description="Analytics API response cache TTL")
    api_timeout_seconds: int = Field(default=30, description="API request timeout")
    default_timeframe: str = Field(default="1h", description="Default analytics timeframe")

    # Removed local analytics settings (no longer needed):
    # - retention_seconds: handled by API server
    # - max_points_per_metric: handled by API server
    # - aggregation_interval_seconds: handled by API server
    # - export settings: handled by API server


class ToolsConfig(BaseModel):
    """Configuration for all available tools."""

    store_context: ToolConfig = Field(default_factory=ToolConfig)
    retrieve_context: ToolConfig = Field(default_factory=ToolConfig)
    search_context: ToolConfig = Field(default_factory=ToolConfig)
    delete_context: ToolConfig = Field(default_factory=lambda: ToolConfig(enabled=False))
    list_context_types: ToolConfig = Field(default_factory=ToolConfig)

    # Fact management tools
    upsert_fact: ToolConfig = Field(default_factory=ToolConfig)
    get_user_facts: ToolConfig = Field(default_factory=ToolConfig)
    forget_context: ToolConfig = Field(default_factory=ToolConfig)

    # Graph and state tools
    query_graph: ToolConfig = Field(default_factory=ToolConfig)
    update_scratchpad: ToolConfig = Field(default_factory=ToolConfig)
    get_agent_state: ToolConfig = Field(default_factory=ToolConfig)

    # Advanced tools
    streaming_search: ToolConfig = Field(default_factory=ToolConfig)
    batch_operations: ToolConfig = Field(default_factory=ToolConfig)
    webhook_management: ToolConfig = Field(default_factory=ToolConfig)
    event_notification: ToolConfig = Field(default_factory=ToolConfig)
    analytics: ToolConfig = Field(default_factory=ToolConfig)
    metrics: ToolConfig = Field(default_factory=ToolConfig)


class Config(BaseModel):
    """Main configuration object."""

    version: str = Field(default="0.1.0", description="Configuration version")
    veris_memory: VerisMemoryConfig = Field(default_factory=VerisMemoryConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    webhooks: WebhookConfig = Field(default_factory=WebhookConfig)
    streaming: StreamingConfig = Field(default_factory=StreamingConfig)
    analytics: AnalyticsConfig = Field(default_factory=AnalyticsConfig)

    class Config:
        extra = "forbid"  # Don't allow extra fields


def load_config(config_path: Optional[Path] = None) -> Config:
    """
    Load configuration from file and environment variables.

    Args:
        config_path: Path to configuration file. If None, looks for
                    VERIS_MCP_CONFIG_PATH environment variable.

    Returns:
        Loaded and validated configuration

    Raises:
        FileNotFoundError: If config file specified but not found
        ValueError: If configuration is invalid
    """
    # Determine config file path
    if config_path is None:
        env_path = os.getenv("VERIS_MCP_CONFIG_PATH")
        if env_path:
            config_path = Path(env_path)

    # Load from file if specified
    config_data: Dict[str, Any] = {}
    if config_path and config_path.exists():
        with open(config_path, "r") as f:
            config_data = json.load(f)
    elif config_path:
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    # Override with environment variables
    env_overrides = {}

    # Server log level override
    log_level = os.getenv("VERIS_MCP_LOG_LEVEL")
    if log_level:
        env_overrides.setdefault("server", {})["log_level"] = log_level

    # Merge environment overrides
    if env_overrides:
        config_data = _deep_merge(config_data, env_overrides)

    return Config(**config_data)


def create_default_config(config_path: Path) -> None:
    """
    Create a default configuration file.

    Args:
        config_path: Path where to create the configuration file
    """
    default_config = {
        "version": "0.1.0",
        "veris_memory": {
            "api_url": "https://api.verismemory.com",
            "api_key": "${VERIS_MEMORY_API_KEY}",
            "user_id": "${VERIS_MEMORY_USER_ID}",
            "timeout_ms": 30000,
            "max_retries": 3,
        },
        "server": {
            "log_level": "INFO",
            "max_concurrent_requests": 10,
            "cache_enabled": True,
            "cache_ttl_seconds": 300,
            "request_timeout_ms": 30000,
        },
        "tools": {
            "store_context": {
                "enabled": True,
                "max_content_size": 1048576,
                "allowed_context_types": ["*"],
            },
            "retrieve_context": {"enabled": True, "max_results": 100, "default_limit": 10},
            "search_context": {"enabled": True, "max_results": 100, "default_limit": 10},
            "delete_context": {"enabled": False, "max_results": 100, "default_limit": 10},
            "list_context_types": {"enabled": True, "max_results": 100, "default_limit": 10},
            "streaming_search": {"enabled": True, "max_results": 10000, "default_limit": 1000},
            "batch_operations": {"enabled": True, "max_results": 1000, "default_limit": 50},
            "webhook_management": {"enabled": True},
            "event_notification": {"enabled": True},
            "analytics": {"enabled": True},
            "metrics": {"enabled": True},
        },
        "webhooks": {
            "enabled": True,
            "max_subscriptions": 1000,
            "event_buffer_size": 10000,
            "max_retries": 3,
            "timeout_seconds": 30.0,
            "initial_backoff_seconds": 1.0,
            "max_backoff_seconds": 60.0,
            "max_concurrent_deliveries": 100,
            "signing_secret": "${WEBHOOK_SIGNING_SECRET}",
        },
        "streaming": {
            "enabled": True,
            "chunk_size": 1024,
            "max_concurrent_streams": 10,
            "buffer_size": 8192,
            "default_batch_size": 50,
            "max_batch_size": 1000,
        },
        "analytics": {
            "enabled": True,
            "retention_seconds": 3600,
            "max_points_per_metric": 10000,
            "aggregation_interval_seconds": 60,
            "cache_ttl_seconds": 300,
            "export_enabled": False,
            "export_endpoint": None,
            "export_interval_seconds": 300,
        },
    }

    # Create directory if it doesn't exist
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Write configuration file
    with open(config_path, "w") as f:
        json.dump(default_config, f, indent=2)


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge two dictionaries.

    Args:
        base: Base dictionary
        override: Override dictionary

    Returns:
        Merged dictionary
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value

    return result
