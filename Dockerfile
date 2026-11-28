# One image with the API and the built frontend. FastAPI serves both on port 8000: the API
# under /api, the Withings page under /withings, the frontend on every other path.
#
# The build context is this repository with the matching kishin-frontend checkout in
# `frontend-src/` (the release workflow puts it there; scripts/build_image.sh in the umbrella
# repository does the same locally). Every base image is pinned by digest; Dependabot moves
# the digests.

# --- the frontend ---------------------------------------------------------
FROM node:26-alpine@sha256:6bd9ab43c0ec0190ca7b2d193906cb8b7edf6e7f4afa43ddeccd6452710bffb5 AS frontend
WORKDIR /src
# --ignore-scripts: no install script of any dependency runs during the build.
COPY frontend-src/package.json frontend-src/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend-src/ ./
# The page and the API share an origin, so the API's address is a path. A variable in the
# environment wins over a `.env` file, and .dockerignore keeps `.env` out of the context.
# No VITE_DEFAULT_CENTER_*: the build's map centre is Paris, and the app asks the server's
# DEFAULT_CENTER_LAT/LON from /api/config after login.
ENV VITE_API_BASE=/api
RUN npm run build

# --- the API's dependencies ----------------------------------------------
FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928 AS build

WORKDIR /app

# Compiler and cmake are for h3, which has no wheel for Python 3.15 yet and is built from source.
# s2geometry comes as a wheel from PyPI. Remove both packages once h3 publishes a 3.15 wheel.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first, in a layer that is only invalidated when pyproject.toml or poetry.lock
# change. --no-root skips the kishin_trails package, whose source is not copied yet.
# no-pip: the virtual environment gets no pip; Poetry installs without it.
COPY pyproject.toml poetry.lock README.md LICENSE ./
RUN pip install --no-cache-dir poetry \
    && poetry config virtualenvs.in-project true \
    && poetry config virtualenvs.options.no-pip true \
    && poetry install --only main --no-interaction --no-ansi --no-root

COPY kishin_trails/ ./kishin_trails/

# Install the kishin_trails package itself (omitted by --no-root above).
RUN poetry install --only main --no-interaction --no-ansi

# --- what runs --------------------------------------------------------------
FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

LABEL org.opencontainers.image.title="Kishin Trails" \
      org.opencontainers.image.source="https://github.com/KishinTrails/kishin-api" \
      org.opencontainers.image.licenses="PolyForm-Noncommercial-1.0.0"

# Debian security fixes published after the base image was built. pip is removed: nothing
# runs it, and it carries its own copies of urllib3, msgpack and setuptools. The last step
# removes every setuid and setgid bit, which nothing here needs.
RUN apt-get update && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && pip uninstall -y pip \
    && groupadd -g 1001 appuser \
    && useradd --create-home appuser -u 1001 -g 1001 \
    && find / -xdev -type f \( -perm -4000 -o -perm -2000 \) -exec chmod a-s {} +

# Owned by root and read-only to the process: it cannot rewrite its own code or the pages.
# The virtual environment's interpreter links to /usr/local/bin/python3.15, which both
# stages have, and its scripts name /app/.venv/bin/python, so it works from the same path.
WORKDIR /app
COPY --from=build /app/.venv ./.venv
COPY --from=build /app/kishin_trails ./kishin_trails
COPY --from=frontend /src/dist ./frontend

# /app/cache holds the Overpass responses. On a server it is a mounted volume owned by
# uid 1001; the empty directory here belongs to that user so a run without the volume works.
RUN mkdir /app/cache && chown appuser:appuser /app/cache

# /docs, /redoc and /openapi.json need no login and list every route: off in
# the image, on for a local run (see config.py).
ENV EXPOSE_DOCS=false \
    FRONTEND_DIR=/app/frontend \
    PYTHONDONTWRITEBYTECODE=1

USER appuser

# Traefik will forward traffic to this port.
# The app must bind to 0.0.0.0 (not 127.0.0.1) to be reachable from outside
# the container. Ensure uvicorn is started with --host 0.0.0.0 in main.py.
EXPOSE 8000

CMD [".venv/bin/python", "-m", "kishin_trails.main"]
