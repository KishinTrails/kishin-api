"""
Configuration management for the Kishin API using Pydantic Settings.
"""

from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

#: Shortest accepted SECRET_KEY. `python -c 'import secrets; print(secrets.token_hex(32))'`
#: prints a 64-character one.
MIN_SECRET_KEY_LENGTH = 32

#: Directories whose files override settings: one file per setting, named after it.
SECRETS_DIRS = ("/run/secrets", "dev-secrets")


class Settings(BaseSettings):
    """
    Application settings, loaded from environment variables or a .env file.

    Attributes:
        DATABASE_URL: SQLAlchemy URL of the PostgreSQL game database (postgresql+psycopg://…). No default.
        SECRET_KEY: Secret key for JWT token signing, at least MIN_SECRET_KEY_LENGTH characters. No default.
        ACCESS_TOKEN_EXPIRE_MINUTES: Token expiration time in minutes.
        KISHIN_USERNAME: Username of the application's only account.
        KISHIN_PASSWORD_HASH: Argon2 hash of that account's password, written by ``kishin password``.
        LOGIN_MAX_ATTEMPTS: Login attempts per client address within LOGIN_INTERVAL; 0 disables the limit.
        LOGIN_INTERVAL: Seconds over which login attempts are counted.
        EXPOSE_DOCS: Whether /docs, /redoc and /openapi.json answer; read when the app is created.
        CORS_ORIGINS: Comma-separated list of allowed origins.
        OVERPASS_URL: Base URL for the Overpass API endpoint.
        DEFAULT_CENTER_LAT: Default latitude for Overpass queries.
        DEFAULT_CENTER_LON: Default longitude for Overpass queries.
        DEBUG_LOCATIONS: Dictionary of debug locations (loaded from .env, not committed).
        HEALTH_DATABASE_URL: SQLAlchemy URL of the health-sync measurement database (read-only account).
        HEALTH_DB_PREFIX: Prefix of the health-sync schema names (health-sync's HEALTH_DB_PREFIX).
        TIMEZONE: IANA time zone that decides the calendar day of a Withings reading.
    """

    # The PostgreSQL game database. The URL holds the password, so on a server
    # it comes from /run/secrets/DATABASE_URL, and locally from
    # dev-secrets/DATABASE_URL (see secrets_dir below). No default: the server
    # refuses to start while it is empty (see servingProblems).
    DATABASE_URL: str = ""

    # Security
    # No default: a committed default would sign real tokens on any server
    # started without the secret. The server refuses to start while it is empty
    # or shorter than MIN_SECRET_KEY_LENGTH (see servingProblems).
    SECRET_KEY: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # The only account. The username is an environment variable; the password
    # hash comes from /run/secrets/KISHIN_PASSWORD_HASH on a server, or from
    # dev-secrets/KISHIN_PASSWORD_HASH locally (see secrets_dir below). Login is
    # refused while either is empty.
    KISHIN_USERNAME: str = ""
    KISHIN_PASSWORD_HASH: str = ""

    # Login throttling per client address (see throttle.py). Behind a reverse
    # proxy, uvicorn takes the client address from X-Forwarded-For only when the
    # proxy's address is in the environment variable FORWARDED_ALLOW_IPS;
    # otherwise every client has the proxy's address and shares one count.
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_INTERVAL: int = 60

    # /docs, /redoc and /openapi.json need no login and list every route. On for
    # a local run; the Dockerfile sets EXPOSE_DOCS=false for the image.
    EXPOSE_DOCS: bool = True

    CORS_ORIGINS: list[str] = ["http://localhost", "http://localhost:5173"]

    # Overpass API
    OVERPASS_URL: str = "https://overpass-api.de/api/interpreter"
    OVERPASS_CONTACT: str = "kishin-trails"
    DEFAULT_CENTER_LAT: float = 48.85454010062465
    DEFAULT_CENTER_LON: float = 2.3476249395829583

    # Debug locations (loaded from .env, not committed)
    DEBUG_LOCATIONS: dict[str,
                          Any] = {}

    # Perlin noise parameters
    NOISE_SCALE: int = 50
    NOISE_OCTAVES: int = 3
    NOISE_AMPLITUDE_DECAY: float = 0.5
    NOISE_ACTIVITY_THRESHOLD: float = 0.5

    # Measurement database written by health-sync, read with a SELECT-only
    # account. The URL holds the password, so on a server it comes from
    # /run/secrets/HEALTH_DATABASE_URL (see secrets_dir below). The scheme
    # postgresql+psycopg:// selects the psycopg 3 driver.
    HEALTH_DATABASE_URL: str = ""
    HEALTH_DB_PREFIX: str = ""

    # IANA time zone, such as Europe/Paris, that decides the calendar day of a
    # Withings reading.
    TIMEZONE: str = "UTC"

    # Load from .env file if it exists. secrets_dir lets SECRET_KEY (or any
    # field) come from a mounted file instead — e.g. a Docker secret at
    # /run/secrets/SECRET_KEY — without it ever passing through `docker
    # inspect`'s Env list the way a plain environment variable does. A
    # missing directory produces a warning, so only the directories that exist
    # are listed. dev-secrets/ (git-ignored) holds the same files for a local
    # run.
    model_config = SettingsConfigDict(
        env_file=".env",
        secrets_dir=tuple(path for path in SECRETS_DIRS if Path(path).is_dir()) or None,
    )


settings = Settings()


def servingProblems(config: Settings) -> list[str]:
    """The settings the server cannot serve without, one sentence each; empty when all are set."""
    problems = []
    if not config.DATABASE_URL:
        problems.append("DATABASE_URL is not set (postgresql+psycopg://user:password@host/kishin).")
    if not config.SECRET_KEY:
        problems.append(
            "SECRET_KEY is not set. Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
        )
    elif len(config.SECRET_KEY) < MIN_SECRET_KEY_LENGTH:
        problems.append(f"SECRET_KEY is shorter than {MIN_SECRET_KEY_LENGTH} characters.")
    if not config.KISHIN_USERNAME:
        problems.append("KISHIN_USERNAME is not set.")
    if not config.KISHIN_PASSWORD_HASH:
        problems.append("KISHIN_PASSWORD_HASH is not set (see `kishin password`).")
    return problems
