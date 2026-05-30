FROM python:3.14-slim

# Run as non-root for security best practices.
# Traefik routes to the container via its published port regardless of user.
RUN useradd --create-home appuser
WORKDIR /app

# Install Poetry and dependencies in a layer that is only invalidated when
# pyproject.toml or poetry.lock change — not when application code changes.
COPY pyproject.toml poetry.lock ./
RUN pip install --no-cache-dir poetry \
    && poetry config virtualenvs.in-project true \
    && poetry install --only main --no-interaction --no-ansi --no-root

# Copy application code separately so the dependency layer above is cached.
COPY kishin_trails/ ./kishin_trails/

# Install the kishin_trails package itself (omitted by --no-root above).
RUN poetry install --only main --no-interaction --no-ansi

# Hand off ownership to the non-root user.
RUN chown -R appuser:appuser /app
USER appuser

# Traefik will forward traffic to this port.
# The app must bind to 0.0.0.0 (not 127.0.0.1) to be reachable from outside
# the container. Ensure uvicorn is started with --host 0.0.0.0 in main.py.
EXPOSE 8000

CMD [".venv/bin/python", "-m", "kishin_trails.main"]
