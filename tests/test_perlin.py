"""
Tests for Perlin noise calculation functions.
"""

import pytest
from unittest.mock import patch, MagicMock

from kishin_trails.perlin import (
    fade,
    lerp,
    grad,
    perlin,
    getNoiseValue,
    latLngToMercator,
    getNoiseForCell,
)


class TestFade:
    """Test the fade function for smooth interpolation."""

    def test_fade_zero(self):
        """Test fade with input 0."""
        result = fade(0.0)
        assert result == 0.0

    def test_fade_one(self):
        """Test fade with input 1."""
        result = fade(1.0)
        assert result == 1.0

    def test_fade_half(self):
        """Test fade with input 0.5."""
        result = fade(0.5)
        assert result == 0.5

    def test_fade_negative(self):
        """Test fade with negative input."""
        result = fade(-0.5)
        assert result < 0

    def test_fade_greater_than_one(self):
        """Test fade with input > 1."""
        result = fade(1.5)
        assert result > 1


class TestLerp:
    """Test the linear interpolation function."""

    def test_lerp_start(self):
        """Test lerp at t=0 returns start value."""
        result = lerp(10.0, 20.0, 0.0)
        assert result == 10.0

    def test_lerp_end(self):
        """Test lerp at t=1 returns end value."""
        result = lerp(10.0, 20.0, 1.0)
        assert result == 20.0

    def test_lerp_half(self):
        """Test lerp at t=0.5 returns midpoint."""
        result = lerp(10.0, 20.0, 0.5)
        assert result == 15.0

    def test_lerp_negative(self):
        """Test lerp with negative t."""
        result = lerp(10.0, 20.0, -0.5)
        assert result == 5.0

    def test_lerp_beyond_one(self):
        """Test lerp with t > 1."""
        result = lerp(10.0, 20.0, 1.5)
        assert result == 25.0


class TestGrad:
    """Test the gradient function."""

    def test_grad_hash_0(self):
        """Test grad with hash value 0."""
        result = grad(0, 1.0, 1.0)
        assert result == 2.0

    def test_grad_hash_1(self):
        """Test grad with hash value 1."""
        result = grad(1, 1.0, 1.0)
        assert result == 0.0

    def test_grad_hash_2(self):
        """Test grad with hash value 2."""
        result = grad(2, 1.0, 1.0)
        assert result == 0.0

    def test_grad_hash_3(self):
        """Test grad with hash value 3."""
        result = grad(3, 1.0, 1.0)
        assert result == -2.0

    def test_grad_negative_coords(self):
        """Test grad with negative coordinates."""
        result = grad(0, -1.0, -1.0)
        assert result == -2.0


class TestPerlin:
    """Test the Perlin noise function."""

    def test_perlin_origin(self):
        """Test Perlin noise at origin."""
        result = perlin(0.0, 0.0)
        assert -1.0 <= result <= 1.0

    def test_perlin_integer_coords(self):
        """Test Perlin noise at integer coordinates."""
        result = perlin(1.0, 1.0)
        assert -1.0 <= result <= 1.0

    def test_perlin_fractional_coords(self):
        """Test Perlin noise at fractional coordinates."""
        result = perlin(0.5, 0.5)
        assert -1.0 <= result <= 1.0

    def test_perlin_negative_coords(self):
        """Test Perlin noise at negative coordinates."""
        result = perlin(-0.5, -0.5)
        assert -1.0 <= result <= 1.0

    def test_perlin_large_coords(self):
        """Test Perlin noise at large coordinates."""
        result = perlin(100.5, 200.7)
        assert -1.0 <= result <= 1.0


class TestGetNoiseValue:
    """Test the multi-octave noise value function."""

    def test_getNoiseValue_defaults(self):
        """Test getNoiseValue with default parameters."""
        result = getNoiseValue(0.5, 0.5, 50)
        assert 0.0 <= result <= 1.0

    def test_getNoiseValue_custom_octaves(self):
        """Test getNoiseValue with custom octaves."""
        result = getNoiseValue(0.5, 0.5, 50, octaves=5)
        assert 0.0 <= result <= 1.0

    def test_getNoiseValue_custom_amplitude(self):
        """Test getNoiseValue with custom amplitude decay."""
        result = getNoiseValue(0.5, 0.5, 50, amplitudeDecay=0.3)
        assert 0.0 <= result <= 1.0

    def test_getNoiseValue_different_coords(self):
        """Test getNoiseValue at different coordinates."""
        result1 = getNoiseValue(0.1, 0.1, 50)
        result2 = getNoiseValue(0.9, 0.9, 50)
        assert 0.0 <= result1 <= 1.0
        assert 0.0 <= result2 <= 1.0

    def test_getNoiseValue_scale_variation(self):
        """Test getNoiseValue with different scales."""
        result1 = getNoiseValue(0.5, 0.5, 10)
        result2 = getNoiseValue(0.5, 0.5, 100)
        assert 0.0 <= result1 <= 1.0
        assert 0.0 <= result2 <= 1.0


class TestLatLngToMercator:
    """Test latitude/longitude to Mercator conversion."""

    def test_latLngToMercator_equator(self):
        """Test conversion at the equator."""
        mercX, mercY = latLngToMercator(0.0, 0.0)
        assert 0.0 <= mercX <= 1.0
        assert 0.0 <= mercY <= 1.0

    def test_latLngToMercator_greenwich(self):
        """Test conversion at Greenwich meridian."""
        mercX, mercY = latLngToMercator(51.5074, 0.0)
        assert 0.0 <= mercX <= 1.0
        assert 0.0 <= mercY <= 1.0

    def test_latLngToMercator_extreme_north(self):
        """Test conversion at extreme north latitude."""
        mercX, mercY = latLngToMercator(85.0, 0.0)
        assert 0.0 <= mercX <= 1.0
        assert 0.0 <= mercY <= 1.0

    def test_latLngToMercator_extreme_south(self):
        """Test conversion at extreme south latitude."""
        mercX, mercY = latLngToMercator(-85.0, 0.0)
        assert 0.0 <= mercX <= 1.0
        assert 0.0 <= mercY <= 1.0


class TestGetNoiseForCell:
    """Test the H3 cell noise function with caching."""

    @pytest.fixture
    def valid_h3_cell(self):
        """Provide a valid H3 cell for testing."""
        return "8a2a1072b597fff"

    def test_getNoiseForCell_returns_valid_range(self, valid_h3_cell):
        """Test getNoiseForCell returns value in [0, 1] range."""
        result = getNoiseForCell(valid_h3_cell, 50)
        assert 0.0 <= result <= 1.0

    def test_getNoiseForCell_custom_parameters(self, valid_h3_cell):
        """Test getNoiseForCell with custom parameters."""
        result = getNoiseForCell(valid_h3_cell, 100, octaves=5, amplitudeDecay=0.3)
        assert 0.0 <= result <= 1.0

    def test_getNoiseForCell_cache_hit(self, valid_h3_cell):
        """Test getNoiseForCell uses cache on second call."""
        from kishin_trails.noise_cache_sqlite import getCachedNoise, setCachedNoise, clearCache, initCache
        
        initCache()
        clearCache()
        
        first_call = getNoiseForCell(valid_h3_cell, 50, 3, 0.5)
        cached_value = getCachedNoise(valid_h3_cell, 50, 3, 0.5)
        
        assert cached_value == first_call
        
        second_call = getNoiseForCell(valid_h3_cell, 50, 3, 0.5)
        assert second_call == first_call

    def test_getNoiseForCell_different_cells_different_values(self):
        """Test different H3 cells produce different noise values."""
        cell1 = "8a2a1072b597fff"
        cell2 = "8a2a1072b59ffff"
        
        result1 = getNoiseForCell(cell1, 50)
        result2 = getNoiseForCell(cell2, 50)
        
        assert result1 != result2
