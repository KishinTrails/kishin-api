"""
Cache for Perlin noise values.

Provides persistent storage for computed Perlin noise values to avoid
redundant calculations. Uses a pickle-based file cache for persistence
across server restarts.
"""

import pickle
from pathlib import Path
from typing import Dict, Tuple

_CACHE_FILE = Path(__file__).parent.parent / "cache" / "noise_cache.pkl"
_cache: Dict[Tuple[str,
                   int],
             float] = {}


def loadCache() -> None:
    """
    Load noise cache from pickle file if it exists.

    Reads the cached noise values from disk and populates the in-memory cache.
    If the file is corrupted or unreadable, initializes an empty cache.
    """
    global _cache
    if _CACHE_FILE.exists():
        try:
            with open(_CACHE_FILE, "rb") as handle:
                _cache = pickle.load(handle)
        except (pickle.UnpicklingError, EOFError):
            _cache = {}


def saveCache() -> None:
    """
    Save in-memory cache to pickle file on disk.

    Creates the cache directory if it doesn't exist and writes the current
    cache state to a pickle file for persistence.
    """
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_CACHE_FILE, "wb") as handle:
        pickle.dump(_cache, handle)


def clearCache() -> None:
    """
    Clear all cached noise values and remove the cache file.

    Resets the in-memory cache to an empty dictionary and deletes the
    persistent cache file if it exists.
    """
    global _cache
    _cache = {}
    if _CACHE_FILE.exists():
        _CACHE_FILE.unlink()


def getCachedNoise(cell: str, scale: int) -> float | None:
    """
    Retrieve a cached Perlin noise value for a specific H3 cell and scale.

    Args:
        cell: H3 cell identifier.
        scale: Noise scale parameter.

    Returns:
        Cached noise value if available, None otherwise.
    """
    return _cache.get((cell, scale))


def setCachedNoise(cell: str, scale: int, value: float) -> None:
    """
    Store a Perlin noise value in the cache and persist to disk.

    Args:
        cell: H3 cell identifier.
        scale: Noise scale parameter.
        value: Computed noise value to cache (range [0, 1]).
    """
    _cache[(cell, scale)] = value
    saveCache()
