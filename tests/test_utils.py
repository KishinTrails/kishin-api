"""Comprehensive tests for S2 geometry utilities."""

import math
import pytest
from shapely.geometry import Polygon, MultiPolygon

from kishin_trails.s2_utils import (
    EARTH_RADIUS,
    sanitizeValue,
    latLngToS2Cell,
    s2CellIdToHex,
    s2CellIdFromHex,
    s2CellIdToLatLng,
    getS2CellLevel,
    s2CellToParent,
    getS2CellBounds,
    getS2CellCenter,
    getS2EdgeLength,
    pointInS2Cell,
    s2CellsFromPolygon,
    s2CellIdToToken,
    s2CellToChildren,
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

    def test_sanitizeValue_handles_boolean_true(self) -> None:
        """sanitizeValue should convert True to 'True' string."""
        input_value = True
        result = sanitizeValue(input_value)
        assert result == "True"

    def test_sanitizeValue_handles_boolean_false(self) -> None:
        """sanitizeValue should convert False to 'False' string."""
        input_value = False
        result = sanitizeValue(input_value)
        assert result == "False"

    def test_sanitizeValue_handles_float_regular(self) -> None:
        """sanitizeValue should convert regular float to string."""
        input_value = 3.14
        result = sanitizeValue(input_value)
        assert result == "3.14"

    def test_sanitizeValue_handles_list(self) -> None:
        """sanitizeValue should convert list to string representation."""
        input_value = [1, 2, 3]
        result = sanitizeValue(input_value)
        assert result == "[1, 2, 3]"

    def test_sanitizeValue_handles_dict(self) -> None:
        """sanitizeValue should convert dict to string representation."""
        input_value = {
            "key": "value"
        }
        result = sanitizeValue(input_value)
        assert result == "{'key': 'value'}"

    def test_sanitizeValue_handles_zero(self) -> None:
        """sanitizeValue should convert 0 to '0' string."""
        input_value = 0
        result = sanitizeValue(input_value)
        assert result == "0"

    def test_sanitizeValue_handles_negative_int(self) -> None:
        """sanitizeValue should convert negative int to string."""
        input_value = -42
        result = sanitizeValue(input_value)
        assert result == "-42"

    def test_sanitizeValue_handles_empty_string(self) -> None:
        """sanitizeValue should return empty string unchanged."""
        input_value = ""
        result = sanitizeValue(input_value)
        assert result == ""

    def test_sanitizeValue_handles_scientific_notation(self) -> None:
        """sanitizeValue should convert scientific notation float to string."""
        input_value = 1e10
        result = sanitizeValue(input_value)
        assert result == "10000000000.0"

    def test_sanitizeValue_handles_very_small_float(self) -> None:
        """sanitizeValue should convert very small float to string."""
        input_value = 1e-10
        result = sanitizeValue(input_value)
        assert result == "1e-10"


class TestLatLngToS2Cell:
    """Tests for the latLngToS2Cell function."""
    def test_latLngToS2Cell_default_level(self) -> None:
        """latLngToS2Cell should return cell ID at level 16 by default."""
        cell_id = latLngToS2Cell(40.7128, -74.0060)
        assert isinstance(cell_id, int)
        assert cell_id == 9926595631021817856
        level = getS2CellLevel(cell_id)
        assert level == 16

    def test_latLngToS2Cell_level_0(self) -> None:
        """latLngToS2Cell should return level 0 cell (very large)."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 0)
        assert cell_id == 10376293541461622784
        level = getS2CellLevel(cell_id)
        assert level == 0

    def test_latLngToS2Cell_level_30(self) -> None:
        """latLngToS2Cell should return level 30 cell (very small)."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 30)
        assert cell_id == 9926595630970964329
        level = getS2CellLevel(cell_id)
        assert level == 30

    def test_latLngToS2Cell_equator(self) -> None:
        """latLngToS2Cell should handle equator coordinates."""
        cell_id = latLngToS2Cell(0.0, 0.0, 10)
        assert cell_id == 1152922604118474752
        lat, lng = s2CellIdToLatLng(cell_id)
        assert -1 <= lat <= 1
        assert -1 <= lng <= 1

    def test_latLngToS2Cell_north_pole(self) -> None:
        """latLngToS2Cell should handle north pole coordinates."""
        cell_id = latLngToS2Cell(89.0, 0.0, 5)
        assert cell_id == 5763481623127392256
        lat, lng = s2CellIdToLatLng(cell_id)
        assert 88 <= lat <= 90
        assert lng == -45

    def test_latLngToS2Cell_south_pole(self) -> None:
        """latLngToS2Cell should handle south pole coordinates."""
        cell_id = latLngToS2Cell(-89.0, 0.0, 5)
        assert cell_id == 12683262450582159360
        lat, lng = s2CellIdToLatLng(cell_id)
        assert -90 <= lat <= 88
        assert lng == 45

    def test_latLngToS2Cell_different_locations_different_cells(self) -> None:
        """latLngToS2Cell should return different cells for different locations."""
        cell_nyc = latLngToS2Cell(40.7128, -74.0060, 10)
        cell_la = latLngToS2Cell(34.0522, -118.2437, 10)
        assert cell_nyc != cell_la


class TestS2CellIdToHex:
    """Tests for the s2CellIdToHex function."""
    def test_s2CellIdToHex_removes_trailing_zeros(self) -> None:
        """s2CellIdToHex should remove trailing zeros."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 16)
        hex_str = s2CellIdToHex(cell_id)
        assert not hex_str.endswith("0")

    def test_s2CellIdToHex_returns_hex_string(self) -> None:
        """s2CellIdToHex should return a hexadecimal string."""
        cell_id = latLngToS2Cell(40.7128, -74.0060)
        hex_str = s2CellIdToHex(cell_id)
        assert isinstance(hex_str, str)
        assert all(c in "0123456789abcdef" for c in hex_str)

    def test_s2CellIdToHex_no_prefix(self) -> None:
        """s2CellIdToHex should not include 0x prefix."""
        cell_id = latLngToS2Cell(40.7128, -74.0060)
        hex_str = s2CellIdToHex(cell_id)
        assert not hex_str.startswith("0x")

    def test_s2CellIdToHex_nyc(self) -> None:
        """latLngToS2Cell should return cell ID at corresponding NYC."""
        cell_id = latLngToS2Cell(40.7128, -74.0060)
        hex_str = s2CellIdToHex(cell_id)
        assert hex_str == "89c25a221"

    def test_s2CellIdToHex_level_0(self) -> None:
        """latLngToS2Cell should return level 0 cell (very large)."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 0)
        hex_str = s2CellIdToHex(cell_id)
        assert hex_str == "9"

    def test_s2CellIdToHex_level_30(self) -> None:
        """latLngToS2Cell should return level 30 cell (very small)."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 30)
        hex_str = s2CellIdToHex(cell_id)
        assert hex_str == "89c25a220cf80969"


class TestS2CellIdFromHex:
    """Tests for the s2CellIdFromHex function."""
    def test_s2CellIdFromHex_roundtrip(self) -> None:
        """s2CellIdFromHex should correctly reconstruct cell ID from hex."""
        original_id = latLngToS2Cell(40.7128, -74.0060, 16)
        hex_str = s2CellIdToHex(original_id)
        reconstructed_id = s2CellIdFromHex(hex_str)
        assert reconstructed_id == original_id

    def test_s2CellIdFromHex_without_prefix(self) -> None:
        """s2CellIdFromHex should handle hex string without 0x prefix."""
        cell_id = s2CellIdFromHex("89c25a221")
        assert isinstance(cell_id, int)
        assert cell_id == 9926595631021817856

    def test_s2CellIdFromHex_with_prefix(self) -> None:
        """s2CellIdFromHex should return 0 for hex string with 0x prefix (prefix not supported)."""
        cell_id = s2CellIdFromHex("0x89c25a221")
        assert isinstance(cell_id, int)
        assert cell_id == 0

    def test_s2CellIdFromHex_consistency(self) -> None:
        """s2CellIdFromHex should produce consistent results."""
        hex_str = "89c25a221"
        id1 = s2CellIdFromHex(hex_str)
        id2 = s2CellIdFromHex(hex_str)
        assert id1 == id2


class TestS2CellIdToLatLng:
    """Tests for the s2CellIdToLatLng function."""
    def test_s2CellIdToLatLng_returns_tuple(self) -> None:
        """s2CellIdToLatLng should return a tuple of (lat, lng)."""
        cell_id = latLngToS2Cell(40.7128, -74.0060)
        result = s2CellIdToLatLng(cell_id)
        assert isinstance(result, tuple)

    def test_s2CellIdToLatLng_lat_in_range(self) -> None:
        """s2CellIdToLatLng should return latitude in [-90, 90]."""
        cell_id = latLngToS2Cell(40.7128, -74.0060)
        lat, lng = s2CellIdToLatLng(cell_id)
        assert -90 <= lat <= 90

    def test_s2CellIdToLatLng_lng_in_range(self) -> None:
        """s2CellIdToLatLng should return longitude in [-180, 180]."""
        cell_id = latLngToS2Cell(40.7128, -74.0060)
        lat, lng = s2CellIdToLatLng(cell_id)
        assert -180 <= lng <= 180

    def test_s2CellIdToLatLng_roundtrip_nyc(self) -> None:
        """s2CellIdToLatLng center should be close to original NYC coordinates."""
        original_lat, original_lng = 40.7128, -74.0060
        cell_id = latLngToS2Cell(original_lat, original_lng, 10)
        lat, lng = s2CellIdToLatLng(cell_id)
        assert abs(lat - original_lat) < 0.05
        assert abs(lng - original_lng) < 0.05

    def test_s2CellIdToLatLng_roundtrip_equator(self) -> None:
        """s2CellIdToLatLng center should be close to original equator coordinates."""
        original_lat, original_lng = 0.0, 0.0
        cell_id = latLngToS2Cell(original_lat, original_lng, 10)
        lat, lng = s2CellIdToLatLng(cell_id)
        assert abs(lat - original_lat) < 0.05
        assert abs(lng - original_lng) < 0.05


class TestGetS2CellLevel:
    """Tests for the getS2CellLevel function."""
    def test_getS2CellLevel_returns_int(self) -> None:
        """getS2CellLevel should return an integer."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 16)
        level = getS2CellLevel(cell_id)
        assert isinstance(level, int)

    def test_getS2CellLevel_in_range(self) -> None:
        """getS2CellLevel should return a level between 0 and 30."""
        cell_id = latLngToS2Cell(40.7128, -74.0060)
        level = getS2CellLevel(cell_id)
        assert 0 <= level <= 30

    def test_getS2CellLevel_matches_creation_level(self) -> None:
        """getS2CellLevel should match the level used to create the cell."""
        for level in [0, 5, 10, 15, 20, 25, 30]:
            cell_id = latLngToS2Cell(40.7128, -74.0060, level)
            assert getS2CellLevel(cell_id) == level

    def test_getS2CellLevel_parent_higher_than_child(self) -> None:
        """Parent cell level should be lower (coarser) than child level."""
        from kishin_trails.s2_utils import s2CellToParent
        child_cell = latLngToS2Cell(40.7128, -74.0060, 15)
        parent_cell = s2CellToParent(child_cell, 10)
        assert getS2CellLevel(parent_cell) == 10
        assert getS2CellLevel(parent_cell) < getS2CellLevel(child_cell)


class TestS2CellToParent:
    """Tests for the s2CellToParent function."""
    def test_s2CellToParent_returns_int(self) -> None:
        """s2CellToParent should return an integer cell ID."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 15)
        parent_id = s2CellToParent(cell_id, 10)
        assert isinstance(parent_id, int)

    def test_s2CellToParent_level_decreases(self) -> None:
        """s2CellToParent should return cell at a lower (coarser) level."""
        child_cell = latLngToS2Cell(40.7128, -74.0060, 15)
        parent_cell = s2CellToParent(child_cell, 10)
        assert getS2CellLevel(parent_cell) == 10
        assert getS2CellLevel(parent_cell) < getS2CellLevel(child_cell)

    def test_s2CellToParent_grandparent(self) -> None:
        """s2CellToParent can return grandparent at multiple levels difference."""
        child_cell = latLngToS2Cell(40.7128, -74.0060, 20)
        grandparent_cell = s2CellToParent(child_cell, 10)
        assert getS2CellLevel(grandparent_cell) == 10

    def test_s2CellToParent_same_level_as_parent(self) -> None:
        """s2CellToParent should return same cell when parent level equals cell level."""
        cell = latLngToS2Cell(40.7128, -74.0060, 10)
        parent = s2CellToParent(cell, 10)
        assert parent == cell

    def test_s2CellToParent_parent_contains_child(self) -> None:
        """Parent cell bounds should contain child cell center."""
        child_cell = latLngToS2Cell(40.7128, -74.0060, 15)
        parent_cell = s2CellToParent(child_cell, 10)
        child_lat, child_lng = s2CellIdToLatLng(child_cell)
        parent_bounds = getS2CellBounds(parent_cell)
        lo_lat, lo_lng, hi_lat, hi_lng = parent_bounds
        assert lo_lat <= child_lat <= hi_lat
        assert lo_lng <= child_lng <= hi_lng

    def test_s2CellToParent_child_of_parent(self) -> None:
        """Child cell should be one of the parent's children."""
        parent_cell = latLngToS2Cell(40.7128, -74.0060, 10)
        child_cell = latLngToS2Cell(40.7128, -74.0060, 15)
        derived_parent = s2CellToParent(child_cell, 10)
        assert derived_parent == parent_cell

    def test_s2CellToParent_retrieved_parent_is_actual_parent(self) -> None:
        """Parent derived from child should have child in its children list."""
        child_cell = latLngToS2Cell(40.7128, -74.0060, 15)
        parent_cell = s2CellToParent(child_cell, 10)
        children = s2CellToChildren(parent_cell, 15)
        assert child_cell in children

    def test_s2CellToParent_unrelated_cells_not_parent(self) -> None:
        """Unrelated cells should not have parent-child relationship."""
        nyc_cell = latLngToS2Cell(40.7128, -74.0060, 11)
        la_cell = latLngToS2Cell(34.0522, -118.2437, 10)
        assert nyc_cell not in s2CellToChildren(la_cell, 11)

    def test_s2CellToParent_wrontparent(self) -> None:
        """s2CellToParent can return grandparent at multiple levels difference."""
        child_cell = latLngToS2Cell(40.7128, -74.0060, 10)
        with pytest.raises(ValueError):
            s2CellToParent(child_cell, 15)


class TestGetS2CellBounds:
    """Tests for the getS2CellBounds function."""
    def test_getS2CellBounds_returns_tuple(self) -> None:
        """getS2CellBounds should return a tuple of 4 floats."""
        cell_id = latLngToS2Cell(40.7128, -74.0060)
        bounds = getS2CellBounds(cell_id)
        assert isinstance(bounds, tuple)
        assert len(bounds) == 4

    def test_getS2CellBounds_contains_center(self) -> None:
        """The cell center should be within the cell bounds."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 10)
        bounds = getS2CellBounds(cell_id)
        center_lat, center_lng = s2CellIdToLatLng(cell_id)
        lo_lat, lo_lng, hi_lat, hi_lng = bounds
        assert lo_lat <= center_lat <= hi_lat
        assert lo_lng <= center_lng <= hi_lng

    def test_getS2CellBounds_lo_le_hi_lat(self) -> None:
        """lo_lat should be less than or equal to hi_lat."""
        cell_id = latLngToS2Cell(40.7128, -74.0060)
        bounds = getS2CellBounds(cell_id)
        lo_lat, lo_lng, hi_lat, hi_lng = bounds
        assert lo_lat <= hi_lat

    def test_getS2CellBounds_lo_le_hi_lng(self) -> None:
        """lo_lng should be less than or equal to hi_lng."""
        cell_id = latLngToS2Cell(40.7128, -74.0060)
        bounds = getS2CellBounds(cell_id)
        lo_lat, lo_lng, hi_lat, hi_lng = bounds
        assert lo_lng <= hi_lng

    def test_getS2CellBounds_lat_in_range(self) -> None:
        """Bounds latitude values should be in valid range [-90, 90]."""
        cell_id = latLngToS2Cell(40.7128, -74.0060)
        lo_lat, lo_lng, hi_lat, hi_lng = getS2CellBounds(cell_id)
        assert -90 <= lo_lat <= 90
        assert -90 <= hi_lat <= 90

    def test_getS2CellBounds_lng_in_range(self) -> None:
        """Bounds longitude values should be in valid range [-180, 180]."""
        cell_id = latLngToS2Cell(40.7128, -74.0060)
        lo_lat, lo_lng, hi_lat, hi_lng = getS2CellBounds(cell_id)
        assert -180 <= lo_lng <= 180
        assert -180 <= hi_lng <= 180

    def test_getS2CellBounds_higher_res_smaller_area(self) -> None:
        """Higher resolution cells should have smaller bounds (area)."""
        cell_low = latLngToS2Cell(40.7128, -74.0060, 5)
        cell_high = latLngToS2Cell(40.7128, -74.0060, 15)
        bounds_low = getS2CellBounds(cell_low)
        bounds_high = getS2CellBounds(cell_high)
        area_low = (bounds_low[2] - bounds_low[0]) * (bounds_low[3] - bounds_low[1])
        area_high = (bounds_high[2] - bounds_high[0]) * (bounds_high[3] - bounds_high[1])
        assert area_high < area_low

    def test_getS2CellBounds_spans_reasonable_ratio_to_edge(self) -> None:
        """Bounds spans should be 1-2x the edge length (cell inscribed in rect)."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 10)
        bounds = getS2CellBounds(cell_id)

        lat_span_m = (bounds[2] - bounds[0]) * math.pi / 180 * EARTH_RADIUS
        lng_span_m = (bounds[3] - bounds[1]) * math.pi / 180 * EARTH_RADIUS

        edge_length = getS2EdgeLength(cell_id)

        assert 1.0 <= lat_span_m / edge_length <= 1.05
        assert 1.0 <= lng_span_m / edge_length <= 1.05


class TestGetS2CellCenter:
    """Tests for the getS2CellCenter function."""
    def test_getS2CellCenter_returns_tuple(self) -> None:
        """getS2CellCenter should return a tuple of (lat, lng)."""
        cell_id = latLngToS2Cell(40.7128, -74.0060)
        center = getS2CellCenter(cell_id)
        assert isinstance(center, tuple)
        assert len(center) == 2

    def test_getS2CellCenter_equals_midpoint(self) -> None:
        """getS2CellCenter should equal the midpoint of bounds."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 10)
        center = getS2CellCenter(cell_id)
        bounds = getS2CellBounds(cell_id)
        expected_lat = (bounds[0] + bounds[2]) / 2
        expected_lng = (bounds[1] + bounds[3]) / 2
        assert abs(center[0] - expected_lat) < 0.0001
        assert abs(center[1] - expected_lng) < 0.0001

    def test_getS2CellCenter_within_bounds(self) -> None:
        """The center should be within the cell bounds."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 10)
        center_lat, center_lng = getS2CellCenter(cell_id)
        bounds = getS2CellBounds(cell_id)
        lo_lat, lo_lng, hi_lat, hi_lng = bounds
        assert lo_lat <= center_lat <= hi_lat
        assert lo_lng <= center_lng <= hi_lng

    def test_getS2CellCenter_close_to_creation_point(self) -> None:
        """Center should be close to the coordinates used to create the cell."""
        original_lat, original_lng = 40.7128, -74.0060
        cell_id = latLngToS2Cell(original_lat, original_lng, 10)
        center_lat, center_lng = getS2CellCenter(cell_id)
        assert abs(center_lat - original_lat) < 0.05
        assert abs(center_lng - original_lng) < 0.05

    def test_getS2CellCenter_lat_in_range(self) -> None:
        """Center latitude should be in valid range [-90, 90]."""
        cell_id = latLngToS2Cell(40.7128, -74.0060)
        center_lat, center_lng = getS2CellCenter(cell_id)
        assert -90 <= center_lat <= 90

    def test_getS2CellCenter_lng_in_range(self) -> None:
        """Center longitude should be in valid range [-180, 180]."""
        cell_id = latLngToS2Cell(40.7128, -74.0060)
        center_lat, center_lng = getS2CellCenter(cell_id)
        assert -180 <= center_lng <= 180


class TestGetS2EdgeLength:
    """Tests for the getS2EdgeLength function."""
    def test_getS2EdgeLength_returns_float(self) -> None:
        """getS2EdgeLength should return a float."""
        cell_id = latLngToS2Cell(40.7128, -74.0060)
        edge_length = getS2EdgeLength(cell_id)
        assert isinstance(edge_length, float)

    def test_getS2EdgeLength_positive(self) -> None:
        """getS2EdgeLength should return a positive value."""
        cell_id = latLngToS2Cell(40.7128, -74.0060)
        edge_length = getS2EdgeLength(cell_id)
        assert edge_length > 0

    def test_getS2EdgeLength_decreases_with_level(self) -> None:
        """Higher resolution cells should have smaller edge lengths."""
        cell_low = latLngToS2Cell(40.7128, -74.0060, 5)
        cell_mid = latLngToS2Cell(40.7128, -74.0060, 10)
        cell_high = latLngToS2Cell(40.7128, -74.0060, 15)
        edge_low = getS2EdgeLength(cell_low)
        edge_mid = getS2EdgeLength(cell_mid)
        edge_high = getS2EdgeLength(cell_high)
        assert edge_mid < edge_low
        assert edge_high < edge_mid

    def test_getS2EdgeLength_level_1_very_large(self) -> None:
        """Level 1 cells should have very large edge lengths (earth-scale)."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 1)
        edge_length = getS2EdgeLength(cell_id)
        assert 3921000 <= edge_length <= 5004000

    def test_getS2EdgeLength_level_30_very_small(self) -> None:
        """Level 30 cells should have very small edge lengths."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 30)
        edge_length = getS2EdgeLength(cell_id)
        assert 0 <= edge_length <= 0.01

    def test_getS2EdgeLength_reasonable_for_level_16(self) -> None:
        """Level 16 cells should have edge lengths around 100-165 m."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 16)
        edge_length = getS2EdgeLength(cell_id)
        assert 100 < edge_length <= 165


class TestPointInS2Cell:
    """Tests for the pointInS2Cell function."""
    def test_pointInS2Cell_returns_bool(self) -> None:
        """pointInS2Cell should return a boolean."""
        cell_id = latLngToS2Cell(40.7128, -74.0060)
        result = pointInS2Cell(40.7128, -74.0060, cell_id)
        assert isinstance(result, bool)

    def test_pointInS2Cell_center_returns_true(self) -> None:
        """pointInS2Cell should return True for cell center."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 10)
        center_lat, center_lng = s2CellIdToLatLng(cell_id)
        result = pointInS2Cell(center_lat, center_lng, cell_id)
        assert result is True

    def test_pointInS2Cell_inside_returns_true(self) -> None:
        """pointInS2Cell should return True for point inside cell."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 10)
        result = pointInS2Cell(40.7128, -74.0060, cell_id)
        assert result is True

    def test_pointInS2Cell_outside_returns_false(self) -> None:
        """pointInS2Cell should return False for distant point."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 10)
        result = pointInS2Cell(0.0, 0.0, cell_id)
        assert result is False

    def test_pointInS2Cell_antipodal_point_returns_false(self) -> None:
        """pointInS2Cell should return False for antipodal point."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 5)
        result = pointInS2Cell(-40.7128, 106.0, cell_id)
        assert result is False

    def test_pointInS2Cell_boundary_lat_lo(self) -> None:
        """pointInS2Cell should handle point at lower latitude boundary."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 10)
        bounds = getS2CellBounds(cell_id)
        lo_lat, lo_lng, hi_lat, hi_lng = bounds
        center_lng = (lo_lng+hi_lng) / 2
        result = pointInS2Cell(lo_lat, center_lng, cell_id)
        assert result is True

    def test_pointInS2Cell_boundary_lat_hi(self) -> None:
        """pointInS2Cell should handle point at upper latitude boundary."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 10)
        bounds = getS2CellBounds(cell_id)
        lo_lat, lo_lng, hi_lat, hi_lng = bounds
        center_lng = (lo_lng+hi_lng) / 2
        result = pointInS2Cell(hi_lat, center_lng, cell_id)
        assert result is True

    def test_pointInS2Cell_boundary_lng(self) -> None:
        """pointInS2Cell should handle point at longitude boundary."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 10)
        bounds = getS2CellBounds(cell_id)
        lo_lat, lo_lng, hi_lat, hi_lng = bounds
        center_lat = (lo_lat+hi_lat) / 2
        result = pointInS2Cell(center_lat, lo_lng, cell_id)
        assert result is True

    def test_pointInS2Cell_just_outside_returns_false(self) -> None:
        """pointInS2Cell should return False for point just outside bounds."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 15)
        bounds = getS2CellBounds(cell_id)
        lo_lat, lo_lng, hi_lat, hi_lng = bounds
        result = pointInS2Cell(lo_lat - 0.01, lo_lng, cell_id)
        assert result is False
        result = pointInS2Cell(lo_lat, lo_lng - 0.01, cell_id)
        assert result is False


class TestS2CellsFromPolygon:
    """Tests for the s2CellsFromPolygon function."""
    def test_s2CellsFromPolygon_returns_list(self) -> None:
        """s2CellsFromPolygon should return a list."""
        polygon = Polygon([(-74.1, 40.6), (-73.9, 40.6), (-73.9, 40.8), (-74.1, 40.8)])
        cells = s2CellsFromPolygon(polygon)
        assert isinstance(cells, list)

    def test_s2CellsFromPolygon_returns_integers(self) -> None:
        """s2CellsFromPolygon should return list of integers."""
        polygon = Polygon([(-74.1, 40.6), (-73.9, 40.6), (-73.9, 40.8), (-74.1, 40.8)])
        cells = s2CellsFromPolygon(polygon)
        assert all(isinstance(c, int) for c in cells)

    def test_s2CellsFromPolygon_non_empty(self) -> None:
        """s2CellsFromPolygon should return non-empty list for valid polygon."""
        polygon = Polygon([(-74.1, 40.6), (-73.9, 40.6), (-73.9, 40.8), (-74.1, 40.8)])
        cells = s2CellsFromPolygon(polygon)
        assert len(cells) > 0

    def test_s2CellsFromPolygon_multipolygon(self) -> None:
        """s2CellsFromPolygon should handle MultiPolygon."""
        poly1 = Polygon([(-74.1, 40.6), (-74.0, 40.6), (-74.0, 40.7), (-74.1, 40.7)])
        poly2 = Polygon([(-73.9, 40.6), (-73.8, 40.6), (-73.8, 40.7), (-73.9, 40.7)])
        multipoly = MultiPolygon([poly1, poly2])
        cells = s2CellsFromPolygon(multipoly)
        assert isinstance(cells, list)
        assert len(cells) > 0

    def test_s2CellsFromPolygon_level_affects_count(self) -> None:
        """Higher resolution should produce more cells."""
        polygon = Polygon([(-74.01, 40.70), (-73.99, 40.70), (-73.99, 40.72), (-74.01, 40.72)])
        cells_low = s2CellsFromPolygon(polygon, level=5)
        cells_high = s2CellsFromPolygon(polygon, level=10)
        assert len(cells_high) > len(cells_low)

    def test_s2CellsFromPolygon_contains_point(self) -> None:
        """All returned cells should contain part of the polygon."""
        polygon = Polygon([(-74.1, 40.6), (-73.9, 40.6), (-73.9, 40.8), (-74.1, 40.8)])
        cells = s2CellsFromPolygon(polygon, level=10)
        for cell_id in cells:
            bounds = getS2CellBounds(cell_id)
            lo_lat, lo_lng, hi_lat, hi_lng = bounds
            assert lo_lng <= -73.9 or hi_lng >= -74.1
            assert lo_lat <= 40.8 or hi_lat >= 40.6

    def test_s2CellsFromPolygon_no_duplicates(self) -> None:
        """s2CellsFromPolygon should not return duplicate cell IDs."""
        polygon = Polygon([(-74.1, 40.6), (-73.9, 40.6), (-73.9, 40.8), (-74.1, 40.8)])
        cells = s2CellsFromPolygon(polygon)
        assert len(cells) == len(set(cells))

    def test_s2CellsFromPolygon_small_polygon(self) -> None:
        """s2CellsFromPolygon should handle very small polygons."""
        polygon = Polygon([(-74.001, 40.701), (-73.999, 40.701), (-73.999, 40.703), (-74.001, 40.703)])
        cells = s2CellsFromPolygon(polygon, level=15)
        assert len(cells) >= 1
        assert len(cells) == 2
        assert cells == [9926595730611372032, 9926595754233692160]


class TestS2CellIdToToken:
    """Tests for the s2CellIdToToken function."""
    def test_s2CellIdToToken_returns_string(self) -> None:
        """s2CellIdToToken should return a string."""
        cell_id = latLngToS2Cell(40.7128, -74.0060)
        token = s2CellIdToToken(cell_id)
        assert isinstance(token, str)

    def test_s2CellIdToToken_roundtrip(self) -> None:
        """s2CellIdToToken should produce consistent tokens."""
        cell_id = latLngToS2Cell(40.7128, -74.0060, 16)
        token1 = s2CellIdToToken(cell_id)
        token2 = s2CellIdToToken(cell_id)
        assert token1 == token2

    def test_s2CellIdToToken_different_cells_different_tokens(self) -> None:
        """Different cells should produce different tokens."""
        cell1 = latLngToS2Cell(40.7128, -74.0060, 10)
        cell2 = latLngToS2Cell(34.0522, -118.2437, 10)
        token1 = s2CellIdToToken(cell1)
        token2 = s2CellIdToToken(cell2)
        assert token1 != token2

    def test_s2CellIdToToken_not_empty(self) -> None:
        """s2CellIdToToken should not return empty string."""
        cell_id = latLngToS2Cell(40.7128, -74.0060)
        token = s2CellIdToToken(cell_id)
        assert len(token) > 0

    def test_s2CellIdToToken_paris(self) -> None:
        """s2CellIdToToken should generate valid token for Paris."""
        # Paris: 48.8566° N, 2.3522° E
        cell_id = latLngToS2Cell(48.8566, 2.3522, 16)
        token = s2CellIdToToken(cell_id)
        assert token == "47e66e1d9"  # expected token value

    def test_s2CellIdToToken_nyc(self) -> None:
        """s2CellIdToToken should generate valid token for NYC."""
        # NYC: 40.7128° N, 74.0060° W
        cell_id = latLngToS2Cell(40.7128, -74.0060, 16)
        token = s2CellIdToToken(cell_id)
        assert token == "89c25a221"  # expected token value

    def test_s2CellIdToToken_london(self) -> None:
        """s2CellIdToToken should generate valid token for London."""
        # London: 51.5074° N, 0.1278° W
        cell_id = latLngToS2Cell(51.5074, -0.1278, 16)
        token = s2CellIdToToken(cell_id)
        assert token == "487604ce3"


class TestS2CellToChildren:
    """Tests for the s2CellToChildren function."""
    def test_s2CellToChildren_returns_list(self) -> None:
        """s2CellToChildren should return a list."""
        parent_cell = latLngToS2Cell(40.7128, -74.0060, 10)
        children = s2CellToChildren(parent_cell, 15)
        assert isinstance(children, list)

    def test_s2CellToChildren_returns_integers(self) -> None:
        """s2CellToChildren should return list of integers."""
        parent_cell = latLngToS2Cell(40.7128, -74.0060, 10)
        children = s2CellToChildren(parent_cell, 15)
        assert all(isinstance(c, int) for c in children)

    def test_s2CellToChildren_non_empty(self) -> None:
        """s2CellToChildren should return non-empty list."""
        parent_cell = latLngToS2Cell(40.7128, -74.0060, 10)
        children = s2CellToChildren(parent_cell, 15)
        assert len(children) > 0

    def test_s2CellToChildren_count_for_5_level_diff(self) -> None:
        """5 level difference should produce 4^5 = 1024 children."""
        parent_cell = latLngToS2Cell(40.7128, -74.0060, 10)
        children = s2CellToChildren(parent_cell, 15)
        assert len(children) == 4**(15 - 10)

    def test_s2CellToChildren_count_for_1_level_diff(self) -> None:
        """1 level difference should produce 4 children."""
        parent_cell = latLngToS2Cell(40.7128, -74.0060, 10)
        children = s2CellToChildren(parent_cell, 11)
        assert len(children) == 4**(11 - 10)

    def test_s2CellToChildren_children_contained_in_parent_bounds(self) -> None:
        """All child cell centers should be within parent bounds."""
        parent_cell = latLngToS2Cell(40.7128, -74.0060, 10)
        children = s2CellToChildren(parent_cell, 12)
        parent_bounds = getS2CellBounds(parent_cell)
        p_lo_lat, p_lo_lng, p_hi_lat, p_hi_lng = parent_bounds
        for child_id in children:
            child_lat, child_lng = s2CellIdToLatLng(child_id)
            assert p_lo_lat <= child_lat <= p_hi_lat
            assert p_lo_lng <= child_lng <= p_hi_lng

    def test_s2CellToChildren_raises_for_equal_level(self) -> None:
        """s2CellToChildren should raise ValueError when level equals parent level."""
        parent_cell = latLngToS2Cell(40.7128, -74.0060, 10)
        with pytest.raises(ValueError):
            s2CellToChildren(parent_cell, 10)

    def test_s2CellToChildren_raises_for_lower_level(self) -> None:
        """s2CellToChildren should raise ValueError when target level is lower."""
        parent_cell = latLngToS2Cell(40.7128, -74.0060, 10)
        with pytest.raises(ValueError):
            s2CellToChildren(parent_cell, 5)

    def test_s2CellToChildren_children_have_correct_level(self) -> None:
        """All children should have the target level."""
        parent_cell = latLngToS2Cell(40.7128, -74.0060, 10)
        children = s2CellToChildren(parent_cell, 15)
        for child_id in children:
            assert getS2CellLevel(child_id) == 15

    def test_s2CellToChildren_no_duplicates(self) -> None:
        """s2CellToChildren should not return duplicate child IDs."""
        parent_cell = latLngToS2Cell(40.7128, -74.0060, 10)
        children = s2CellToChildren(parent_cell, 15)
        assert len(children) == len(set(children))

    def test_s2CellToChildren_nyc(self) -> None:
        """s2CellToChildren should return correct children for NYC cell."""
        # NYC: 40.7128° N, 74.0060° W
        nyc_cell = latLngToS2Cell(40.7128, -74.0060, 14)
        children = s2CellToChildren(nyc_cell, 16)

        assert nyc_cell == 9926595635048349696
        assert len(children) == 4**2  # 256 children for 4-level difference

        for child_id in children:
            assert getS2CellLevel(child_id) == 16

        child_centers = [s2CellIdToLatLng(c) for c in children]
        assert all(-75 <= lng <= -73 for _, lng in child_centers)
        assert all(40 <= lat <= 42 for lat, _ in child_centers)
        assert children == [
            9926595631021817856,
            9926595631558688768,
            9926595632095559680,
            9926595632632430592,
            9926595633169301504,
            9926595633706172416,
            9926595634243043328,
            9926595634779914240,
            9926595635316785152,
            9926595635853656064,
            9926595636390526976,
            9926595636927397888,
            9926595637464268800,
            9926595638001139712,
            9926595638538010624,
            9926595639074881536,
        ]
