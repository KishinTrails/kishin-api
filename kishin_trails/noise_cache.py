"""
SQLAlchemy-based persistent cache for Perlin noise values keyed by S2 cell.

Avoids redundant Perlin computation by storing results in a SQLite table.
Designed for concurrent use across ``multiprocessing.Pool`` workers.

Design rationale
----------------
Each forked worker process must own its own SQLAlchemy engine and connection
pool.  Sharing the parent's engine across ``fork()`` corrupts SQLite's
internal state and causes the writer lock to never be released.

``_get_session`` uses a ``threading.local`` to create one engine per process
(or per thread, if the caller later switches to a thread-pool executor).
This is intentionally separate from the ``engine`` / ``SESSION_LOCAL`` objects
in ``database.py``, which are designed for FastAPI's single-process request
lifecycle and must not be reused across forked processes.

SQLite concurrency settings applied per connection
--------------------------------------------------
* ``journal_mode=WAL``  — Write-Ahead Logging; allows concurrent readers and
  one writer instead of an exclusive file lock on every operation.
* ``synchronous=NORMAL`` — Safe under WAL; significantly faster than FULL.
* ``busy_timeout=10000`` — Retry for up to 10 s before raising
  ``OperationalError: database is locked``, giving concurrent writers time
  to serialise without failing.

Write strategy
--------------
``setCachedNoise`` uses a raw ``INSERT OR IGNORE`` rather than
``session.merge()``.  ``merge()`` does a SELECT then INSERT, which is not
atomic and loses the race between those two steps under multiprocessing.
Because Perlin noise is fully deterministic, silently discarding a duplicate
write is always correct — whoever wins the race wrote the right value.
"""

import logging
import threading
from typing import Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from kishin_trails.database import Base, SQLALCHEMY_DATABASE_URL
from kishin_trails.models import NoiseCache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-process SQLite pragmas
# ---------------------------------------------------------------------------


def _set_sqlite_pragmas(dbapi_conn, _connection_record) -> None:
    """
    Apply SQLite connection-level PRAGMAs required for concurrent cache access.

    Registered as a SQLAlchemy ``"connect"`` event listener on each
    per-process engine created by ``_get_session``.  Unlike the listener in
    ``database.py`` (which guards against non-SQLite backends), this module
    always targets SQLite, so the ``isinstance`` check is omitted.

    Args:
        dbapi_conn: Raw DBAPI connection object provided by SQLAlchemy.
        _connection_record: Internal SQLAlchemy connection record (unused).
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.close()


# ---------------------------------------------------------------------------
# Per-process session factory
# ---------------------------------------------------------------------------

_LOCAL = threading.local()


def _get_session():
    """
    Return a session bound to this process's private engine.

    The engine is created lazily on the first call within each process (or
    thread).  Subsequent calls within the same process return a new session
    from the cached session factory, avoiding the overhead of engine
    construction.

    A pool size of 1 with no overflow is appropriate here: each forked worker
    is single-threaded, so a larger pool would only waste file descriptors.

    Returns:
        sqlalchemy.orm.Session: A new session from the per-process factory.
    """
    if not getattr(_LOCAL, "session_factory", None):
        _engine = create_engine(
            SQLALCHEMY_DATABASE_URL,
            connect_args={
                "check_same_thread": False
            },
            # One connection per worker process is sufficient.
            pool_size=1,
            max_overflow=0,
        )

        # Register the pragma listener on this engine instance.
        event.listen(_engine, "connect", _set_sqlite_pragmas)

        # Ensure the cache table exists in this process before any reads/writes.
        Base.metadata.create_all(bind=_engine)

        _LOCAL.session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=_engine,
        )

    return _LOCAL.session_factory()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def initCache() -> None:
    """
    Initialise the noise cache schema for the current process.

    Triggers lazy engine and table creation via ``_get_session``.  Safe to
    call multiple times; ``create_all`` is idempotent.
    """
    session = _get_session()
    session.close()
    logger.info("Noise cache initialised")


def getCachedNoise(
    s2Cell: str,
    scale: int,
    octaves: int,
    amplitudeDecay: float,
) -> Optional[float]:
    """
    Retrieve a cached Perlin noise value for an S2 cell and parameter set.

    Args:
        s2Cell: S2 cell hex token.
        scale: Noise scale parameter.
        octaves: Number of noise octaves.
        amplitudeDecay: Per-octave amplitude multiplier.

    Returns:
        The cached noise value as a ``float`` if a matching record exists,
        or ``None`` if the combination has not yet been computed.
    """
    session = _get_session()
    try:
        result = session.query(NoiseCache).filter(
            NoiseCache.s2_cell_id == s2Cell,
            NoiseCache.scale == scale,
            NoiseCache.octaves == octaves,
            NoiseCache.amplitude_decay == amplitudeDecay,
        ).first()
        return float(result.noise_value) if result is not None else None
    finally:
        session.close()


def setCachedNoise(
    s2Cell: str,
    scale: int,
    octaves: int,
    amplitudeDecay: float,
    value: float,
) -> None:
    """
    Persist a computed Perlin noise value in the cache.

    Uses ``INSERT OR IGNORE`` so that concurrent workers racing to cache the
    same key do not raise a ``UNIQUE`` constraint error.  Because noise values
    are fully deterministic, silently discarding a duplicate write is always
    correct — whoever wins the race wrote the right value.

    Args:
        s2Cell: S2 cell hex token.
        scale: Noise scale parameter.
        octaves: Number of noise octaves.
        amplitudeDecay: Per-octave amplitude multiplier.
        value: Computed noise value in [0, 1].
    """
    session = _get_session()
    try:
        session.execute(
            text(
                "INSERT OR IGNORE INTO noise_cache "
                "(s2_cell_id, scale, octaves, amplitude_decay, noise_value) "
                "VALUES (:s2_cell_id, :scale, :octaves, :amplitude_decay, :noise_value)"
            ),
            {
                "s2_cell_id": s2Cell,
                "scale": scale,
                "octaves": octaves,
                "amplitude_decay": amplitudeDecay,
                "noise_value": value,
            },
        )
        session.commit()
    finally:
        session.close()


def clearCache() -> None:
    """
    Delete all entries from the noise cache.

    Intended for use in tests and development workflows where a clean cache
    state is required.  Has no effect on the schema; the table is truncated,
    not dropped.
    """
    session = _get_session()
    try:
        session.query(NoiseCache).delete()
        session.commit()
        logger.info("Noise cache cleared")
    finally:
        session.close()
