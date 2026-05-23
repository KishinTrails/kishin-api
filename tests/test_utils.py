"""Comprehensive tests for S2 geometry utilities using hexadecimal tokens."""

import math
import pytest
from shapely.geometry import Polygon, MultiPolygon

from kishin_trails.utils import (
    EARTH_RADIUS,
    sanitizeValue,
    latLngToS2Cell,
    s2CellIdToLatLng,
    getS2CellLevel,
    s2CellToParent,
    getS2CellBounds,
    getS2CellCenter,
    getS2EdgeLength,
    pointInS2Cell,
    s2CellsFromPolygon,
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
        """latLngToS2Cell should return hex token at level 16 by default."""
        token = latLngToS2Cell(40.7128, -74.0060)
        assert isinstance(token, str)
        assert token == "89c25a221"
        assert getS2CellLevel(token) == 16

    def test_latLngToS2Cell_level_0(self) -> None:
        """latLngToS2Cell should return level 0 cell token."""
        token = latLngToS2Cell(40.7128, -74.0060, 0)
        assert token == "9"
        assert getS2CellLevel(token) == 0

    def test_latLngToS2Cell_level_30(self) -> None:
        """latLngToS2Cell should return level 30 cell token."""
        token = latLngToS2Cell(40.7128, -74.0060, 30)
        assert token == "89c25a220cf80969"
        assert getS2CellLevel(token) == 30

    def test_latLngToS2Cell_equator(self) -> None:
        """latLngToS2Cell should handle equator coordinates."""
        token = latLngToS2Cell(0.0, 0.0, 10)
        assert token == "100001"
        lat, lng = s2CellIdToLatLng(token)
        assert -1 <= lat <= 1
        assert -1 <= lng <= 1

    def test_latLngToS2Cell_north_pole(self) -> None:
        """latLngToS2Cell should handle north pole coordinates."""
        token = latLngToS2Cell(89.0, 0.0, 5)
        assert token == "4ffc"
        lat, lng = s2CellIdToLatLng(token)
        assert 88 <= lat <= 90
        assert lng == -45

    def test_latLngToS2Cell_south_pole(self) -> None:
        """latLngToS2Cell should handle south pole coordinates."""
        token = latLngToS2Cell(-89.0, 0.0, 5)
        assert token == "b004"
        lat, lng = s2CellIdToLatLng(token)
        assert -90 <= lat <= 88
        assert lng == 45

    def test_latLngToS2Cell_different_locations_different_cells(self) -> None:
        """latLngToS2Cell should return different cells for different locations."""
        cell_nyc = latLngToS2Cell(40.7128, -74.0060, 10)
        cell_la = latLngToS2Cell(34.0522, -118.2437, 10)
        assert cell_nyc != cell_la


class TestS2CellIdToLatLng:
    """Tests for the s2CellIdToLatLng function."""
    def test_s2CellIdToLatLng_returns_tuple(self) -> None:
        """s2CellIdToLatLng should return a tuple of (lat, lng)."""
        token = latLngToS2Cell(40.7128, -74.0060)
        result = s2CellIdToLatLng(token)
        assert isinstance(result, tuple)

    def test_s2CellIdToLatLng_lat_in_range(self) -> None:
        """s2CellIdToLatLng should return latitude in [-90, 90]."""
        token = latLngToS2Cell(40.7128, -74.0060)
        lat, lng = s2CellIdToLatLng(token)
        assert -90 <= lat <= 90

    def test_s2CellIdToLatLng_lng_in_range(self) -> None:
        """s2CellIdToLatLng should return longitude in [-180, 180]."""
        token = latLngToS2Cell(40.7128, -74.0060)
        lat, lng = s2CellIdToLatLng(token)
        assert -180 <= lng <= 180

    def test_s2CellIdToLatLng_roundtrip_nyc(self) -> None:
        """s2CellIdToLatLng center should be close to original NYC coordinates."""
        original_lat, original_lng = 40.7128, -74.0060
        token = latLngToS2Cell(original_lat, original_lng, 10)
        lat, lng = s2CellIdToLatLng(token)
        assert abs(lat - original_lat) < 0.05
        assert abs(lng - original_lng) < 0.05

    def test_s2CellIdToLatLng_roundtrip_equator(self) -> None:
        """s2CellIdToLatLng center should be close to original equator coordinates."""
        original_lat, original_lng = 0.0, 0.0
        token = latLngToS2Cell(original_lat, original_lng, 10)
        lat, lng = s2CellIdToLatLng(token)
        assert abs(lat - original_lat) < 0.05
        assert abs(lng - original_lng) < 0.05


class TestGetS2CellLevel:
    """Tests for the getS2CellLevel function."""
    def test_getS2CellLevel_returns_int(self) -> None:
        """getS2CellLevel should return an integer."""
        token = latLngToS2Cell(40.7128, -74.0060, 16)
        level = getS2CellLevel(token)
        assert isinstance(level, int)

    def test_getS2CellLevel_in_range(self) -> None:
        """getS2CellLevel should return a level between 0 and 30."""
        token = latLngToS2Cell(40.7128, -74.0060)
        level = getS2CellLevel(token)
        assert 0 <= level <= 30

    def test_getS2CellLevel_matches_creation_level(self) -> None:
        """getS2CellLevel should match the level used to create the cell."""
        for level in [0, 5, 10, 15, 20, 25, 30]:
            token = latLngToS2Cell(40.7128, -74.0060, level)
            assert getS2CellLevel(token) == level

    def test_getS2CellLevel_parent_higher_than_child(self) -> None:
        """Parent cell level should be lower (coarser) than child level."""
        child_token = latLngToS2Cell(40.7128, -74.0060, 15)
        parent_token = s2CellToParent(child_token, 10)
        assert getS2CellLevel(parent_token) == 10
        assert getS2CellLevel(parent_token) < getS2CellLevel(child_token)


class TestS2CellToParent:
    """Tests for the s2CellToParent function."""
    def test_s2CellToParent_returns_token(self) -> None:
        """s2CellToParent should return a hex token string."""
        token = latLngToS2Cell(40.7128, -74.0060, 15)
        parent_token = s2CellToParent(token, 10)
        assert isinstance(parent_token, str)

    def test_s2CellToParent_level_decreases(self) -> None:
        """s2CellToParent should return cell at a lower (coarser) level."""
        child_token = latLngToS2Cell(40.7128, -74.0060, 15)
        parent_token = s2CellToParent(child_token, 10)
        assert getS2CellLevel(parent_token) == 10
        assert getS2CellLevel(parent_token) < getS2CellLevel(child_token)

    def test_s2CellToParent_grandparent(self) -> None:
        """s2CellToParent can return grandparent at multiple levels difference."""
        child_token = latLngToS2Cell(40.7128, -74.0060, 20)
        grandparent_token = s2CellToParent(child_token, 10)
        assert getS2CellLevel(grandparent_token) == 10

    def test_s2CellToParent_same_level_as_parent(self) -> None:
        """s2CellToParent should return same cell when parent level equals cell level."""
        token = latLngToS2Cell(40.7128, -74.0060, 10)
        parent = s2CellToParent(token, 10)
        assert parent == token

    def test_s2CellToParent_parent_contains_child(self) -> None:
        """Parent cell bounds should contain child cell center."""
        child_token = latLngToS2Cell(40.7128, -74.0060, 15)
        parent_token = s2CellToParent(child_token, 10)
        child_lat, child_lng = s2CellIdToLatLng(child_token)
        parent_bounds = getS2CellBounds(parent_token)
        lo_lat, lo_lng, hi_lat, hi_lng = parent_bounds
        assert lo_lat <= child_lat <= hi_lat
        assert lo_lng <= child_lng <= hi_lng

    def test_s2CellToParent_child_of_parent(self) -> None:
        """Child cell should be one of the parent's children."""
        parent_token = latLngToS2Cell(40.7128, -74.0060, 10)
        child_token = latLngToS2Cell(40.7128, -74.0060, 15)
        derived_parent = s2CellToParent(child_token, 10)
        assert derived_parent == parent_token

    def test_s2CellToParent_retrieved_parent_is_actual_parent(self) -> None:
        """Parent derived from child should have child in its children list."""
        child_token = latLngToS2Cell(40.7128, -74.0060, 15)
        parent_token = s2CellToParent(child_token, 10)
        children = s2CellToChildren(parent_token, 15)
        assert child_token in children

    def test_s2CellToParent_unrelated_cells_not_parent(self) -> None:
        """Unrelated cells should not have parent-child relationship."""
        nyc_token = latLngToS2Cell(40.7128, -74.0060, 11)
        la_token = latLngToS2Cell(34.0522, -118.2437, 10)
        assert nyc_token not in s2CellToChildren(la_token, 11)


class TestGetS2CellBounds:
    """Tests for the getS2CellBounds function."""
    def test_getS2CellBounds_returns_tuple(self) -> None:
        """getS2CellBounds should return a tuple of 4 floats."""
        token = latLngToS2Cell(40.7128, -74.0060)
        bounds = getS2CellBounds(token)
        assert isinstance(bounds, tuple)
        assert len(bounds) == 4

    def test_getS2CellBounds_contains_center(self) -> None:
        """The cell center should be within the cell bounds."""
        token = latLngToS2Cell(40.7128, -74.0060, 10)
        bounds = getS2CellBounds(token)
        center_lat, center_lng = s2CellIdToLatLng(token)
        lo_lat, lo_lng, hi_lat, hi_lng = bounds
        assert lo_lat <= center_lat <= hi_lat
        assert lo_lng <= center_lng <= hi_lng

    def test_getS2CellBounds_lo_le_hi_lat(self) -> None:
        """lo_lat should be less than or equal to hi_lat."""
        token = latLngToS2Cell(40.7128, -74.0060)
        bounds = getS2CellBounds(token)
        lo_lat, lo_lng, hi_lat, hi_lng = bounds
        assert lo_lat <= hi_lat

    def test_getS2CellBounds_lo_le_hi_lng(self) -> None:
        """lo_lng should be less than or equal to hi_lng."""
        token = latLngToS2Cell(40.7128, -74.0060)
        bounds = getS2CellBounds(token)
        lo_lat, lo_lng, hi_lat, hi_lng = bounds
        assert lo_lng <= hi_lng

    def test_getS2CellBounds_lat_in_range(self) -> None:
        """Bounds latitude values should be in valid range [-90, 90]."""
        token = latLngToS2Cell(40.7128, -74.0060)
        lo_lat, lo_lng, hi_lat, hi_lng = getS2CellBounds(token)
        assert -90 <= lo_lat <= 90
        assert -90 <= hi_lat <= 90

    def test_getS2CellBounds_lng_in_range(self) -> None:
        """Bounds longitude values should be in valid range [-180, 180]."""
        token = latLngToS2Cell(40.7128, -74.0060)
        lo_lat, lo_lng, hi_lat, hi_lng = getS2CellBounds(token)
        assert -180 <= lo_lng <= 180
        assert -180 <= hi_lng <= 180

    def test_getS2CellBounds_higher_res_smaller_area(self) -> None:
        """Higher resolution cells should have smaller bounds (area)."""
        token_low = latLngToS2Cell(40.7128, -74.0060, 5)
        token_high = latLngToS2Cell(40.7128, -74.0060, 15)
        bounds_low = getS2CellBounds(token_low)
        bounds_high = getS2CellBounds(token_high)
        area_low = (bounds_low[2] - bounds_low[0]) * (bounds_low[3] - bounds_low[1])
        area_high = (bounds_high[2] - bounds_high[0]) * (bounds_high[3] - bounds_high[1])
        assert area_high < area_low

    def test_getS2CellBounds_spans_reasonable_ratio_to_edge(self) -> None:
        """Bounds spans should be 1-2x the edge length (cell inscribed in rect)."""
        token = latLngToS2Cell(40.7128, -74.0060, 10)
        bounds = getS2CellBounds(token)

        lat_span_m = (bounds[2] - bounds[0]) * math.pi / 180 * EARTH_RADIUS
        lng_span_m = (bounds[3] - bounds[1]) * math.pi / 180 * EARTH_RADIUS

        edge_length = getS2EdgeLength(token)

        assert 1.0 <= lat_span_m / edge_length <= 1.05
        assert 1.0 <= lng_span_m / edge_length <= 1.05


class TestGetS2CellCenter:
    """Tests for the getS2CellCenter function."""
    def test_getS2CellCenter_returns_tuple(self) -> None:
        """getS2CellCenter should return a tuple of (lat, lng)."""
        token = latLngToS2Cell(40.7128, -74.0060)
        center = getS2CellCenter(token)
        assert isinstance(center, tuple)
        assert len(center) == 2

    def test_getS2CellCenter_equals_midpoint(self) -> None:
        """getS2CellCenter should equal the midpoint of bounds."""
        token = latLngToS2Cell(40.7128, -74.0060, 10)
        center = getS2CellCenter(token)
        bounds = getS2CellBounds(token)
        expected_lat = (bounds[0] + bounds[2]) / 2
        expected_lng = (bounds[1] + bounds[3]) / 2
        assert abs(center[0] - expected_lat) < 0.0001
        assert abs(center[1] - expected_lng) < 0.0001

    def test_getS2CellCenter_within_bounds(self) -> None:
        """The center should be within the cell bounds."""
        token = latLngToS2Cell(40.7128, -74.0060, 10)
        center_lat, center_lng = getS2CellCenter(token)
        bounds = getS2CellBounds(token)
        lo_lat, lo_lng, hi_lat, hi_lng = bounds
        assert lo_lat <= center_lat <= hi_lat
        assert lo_lng <= center_lng <= hi_lng

    def test_getS2CellCenter_close_to_creation_point(self) -> None:
        """Center should be close to the coordinates used to create the cell."""
        original_lat, original_lng = 40.7128, -74.0060
        token = latLngToS2Cell(original_lat, original_lng, 10)
        center_lat, center_lng = getS2CellCenter(token)
        assert abs(center_lat - original_lat) < 0.05
        assert abs(center_lng - original_lng) < 0.05

    def test_getS2CellCenter_lat_in_range(self) -> None:
        """Center latitude should be in valid range [-90, 90]."""
        token = latLngToS2Cell(40.7128, -74.0060)
        center_lat, center_lng = getS2CellCenter(token)
        assert -90 <= center_lat <= 90

    def test_getS2CellCenter_lng_in_range(self) -> None:
        """Center longitude should be in valid range [-180, 180]."""
        token = latLngToS2Cell(40.7128, -74.0060)
        center_lat, center_lng = getS2CellCenter(token)
        assert -180 <= center_lng <= 180


class TestGetS2EdgeLength:
    """Tests for the getS2EdgeLength function."""
    def test_getS2EdgeLength_returns_float(self) -> None:
        """getS2EdgeLength should return a float."""
        token = latLngToS2Cell(40.7128, -74.0060)
        edge_length = getS2EdgeLength(token)
        assert isinstance(edge_length, float)

    def test_getS2EdgeLength_positive(self) -> None:
        """getS2EdgeLength should return a positive value."""
        token = latLngToS2Cell(40.7128, -74.0060)
        edge_length = getS2EdgeLength(token)
        assert edge_length > 0

    def test_getS2EdgeLength_decreases_with_level(self) -> None:
        """Higher resolution cells should have smaller edge lengths."""
        token_low = latLngToS2Cell(40.7128, -74.0060, 5)
        token_mid = latLngToS2Cell(40.7128, -74.0060, 10)
        token_high = latLngToS2Cell(40.7128, -74.0060, 15)
        edge_low = getS2EdgeLength(token_low)
        edge_mid = getS2EdgeLength(token_mid)
        edge_high = getS2EdgeLength(token_high)
        assert edge_mid < edge_low
        assert edge_high < edge_mid

    def test_getS2EdgeLength_level_1_very_large(self) -> None:
        """Level 1 cells should have very large edge lengths (earth-scale)."""
        token = latLngToS2Cell(40.7128, -74.0060, 1)
        edge_length = getS2EdgeLength(token)
        assert 3921000 <= edge_length <= 5004000

    def test_getS2EdgeLength_level_30_very_small(self) -> None:
        """Level 30 cells should have very small edge lengths."""
        token = latLngToS2Cell(40.7128, -74.0060, 30)
        edge_length = getS2EdgeLength(token)
        assert 0 <= edge_length <= 0.01

    def test_getS2EdgeLength_reasonable_for_level_16(self) -> None:
        """Level 16 cells should have edge lengths around 100-165 m."""
        token = latLngToS2Cell(40.7128, -74.0060, 16)
        edge_length = getS2EdgeLength(token)
        assert 100 < edge_length <= 165


class TestPointInS2Cell:
    """Tests for the pointInS2Cell function."""
    def test_pointInS2Cell_returns_bool(self) -> None:
        """pointInS2Cell should return a boolean."""
        token = latLngToS2Cell(40.7128, -74.0060)
        result = pointInS2Cell(token, 40.7128, -74.0060)
        assert isinstance(result, bool)

    def test_pointInS2Cell_center_returns_true(self) -> None:
        """pointInS2Cell should return True for cell center."""
        token = latLngToS2Cell(40.7128, -74.0060, 10)
        center_lat, center_lng = s2CellIdToLatLng(token)
        result = pointInS2Cell(token, center_lat, center_lng)
        assert result is True

    def test_pointInS2Cell_inside_returns_true(self) -> None:
        """pointInS2Cell should return True for point inside cell."""
        token = latLngToS2Cell(40.7128, -74.0060, 10)
        result = pointInS2Cell(token, 40.7128, -74.0060)
        assert result is True

    def test_pointInS2Cell_outside_returns_false(self) -> None:
        """pointInS2Cell should return False for distant point."""
        token = latLngToS2Cell(40.7128, -74.0060, 10)
        result = pointInS2Cell(token, 0.0, 0.0)
        assert result is False

    def test_pointInS2Cell_antipodal_point_returns_false(self) -> None:
        """pointInS2Cell should return False for antipodal point."""
        token = latLngToS2Cell(40.7128, -74.0060, 5)
        result = pointInS2Cell(token, -40.7128, 106.0)
        assert result is False

    def test_pointInS2Cell_boundary_lat_lo(self) -> None:
        """pointInS2Cell should handle point at lower latitude boundary."""
        token = latLngToS2Cell(40.7128, -74.0060, 10)
        bounds = getS2CellBounds(token)
        lo_lat, lo_lng, hi_lat, hi_lng = bounds
        center_lng = (lo_lng+hi_lng) / 2
        result = pointInS2Cell(token, lo_lat, center_lng)
        assert result is True

    def test_pointInS2Cell_boundary_lat_hi(self) -> None:
        """pointInS2Cell should handle point at upper latitude boundary."""
        token = latLngToS2Cell(40.7128, -74.0060, 10)
        bounds = getS2CellBounds(token)
        lo_lat, lo_lng, hi_lat, hi_lng = bounds
        center_lng = (lo_lng+hi_lng) / 2
        result = pointInS2Cell(token, hi_lat, center_lng)
        assert result is True

    def test_pointInS2Cell_boundary_lng(self) -> None:
        """pointInS2Cell should handle point at longitude boundary."""
        token = latLngToS2Cell(40.7128, -74.0060, 10)
        bounds = getS2CellBounds(token)
        lo_lat, lo_lng, hi_lat, hi_lng = bounds
        center_lat = (lo_lat+hi_lat) / 2
        result = pointInS2Cell(token, center_lat, lo_lng)
        assert result is True

    def test_pointInS2Cell_just_outside_returns_false(self) -> None:
        """pointInS2Cell should return False for point just outside bounds."""
        token = latLngToS2Cell(40.7128, -74.0060, 15)
        bounds = getS2CellBounds(token)
        lo_lat, lo_lng, hi_lat, hi_lng = bounds
        result = pointInS2Cell(token, lo_lat - 0.01, lo_lng)
        assert result is False
        result = pointInS2Cell(token, lo_lat, lo_lng - 0.01)
        assert result is False


class TestS2CellsFromPolygon:
    """Tests for the s2CellsFromPolygon function."""
    def test_s2CellsFromPolygon_returns_list(self) -> None:
        """s2CellsFromPolygon should return a list."""
        polygon = Polygon([(-74.1, 40.6), (-73.9, 40.6), (-73.9, 40.8), (-74.1, 40.8)])
        cells = s2CellsFromPolygon(polygon)
        assert isinstance(cells, list)

    def test_s2CellsFromPolygon_returns_tokens(self) -> None:
        """s2CellsFromPolygon should return list of hex tokens."""
        polygon = Polygon([(-74.1, 40.6), (-73.9, 40.6), (-73.9, 40.8), (-74.1, 40.8)])
        cells = s2CellsFromPolygon(polygon)
        assert all(isinstance(c, str) for c in cells)

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
        for token in cells:
            bounds = getS2CellBounds(token)
            lo_lat, lo_lng, hi_lat, hi_lng = bounds
            assert lo_lng <= -73.9 or hi_lng >= -74.1
            assert lo_lat <= 40.8 or hi_lat >= 40.6

    def test_s2CellsFromPolygon_no_duplicates(self) -> None:
        """s2CellsFromPolygon should not return duplicate cell tokens."""
        polygon = Polygon([(-74.1, 40.6), (-73.9, 40.6), (-73.9, 40.8), (-74.1, 40.8)])
        cells = s2CellsFromPolygon(polygon)
        assert len(cells) == len(set(cells))

    def test_s2CellsFromPolygon_small_polygon(self) -> None:
        """s2CellsFromPolygon should handle very small polygons."""
        polygon = Polygon(
            [
                (40.71399069477008,
                 -74.00627952379683),
                (40.71200910820379,
                 -74.00790906294003),
                (40.71172470378049,
                 -74.00766630869757),
                (40.712312443321565,
                 -74.00527003756989),
                (40.713127469765844,
                 -74.00426056204401),
            ]
        )
        expected_results = {
            13: [
                '89c25a1c',
                '89c25a24',
            ],
            14: [
                '89c25a19',
                '89c25a21',
                '89c25a23',
            ],
            15: [
                '89c25a18c',
                '89c25a21c',
                '89c25a224',
            ],
            16: [
                '89c25a189',
                '89c25a18b',
                '89c25a21f',
                '89c25a221',
                '89c25a223',
                '89c25a225',
                '89c25a227',
            ],
            17:
                [
                    '89c25a1884',
                    '89c25a188c',
                    '89c25a1894',
                    '89c25a189c',
                    '89c25a18a4',
                    '89c25a18ac',
                    '89c25a21fc',
                    '89c25a2204',
                    '89c25a220c',
                    '89c25a2214',
                    '89c25a221c',
                    '89c25a2224',
                    '89c25a222c',
                    '89c25a223c',
                    '89c25a2244',
                    '89c25a226c',
                    '89c25a2274',
                    '89c25a227c',
                ],
            18:
                [
                    '89c25a1883',
                    '89c25a1885',
                    '89c25a1887',
                    '89c25a1889',
                    '89c25a188b',
                    '89c25a188d',
                    '89c25a188f',
                    '89c25a1891',
                    '89c25a1893',
                    '89c25a1897',
                    '89c25a1899',
                    '89c25a189b',
                    '89c25a189d',
                    '89c25a189f',
                    '89c25a18a1',
                    '89c25a18a3',
                    '89c25a18a5',
                    '89c25a18a7',
                    '89c25a18a9',
                    '89c25a18ab',
                    '89c25a21f9',
                    '89c25a21ff',
                    '89c25a2201',
                    '89c25a2203',
                    '89c25a2205',
                    '89c25a2207',
                    '89c25a2209',
                    '89c25a220b',
                    '89c25a220d',
                    '89c25a220f',
                    '89c25a2211',
                    '89c25a2213',
                    '89c25a2215',
                    '89c25a2217',
                    '89c25a2219',
                    '89c25a221b',
                    '89c25a221d',
                    '89c25a221f',
                    '89c25a2221',
                    '89c25a2223',
                    '89c25a2225',
                    '89c25a222f',
                    '89c25a223b',
                    '89c25a223d',
                    '89c25a223f',
                    '89c25a2241',
                    '89c25a226b',
                    '89c25a226d',
                    '89c25a226f',
                    '89c25a2271',
                    '89c25a2273',
                    '89c25a2275',
                    '89c25a2277',
                    '89c25a2279'
                ],
        }
        for level in range(13, 19):
            cells = s2CellsFromPolygon(polygon, level=level)
            assert len(cells) == len(expected_results[level])
            assert sorted(cells) == sorted(expected_results[level])


class TestInvalidS2Cells:
    """Tests for invalid S2 cell handling."""
    def test_s2CellIdToLatLng_raises_for_invalid_cell(self) -> None:
        """s2CellIdToLatLng should raise ValueError for invalid cell token."""
        with pytest.raises(ValueError, match="Invalid S2 cell token"):
            s2CellIdToLatLng("not_a_valid_s2_cell")

    def test_getS2CellLevel_raises_for_invalid_cell(self) -> None:
        """getS2CellLevel should raise ValueError for invalid cell token."""
        with pytest.raises(ValueError, match="Invalid S2 cell token"):
            getS2CellLevel("invalid_cell_token")

    def test_s2CellToParent_raises_for_invalid_cell(self) -> None:
        """s2CellToParent should raise ValueError for invalid cell token."""
        with pytest.raises(ValueError, match="Invalid S2 cell token"):
            s2CellToParent("totally_invalid", 10)

    def test_getS2CellBounds_raises_for_invalid_cell(self) -> None:
        """getS2CellBounds should raise ValueError for invalid cell token."""
        with pytest.raises(ValueError, match="Invalid S2 cell token"):
            getS2CellBounds("this_is_not_valid")

    def test_getS2CellCenter_raises_for_invalid_cell(self) -> None:
        """getS2CellCenter should raise ValueError for invalid cell token."""
        with pytest.raises(ValueError, match="Invalid S2 cell token"):
            getS2CellCenter("bad_cell_id")

    def test_getS2EdgeLength_raises_for_invalid_cell(self) -> None:
        """getS2EdgeLength should raise ValueError for invalid cell token."""
        with pytest.raises(ValueError, match="Invalid S2 cell token"):
            getS2EdgeLength("invalid")

    def test_pointInS2Cell_raises_for_invalid_cell(self) -> None:
        """pointInS2Cell should raise ValueError for invalid cell token."""
        with pytest.raises(ValueError, match="Invalid S2 cell token"):
            pointInS2Cell("nonsense_cell", 40.7128, -74.0060)

    def test_s2CellToChildren_raises_for_invalid_cell(self) -> None:
        """s2CellToChildren should raise ValueError for invalid cell token."""
        with pytest.raises(ValueError, match="Invalid S2 cell token"):
            s2CellToChildren("xyz123", 15)

    def test_0x_prefix_stripped_correctly(self) -> None:
        """0x prefix should be stripped and cell should be processed correctly."""
        valid_token = "89c25a221"
        lat, lng = s2CellIdToLatLng(valid_token)
        lat_with_prefix, lng_with_prefix = s2CellIdToLatLng(f"0x{valid_token}")
        assert (lat, lng) == (lat_with_prefix, lng_with_prefix)


class TestS2CellToChildren:
    """Tests for the s2CellToChildren function."""
    def test_s2CellToChildren_returns_list(self) -> None:
        """s2CellToChildren should return a list."""
        parent_token = latLngToS2Cell(40.7128, -74.0060, 10)
        children = s2CellToChildren(parent_token, 15)
        assert isinstance(children, list)

    def test_s2CellToChildren_returns_tokens(self) -> None:
        """s2CellToChildren should return list of hex tokens."""
        parent_token = latLngToS2Cell(40.7128, -74.0060, 10)
        children = s2CellToChildren(parent_token, 15)
        assert all(isinstance(c, str) for c in children)

    def test_s2CellToChildren_non_empty(self) -> None:
        """s2CellToChildren should return non-empty list."""
        parent_token = latLngToS2Cell(40.7128, -74.0060, 10)
        children = s2CellToChildren(parent_token, 15)
        assert len(children) > 0

    def test_s2CellToChildren_count_for_5_level_diff(self) -> None:
        """5 level difference should produce 4^5 = 1024 children."""
        parent_token = latLngToS2Cell(40.7128, -74.0060, 10)
        children = s2CellToChildren(parent_token, 15)
        assert len(children) == 4**(15 - 10)

    def test_s2CellToChildren_count_for_1_level_diff(self) -> None:
        """1 level difference should produce 4 children."""
        parent_token = latLngToS2Cell(40.7128, -74.0060, 10)
        children = s2CellToChildren(parent_token, 11)
        assert len(children) == 4**(11 - 10)

    def test_s2CellToChildren_children_contained_in_parent_bounds(self) -> None:
        """All child cell centers should be within parent bounds."""
        parent_token = latLngToS2Cell(40.7128, -74.0060, 10)
        children = s2CellToChildren(parent_token, 12)
        parent_bounds = getS2CellBounds(parent_token)
        p_lo_lat, p_lo_lng, p_hi_lat, p_hi_lng = parent_bounds
        for child_token in children:
            child_lat, child_lng = s2CellIdToLatLng(child_token)
            assert p_lo_lat <= child_lat <= p_hi_lat
            assert p_lo_lng <= child_lng <= p_hi_lng

    def test_s2CellToChildren_raises_for_equal_level(self) -> None:
        """s2CellToChildren should raise ValueError when level equals parent level."""
        parent_token = latLngToS2Cell(40.7128, -74.0060, 10)
        with pytest.raises(ValueError):
            s2CellToChildren(parent_token, 10)

    def test_s2CellToChildren_raises_for_lower_level(self) -> None:
        """s2CellToChildren should raise ValueError when target level is lower."""
        parent_token = latLngToS2Cell(40.7128, -74.0060, 10)
        with pytest.raises(ValueError):
            s2CellToChildren(parent_token, 5)

    def test_s2CellToChildren_children_have_correct_level(self) -> None:
        """All children should have the target level."""
        parent_token = latLngToS2Cell(40.7128, -74.0060, 10)
        children = s2CellToChildren(parent_token, 15)
        for child_token in children:
            assert getS2CellLevel(child_token) == 15

    def test_s2CellToChildren_no_duplicates(self) -> None:
        """s2CellToChildren should not return duplicate child tokens."""
        parent_token = latLngToS2Cell(40.7128, -74.0060, 10)
        children = s2CellToChildren(parent_token, 15)
        assert len(children) == len(set(children))

    def test_s2CellToChildren_nyc(self) -> None:
        """s2CellToChildren should return correct children for NYC cell."""
        # NYC: 40.7128° N, 74.0060° W
        nyc_token = latLngToS2Cell(40.7128, -74.0060, 14)
        children = s2CellToChildren(nyc_token, 16)

        assert nyc_token == "89c25a23"
        assert len(children) == 4**2

        for child_token in children:
            assert getS2CellLevel(child_token) == 16

        child_centers = [s2CellIdToLatLng(c) for c in children]
        assert all(-75 <= lng <= -73 for _, lng in child_centers)
        assert all(40 <= lat <= 42 for lat, _ in child_centers)
        assert sorted(children) == sorted(
            [
                '89c25a221',
                '89c25a223',
                '89c25a225',
                '89c25a227',
                '89c25a229',
                '89c25a22b',
                '89c25a22d',
                '89c25a22f',
                '89c25a231',
                '89c25a233',
                '89c25a235',
                '89c25a237',
                '89c25a239',
                '89c25a23b',
                '89c25a23d',
                '89c25a23f',
            ]
        )
