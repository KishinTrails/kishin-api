"""Tests for the sanitize_value utility function."""

import pytest

from kishin_trails.utils import get_h3_cell_radius, get_h3_circle, sanitize_value


class TestSanitizeValue:
    """Tests for the sanitize_value utility function."""
    def test_sanitize_value_handles_string(self) -> None:
        """sanitize_value should return strings unchanged."""
        input_value = "test"
        result = sanitize_value(input_value)
        assert result == input_value

    def test_sanitize_value_handles_int(self) -> None:
        """sanitize_value should convert int to string."""
        input_value = 42
        result = sanitize_value(input_value)
        assert result == str(input_value)

    def test_sanitize_value_handles_float_nan(self) -> None:
        """sanitize_value should return None for NaN."""
        input_value = float("nan")
        result = sanitize_value(input_value)
        assert result is None

    def test_sanitize_value_handles_float_inf(self) -> None:
        """sanitize_value should return None for positive infinity."""
        input_value = float("inf")
        result = sanitize_value(input_value)
        assert result is None

    def test_sanitize_value_handles_float_negative_inf(self) -> None:
        """sanitize_value should return None for negative infinity."""
        input_value = float("-inf")
        result = sanitize_value(input_value)
        assert result is None

    def test_sanitize_value_handles_none(self) -> None:
        """sanitize_value should convert None to 'None' string."""
        input_value = None
        result = sanitize_value(input_value)
        assert result == str(input_value)


class TestGetH3CellRadius:
    """Tests for the get_h3_cell_radius utility function."""
    def test_get_h3_cell_radius_res10(self) -> None:
        """get_h3_cell_radius should return ~150m for resolution 10 cells."""
        cell = "8a1fb4662787fff"
        radius = get_h3_cell_radius(cell)
        assert 150 <= radius <= 155

    def test_get_h3_cell_radius_res9(self) -> None:
        """get_h3_cell_radius should return ~400m for resolution 9 cells."""
        cell = "891fb46627bffff"
        radius = get_h3_cell_radius(cell)
        assert 395 <= radius <= 405

    def test_get_h3_cell_radius_res5(self) -> None:
        """get_h3_cell_radius should return ~20km for resolution 5 cells."""
        cell = "851fb467fffffff"
        radius = get_h3_cell_radius(cell)
        assert 19700 <= radius <= 19800


class TestGetH3Circle:
    """Tests for the get_h3_circle utility function."""
    def test_get_h3_circle_level0(self) -> None:
        """get_h3_circle should return cell center and radius for level 0."""
        cell = "8a1fb4662787fff"
        lat, lng, radius, search_cell = get_h3_circle(cell, 0)
        assert search_cell == cell
        assert 48 <= lat <= 49
        assert 2 <= lng <= 3
        assert 150 <= radius <= 155

    def test_get_h3_circle_level1(self) -> None:
        """get_h3_circle should return parent cell for level 1."""
        cell = "8a1fb4662787fff"
        lat, lng, radius, search_cell = get_h3_circle(cell, 1)
        assert search_cell != cell
        assert 400 <= radius <= 405

    def test_get_h3_circle_invalid_level(self) -> None:
        """get_h3_circle should raise ValueError for invalid parent level."""
        cell = "8a1fb4662787fff"
        with pytest.raises(ValueError, match="exceeds cell resolution"):
            get_h3_circle(cell, 15)
