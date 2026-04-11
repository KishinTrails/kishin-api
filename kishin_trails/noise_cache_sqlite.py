"""
SQLite-based cache for Perlin noise values.

Provides persistent, multiprocessing-safe storage for computed Perlin noise values.
Uses SQLite with proper locking to allow concurrent access from multiple processes.
"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager

_CACHE_DB = Path(__file__).parent.parent / "cache" / "noise_cache.db"


def _get_connection() -> sqlite3.Connection:
    """
    Create a database connection with appropriate settings for concurrent access.
    
    Returns:
        SQLite connection object with timeout and WAL mode configured.
    """
    conn = sqlite3.connect(str(_CACHE_DB), timeout=30.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@contextmanager
def _get_cursor():
    """
    Context manager for database cursors with proper cleanup.
    
    Yields:
        SQLite cursor object.
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        yield cursor
    finally:
        conn.close()


def initCache() -> None:
    """
    Initialize the SQLite cache database and create tables if they don't exist.
    
    Creates the cache directory and the noise_cache table with appropriate indexes.
    Safe to call multiple times (idempotent).
    """
    _CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    
    with _get_cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS noise_cache (
                cell TEXT NOT NULL,
                scale INTEGER NOT NULL,
                octaves INTEGER NOT NULL,
                amplitude_decay REAL NOT NULL,
                noise_value REAL NOT NULL,
                PRIMARY KEY (cell, scale, octaves, amplitude_decay)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_cell ON noise_cache(cell)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_scale ON noise_cache(scale)
        """)


def loadCache() -> None:
    """
    Load noise cache from pickle file and migrate to SQLite if needed.
    
    This provides backward compatibility with the old pickle-based cache.
    If the pickle cache exists, it will be loaded and migrated to SQLite.
    """
    from kishin_trails.noise_cache import _CACHE_FILE as PICKLE_CACHE_FILE
    
    initCache()
    
    if PICKLE_CACHE_FILE.exists():
        import pickle
        try:
            with open(PICKLE_CACHE_FILE, "rb") as handle:
                old_cache = pickle.load(handle)
            
            migrated_count = 0
            with _get_cursor() as cursor:
                for (cell, scale, octaves, amplitudeDecay), value in old_cache.items():
                    cursor.execute("""
                        INSERT OR REPLACE INTO noise_cache 
                        (cell, scale, octaves, amplitude_decay, noise_value)
                        VALUES (?, ?, ?, ?, ?)
                    """, (cell, scale, octaves, amplitudeDecay, value))
                    migrated_count += 1
            
            if migrated_count > 0:
                print(f"Migrated {migrated_count} entries from pickle cache to SQLite")
                PICKLE_CACHE_FILE.unlink()
                print(f"Removed old pickle cache: {PICKLE_CACHE_FILE}")
        except (pickle.UnpicklingError, EOFError):
            pass


def saveCache() -> None:
    """
    No-op for SQLite cache.
    
    SQLite writes are immediate and persistent, no separate save step needed.
    """
    pass


def clearCache() -> None:
    """
    Clear all cached noise values from the SQLite database.
    
    Deletes all rows from the noise_cache table.
    """
    initCache()
    with _get_cursor() as cursor:
        cursor.execute("DELETE FROM noise_cache")


def getCachedNoise(cell: str, scale: int, octaves: int, amplitudeDecay: float) -> float | None:
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
    with _get_cursor() as cursor:
        cursor.execute("""
            SELECT noise_value FROM noise_cache
            WHERE cell = ? AND scale = ? AND octaves = ? AND amplitude_decay = ?
        """, (cell, scale, octaves, amplitudeDecay))
        
        row = cursor.fetchone()
        return row[0] if row else None


def setCachedNoise(cell: str, scale: int, octaves: int, amplitudeDecay: float, value: float) -> None:
    """
    Store a Perlin noise value in the SQLite cache.
    
    Uses INSERT OR REPLACE to handle concurrent writes safely.
    The write is immediately persistent and visible to other processes.
    
    Args:
        cell: H3 cell identifier.
        scale: Noise scale parameter.
        octaves: Number of noise octaves.
        amplitudeDecay: Amplitude decay factor per octave.
        value: Computed noise value to cache (range [0, 1]).
    """
    with _get_cursor() as cursor:
        cursor.execute("""
            INSERT OR REPLACE INTO noise_cache
            (cell, scale, octaves, amplitude_decay, noise_value)
            VALUES (?, ?, ?, ?, ?)
        """, (cell, scale, octaves, amplitudeDecay, value))
