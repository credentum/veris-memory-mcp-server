"""Main entry point for running the Veris Memory MCP Server."""

import sys
from .main import main

if __name__ == "__main__":
    # Click will handle sys.argv automatically
    main()