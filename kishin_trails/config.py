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
        OVERPASS_URL: Base URL for the Overpass API endpoint.
        DEFAULT_CENTER_LAT: Default latitude for Overpass queries.
        DEFAULT_CENTER_LON: Default longitude for Overpass queries.
        DEBUG_LOCATIONS: Dictionary of debug locations (loaded from .env, not committed).
    """

    DATABASE_URL: str = "sqlite:///./kishin.db"

    # Security
    # In production, this MUST be a secure 32-byte secret.
    SECRET_KEY: str = "CHANGE_ME"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Overpass API
    OVERPASS_URL: str = "https://overpass-api.de/api/interpreter"
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

    # Load from .env file if it exists
    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
