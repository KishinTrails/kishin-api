"""
Database configuration using SQLAlchemy with SQLite.
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
    Base class for SQLAlchemy models.
    """


def getDb():
    """
    Dependency to get a database session.
    Yields a session and ensures it's closed after the request.
    """
    dbSession = SESSION_LOCAL()
    try:
        yield dbSession
    finally:
        dbSession.close()
