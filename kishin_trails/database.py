"""
Database configuration and session management using SQLAlchemy.

Provides database engine setup, session factory, and base model class
for the application's ORM layer. Uses SQLite by default with support
for other databases via configuration.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from kishin_trails.config import settings

# DATABASE_URL is now loaded from settings (defaulting to local kishin.db)
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# connect_args={"check_same_thread": False} is required only for SQLite.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={
        "check_same_thread": False
    }
)
SESSION_LOCAL = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """
    Base declarative class for all SQLAlchemy ORM models.

    All database models should inherit from this class to enable
    SQLAlchemy's declarative mapping and metadata management.
    """


def getDb():
    """
    FastAPI dependency that provides a database session for request handlers.

    Creates a new database session from the session factory, yields it for
    use in endpoint handlers, and ensures proper cleanup after the request
    completes.

    Yields:
        SQLAlchemy Session object for database operations.

    Note:
        This is used as a dependency injection in FastAPI route handlers
        via Depends(getDb).
    """
    dbSession = SESSION_LOCAL()
    try:
        yield dbSession
    finally:
        dbSession.close()
