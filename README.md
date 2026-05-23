<p align="center">
  <img src="logo.png" alt="Kishin Trails Logo" width="200"/>
</p>

# Kishin Trails API

[![FastAPI](https://img.shields.io/badge/FastAPI-0.128+-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.13+-3776AB?logo=python)](https://www.python.org/)
[![Poetry](https://img.shields.io/badge/Poetry-2.0+-60A5FA?logo=python)](https://python-poetry.org/)

---

## ⚠️ WARNING: Under Heavy Development ⚠️

**This project is currently under active and heavy development. It is NOT ready for general use and may contain bugs, incomplete features, or breaking changes. Use at your own risk.**

---

Backend API service for the Kishin Trails project, providing OSM data integration, user authentication, and geo-spatial operations with S2 cell fog-of-war mechanics.

## Features

- **User Authentication** - JWT-based auth with registration/login
- **POI Discovery** - Points of interest from OpenStreetMap (peaks, natural areas, industrial zones)
- **S2 Geospatial Indexing** - Google's S2 geometry library for location-based queries
- **Exploration Tracking** - Track user-explored S2 cells for fog-of-war mechanics
- **GPX Import Script** - CLI tool to import hiking trails from GPX files

## Prerequisites

- Python 3.13 or later
- Poetry 2.0 or later
- [kishin-frontend](https://github.com/KishinTrails/kishin-frontend) (optional, for UI)

## Getting Started

### Install Dependencies

```bash
poetry install
```

### Environment Configuration

Create a `.env` file in the project root.

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

These provide comprehensive, always-up-to-date documentation of all available endpoints, request/response schemas, and authentication requirements.

## CLI Scripts

### `import_gpx.py` - Import GPX Tracks

Import GPX files and mark S2 cells as explored for a user.

```bash
poetry run python scripts/import_gpx.py <gpx_file> --user <username> [--resolution 16] [--dry-run]
```

**Arguments:**
- `gpx_file` - Path to GPX file
- `--user` - Username to associate explored cells with
- `--resolution` - S2 level (default: 16)
- `--dry-run` - Show what would be imported without saving

### `debug_geo.py` - Debug Geo/S2/Overpass Utilities

Debug tool for testing coordinates, S2 cells, and Overpass queries.

```bash
poetry run python scripts/debug_geo.py --location <name> [--overpass] [--execute]
poetry run python scripts/debug_geo.py --lat <lat> --lng <lng> [--resolution 16]
poetry run python scripts/debug_geo.py --s2-cell <cell_id> [--parent-level 0]
poetry run python scripts/debug_geo.py --list-locations
```

**Arguments:**
- `--location` - Use predefined location from DEBUG_LOCATIONS
- `--lat` / `--lng` - Use specific coordinates
- `--s2-cell` - Use specific S2 cell
- `--h3-cell` - Use specific H3 cell (converted to S2)
- `--resolution` - S2 level (default: 16)
- `--parent-level` - S2 parent level for search (default: 0)
- `--overpass` - Output Overpass query
- `--execute` - Execute the Overpass query
- `--list-locations` - List available debug locations

### `find_perlin_params.py` - Find Optimal Perlin Noise Parameters

Test Perlin noise parameter combinations against S2 cells with configurable conditions to find optimal configurations.

```bash
poetry run python scripts/find_perlin_params.py --config <config.json> [--no-cache]
```

**Arguments:**
- `--config` - Path to JSON configuration file with conditions and state_space
- `--no-cache` - Run without using or saving to cache

**Config file format:**
```json
{
  "conditions": [
    {"type": "min_active", "cells": [...], "count": 5},
    {"type": "cell_must_be_active", "cells": ["851f9633fffffff"]}
  ],
  "state_space": {
    "scale": {"min": 50, "max": 300, "step": 10},
    "threshold": {"min": 0.3, "max": 0.7, "step": 0.05},
    "octaves": {"min": 2, "max": 4, "step": 1},
    "amplitudeDecay": {"min": 0.4, "max": 0.6, "step": 0.1}
  }
}
```

### `populate_cache.py` - Pre-populate POI Cache

Populate cache with POI data for S2 tiles. Takes comma-separated S2 cell IDs as argument.

```bash
poetry run python scripts/populate_cache.py 89c25a221,89c25a223 [--dry-run] [--fill-polygons] [--no-cache]
```

**Arguments:**
- `s2_cells` - Comma-separated S2 cell IDs (level <= 16), e.g., `'89c25a221,89c25a223'`
- `--dry-run` - Print what would be done without actually caching
- `--fill-polygons` - Run polygon interior filling after processing tiles (second pass)
- `--fill-only` - Only run polygon filling, skip tile processing
- `--no-cache` - Re-process all tiles, inserting only missing POIs (preserve existing data)

## CI/CD

GitHub Actions workflows run on every push and pull request to `main`:

**Linting** (`.github/workflows/lint.yaml`):
- Run pylint with custom configuration (fail under 9.5)
- Run ty type checker

**Testing** (`.github/workflows/test.yaml`):
- Run pytest with coverage reporting

## 🔗 Useful Links

- [S2 Viewer](https://igorgatis.github.io/ws2/) - Visualize S2 cells
- [Overpass Turbo](https://overpass-turbo.eu) - Query and explore OSM data

## 📂 Related Projects

- [kishin-frontend](https://github.com/KishinTrails/kishin-frontend) - Vue 3/Ionic mobile frontend

---

*© 2026 Kishin Trails. Built with care, code, and a spirit to explore.*
