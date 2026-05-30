"""
Database configuration and session management using SQLAlchemy.

Provides database engine setup, session factory, and base model class
for the application's ORM layer. Uses SQLite by default with support
for other databases via configuration.

SQLite-specific behaviour
-------------------------
When the configured database is SQLite, two connection-level PRAGMAs are
applied automatically on every new connection (via a SQLAlchemy event hook):

* ``journal_mode=WAL`` — Write-Ahead Logging mode.  WAL writes changes to a
  separate ``-wal`` file instead of modifying the database file in-place.
  This allows concurrent readers without blocking the writer, and vice versa.
  It is strictly better than the default rollback-journal mode for any
  workload that mixes reads and writes across threads or processes.

* ``busy_timeout=5000`` — Instead of raising ``OperationalError: database is
  locked`` immediately when another connection holds the write lock, SQLite
  will retry for up to 5 000 ms before giving up.  This is essential for
  multi-process workloads (e.g. ``multiprocessing.Pool``) where many workers
  may attempt concurrent writes.

These PRAGMAs have no effect and are not applied when the backend is
PostgreSQL or any other non-SQLite engine.

Multi-process usage
-------------------
SQLAlchemy engine objects must **not** be shared across ``fork()``-created
child processes.  Call ``init_engine()`` inside each worker's initializer
(e.g. ``Pool(initializer=init_engine)``) so every process owns its own
connection pool.  See ``find_perlin_params.py`` for an example.
"""

import sqlite3

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from kishin_trails.config import settings

# Exposed as a module-level constant so other modules (e.g. noise_cache.py)
# can import the URL without depending on the settings object directly.
SQLALCHEMY_DATABASE_URL: str = settings.DATABASE_URL

# ---------------------------------------------------------------------------
# SQLite connection-level PRAGMAs
# ---------------------------------------------------------------------------


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _connection_record) -> None:
    """
    Apply SQLite-specific PRAGMAs on every new connection.

    This listener fires for *all* SQLAlchemy engines, but the ``isinstance``
    guard ensures the PRAGMAs are only sent to SQLite connections, leaving
    PostgreSQL and other backends untouched.

    PRAGMAs applied
    ~~~~~~~~~~~~~~~
    - ``journal_mode=WAL``: enables Write-Ahead Logging (see module docstring).
    - ``busy_timeout=5000``: retry for up to 5 s before raising a lock error.

    Args:
        dbapi_conn: Raw DBAPI connection object provided by SQLAlchemy.
        _connection_record: Internal SQLAlchemy connection record (unused).
    """
    if not isinstance(dbapi_conn, sqlite3.Connection):
        return

    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


# ---------------------------------------------------------------------------
# Engine and session factory
# ---------------------------------------------------------------------------


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

    # ``check_same_thread=False`` is required for SQLite when the same engine
    # is used from multiple threads inside a single process (e.g. FastAPI with
    # a thread-pool executor).  It is silently ignored by other backends.
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={
            "check_same_thread": False
        },
    )

    SESSION_LOCAL = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Initialise at import time for the main process.
engine = None
SESSION_LOCAL = None
init_engine()

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
