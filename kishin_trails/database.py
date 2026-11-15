"""
Database configuration and session management using SQLAlchemy.

The game database is PostgreSQL, reached through psycopg 3
(``postgresql+psycopg://`` URLs). ``DATABASE_URL`` holds its password, so on a
server it comes from ``/run/secrets/DATABASE_URL`` (see ``config.py``).

Importing this module never needs ``DATABASE_URL``: without it, ``engine`` points
at no server and fails on its first connection. The server refuses to start
without the setting (``config.servingProblems``), and the CLI says so before
opening a session (``cli/common.openSession``).

Multi-process usage
-------------------
SQLAlchemy engine objects must **not** be shared across ``fork()``-created
child processes.  Call ``init_engine()`` inside each worker's initializer
(e.g. ``Pool(initializer=init_engine)``) so every process owns its own
connection pool.  See ``perlin_search.py`` for an example.
"""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from kishin_trails.config import settings

#: The URL of an engine that points at no server, used while DATABASE_URL is unset.
UNCONFIGURED_URL = "postgresql+psycopg://"

# Exposed as a module-level constant so other modules (e.g. noise_cache.py)
# can import the URL without depending on the settings object directly.
SQLALCHEMY_DATABASE_URL: str = settings.DATABASE_URL or UNCONFIGURED_URL


def _newEngine() -> Engine:
    """An engine for SQLALCHEMY_DATABASE_URL. ``pool_pre_ping`` replaces connections
    the server closed, for example after a PostgreSQL restart."""
    return create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)


def init_engine() -> None:
    """
    (Re-)initialise the module-level ``engine`` and ``SESSION_LOCAL`` objects.

    This function **must** be called inside each child process when using
    ``multiprocessing.Pool`` or similar, because SQLAlchemy engine objects —
    and the underlying DBAPI connections they hold — are not safe to share
    across ``fork()``.

    Typical usage in a Pool initializer::

        from kishin_trails.database import init_engine
        with Pool(initializer=init_engine) as pool:
            ...

    Calling this function in the main process is also fine; ``engine`` and
    ``SESSION_LOCAL`` are simply replaced with fresh instances.
    """
    global engine, SESSION_LOCAL  # noqa: PLW0603
    engine = _newEngine()
    SESSION_LOCAL = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Initialise at import time for the main process.  engine and SESSION_LOCAL
# are assigned here with their real types so importers and the type checker
# always see Engine / sessionmaker, never None.
engine = _newEngine()
SESSION_LOCAL = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ---------------------------------------------------------------------------
# ORM base class
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """
    Base declarative class for all SQLAlchemy ORM models.

    Every model in the application should inherit from this class to
    participate in SQLAlchemy's declarative mapping and share the common
    ``metadata`` object (used, for example, by ``Base.metadata.create_all``).
    """


# ---------------------------------------------------------------------------
# FastAPI session dependency
# ---------------------------------------------------------------------------


def getDb():
    """
    FastAPI dependency that provides a database session per request.

    Opens a new session from ``SESSION_LOCAL``, yields it to the route
    handler, and guarantees ``close()`` is called — even if the handler
    raises an exception — via the ``finally`` block.

    Usage in a route::

        @app.get("/items")
        def list_items(db: Session = Depends(getDb)):
            return db.query(Item).all()

    Yields:
        sqlalchemy.orm.Session: A transactional database session.
    """
    db_session = SESSION_LOCAL()
    try:
        yield db_session
    finally:
        db_session.close()
