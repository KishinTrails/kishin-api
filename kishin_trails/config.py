"""
Configuration management for the Kishin API using Pydantic Settings.
"""

from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings, loaded from environment variables or a .env file.

    Attributes:
        DATABASE_URL: SQLAlchemy database connection string.
        SECRET_KEY: Secret key for JWT token signing. In production, this MUST be a secure 32-byte secret.
        ALGORITHM: Algorithm used for JWT token encoding (default: HS256).
        ACCESS_TOKEN_EXPIRE_MINUTES: Token expiration time in minutes.
        CORS_ORIGINS: Comma-separated list of allowed origins.
        OVERPASS_URL: Base URL for the Overpass API endpoint.
        DEFAULT_CENTER_LAT: Default latitude for Overpass queries.
        DEFAULT_CENTER_LON: Default longitude for Overpass queries.
        DEBUG_LOCATIONS: Dictionary of debug locations (loaded from .env, not committed).
        HEALTH_DATABASE_URL: SQLAlchemy URL of the health-sync measurement database (read-only account).
        HEALTH_DB_PREFIX: Prefix of the health-sync schema names (health-sync's HEALTH_DB_PREFIX).
        TIMEZONE: IANA time zone that decides the calendar day of a Withings reading.
    """

    DATABASE_URL: str = "sqlite:///./kishin.db"

    # Security
    # In production, this MUST be a secure 32-byte secret.
    SECRET_KEY: str = "CHANGE_ME"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
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
    # missing secrets_dir (the normal case outside a container) only
    # produces a warning, so this is a no-op for local/.env development.
    model_config = SettingsConfigDict(env_file=".env", secrets_dir="/run/secrets")


settings = Settings()
