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

Backend API service for the Kishin Trails project, providing OSM data integration, user authentication, and geo-spatial operations with H3 fog-of-war mechanics.

## Features

- **User Authentication** - JWT-based auth with registration/login
- **POI Discovery** - Points of interest from OpenStreetMap (peaks, natural areas, industrial zones)
- **H3 Geospatial Indexing** - Uber's hexagonal spatial index for location-based queries
- **Exploration Tracking** - Track user-explored H3 cells for fog-of-war mechanics
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

Import GPX files and mark H3 cells as explored for a user.

```bash
poetry run python scripts/import_gpx.py <gpx_file> --user <username> [--resolution 10] [--dry-run]
```

**Arguments:**
- `gpx_file` - Path to GPX file
- `--user` - Username to associate explored cells with
- `--resolution` - H3 resolution (default: 10)
- `--dry-run` - Show what would be imported without saving

### `debug_geo.py` - Debug Geo/H3/Overpass Utilities

Debug tool for testing coordinates, H3 cells, and Overpass queries.

```bash
poetry run python scripts/debug_geo.py --location <name> [--overpass] [--execute]
poetry run python scripts/debug_geo.py --lat <lat> --lng <lng> [--resolution 10]
poetry run python scripts/debug_geo.py --h3-cell <cell_id> [--level 0]
poetry run python scripts/debug_geo.py --list-locations
```

**Arguments:**
- `--location` - Use predefined location from DEBUG_LOCATIONS
- `--lat` / `--lng` - Use specific coordinates
- `--h3-cell` - Use specific H3 cell
- `--resolution` - H3 resolution (default: 10)
- `--level` - H3 parent level for search (default: 0)
- `--radius` - Override radius in meters
- `--overpass` - Output Overpass query
- `--execute` - Execute the Overpass query
- `--list-locations` - List available debug locations

### `find_perlin_params.py` - Find Optimal Perlin Noise Parameters

Test Perlin noise parameter combinations against H3 cells with configurable conditions to find optimal configurations.

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

Populate cache with POI data for H3 tiles. Takes comma-separated H3 cell IDs as argument.

```bash
poetry run python scripts/populate_cache.py 851f9633fffffff,851f9637fffffff [--dry-run] [--fill-polygons] [--no-cache]
```

**Arguments:**
- `h3_cells` - Comma-separated H3 cell IDs (resolution <= 10), e.g., `'tile1,tile2,tile3'`
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

- [H3 Viewer](https://clupasq.github.io/h3-viewer/) - Visualize H3 cells
- [Overpass Turbo](https://overpass-turbo.eu) - Query and explore OSM data

## 📂 Related Projects

- [kishin-frontend](https://github.com/KishinTrails/kishin-frontend) - Vue 3/Ionic mobile frontend

---

*© 2026 Kishin Trails. Built with care, code, and a spirit to explore.*
