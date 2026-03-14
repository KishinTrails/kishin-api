# Kishin API - Developer Guide for Agents

## Project Overview
FastAPI server for the Kishin project, handling OSM data via Overpass API, user authentication, and geo-spatial operations.

## Build & Test Commands

**Running tests (single test):**
```bash
poetry run pytest test/test_overpass.py::test_defaults_are_reasonable -v
```

**Run all tests:**
```bash
poetry run pytest -v
```

**Run tests with coverage:**
```bash
poetry run pytest --cov=kishin_trails -v
```

**Development server:**
```bash
poetry run python -m kishin_trails.main
```

**Install dependencies (Poetry):**
```bash
poetry install
poetry shell
```

## Code Style Guidelines

### Imports
- Standard library imports first
- Third-party imports second (geopandas, shapely, fastapi, etc.)
- Local imports last (kishin_trails.*)
- Use `from __future__ import annotations` for forward references
- Group related imports with blank lines between logical groups

### Type Hints
- Use `type hints` for all function parameters and return types
- Prefer `str | None` over `Optional[str]`
- Use `Annotated` for FastAPI dependencies
- Use `List[X]` for generic lists, `Dict[str, Any]` for mappings

### Naming Conventions
- Files: lowercase with underscores (`overpass.py`, `auth.py`)
- Classes: PascalCase (`User`, `Base`, `Settings`)
- Functions/variables: camelCase (`getPasswordHash`, `buildBbox`)
- Constants: UPPER_CASE (`DATABASE_URL`, `OVERPASS_URL`)
- Modules with "test": `test_<module>.py`

### Error Handling
- Use HTTPException with appropriate status codes (400, 401, 404)
- Validate inputs with FastAPI Query/Body parameters and types
- Use `try/except` for external service calls (Overpass API, JWT decode)
- Log errors using the module logger with INFO/ERROR levels
- Raise ValueError for logical errors (CRS mismatch, invalid arguments)

### Database
- Use SQLAlchemy ORM with declarative Base
- All models inherit from `Base`
- Use dependency injection for database sessions (`get_db`)
- Create models in lifespan event handler
- Never commit models directly; use Session

### API Design
- Use FastAPI routers with clear prefixes (`/auth`, `/elements`)
- Include summary and description for all endpoints
- Use Pydantic schemas for request/response validation
- Implement proper authentication with JWT tokens
- Return JSON responses consistently

### Testing
- Use pytest with pytest_asyncio for async tests
- All async tests use `@pytest.mark.asyncio` decorator
- Use fixtures from `conftest.py` for database and HTTP client
- Mock external services (requests.post) with unittest.mock
- Tests should isolate dependencies (in-memory SQLite for tests)
- Use `tmp_path` fixture for file-based test isolation

### Logging
- Use Python logging module with format: `%(asctime)s [%(levelname)s] %(name)s — %(message)s`
- Create module-specific loggers (`logging.getLogger(__name__)`)
- Log INFO for normal operations, ERROR for failures
- Log request/response details for debugging

### Configuration
- All config via Pydantic Settings loaded from `.env`
- Never hardcode secrets in code
- Required env vars: `SECRET_KEY`, `DATABASE_URL`
- Default values provided for all settings

### Geo-Spatial Code
- Use geopandas for GeoDataFrames
- Always set CRS to "EPSG:4326" for latitude/longitude
- Convert to "EPSG:3857" for distance calculations
- Validate CRS compatibility before spatial operations
- Handle None/NaN geometries explicitly

### Git & Version Control
- Commit messages: concise, imperative mood ("Add user auth", "Fix bbox calculation")
- Push before creating PRs
- PR title: descriptive, summarizes changes
- Include test updates for all changes

### Dependencies
- FastAPI for web framework
- SQLAlchemy for database ORM
- Pydantic for validation
- Shapely/geopandas for geometry handling
- JWT/pwdlib for authentication
- Requests for HTTP client

### Agent Instructions
- ONLY do exactly what is asked. Do not add features, refactor, or improve code beyond the explicit request.
- When asked to create a class/factory, only create that class/factory. Do not add subclasses, methods, or related functionality unless explicitly requested.
- Do not modify other files unless explicitly instructed.
- Do not add comments, documentation, or explanations unless asked.
- Do not replace or refactor existing code unless explicitly told to do so.
- Never remove existing comments from files unless explicitly told to do so.
