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

- **User Authentication** - JWT-based login; accounts are created with the `kishin` CLI, not over HTTP
- **POI Discovery** - Points of interest from OpenStreetMap (peaks, natural areas, industrial zones)
- **S2 Geospatial Indexing** - Google's S2 geometry library for location-based queries
- **Exploration Tracking** - Track user-explored S2 cells for fog-of-war mechanics
- **`kishin` CLI** - Account administration, database maintenance, GPX import, cache population, and geo/noise debugging

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

## `kishin` CLI

Installed as a console script by `poetry install`; run `poetry run kishin --help` for
the full command tree, or `poetry run kishin <group> --help` for one group.

### `kishin user` - Account Administration

The only way to create an account — `POST /auth/register` does not exist.

```bash
poetry run kishin user list
poetry run kishin user create alice [--password '...']
poetry run kishin user show alice [--tiles]
poetry run kishin user reset-password alice [--password '...']
poetry run kishin user rename alice alicia
poetry run kishin user delete alice [--yes]
```

Omit `--password` on `create`/`reset-password` and one is generated and printed once.

### `kishin db` - Database Maintenance

```bash
poetry run kishin db init         # create any missing tables
poetry run kishin db stats        # row counts per table
poetry run kishin db checkpoint   # run a WAL checkpoint now
```

### `kishin gpx import` - Import GPX Tracks

Import a GPX file and mark its S2 cells as explored for a user.

```bash
poetry run kishin gpx import <gpx_file> --user <username> [--resolution 16] [--dry-run]
```

### `kishin geo` - Debug Geo/S2/Overpass Utilities

```bash
poetry run kishin geo cell <lat> <lng> [--resolution 16]
poetry run kishin geo info <s2_cell> [--parent-level 0]
poetry run kishin geo h3 <h3_cell>
poetry run kishin geo locations [--location <name>]
poetry run kishin geo overpass <s2_cell> [--execute]
```

### `kishin noise` - Perlin Noise Fog-of-War Gate

```bash
poetry run kishin noise cell <s2_cell> [--scale] [--octaves] [--amplitude-decay]
poetry run kishin noise search --config <config.json>
poetry run kishin noise clear-cache [--yes]
```

`search` grid-searches Perlin noise parameters against S2 cells with configurable
activation conditions. **Config file format:**
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

### `kishin cache` - Pre-populate the POI Cache

```bash
poetry run kishin cache populate 89c25a221,89c25a223 [--dry-run] [--fill-polygons] [--no-cache]
poetry run kishin cache populate --fill-only
poetry run kishin cache show 89c25a221
```

`populate` takes comma-separated S2 cell IDs (level <= 16), uncompacts them to level
16, and queries Overpass once per level-9 parent. `--fill-polygons` runs a second pass
filling the interior tiles of polygon features (forests, parks, industrial zones)
after the first pass stores them.

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
