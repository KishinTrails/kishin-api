"""
Tests for SQLite-based noise cache with multiprocessing support.
"""

import pytest
from concurrent.futures import ProcessPoolExecutor

from kishin_trails.noise_cache_sqlite import initCache, clearCache, setCachedNoise, getCachedNoise


def worker_task(worker_id: int) -> float:
    """
    Worker function for testing multiprocessing cache access.
    
    Each worker initializes its own connection and writes/reads a value.
    """
    initCache()
    cell = f"worker_{worker_id}_cell"
    value = worker_id / 10.0
    setCachedNoise(cell, 50, 3, 0.5, value)
    result = getCachedNoise(cell, 50, 3, 0.5)
    return result if result is not None else 0.0


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
    
    def test_multiprocessing_concurrent_writes(self):
        """Test that multiple processes can write to cache concurrently."""
        num_workers = 4
        
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(worker_task, i) for i in range(num_workers)]
            results = [f.result() for f in futures]
        
        expected = [i / 10.0 for i in range(num_workers)]
        assert results == expected
    
    def test_multiprocessing_data_persistence(self):
        """Test that worker writes are visible to main process."""
        num_workers = 4
        
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(worker_task, i) for i in range(num_workers)]
            futures = [f.result() for f in futures]
        
        for i in range(num_workers):
            cell = f"worker_{i}_cell"
            val = getCachedNoise(cell, 50, 3, 0.5)
            assert val == i / 10.0, f"Worker {i} value not persisted"
    
    def test_clear_cache(self):
        """Test cache clearing."""
        setCachedNoise("cell1", 50, 3, 0.5, 0.5)
        setCachedNoise("cell2", 50, 3, 0.5, 0.6)
        
        clearCache()
        
        assert getCachedNoise("cell1", 50, 3, 0.5) is None
        assert getCachedNoise("cell2", 50, 3, 0.5) is None
