"""
SQLAlchemy-based cache for Perlin noise values.

Provides persistent storage for computed Perlin noise values to avoid
redundant calculations. Uses WAL journal mode and per-process sessions
to avoid SQLite locking issues under multiprocessing.
"""

import logging
import threading
from typing import Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from kishin_trails.database import Base, SQLALCHEMY_DATABASE_URL
from kishin_trails.models import NoiseCache

logger = logging.getLogger("noise_cache")

# ---------------------------------------------------------------------------
# Per-process engine + session factory
#
# When ProcessPoolExecutor forks the parent process, each child inherits the
# parent's file descriptors and SQLAlchemy connection pool. Sharing those
# connections across OS processes corrupts SQLite's internal state and causes
# the writer lock to never be released, which is the primary source of hangs.
#
# The fix: each process creates its OWN engine lazily the first time it needs
# the cache. _LOCAL is a threading.local so the same pattern also works safely
# if you later switch to ThreadPoolExecutor.
#
# Note: we deliberately do NOT import SESSION_LOCAL or engine from database.py
# here. Those shared objects are designed for FastAPI's single-process request
# lifecycle (see cache.py / getDb()). Reusing them across forked processes
# would corrupt the connection pool. We re-create an engine from the same URL
# but with WAL pragmas and a pool sized for single-threaded worker processes.
# ---------------------------------------------------------------------------

_LOCAL = threading.local()


def _get_session():
    """
	Return a Session bound to this process's private engine.

    Creates the engine (and enables WAL mode) on first call per process.
    Mirrors the connect_args pattern from database.py for consistency.
    """
    if not getattr(_LOCAL, "session_factory", None):
        # Same URL as the rest of the app (loaded from settings), same
        # check_same_thread=False flag as database.py — different pool instance.
        _engine = create_engine(
            SQLALCHEMY_DATABASE_URL,
            connect_args={
                "check_same_thread": False
            },
            # A pool size of 1 is fine: each forked worker is single-threaded.
            pool_size=1,
            max_overflow=0,
        )

        # Enable WAL journal mode immediately after every new connection.
        # WAL allows concurrent readers + one writer instead of exclusive locks,
        # which is the second major source of hangs.
        @event.listens_for(_engine, "connect")
        def _set_wal(dbapi_conn, _connection_record):
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
            # NORMAL sync is safe under WAL and much faster than FULL.
            dbapi_conn.execute("PRAGMA synchronous=NORMAL")
            # Give the writer up to 10 s to release its lock before raising.
            # Without this, concurrent writers raise "database is locked" immediately.
            dbapi_conn.execute("PRAGMA busy_timeout=10000")

        Base.metadata.create_all(bind=_engine)
        # Match database.py's sessionmaker flags (autocommit=False, autoflush=False).
        _LOCAL.session_factory = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

    return _LOCAL.session_factory()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def initCache() -> None:
    """
	Initialize the noise cache database tables."""
    session = _get_session()
    session.close()
    logger.info("Noise cache tables initialized")


def getCachedNoise(cell: str, scale: int, octaves: int, amplitudeDecay: float) -> Optional[float]:
    """
	Retrieve a cached Perlin noise value for a specific H3 cell and parameters.

    Args:
        cell: H3 cell identifier.
        scale: Noise scale parameter.
        octaves: Number of noise octaves.
        amplitudeDecay: Amplitude decay factor per octave.

    Returns:
        Cached noise value if available, None otherwise.
    """
    session = _get_session()
    try:
        result = session.query(NoiseCache).filter(
            NoiseCache.cell == cell,
            NoiseCache.scale == scale,
            NoiseCache.octaves == octaves,
            NoiseCache.amplitude_decay == amplitudeDecay,
        ).first()

        return float(result.noise_value) if result is not None else None
    finally:
        session.close()


def setCachedNoise(cell: str, scale: int, octaves: int, amplitudeDecay: float, value: float) -> None:
    """
	Store a Perlin noise value in the cache.

    Uses INSERT OR IGNORE so that concurrent workers racing to cache the same
    key don't raise a UNIQUE constraint error. Since noise values are fully
    deterministic, silently discarding a duplicate write is always correct —
    whoever wins the race wrote the right value.

    session.merge() is NOT used here: it does a SELECT then INSERT, which is
    not atomic and loses the race between those two steps under multiprocessing.

    Args:
        cell: H3 cell identifier.
        scale: Noise scale parameter.
        octaves: Number of noise octaves.
        amplitudeDecay: Amplitude decay factor per octave.
        value: Computed noise value to cache (range [0, 1]).
    """
    session = _get_session()
    try:
        session.execute(
            text(
                "INSERT OR IGNORE INTO noise_cache "
                "(cell, scale, octaves, amplitude_decay, noise_value) "
                "VALUES (:cell, :scale, :octaves, :amplitude_decay, :noise_value)"
            ),
            {
                "cell": cell,
                "scale": scale,
                "octaves": octaves,
                "amplitude_decay": amplitudeDecay,
                "noise_value": value
            },
        )
        session.commit()
    finally:
        session.close()


def clearCache() -> None:
    """
    Clear all entries from the noise cache.
    
    Useful for testing and resetting cache state.
    """
    session = _get_session()
    try:
        session.query(NoiseCache).delete()
        session.commit()
        logger.info("Noise cache cleared")
    finally:
        session.close()
