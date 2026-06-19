# Contributing Guide

Thank you for your interest in contributing to the OpenEO Workspaces API!

## Code of Conduct

This project adheres to the [OpenEO Consortium Code of Conduct](https://openeo.org).

## Getting Started

1. **Fork the repository**
   ```bash
   git clone git@github.com:yourusername/openeo-workspaces-api.git
   cd openeo-workspaces-api
   ```

2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Set up development environment**
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   pip install pytest pytest-asyncio black isort flake8 mypy
   ```

## Development Workflow

### Code Style

We use the following tools for code quality:

- **Black** for formatting
- **isort** for import sorting
- **Flake8** for linting
- **mypy** for type checking

Before committing, run:

```bash
make format
make lint
```

### Testing

Write tests for new features:

```bash
# Run tests
make test

# Run specific test
pytest tests/test_file.py::test_function

# Run with coverage
pytest tests/ --cov=workspace_service
```

### Documentation

- Update docstrings using Google style
- Update README if adding features
- Add examples for new endpoints

## Commit Message Guidelines

Use conventional commits:

```
feat: Add new feature
fix: Fix a bug
docs: Update documentation
style: Format code
refactor: Refactor code
test: Add tests
chore: Update dependencies
```

Example:
```
feat: Add workspace tagging support

- Add tags field to workspace schema
- Implement GET /workspaces?tags=tag1,tag2 filtering
- Add tests for tagging functionality
```

## Pull Request Process

1. **Update code and tests**
   ```bash
   # Make your changes
   make format && make lint && make test
   ```

2. **Commit and push**
   ```bash
   git add .
   git commit -m "feat: your feature description"
   git push origin feature/your-feature-name
   ```

3. **Create Pull Request**
   - Provide clear description of changes
   - Link related issues
   - Include screenshots/examples if applicable

4. **Code Review**
   - Address feedback from maintainers
   - Keep discussion professional and constructive

## Adding Features

### New Endpoints

1. **Define Pydantic model** in `workspace_service/models.py`
2. **Implement route handler** in appropriate `workspace_service/routes/` file
3. **Add tests** in `tests/`
4. **Update OpenAPI spec** if needed
5. **Update README** with endpoint documentation

### New Workspace Provider

1. **Add provider config** to `workspace_service/routes/providers.py`
2. **Define required parameters**
3. **Update workspace models** if provider needs new fields
4. **Add provider-specific tests**

### Database Changes

1. **Update Elasticsearch mapping** in `workspace_service/db.py`
2. **Add migration if breaking change**
3. **Update models** to reflect schema

## Architecture

```
workspace_service/
├── config.py        # Configuration
├── auth.py          # Authentication
├── db.py            # Database layer
├── models.py        # Data models
└── routes/          # API endpoints
    ├── providers.py
    └── workspaces.py
```

## Key Concepts

### User Scoping

All workspace operations are scoped to the authenticated user via the `sub` claim in the JWT token:

```python
user_id = token.sub
workspace = await db.get_workspace(workspace_id, user_id)
```

### Status States

Workspaces have these states:
- `provisioning`: Being created, not ready yet
- `ready`: Available for use
- `unavailable`: Connection lost or error

### Provider Configuration

Providers define:
- `intents`: "create" (new workspace) or "register" (existing)
- `parameters`: Required provider-specific configuration
- `title/description`: User-facing information

## Reporting Issues

### Bug Reports

Include:
- Python version and OS
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs/error messages

### Feature Requests

Describe:
- Use case and motivation
- Proposed solution
- Example API usage
- Any related issues

## Licensing

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.

## Questions?

- Open an issue for discussion
- Email: openeo.psc@uni-muenster.de
- Check [openeo.org](https://openeo.org) for more info

## Resources

- [OpenEO API Spec](https://github.com/Open-EO/openeo-api)
- [FastAPI Docs](https://fastapi.tiangolo.com)
- [Elasticsearch Guide](https://www.elastic.co/guide/en/elasticsearch/reference/current/index.html)
- [Kubernetes Docs](https://kubernetes.io/docs/)
