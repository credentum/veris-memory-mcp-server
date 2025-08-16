"""
Veris Memory MCP Server

A Model Context Protocol server that provides Claude CLI with access to Veris Memory
context storage and retrieval capabilities.
"""

__version__ = "0.2.0"
__author__ = "Veris Memory Team"
__license__ = "MIT"

from .config.settings import Config, load_config
from .server import VerisMemoryMCPServer
from .utils import HealthChecker, MemoryCache

__all__ = [
    "VerisMemoryMCPServer",
    "Config",
    "load_config",
    "MemoryCache",
    "HealthChecker",
    "__version__",
    "__author__",
    "__license__",
]
