"""Cache for Perlin noise values."""

import pickle
from pathlib import Path
from typing import Dict, Tuple

_CACHE_FILE = Path(__file__).parent.parent / "cache" / "noise_cache.pkl"
_cache: Dict[Tuple[str, int], float] = {}


def loadCache() -> None:
    """Load cache from pickle file if it exists."""
    global _cache
    if _CACHE_FILE.exists():
        try:
            with open(_CACHE_FILE, "rb") as f:
                _cache = pickle.load(f)
        except (pickle.UnpicklingError, EOFError):
            _cache = {}


def saveCache() -> None:
    """Save cache to pickle file."""
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_CACHE_FILE, "wb") as f:
        pickle.dump(_cache, f)


def clearCache() -> None:
    """Clear cache and remove cache file."""
    global _cache
    _cache = {}
    if _CACHE_FILE.exists():
        _CACHE_FILE.unlink()


def getCachedNoise(cell: str, scale: int) -> float | None:
    """Get cached noise value if available."""
    return _cache.get((cell, scale))


def setCachedNoise(cell: str, scale: int, value: float) -> None:
    """Set and persist a noise value in cache."""
    _cache[(cell, scale)] = value
    saveCache()
