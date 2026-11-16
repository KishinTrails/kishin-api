# Two stages. The build stage holds the compiler, cmake and Poetry; the runtime stage gets
# only the virtual environment and the application, so none of them is in the published image.

FROM python:3.15-slim AS build

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


FROM python:3.15-slim

# Debian security fixes published after the base image was built. pip is removed: nothing
# runs it, and it carries its own copies of urllib3, msgpack and setuptools.
RUN apt-get update && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && pip uninstall -y pip

# Run as non-root for security best practices.
# Traefik routes to the container via its published port regardless of user.
RUN groupadd -g 1001 appuser \
    && useradd --create-home appuser -u 1001 -g 1001
WORKDIR /app

# The virtual environment's interpreter links to /usr/local/bin/python3.15, which both
# stages have, and its scripts name /app/.venv/bin/python, so it works from the same path.
COPY --from=build --chown=appuser:appuser /app/.venv ./.venv
COPY --from=build --chown=appuser:appuser /app/kishin_trails ./kishin_trails
RUN chown appuser:appuser /app

# /docs, /redoc and /openapi.json need no login and list every route: off in
# the image, on for a local run (see config.py).
ENV EXPOSE_DOCS=false

USER appuser

# Traefik will forward traffic to this port.
# The app must bind to 0.0.0.0 (not 127.0.0.1) to be reachable from outside
# the container. Ensure uvicorn is started with --host 0.0.0.0 in main.py.
EXPOSE 8000

CMD [".venv/bin/python", "-m", "kishin_trails.main"]
