"""
Configuration management for the Kishin API using Pydantic Settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings, loaded from environment variables or a .env file.
    """

    # Database
    DATABASE_URL: str = "sqlite:///./kishin.db"

    # Security
    # In production, this MUST be a secure 32-byte secret.
    SECRET_KEY: str = "CHANGE_ME"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Overpass API
    OVERPASS_URL: str = "https://overpass-api.de/api/interpreter"

    # Load from .env file if it exists
    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
