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

Backend API service for the Kishin Trails project: OSM data integration, S2 cell fog-of-war
mechanics, the athlete's Garmin and Withings data, training plans, and login for its single
account.

## Features

- **Single account** - JWT-based login for one account, configured by `KISHIN_USERNAME` and `KISHIN_PASSWORD_HASH`
- **POI Discovery** - Points of interest from OpenStreetMap (peaks, natural areas, industrial zones)
- **S2 Geospatial Indexing** - Google's S2 geometry library for location-based queries
- **Exploration Tracking** - Track the explored S2 cells for fog-of-war mechanics
- **Athlete data** - Garmin activities (with GPS track and records) and Withings body
  measurements, read-only from the database health-sync fills
- **Training plans** - A plan imported from a JSON file, its weekly progression, and the
  completion of each training against a Garmin run
- **`kishin` CLI** - The account's password, database maintenance, GPX import, cache population,
  training plans, health data queries, geo/noise debugging, and the server itself

## API routes

Every API route is under `/api`. Every other path is a page of the web app when
`FRONTEND_DIR` is set (see Deployment), except `/withings`.

| Prefix | What it serves |
|--------|----------------|
| `/api/auth` | `POST /api/auth/login`, throttled per client address |
| `/api/config` | The map's default centre (`DEFAULT_CENTER_LAT` / `DEFAULT_CENTER_LON`), read by the app after login |
| `/api/poi` | POIs of one or several S2 cells; every tile with an active POI type, for the app's cache |
| `/api/trails` | The explored S2 cells: list, and record a new one |
| `/api/noise` | Perlin noise values of a set of S2 cells |
| `/api/athlete` | Activities, daily totals, one activity with its track and records, body measurements |
| `/api/plan` | The active plan's progression; candidate runs and completion of a training |
| `/withings` | A static page showing the code of Withings' OAuth redirect (health-sync's first sync) |

Every `/api` route except `/api/` and `/api/auth/login` needs `Authorization: Bearer <token>`.
`/api/athlete` answers 503 and `/api/plan` leaves out the Garmin figures while
`HEALTH_DATABASE_URL` is not set.

## Prerequisites

- Python 3.13 or later
- Poetry 2.0 or later
- PostgreSQL 17, the server health-sync writes to (locally: health-sync's `compose.dev.yaml`)
- Docker, for the tests (see Testing below)
- [kishin-frontend](https://github.com/KishinTrails/kishin-frontend) (optional, for UI)

## Getting Started

### Install Dependencies

```bash
poetry install
```

### Environment Configuration

Create a `.env` file in the project root.

**Required variables** (the server refuses to start while `DATABASE_URL`, `SECRET_KEY`,
`KISHIN_USERNAME` or `KISHIN_PASSWORD_HASH` is missing):
- `SECRET_KEY` - For JWT token signing; no default, at least 32 characters. Generate one with
  `python -c 'import secrets; print(secrets.token_hex(32))'`
- `DATABASE_URL` - The PostgreSQL game database, `postgresql+psycopg://user:password@host/kishin`;
  no default. It holds a password, so it is read from the file `/run/secrets/DATABASE_URL`, or
  `dev-secrets/DATABASE_URL` for a local run
- `KISHIN_USERNAME` - Username of the only account
- `KISHIN_PASSWORD_HASH` - Argon2 hash of its password. Read from the file
  `/run/secrets/KISHIN_PASSWORD_HASH`, or `dev-secrets/KISHIN_PASSWORD_HASH` for a local run
  (git-ignored); `kishin password` writes it

**Optional settings** (defaults in `kishin_trails/config.py`):
- `HEALTH_DATABASE_URL` - health-sync's PostgreSQL database, read by `/athlete`, `/plan` and
  `kishin health`; read from `/run/secrets/HEALTH_DATABASE_URL` or
  `dev-secrets/HEALTH_DATABASE_URL`, like `DATABASE_URL`. `HEALTH_DB_PREFIX` is health-sync's
  schema name prefix
- `TIMEZONE` - IANA time zone deciding the calendar day of a Withings reading (default `UTC`)
- `CORS_ORIGINS`, `ACCESS_TOKEN_EXPIRE_MINUTES` (default 1440), `OVERPASS_URL`,
  `DEFAULT_CENTER_LAT` / `DEFAULT_CENTER_LON` (default central Paris), and the Perlin noise
  gate `NOISE_SCALE`, `NOISE_OCTAVES`, `NOISE_AMPLITUDE_DECAY`, `NOISE_ACTIVITY_THRESHOLD`

**API documentation:** `/docs`, `/redoc` and `/openapi.json` answer while `EXPOSE_DOCS` is true
(the default). The Dockerfile sets it to false, so the image does not serve them.

**Login throttling:** a client address that makes `LOGIN_MAX_ATTEMPTS` (default 5) login
attempts within `LOGIN_INTERVAL` seconds (default 60) gets 429 until the oldest attempt is that
old; a successful login clears its count. Behind a reverse proxy, set the environment variable
`FORWARDED_ALLOW_IPS` to the proxy's address, so uvicorn takes the client address from
`X-Forwarded-For`. Without it every client has the proxy's address and shares one count.

### Run Development Server

```bash
poetry run kishin run            # or: poetry run python -m kishin_trails.main
poetry run kishin run --reload   # restart when a source file changes
```

The API will be available at `http://localhost:8000/api`. Both commands refuse to start while a
required setting is missing, and name the missing ones. To serve a frontend build from the same
process, set `FRONTEND_DIR` to kishin-frontend's `dist/` (built with `VITE_API_BASE=/api`).

### API Documentation

Interactive API docs are available at (while `EXPOSE_DOCS` is true; off in the Docker image):
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

These provide comprehensive, always-up-to-date documentation of all available endpoints, request/response schemas, and authentication requirements.

## `kishin` CLI

Installed as a console script by `poetry install`; run `poetry run kishin --help` for
the full command tree, or `poetry run kishin <group> --help` for one group.

### `kishin password` - The Account's Password

Prompts for a password twice and writes its Argon2 hash to the file, readable by its owner
only. The server reads it at startup. Each token holds the start of the SHA-256 of the hash it
was issued for, so once the server restarts with a new hash it refuses every earlier token.

```bash
mkdir -p dev-secrets
poetry run kishin password dev-secrets/KISHIN_PASSWORD_HASH
```

### `kishin db` - Database Maintenance

```bash
poetry run kishin db init         # create any missing tables
poetry run kishin db stats        # row counts per table
poetry run kishin db copy-from-sqlite cache/kishin.db   # copy a SQLite game database, once
```

`copy-from-sqlite` reads the SQLite file the earlier versions used, read-only, and copies every
current table into empty PostgreSQL tables, in one transaction. Tables the file lacks are
reported and skipped; its old tables (`users`, `user_*`) are ignored.

### The database

The game data (tiles, POIs, noise cache, explored tiles, plans) is in a PostgreSQL database,
`kishin`, on the server that holds health-sync's `health` database. One user, `kishin-trails`,
owns `kishin` and reads `health`. health-sync's `db/setup.sh` creates the user; `db/setup.sh`
here creates the database. Locally, with health-sync's development database running
(`make dev-up dev-db` in health-sync):

```bash
DB_EXEC='docker compose -f ../health-sync/compose.dev.yaml exec -T db psql -U postgres -X -q -v ON_ERROR_STOP=1' db/setup.sh
```

The server creates its tables at startup.

### `kishin plan` - Training Plans

```bash
poetry run kishin plan import plan.json --start 2026-11-16   # becomes the active plan
poetry run kishin plan list                                  # * marks the active plan
poetry run kishin plan show
poetry run kishin plan delete <plan_id>
```

The plan file holds personal goals; keep it out of the repository.

### `kishin health` - Read the health-sync Database

Read-only queries on the database named by `HEALTH_DATABASE_URL`:

```bash
poetry run kishin health activities --days 30
poetry run kishin health cells <activity_id>     # S2 cells crossed by its GPS track
poetry run kishin health measures                # fat ratio and muscle mass per day
poetry run kishin health multiplier --start 2026-11-16          # Willpower cap multiplier per day
poetry run kishin health willpower <activity_id> --type long --target-km 12
```

### `kishin gpx import` - Import GPX Tracks

Import a GPX file and mark its S2 cells as explored.

```bash
poetry run kishin gpx import <gpx_file> [--resolution 16] [--dry-run]
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

The tests run against PostgreSQL. `tests/conftest.py` starts a throwaway `postgres:17-alpine`
container with testcontainers for the run, creates the databases `kishin_test` and
`health_test` in it, empties the tables after each test, and removes the container at the end;
Docker must be running. To use an existing server instead, set `TEST_DATABASE_URL` to a
superuser URL on it: `kishin_test` and `health_test` are then dropped and created there.

**Release** (`.github/workflows/release.yaml`), only for a tag `vX.Y.Z` that matches the version
in `pyproject.toml` and in kishin-frontend's `package.json` at the same tag. Tag the frontend
first: the workflow checks it out at the tag.
- Run the tests, pylint and ty; the frontend's lint, unit tests and build
- Build the image without a layer cache and scan it with Trivy; a fixable critical or high
  vulnerability, or a secret found in the image, stops the release
- Push `ghcr.io/kishintrails/kishin-trails` as `X.Y.Z`, `X.Y` and `latest`, with a build provenance
  attestation and a CycloneDX SBOM attestation. Check one before deploying it:
  `gh attestation verify oci://ghcr.io/kishintrails/kishin-trails@sha256:<digest> --owner KishinTrails`

**Pull request image build** (`.github/workflows/pr_image_build.yaml`): builds the image, with
kishin-frontend's `main`, without pushing it, when a pull request changes the Dockerfile or the
dependencies.

## Deployment

One image, `ghcr.io/kishintrails/kishin-trails`, holds the API and the built web app. One
process answers both on port 8000: the API under `/api`, the Withings page under `/withings`,
the web app on every other path. The web app calls `/api` on the address it was loaded from.
The Android app calls the same server at `https://<host>/api`.

**What is in the image**
- `/app/kishin_trails` and `/app/.venv`: the API. `/app/frontend`: kishin-frontend's build,
  made with `VITE_API_BASE=/api` and without `VITE_DEFAULT_CENTER_*`, so its own map centre is
  central Paris; the app reads the server's centre from `/api/config` after login. These belong
  to root and the process cannot write to them.
- `/app/cache`, empty, for the Overpass responses: mount a volume there, writable by uid 1001.
- No database, no `.env`, no secret. `.dockerignore` is an allowlist, so a file added to either
  repository later is left out until it is named there.
- The process runs as uid/gid 1001, `appuser`.

**Environment the image sets**

| Variable | Value | Why |
|---|---|---|
| `FRONTEND_DIR` | `/app/frontend` | serve the web app |
| `EXPOSE_DOCS` | `false` | `/docs`, `/redoc` and `/openapi.json` need no login and list every route; they answer 404 |

**What to provide**: the secrets as files in `/run/secrets` (`SECRET_KEY`, `KISHIN_PASSWORD_HASH`,
`DATABASE_URL`, and `HEALTH_DATABASE_URL` for `/api/athlete`), `KISHIN_USERNAME`,
`DEFAULT_CENTER_LAT` / `DEFAULT_CENTER_LON`, and behind a reverse proxy `FORWARDED_ALLOW_IPS`
set to the proxy's address (see Login throttling).

**Headers.** Each page answers `Cache-Control: no-cache`, except the files under `/assets/`,
whose names change with their content (`immutable`), and `Content-Security-Policy:
frame-ancestors 'none'`. The rest of the page's policy is the `<meta>` tag of the build
(kishin-frontend's `vite.config.ts`). The reverse proxy adds HSTS and the other headers. A
`Permissions-Policy` from the proxy must allow `geolocation=(self)`, or the browser refuses the
map's position marker.

**ghcr settings, once, after the first publish**: make the package public, and check in its
settings that it is linked to `kishin-api` and that this repository's Actions have write access.
Then check from a machine without a registry login: `docker logout ghcr.io` and
`docker pull ghcr.io/kishintrails/kishin-trails:X.Y.Z`.

## 🔗 Useful Links

- [S2 Viewer](https://igorgatis.github.io/ws2/) - Visualize S2 cells
- [Overpass Turbo](https://overpass-turbo.eu) - Query and explore OSM data

## 📂 Related Projects

- [kishin-frontend](https://github.com/KishinTrails/kishin-frontend) - Vue 3/Ionic mobile frontend

## 📜 License

This project is released under the [PolyForm Noncommercial License 1.0.0](LICENSE). Any
noncommercial purpose is permitted, which the licence spells out as including personal
study, hobby projects and use by charities, schools, public research organisations and
government bodies. It grants no licence for commercial use. The `LICENSE` file is the
terms; this paragraph is not.

---

*© 2026 Kishin Trails. Built with care, code, and a spirit to explore.*
