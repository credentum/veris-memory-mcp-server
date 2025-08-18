"""
Main entry point for Veris Memory MCP Server.

This module provides the command-line interface for the MCP server,
handling startup, configuration, and integration with Claude CLI.
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional

import click
import structlog

from .config.settings import load_config
from .server import VerisMemoryMCPServer
from .utils.logging import setup_logging


@click.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Path to configuration file",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    help="Set logging level",
)
@click.option(
    "--stdio/--no-stdio",
    default=True,
    help="Use stdio transport for Claude CLI (default)",
)
@click.version_option()
def main(
    config: Optional[Path] = None,
    log_level: Optional[str] = None,
    stdio: bool = True,
) -> None:
    """
    Veris Memory MCP Server - Provides Claude CLI access to Veris Memory.

    This server implements the Model Context Protocol to expose Veris Memory
    context storage and retrieval capabilities to Claude CLI and other MCP hosts.
    """
    try:
        # Load configuration
        config_data = load_config(config_path=config)

        # Set up logging
        if log_level:
            config_data.server.log_level = log_level.upper()

        setup_logging(config_data.server.log_level)
        logger = structlog.get_logger()

        logger.info(
            "Starting Veris Memory MCP Server",
            version=config_data.version,
            config_file=str(config) if config else "default",
            log_level=config_data.server.log_level,
        )

        # Validate required environment variables
        if not config_data.veris_memory.api_key:
            logger.error("VERIS_MEMORY_API_KEY environment variable is required")
            sys.exit(1)

        if not config_data.veris_memory.user_id:
            logger.error("VERIS_MEMORY_USER_ID environment variable is required")
            sys.exit(1)

        # Create and run server
        server = VerisMemoryMCPServer(config_data)

        if stdio:
            logger.info("Starting server in stdio mode for Claude CLI")
            asyncio.run(server.run_stdio())
        else:
            logger.error("Only stdio transport is currently supported")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
        sys.exit(0)
    except Exception as e:
        logger.error("Server startup failed", error=str(e), exc_info=True)
        sys.exit(1)


@click.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(path_type=Path),
    help="Path to save configuration file",
)
def init_config(config: Optional[Path] = None) -> None:
    """Initialize a configuration file with default settings."""
    from .config.settings import create_default_config

    config_path = config or Path("config.json")

    if config_path.exists():
        click.echo(f"Configuration file already exists: {config_path}")
        if not click.confirm("Overwrite?"):
            return

    try:
        create_default_config(config_path)
        click.echo(f"Created configuration file: {config_path}")
        click.echo("\nNext steps:")
        click.echo("1. Set environment variables:")
        click.echo("   export VERIS_MEMORY_API_KEY='your-api-key'")
        click.echo("   export VERIS_MEMORY_USER_ID='your-user-id'")
        click.echo("2. Add to Claude CLI:")
        click.echo(
            "   claude mcp add veris-memory --env VERIS_MEMORY_API_KEY --env VERIS_MEMORY_USER_ID -- veris-memory-mcp-server"
        )
    except Exception as e:
        click.echo(f"Failed to create configuration file: {e}", err=True)
        sys.exit(1)


@click.group()
def cli() -> None:
    """Veris Memory MCP Server CLI."""
    pass


cli.add_command(main, name="serve")
cli.add_command(init_config, name="init")


if __name__ == "__main__":
    main()
