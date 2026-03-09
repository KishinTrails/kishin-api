"""Tests for the POI module."""

import json
import math
from typing import Any

import pytest
from shapely.geometry import Point

from kishin_trails.poi import IndustrialPoI, NaturalPoI, PeakPoI, PoI, transform_waypoint_to_poi


class TestPoI:
    """Tests for the PoI base class."""
    def test_poi_initializes_with_id_and_name(self) -> None:
        """PoI should initialize with provided id and name."""
        expected_id = 123
        expected_name = "Test POI"
        poi = PoI(id=expected_id, name=expected_name, geometry=None)
        assert poi.id == expected_id
        assert poi.name == expected_name

    def test_poi_default_name_when_none(self) -> None:
        """PoI should use default name when name is None."""
        expected_id = 456
        poi = PoI(id=expected_id, name=None, geometry=None)
        assert poi.id == expected_id
        assert poi.name == f"POI {expected_id}"

    def test_poi_to_dict_returns_correct_dict(self) -> None:
        """PoI.to_dict() should return a dict with correct attributes."""
        expected_id = 789
        expected_name = "Another POI"
        poi = PoI(id=expected_id, name=expected_name, geometry=None)
        result = poi.to_dict()
        assert isinstance(result, dict)
        assert result["id"] == expected_id
        assert result["name"] == expected_name

    def test_poi_to_dict_is_json_serializable(self) -> None:
        """PoI.to_dict() should produce JSON-serializable output."""
        expected_id = 111
        expected_name = "JSON POI"
        poi = PoI(id=expected_id, name=expected_name, geometry=None)
        result = poi.to_dict()
        json_str = json.dumps(result)
        assert json_str is not None
        parsed = json.loads(json_str)
        assert parsed["id"] == expected_id
        assert parsed["name"] == expected_name


class TestPoIGeometry:
    """Tests for the geometry parameter in PoI classes."""
    def test_poi_with_geometry_point(self) -> None:
        """PoI should store geometry when provided as Point."""
        expected_geometry = Point(2.0, 45.0)
        poi = PoI(id=1, name="Test", geometry=expected_geometry)
        assert poi.geometry == expected_geometry
        assert poi.geometry.x == 2.0
        assert poi.geometry.y == 45.0

    def test_poi_with_geometry_none(self) -> None:
        """PoI should handle geometry=None."""
        poi = PoI(id=1, name="Test", geometry=None)
        assert poi.geometry is None

    def test_poi_to_dict_includes_geometry(self) -> None:
        """PoI.to_dict() should include geometry when present."""
        expected_geometry = Point(3.0, 46.0)
        poi = PoI(id=1, name="Test", geometry=expected_geometry)
        result = poi.to_dict()
        assert "geometry" in result
        assert result["geometry"] == expected_geometry

    def test_poi_to_dict_excludes_geometry_when_none(self) -> None:
        """PoI.to_dict() should handle geometry=None."""
        poi = PoI(id=1, name="Test", geometry=None)
        result = poi.to_dict()
        assert "geometry" in result
        assert result["geometry"] is None

    def test_peakpoi_with_geometry(self) -> None:
        """PeakPoI should store geometry when provided."""
        waypoint = {
            "id": 100,
            "tags": {
                "name": "Mont Blanc",
                "natural": "peak",
                "ele": "4808",
                "geometry": Point(2.0, 45.0),
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        assert isinstance(result, PeakPoI)
        assert result.geometry is not None
        assert result.geometry.x == 2.0
        assert result.geometry.y == 45.0

    def test_naturalpoi_with_geometry(self) -> None:
        """NaturalPoI should store geometry when provided."""
        waypoint = {
            "id": 101,
            "tags": {
                "name": "Central Park",
                "leisure": "park",
                "geometry": Point(3.0, 46.0),
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        assert isinstance(result, NaturalPoI)
        assert result.geometry is not None
        assert result.geometry.x == 3.0

    def test_industrialpoi_with_geometry(self) -> None:
        """IndustrialPoI should store geometry when provided."""
        waypoint = {
            "id": 102,
            "tags": {
                "name": "Factory",
                "landuse": "industrial",
                "geometry": Point(4.0, 47.0),
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        assert isinstance(result, IndustrialPoI)
        assert result.geometry is not None
        assert result.geometry.x == 4.0


class TestTransformWaypointToPoi:
    """Tests for the transform_waypoint_to_poi factory function."""
    def test_transform_waypoint_to_poi_returns_poi_instance(self) -> None:
        """transform_waypoint_to_poi should return a PoI instance."""
        waypoint = {
            "id": 1,
            "tags": {
                "name": "Test"
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        assert isinstance(result, PoI)
        assert result.id == waypoint["id"]
        assert result.name == waypoint["tags"]["name"]

    def test_transform_waypoint_to_poi_with_normal_name(self) -> None:
        """transform_waypoint_to_poi should preserve normal name."""
        waypoint = {
            "id": 123,
            "tags": {
                "name": "Mountain Peak"
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        assert result.id == waypoint["id"]
        assert result.name == waypoint["tags"]["name"]

    def test_transform_waypoint_to_poi_with_empty_tags(self) -> None:
        """transform_waypoint_to_poi should handle empty tags."""
        waypoint = {
            "id": 456,
            "tags": {}
        }
        result = transform_waypoint_to_poi(waypoint)
        assert isinstance(result, PoI)
        assert result.id == waypoint["id"]
        assert result.name == f"POI {waypoint['id']}"

    def test_transform_waypoint_to_poi_with_nan_name(self) -> None:
        """transform_waypoint_to_poi should handle NaN name."""
        waypoint = {
            "id": 789,
            "tags": {
                "name": float("nan")
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        assert isinstance(result, PoI)
        assert result.id == waypoint["id"]
        assert result.name == f"POI {waypoint['id']}"

    def test_transform_waypoint_to_poi_to_dict_is_json_serializable(self) -> None:
        """transform_waypoint_to_poi result should be JSON serializable."""
        waypoint = {
            "id": 111,
            "tags": {
                "name": "Test POI"
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        result_dict = result.to_dict()
        json_str = json.dumps(result_dict)
        assert json_str is not None
        parsed = json.loads(json_str)
        assert parsed["id"] == waypoint["id"]
        assert parsed["name"] == waypoint["tags"]["name"]


class TestTransformWaypointToPeakPoI:
    """Tests for the PeakPoi class."""
    def test_poi_is_peak(self) -> None:
        """PoI with peak characteristics should be categorized as a PeakPoI."""
        waypoint = {
            "id": 111,
            "tags": {
                "name": "Peak of Test",
                "natural": "peak",
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        assert isinstance(result, PeakPoI)
        assert isinstance(result, PoI)
        assert result.id == waypoint["id"]
        assert result.name == waypoint["tags"]["name"]

    def test_peakpoi_elevation_present(self) -> None:
        """PeakPoI should have elevation when ele tag is present and positive."""
        waypoint = {
            "id": 200,
            "tags": {
                "name": "Mont Blanc",
                "natural": "peak",
                "ele": "4808",
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        assert isinstance(result, PeakPoI)
        assert result.elevation == "4808"

    def test_peakpoi_elevation_absent(self) -> None:
        """PeakPoI should have elevation=None when ele tag is absent."""
        waypoint = {
            "id": 201,
            "tags": {
                "name": "Unnamed Peak",
                "natural": "peak",
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        assert isinstance(result, PeakPoI)
        assert result.elevation is None

    def test_peakpoi_elevation_zero(self) -> None:
        """PeakPoI should have elevation=None when ele is 0."""
        waypoint = {
            "id": 202,
            "tags": {
                "name": "Zero Elevation Peak",
                "natural": "peak",
                "ele": "0",
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        assert isinstance(result, PeakPoI)
        assert result.elevation is None

    def test_peakpoi_elevation_negative(self) -> None:
        """PeakPoI should have elevation=None when ele is negative."""
        waypoint = {
            "id": 203,
            "tags": {
                "name": "Negative Elevation Peak",
                "natural": "peak",
                "ele": "-100",
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        assert isinstance(result, PeakPoI)
        assert result.elevation is None


class TestTransformWaypointToNaturalPoI:
    """Tests for the NaturalPoI class."""
    def test_naturalpoi_from_leisure_park(self) -> None:
        """NaturalPoI should be returned for leisure=park."""
        waypoint = {
            "id": 300,
            "tags": {
                "name": "Central Park",
                "leisure": "park",
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        assert isinstance(result, NaturalPoI)
        assert isinstance(result, PoI)
        assert result.id == waypoint["id"]
        assert result.name == waypoint["tags"]["name"]

    def test_naturalpoi_from_landuse_forest(self) -> None:
        """NaturalPoI should be returned for landuse=forest."""
        waypoint = {
            "id": 301,
            "tags": {
                "name": "Black Forest",
                "landuse": "forest",
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        assert isinstance(result, NaturalPoI)

    def test_naturalpoi_from_landuse_recreation_ground(self) -> None:
        """NaturalPoI should be returned for landuse=recreation_ground."""
        waypoint = {
            "id": 302,
            "tags": {
                "name": "Recreation Area",
                "landuse": "recreation_ground",
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        assert isinstance(result, NaturalPoI)

    def test_naturalpoi_from_landuse_education(self) -> None:
        """NaturalPoI should be returned for landuse=education."""
        waypoint = {
            "id": 303,
            "tags": {
                "name": "School Grounds",
                "landuse": "education",
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        assert isinstance(result, NaturalPoI)

    def test_naturalpoi_without_name(self) -> None:
        """NaturalPoI should use default name when name is None."""
        waypoint = {
            "id": 304,
            "tags": {
                "leisure": "park",
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        assert isinstance(result, NaturalPoI)
        assert result.name == f"POI {waypoint['id']}"

    def test_naturalpoi_to_dict(self) -> None:
        """NaturalPoI.to_dict() should return correct dict."""
        waypoint = {
            "id": 305,
            "tags": {
                "name": "Test Park",
                "leisure": "park",
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        result_dict = result.to_dict()
        assert result_dict["id"] == 305
        assert result_dict["name"] == "Test Park"


class TestTransformWaypointToIndustrialPoI:
    """Tests for the IndustrialPoI class."""
    def test_industrialpoi_from_landuse_industrial(self) -> None:
        """IndustrialPoI should be returned for landuse=industrial."""
        waypoint = {
            "id": 400,
            "tags": {
                "name": "Industrial Zone",
                "landuse": "industrial",
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        assert isinstance(result, IndustrialPoI)
        assert isinstance(result, PoI)
        assert result.id == waypoint["id"]
        assert result.name == waypoint["tags"]["name"]

    def test_industrialpoi_without_name(self) -> None:
        """IndustrialPoI should use default name when name is None."""
        waypoint = {
            "id": 401,
            "tags": {
                "landuse": "industrial",
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        assert isinstance(result, IndustrialPoI)
        assert result.name == f"POI {waypoint['id']}"

    def test_industrialpoi_to_dict(self) -> None:
        """IndustrialPoI.to_dict() should return correct dict."""
        waypoint = {
            "id": 402,
            "tags": {
                "name": "Factory",
                "landuse": "industrial",
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        result_dict = result.to_dict()
        assert result_dict["id"] == 402
        assert result_dict["name"] == "Factory"


class TestPoiTypePriority:
    """Tests for POI type priority when multiple tags match."""
    def test_peak_takes_priority_over_natural(self) -> None:
        """PeakPoI should take priority over NaturalPoI."""
        waypoint = {
            "id": 500,
            "tags": {
                "name": "Mountain in Park",
                "natural": "peak",
                "leisure": "park",
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        assert isinstance(result, PeakPoI)
        assert not isinstance(result, NaturalPoI)

    def test_natural_takes_priority_over_industrial(self) -> None:
        """NaturalPoI should take priority over IndustrialPoI."""
        waypoint = {
            "id": 501,
            "tags": {
                "name": "Park near Factory",
                "leisure": "park",
                "landuse": "industrial",
            }
        }
        result = transform_waypoint_to_poi(waypoint)
        assert isinstance(result, NaturalPoI)
        assert not isinstance(result, IndustrialPoI)
