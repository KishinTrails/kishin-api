"""
Tests for SQLAlchemy-based noise cache using S2 geometry tokens.
"""

import pytest
from kishin_trails.noise_cache import getCachedNoise, setCachedNoise, clearCache, initCache
from kishin_trails.utils import latLngToS2Cell


class TestNoiseCache:
    """Tests for the persistent Perlin noise cache."""

    @pytest.fixture(autouse=True)
    def setup_cache(self):
        """Initialize and clear cache before each test."""
        initCache()
        clearCache()
        yield

    def test_set_and_get_noise(self):
        """Test basic set and retrieve operations."""
        s2_token = latLngToS2Cell(45.0, 5.0, 16)
        perlin_value = 0.75
        
        setCachedNoise(s2_token, 50, 3, 0.5, perlin_value)
        result = getCachedNoise(s2_token, 50, 3, 0.5)
        
        assert result == perlin_value

    def test_get_nonexistent_noise(self):
        """Test retrieving a value that isn't in the cache."""
        s2_token = latLngToS2Cell(45.0, 5.0, 16)
        result = getCachedNoise(s2_token, 50, 3, 0.5)
        assert result is None

    def test_cache_idempotency(self):
        """Test that setting the same value multiple times is safe."""
        s2_token = latLngToS2Cell(45.0, 5.0, 16)
        val1 = 0.5
        val2 = 0.6  # In practice it would be the same value
        
        setCachedNoise(s2_token, 50, 3, 0.5, val1)
        setCachedNoise(s2_token, 50, 3, 0.5, val2)
        
        result = getCachedNoise(s2_token, 50, 3, 0.5)
        assert result == val1  # First one wins due to INSERT OR IGNORE

    def test_different_params_different_cache(self):
        """Test that different parameters create distinct cache entries."""
        s2_token = latLngToS2Cell(45.0, 5.0, 16)
        
        setCachedNoise(s2_token, 50, 3, 0.5, 0.1)
        setCachedNoise(s2_token, 100, 3, 0.5, 0.2)
        setCachedNoise(s2_token, 50, 5, 0.5, 0.3)
        setCachedNoise(s2_token, 50, 3, 0.8, 0.4)
        
        assert getCachedNoise(s2_token, 50, 3, 0.5) == 0.1
        assert getCachedNoise(s2_token, 100, 3, 0.5) == 0.2
        assert getCachedNoise(s2_token, 50, 5, 0.5) == 0.3
        assert getCachedNoise(s2_token, 50, 3, 0.8) == 0.4

    def test_different_cells_different_cache(self):
        """Test that different S2 cells have separate cache entries."""
        token1 = latLngToS2Cell(45.0, 5.0, 16)
        token2 = latLngToS2Cell(45.1, 5.1, 16)
        
        setCachedNoise(token1, 50, 3, 0.5, 0.55)
        setCachedNoise(token2, 50, 3, 0.5, 0.66)
        
        assert getCachedNoise(token1, 50, 3, 0.5) == 0.55
        assert getCachedNoise(token2, 50, 3, 0.5) == 0.66
