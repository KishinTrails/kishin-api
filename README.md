<p align="center">
  <img src="logo.png" alt="Kishin Trails Logo" width="200"/>
</p>

# Kishin Trails API

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python)](https://www.python.org/)
[![Poetry](https://img.shields.io/badge/Poetry-1.8+-60A5FA?logo=python)](https://python-poetry.org/)

## ⚠️ WARNING: Under Heavy Development ⚠️

**This project is currently under active and heavy development. It is NOT ready for general use and may contain bugs, incomplete features, or breaking changes. Use at your own risk.**

Backend API service for the Kishin Trails project, providing OSM data integration, user authentication, and geo-spatial operations with H3 fog-of-war mechanics.

## Features

- **User Authentication** - JWT-based auth with registration/login
- **POI Discovery** - Points of interest from OpenStreetMap (peaks, natural areas, industrial zones)
- **H3 Geospatial Indexing** - Uber's hexagonal spatial index for location-based queries
- **Exploration Tracking** - Track user-explored H3 cells for fog-of-war mechanics
- **Caching Layer** - SQLite-based caching for POI data to reduce Overpass API calls
- **GPX Import** - Import hiking trails from GPX files

## Tech Stack

- **Framework**: FastAPI with async support
- **Database**: SQLite with SQLAlchemy ORM
- **Geospatial**: Shapely, GeoPandas, H3
- **Authentication**: JWT with pwdlib
- **Data**: OpenStreetMap via Overpass API
- **Testing**: pytest with pytest-asyncio
- **Package Management**: Poetry

## Prerequisites

- Python 3.12 or later
- Poetry 1.8 or later
- [kishin-frontend](https://github.com/KishinTrails/kishin-frontend) (optional, for UI)

## Getting Started

### Install Dependencies

```bash
poetry install
poetry shell
```

### Environment Configuration

Create a `.env` file in the project root:

```env
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///kishin.db
ACCESS_TOKEN_EXPIRE_MINUTES=30
DEFAULT_CENTER_LAT=45.0
DEFAULT_CENTER_LON=6.0
DEFAULT_POI_RADIUS_M=100
```

**Required variables:**
- `SECRET_KEY` - For JWT token signing
- `DATABASE_URL` - Database connection string

### Run Development Server

```bash
poetry run python -m kishin_trails.main
```

The API will be available at `http://localhost:8000`.

### API Documentation

Interactive API docs are available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Available Scripts

| Command | Description |
|---------|-------------|
| `poetry run python -m kishin_trails.main` | Start development server |
| `poetry run pytest -v` | Run all tests |
| `poetry run pytest --cov=kishin_trails -v` | Run tests with coverage |
| `poetry install` | Install dependencies |
| `poetry shell` | Activate virtual environment |

## API Endpoints

### Authentication

- **POST** `/auth/register` - Register new user
  - Body: `{ "username": "string", "password": "string" }`
  - Returns: User object with id and username

- **POST** `/auth/login` - Login to receive JWT
  - Body: `application/x-www-form-urlencoded` with `username` and `password`
  - Returns: `{ "access_token": "string", "token_type": "bearer" }`

- **GET** `/me` - Get current user info (protected)
  - Headers: `Authorization: Bearer <token>`
  - Returns: `{ "username": "string", "id": integer }`

### POI (Points of Interest)

All POI endpoints require authentication.

- **GET** `/poi/bycell?h3Cell={cell}` - Get POI for single H3 cell
  - Query: `h3Cell` - H3 cell identifier (e.g., `851f9633fffffff`)
  - Returns: POI data with type, center coordinates, and POI details
  - Status 404: No POI data for this cell

- **GET** `/poi/bycells?h3Cells={cell1}&h3Cells={cell2}...` - Batch fetch POIs
  - Query: `h3Cells` - List of H3 cell identifiers (up to 100)
  - Returns: `{ "cells": [...], "count": integer }`
  - Status 204: No valid tiles found

### Trails

All trails endpoints require authentication.

- **GET** `/trails/explored` - Get user's explored H3 cells
  - Returns: `{ "explored": ["851f9633fffffff", ...] }`

### Root

- **GET** `/` - Public root endpoint
  - Returns: Welcome message

## Data Models

### User
```json
{
  "id": 1,
  "username": "string"
}
```

### Token
```json
{
  "access_token": "string",
  "token_type": "bearer"
}
```

### POI Response
```json
{
  "h3_cell": "851f9633fffffff",
  "type": "peak|natural|industrial",
  "center": {
    "lat": 45.123,
    "lng": 6.456
  },
  "count": 1,
  "poi": {
    "id": 123456,
    "name": "Mont Blanc",
    "geometry": "POINT(...)",
    "elevation": 4809
  }
}
```

### Explored Tiles
```json
{
  "explored": ["851f9633fffffff", "851f9637fffffff"]
}
```

## Testing

### Run All Tests

```bash
poetry run pytest -v
```

### Run Single Test

```bash
poetry run pytest test/test_overpass.py::test_defaults_are_reasonable -v
```

### Run with Coverage

```bash
poetry run pytest --cov=kishin_trails -v
```

Coverage reports are generated in `.coverage`.

## Code Quality

### Type Checking

The project uses strict type hints throughout. Run mypy (if configured):

```bash
poetry run mypy kishin_trails/
```

### Logging

Logs are configured with format: `%(asctime)s [%(levelname)s] %(name)s — %(message)`

Module-specific loggers are used (e.g., `logging.getLogger("PoI")`).

## CI/CD

GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every push and pull request to `main`:

1. Install dependencies
2. Run linting
3. Run tests with coverage
4. Build validation

## 🧪 Quality and Testing

Kishin Trails uses **AI-assisted development** tools to accelerate coding, followed by **human validation** and **automated tests** for correctness.

- pytest for unit and integration tests
- pytest-asyncio for async test support
- SQLite in-memory database for test isolation
- Mocked external services (Overpass API)

---

## 🔗 Useful Links

- [H3 Viewer](https://clupasq.github.io/h3-viewer/) - Visualize H3 cells
- [Overpass Turbo](https://overpass-turbo.eu) - Query and explore OSM data
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Shapely Documentation](https://shapely.readthedocs.io/)

---

## 📂 Related Projects

- [kishin-api](https://github.com/KishinTrails/kishin-api) - This repository
- [kishin-frontend](https://github.com/KishinTrails/kishin-frontend) - Vue 3/Ionic mobile frontend

---

## 📜 License

This project is released under the [MIT License](LICENSE).

---

*© 2026 Kishin Trails. Built with care, code, and a spirit to explore.*
