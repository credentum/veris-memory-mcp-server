"""
Veris Memory MCP Server

A Model Context Protocol server that provides Claude CLI with access to Veris Memory
context storage and retrieval capabilities.
"""

__version__ = "0.1.0"
__author__ = "Veris Memory Team"
__license__ = "MIT"

from .server import VerisMemoryMCPServer

__all__ = ["VerisMemoryMCPServer", "__version__", "__author__", "__license__"]