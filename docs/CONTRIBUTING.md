# Contributing to Veris Memory MCP Server

Thank you for your interest in contributing! This document provides guidelines for contributing to the Veris Memory MCP Server project.

## Development Setup

### Prerequisites

- Python 3.10 or higher
- Git
- GitHub account

### Environment Setup

1. **Fork and clone the repository:**
   ```bash
   git clone https://github.com/your-username/veris-memory-mcp-server.git
   cd veris-memory-mcp-server
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install development dependencies:**
   ```bash
   pip install -e ".[dev,test]"
   ```

4. **Install pre-commit hooks:**
   ```bash
   pre-commit install
   ```

5. **Set up environment variables for testing:**
   ```bash
   export VERIS_MEMORY_API_KEY="test-key"
   export VERIS_MEMORY_USER_ID="test-user"
   ```

## Development Workflow

### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Make Your Changes

Follow these guidelines:

- **Code Style**: We use Black, isort, and flake8
- **Type Hints**: All new code must include type hints
- **Documentation**: Update docstrings and documentation
- **Tests**: Add tests for new functionality

### 3. Run Quality Checks

```bash
# Format code
black src tests examples
isort src tests examples

# Type checking
mypy src --config-file mypy.ini

# Linting
flake8 src tests examples

# Security scan
bandit -r src/

# Run tests
pytest --cov=src/veris_memory_mcp_server --cov-report=term-missing
```

### 4. Commit Your Changes

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```bash
git add .
git commit -m "feat: add new context validation feature"
```

**Commit Types:**
- `feat:` - New features
- `fix:` - Bug fixes
- `docs:` - Documentation changes
- `test:` - Test additions/changes
- `refactor:` - Code refactoring
- `perf:` - Performance improvements
- `chore:` - Maintenance tasks

### 5. Push and Create Pull Request

```bash
git push origin feature/your-feature-name
```

Then create a pull request through GitHub.

## Code Guidelines

### Python Code Style

- **Line Length**: Maximum 100 characters
- **Imports**: Use isort for organizing imports
- **Formatting**: Use Black for code formatting
- **Naming**: Use descriptive names, follow PEP 8
- **Type Hints**: Required for all new code

Example:
```python
from typing import Any, Dict, List, Optional

async def process_context(
    context_type: str,
    content: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Process context data with validation.
    
    Args:
        context_type: Type of context to process
        content: Context content data
        metadata: Optional metadata
        
    Returns:
        Processed context result
        
    Raises:
        ValidationError: If context data is invalid
    """
    # Implementation here
    pass
```

### Documentation

- **Docstrings**: Use Google-style docstrings
- **Type Hints**: Include in function signatures
- **Examples**: Provide usage examples where helpful
- **README**: Update README.md for user-facing changes

### Testing

- **Coverage**: Aim for >90% test coverage
- **Test Types**: Unit tests, integration tests, and example tests
- **Mocking**: Use mocks for external dependencies
- **Fixtures**: Use pytest fixtures for reusable test components

Example test:
```python
import pytest
from unittest.mock import AsyncMock

from veris_memory_mcp_server.tools.store_context import StoreContextTool


class TestStoreContextTool:
    @pytest.fixture
    def mock_client(self):
        client = AsyncMock()
        client.store_context.return_value = {"context_id": "test-123"}
        return client
    
    @pytest.fixture
    def tool(self, mock_client):
        return StoreContextTool(mock_client, {"max_content_size": 1000})
    
    @pytest.mark.asyncio
    async def test_store_success(self, tool, mock_client):
        result = await tool.execute({
            "context_type": "test",
            "content": {"text": "Test content"}
        })
        
        assert not result.is_error
        mock_client.store_context.assert_called_once()
```

## Project Structure

```
veris-memory-mcp-server/
├── src/veris_memory_mcp_server/    # Main package
│   ├── protocol/                   # MCP protocol implementation
│   ├── tools/                      # Tool implementations
│   ├── client/                     # Veris Memory client wrapper
│   ├── config/                     # Configuration management
│   └── utils/                      # Utility modules
├── tests/                          # Test files
│   ├── unit/                       # Unit tests
│   └── integration/                # Integration tests
├── examples/                       # Usage examples
├── docs/                          # Documentation
└── scripts/                       # Utility scripts
```

## Adding New Features

### Adding a New Tool

1. **Create tool class** in `src/veris_memory_mcp_server/tools/`:
   ```python
   from .base import BaseTool, ToolResult
   
   class YourNewTool(BaseTool):
       name = "your_tool"
       description = "Description of your tool"
       
       def get_schema(self):
           # Define tool schema
           pass
       
       async def execute(self, arguments):
           # Implement tool logic
           pass
   ```

2. **Add tool to server** in `server.py`:
   ```python
   if self.config.tools.your_tool.enabled:
       tool = YourNewTool(self.veris_client, config.dict())
       self._tools["your_tool"] = tool
       self.mcp_handler.register_tool(tool.get_schema(), tool)
   ```

3. **Add configuration** in `config/settings.py`:
   ```python
   class ToolsConfig(BaseModel):
       your_tool: ToolConfig = Field(default_factory=ToolConfig)
   ```

4. **Add tests** in `tests/unit/test_tools.py`:
   ```python
   class TestYourNewTool:
       # Add comprehensive tests
       pass
   ```

### Adding New Protocol Features

1. **Update schemas** in `protocol/schemas.py`
2. **Update handlers** in `protocol/handlers.py`
3. **Add tests** in `tests/unit/test_protocol.py`

## Testing Guidelines

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/veris_memory_mcp_server --cov-report=html

# Run specific test file
pytest tests/unit/test_tools.py

# Run specific test
pytest tests/unit/test_tools.py::TestStoreContextTool::test_store_success

# Run tests with different markers
pytest -m "unit"      # Unit tests only
pytest -m "integration"  # Integration tests only
```

### Test Categories

- **Unit Tests**: Test individual functions/classes in isolation
- **Integration Tests**: Test component interactions
- **Example Tests**: Test example scripts work correctly

### Writing Good Tests

1. **Descriptive Names**: Test names should describe what is being tested
2. **Arrange-Act-Assert**: Structure tests clearly
3. **Mock External Dependencies**: Don't rely on external services
4. **Test Edge Cases**: Include error conditions and boundary cases
5. **Use Fixtures**: Reuse common test setup

## Documentation

### API Documentation

- Use clear, descriptive docstrings
- Include parameter types and return values
- Provide usage examples
- Document exceptions that can be raised

### User Documentation

- Update README.md for user-facing changes
- Add examples to the examples/ directory
- Update integration guides
- Keep CHANGELOG.md current

## Release Process

### Version Bumping

We use semantic versioning (MAJOR.MINOR.PATCH):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backwards compatible)
- **PATCH**: Bug fixes (backwards compatible)

### Changelog

Update CHANGELOG.md with:
- New features
- Bug fixes
- Breaking changes
- Deprecations

## Getting Help

- **GitHub Issues**: For bug reports and feature requests
- **GitHub Discussions**: For questions and general discussion
- **Code Review**: All PRs require review before merging

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Help others learn and grow
- Focus on what's best for the project

## Recognition

Contributors will be recognized in:
- CONTRIBUTORS.md file
- Release notes for significant contributions
- GitHub contributor listings

Thank you for contributing to Veris Memory MCP Server!