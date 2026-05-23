"""
Tests for noise API endpoints.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

from kishin_trails.noise_cache import clearCache, initCache


class TestNoiseRouter:
    """Test the noise API router and endpoints."""
    @pytest.fixture(autouse=True)
    def setup_cache(self):
        """Initialize and clear cache before each test."""
        initCache()
        clearCache()
        yield

    @pytest.fixture
    def noise_router(self):
        """Provide the noise router for testing."""
        from kishin_trails.noise import router
        return router

    @pytest.fixture
    def getCellNoise(self, noise_router):
        """Get the getCellNoise endpoint function."""
        return noise_router.routes[0].endpoint

    def test_getCellNoise_empty_cells(self, getCellNoise):
        """Test getCellNoise with empty cells list returns empty array."""
        from kishin_trails.schemas import NoiseRequest

        request = NoiseRequest(cells=[], scale=50, octaves=3, amplitudeDecay=0.5)
        result = getCellNoise(request)
        assert result == []

    def test_getCellNoise_exceeds_limit(self, getCellNoise):
        """Test getCellNoise raises HTTPException for > 1000 cells."""
        from kishin_trails.schemas import NoiseRequest

        request = NoiseRequest(cells=["89c25a221"] * 1001, scale=50, octaves=3, amplitudeDecay=0.5)

        with pytest.raises(HTTPException) as exc_info:
            getCellNoise(request)

        assert exc_info.value.status_code == 400
        assert "Maximum 1000 cells" in exc_info.value.detail

    def test_getCellNoise_valid_cells(self, getCellNoise):
        """Test getCellNoise returns correct format for valid cells."""
        from kishin_trails.schemas import NoiseRequest

        request = NoiseRequest(cells=["89c25a221", "89c25a223"], scale=50, octaves=3, amplitudeDecay=0.5)

        result = getCellNoise(request)

        assert len(result) == 2
        assert result[0]["cell"] == "89c25a221"
        assert "noise" in result[0]
        assert 0.0 <= result[0]["noise"] <= 1.0
        assert result[1]["cell"] == "89c25a223"
        assert "noise" in result[1]

    def test_getCellNoise_custom_parameters(self, getCellNoise):
        """Test getCellNoise with custom octaves and amplitudeDecay."""
        from kishin_trails.schemas import NoiseRequest

        request = NoiseRequest(cells=["89c25a221"], scale=100, octaves=5, amplitudeDecay=0.3)

        result = getCellNoise(request)

        assert len(result) == 1
        assert result[0]["cell"] == "89c25a221"
        assert 0.0 <= result[0]["noise"] <= 1.0

    def test_getCellNoise_invalid_cell_skipped(self, getCellNoise):
        """Test getCellNoise skips invalid cells gracefully."""
        from kishin_trails.schemas import NoiseRequest

        request = NoiseRequest(cells=["not_a_valid_s2_cell", "89c25a221"], scale=50, octaves=3, amplitudeDecay=0.5)

        result = getCellNoise(request)

        assert len(result) == 1
        assert result[0]["cell"] == "89c25a221"

    def test_getCellNoise_exactly_1000_cells(self, getCellNoise):
        """Test getCellNoise accepts exactly 1000 cells."""
        from kishin_trails.schemas import NoiseRequest

        request = NoiseRequest(cells=["89c25a221"] * 1000, scale=50, octaves=3, amplitudeDecay=0.5)

        result = getCellNoise(request)
        assert len(result) == 1000
