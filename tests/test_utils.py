"""Tests for the sanitizeValue utility function."""

import pytest

from kishin_trails.utils import (
    getH3Cell,
    getH3CellRadius,
    getH3Circle,
    pointInH3Hexagon,
    sanitizeValue,
)


class TestSanitizeValue:
    """Tests for the sanitizeValue utility function."""
    def test_sanitizeValue_handles_string(self) -> None:
        """sanitizeValue should return strings unchanged."""
        input_value = "test"
        result = sanitizeValue(input_value)
        assert result == input_value

    def test_sanitizeValue_handles_int(self) -> None:
        """sanitizeValue should convert int to string."""
        input_value = 42
        result = sanitizeValue(input_value)
        assert result == str(input_value)

    def test_sanitizeValue_handles_float_nan(self) -> None:
        """sanitizeValue should return None for NaN."""
        input_value = float("nan")
        result = sanitizeValue(input_value)
        assert result is None

    def test_sanitizeValue_handles_float_inf(self) -> None:
        """sanitizeValue should return None for positive infinity."""
        input_value = float("inf")
        result = sanitizeValue(input_value)
        assert result is None

    def test_sanitizeValue_handles_float_negative_inf(self) -> None:
        """sanitizeValue should return None for negative infinity."""
        input_value = float("-inf")
        result = sanitizeValue(input_value)
        assert result is None

    def test_sanitizeValue_handles_none(self) -> None:
        """sanitizeValue should convert None to 'None' string."""
        input_value = None
        result = sanitizeValue(input_value)
        assert result == str(input_value)


class TestGetH3CellRadius:
    """Tests for the getH3CellRadius utility function."""
    def test_getH3CellRadius_res10(self) -> None:
        """getH3CellRadius should return ~150m for resolution 10 cells."""
        cell = "8a1fb4662787fff"
        radius = getH3CellRadius(cell)
        assert 70 <= radius <= 80

    def test_getH3CellRadius_res9(self) -> None:
        """getH3CellRadius should return ~400m for resolution 9 cells."""
        cell = "891fb46627bffff"
        radius = getH3CellRadius(cell)
        assert 195 <= radius <= 205

    def test_getH3CellRadius_res5(self) -> None:
        """getH3CellRadius should return ~20km for resolution 5 cells."""
        cell = "851fb467fffffff"
        radius = getH3CellRadius(cell)
        assert 9850 <= radius <= 9860


class TestGetH3Circle:
    """Tests for the getH3Circle utility function."""
    def test_getH3Circle_level0(self) -> None:
        """getH3Circle should return cell center and radius for level 0."""
        cell = "8a1fb4662787fff"
        lat, lng, radius, search_cell = getH3Circle(cell, 0)
        assert search_cell == cell
        assert 48 <= lat <= 49
        assert 2 <= lng <= 3
        assert 70 <= radius <= 80

    def test_getH3Circle_level1(self) -> None:
        """getH3Circle should return parent cell for level 1."""
        cell = "8a1fb4662787fff"
        lat, lng, radius, search_cell = getH3Circle(cell, 1)
        assert search_cell != cell
        assert 195 <= radius <= 205

    def test_getH3Circle_invalid_level(self) -> None:
        """getH3Circle should raise ValueError for invalid parent level."""
        cell = "8a1fb4662787fff"
        with pytest.raises(ValueError, match="exceeds cell resolution"):
            getH3Circle(cell, 15)


class TestPointInH3Hexagon:
    """Tests for the pointInH3Hexagon utility function."""
    def test_pointInH3Hexagon_center(self) -> None:
        """pointInH3Hexagon should return True for center point."""
        lat, lng = 40.7128, -74.0060
        cell = getH3Cell(lat, lng, 9)
        result = pointInH3Hexagon(lat, lng, cell)
        assert result is True

    def test_pointInH3Hexagon_outside(self) -> None:
        """pointInH3Hexagon should return False for distant point."""
        lat, lng = 40.7128, -74.0060
        cell = getH3Cell(lat, lng, 9)
        result = pointInH3Hexagon(0, 0, cell)
        assert result is False

    def test_pointInH3Hexagon_on_edge(self) -> None:
        """pointInH3Hexagon should return False for point on edge."""
        lat, lng = 40.7128, -74.0060
        cell = getH3Cell(lat, lng, 9)
        edge_lat = lat + 0.01
        edge_lng = lng + 0.01
        result = pointInH3Hexagon(edge_lat, edge_lng, cell)
        assert result is False
