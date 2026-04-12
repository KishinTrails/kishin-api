"""
Tests for SQLite-based noise cache with multiprocessing support.
"""

import pytest
from concurrent.futures import ProcessPoolExecutor

from kishin_trails.noise_cache import initCache, clearCache, setCachedNoise, getCachedNoise


class TestSQLiteCache:
    """Test SQLite cache functionality."""
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """Initialize and clear cache before each test."""
        initCache()
        clearCache()
        yield

    def test_basic_set_get(self):
        """Test basic cache set and get operations."""
        setCachedNoise("test_cell", 50, 3, 0.5, 0.75)
        result = getCachedNoise("test_cell", 50, 3, 0.5)
        assert result == 0.75

    def test_cache_miss(self):
        """Test cache returns None for missing values."""
        result = getCachedNoise("nonexistent", 50, 3, 0.5)
        assert result is None

    def test_different_parameters(self):
        """Test cache distinguishes different parameter combinations."""
        setCachedNoise("cell1", 50, 3, 0.5, 0.1)
        setCachedNoise("cell1", 100, 3, 0.5, 0.2)
        setCachedNoise("cell1", 50, 5, 0.5, 0.3)
        setCachedNoise("cell1", 50, 3, 0.3, 0.4)

        assert getCachedNoise("cell1", 50, 3, 0.5) == 0.1
        assert getCachedNoise("cell1", 100, 3, 0.5) == 0.2
        assert getCachedNoise("cell1", 50, 5, 0.5) == 0.3
        assert getCachedNoise("cell1", 50, 3, 0.3) == 0.4

    def test_clear_cache(self):
        """Test cache clearing."""
        setCachedNoise("cell1", 50, 3, 0.5, 0.5)
        setCachedNoise("cell2", 50, 3, 0.5, 0.6)

        clearCache()

        assert getCachedNoise("cell1", 50, 3, 0.5) is None
        assert getCachedNoise("cell2", 50, 3, 0.5) is None

    def test_clear_cache(self):
        """Test cache clearing."""
        setCachedNoise("cell1", 50, 3, 0.5, 0.5)
        setCachedNoise("cell2", 50, 3, 0.5, 0.6)

        clearCache()

        assert getCachedNoise("cell1", 50, 3, 0.5) is None
        assert getCachedNoise("cell2", 50, 3, 0.5) is None
