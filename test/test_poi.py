"""Tests for the POI module."""

import json
import math
from typing import Any

import pytest
from shapely.geometry import Point

from kishin_trails.poi import IndustrialPoI, NaturalPoI, PeakPoI, PoI, filterWaypointsForCache, transformWaypointToPoi


class TestPoI:
    """Tests for the PoI base class."""
    def test_poi_initializes_with_id_and_name(self) -> None:
        """PoI should initialize with provided id and name."""
        expectedOsmId = 123
        expected_name = "Test POI"
        poi = PoI(osmId=expectedOsmId, name=expected_name, geometry=None)
        assert poi.osmId == expectedOsmId
        assert poi.name == expected_name

    def test_poi_default_name_when_none(self) -> None:
        """PoI should not use default name when name is None."""
        expectedOsmId = 456
        poi = PoI(osmId=expectedOsmId, name=None, geometry=None)
        assert poi.osmId == expectedOsmId
        assert poi.name == None

    def test_poi_toDict_returns_correct_dict(self) -> None:
        """PoI.toDict() should return a dict with correct attributes."""
        expectedOsmId = 789
        expected_name = "Another POI"
        poi = PoI(osmId=expectedOsmId, name=expected_name, geometry=None)
        result = poi.toDict()
        assert isinstance(result, dict)
        assert result["osm_id"] == expectedOsmId
        assert result["name"] == expected_name

    def test_poi_toDict_is_json_serializable(self) -> None:
        """PoI.toDict() should produce JSON-serializable output."""
        expectedOsmId = 111
        expected_name = "JSON POI"
        poi = PoI(osmId=expectedOsmId, name=expected_name, geometry=None)
        result = poi.toDict()
        json_str = json.dumps(result)
        assert json_str is not None
        parsed = json.loads(json_str)
        assert parsed["osm_id"] == expectedOsmId
        assert parsed["name"] == expected_name


class TestPoIGeometry:
    """Tests for the geometry parameter in PoI classes."""
    def test_poi_with_geometry_point(self) -> None:
        """PoI should store geometry when provided as Point."""
        expected_geometry = Point(2.0, 45.0)
        poi = PoI(osmId=1, name="Test", geometry=expected_geometry)
        assert poi.geometry == expected_geometry
        assert poi.geometry is not None
        assert poi.geometry.x == 2.0
        assert poi.geometry.y == 45.0

    def test_poi_with_geometry_none(self) -> None:
        """PoI should handle geometry=None."""
        poi = PoI(osmId=1, name="Test", geometry=None)
        assert poi.geometry is None

    def test_poi_toDict_includes_geometry(self) -> None:
        """PoI.toDict() should include geometry when present."""
        expected_geometry = Point(3.0, 46.0)
        poi = PoI(osmId=1, name="Test", geometry=expected_geometry)
        result = poi.toDict()
        assert "lat" in result
        assert "lon" in result
        assert result["lat"] == expected_geometry.y
        assert result["lon"] == expected_geometry.x

    def test_poi_toDict_excludes_geometry_when_none(self) -> None:
        """PoI.toDict() should handle geometry=None."""
        poi = PoI(osmId=1, name="Test", geometry=None)
        result = poi.toDict()
        assert "geometry" not in result

    def test_peakpoi_with_geometry(self) -> None:
        """PeakPoI should store geometry when provided."""
        waypoint = {
            "id": 100,
            "tags": {
                "name": "Mont Blanc",
                "natural": "peak",
                "ele": "4808",
                "geometry": Point(2.0,
                                  45.0),
            }
        }
        result = transformWaypointToPoi(waypoint)
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
                "geometry": Point(3.0,
                                  46.0),
            }
        }
        result = transformWaypointToPoi(waypoint)
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
                "geometry": Point(4.0,
                                  47.0),
            }
        }
        result = transformWaypointToPoi(waypoint)
        assert isinstance(result, IndustrialPoI)
        assert result.geometry is not None
        assert result.geometry.x == 4.0


class TestTransformWaypointToPoi:
    """Tests for the transformWaypointToPoi factory function."""
    def test_transformWaypointToPoi_returns_poi_instance(self) -> None:
        """transformWaypointToPoi should return a PoI instance."""
        waypoint = {
            "id": 1,
            "tags": {
                "name": "Test"
            }
        }
        result = transformWaypointToPoi(waypoint)
        assert isinstance(result, PoI)
        assert result.osmId == waypoint["id"]
        assert result.name == waypoint["tags"]["name"]

    def test_transformWaypointToPoi_with_normal_name(self) -> None:
        """transformWaypointToPoi should preserve normal name."""
        waypoint = {
            "id": 123,
            "tags": {
                "name": "Mountain Peak"
            }
        }
        result = transformWaypointToPoi(waypoint)
        assert result.osmId == waypoint["id"]
        assert result.name == waypoint["tags"]["name"]

    def test_transformWaypointToPoi_with_empty_tags(self) -> None:
        """transformWaypointToPoi should handle empty tags."""
        waypoint = {
            "id": 456,
            "tags": {}
        }
        result = transformWaypointToPoi(waypoint)
        assert isinstance(result, PoI)
        assert result.osmId == waypoint["id"]
        assert result.name == None

    def test_transformWaypointToPoi_with_nan_name(self) -> None:
        """transformWaypointToPoi should handle NaN name."""
        waypoint = {
            "id": 789,
            "tags": {
                "name": float("nan")
            }
        }
        result = transformWaypointToPoi(waypoint)
        assert isinstance(result, PoI)
        assert result.osmId == waypoint["id"]
        assert result.name == None

    def test_transformWaypointToPoi_toDict_is_json_serializable(self) -> None:
        """transformWaypointToPoi result should be JSON serializable."""
        waypoint = {
            "id": 111,
            "tags": {
                "name": "Test POI"
            }
        }
        result = transformWaypointToPoi(waypoint)
        result_dict = result.toDict()
        json_str = json.dumps(result_dict)
        assert json_str is not None
        parsed = json.loads(json_str)
        assert parsed["osm_id"] == waypoint["id"]
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
        result = transformWaypointToPoi(waypoint)
        assert isinstance(result, PeakPoI)
        assert isinstance(result, PoI)
        assert result.osmId == waypoint["id"]
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
        result = transformWaypointToPoi(waypoint)
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
        result = transformWaypointToPoi(waypoint)
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
        result = transformWaypointToPoi(waypoint)
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
        result = transformWaypointToPoi(waypoint)
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
        result = transformWaypointToPoi(waypoint)
        assert isinstance(result, NaturalPoI)
        assert isinstance(result, PoI)
        assert result.osmId == waypoint["id"]
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
        result = transformWaypointToPoi(waypoint)
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
        result = transformWaypointToPoi(waypoint)
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
        result = transformWaypointToPoi(waypoint)
        assert isinstance(result, NaturalPoI)

    def test_naturalpoi_without_name(self) -> None:
        """NaturalPoI should use default name when name is None."""
        waypoint = {
            "id": 304,
            "tags": {
                "leisure": "park",
            }
        }
        result = transformWaypointToPoi(waypoint)
        assert isinstance(result, NaturalPoI)
        assert result.name == None

    def test_naturalpoi_toDict(self) -> None:
        """NaturalPoI.toDict() should return correct dict."""
        waypoint = {
            "id": 305,
            "tags": {
                "name": "Test Park",
                "leisure": "park",
            }
        }
        result = transformWaypointToPoi(waypoint)
        result_dict = result.toDict()
        assert result_dict["osm_id"] == 305
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
        result = transformWaypointToPoi(waypoint)
        assert isinstance(result, IndustrialPoI)
        assert isinstance(result, PoI)
        assert result.osmId == waypoint["id"]
        assert result.name == waypoint["tags"]["name"]

    def test_industrialpoi_without_name(self) -> None:
        """IndustrialPoI should use default name when name is None."""
        waypoint = {
            "id": 401,
            "tags": {
                "landuse": "industrial",
            }
        }
        result = transformWaypointToPoi(waypoint)
        assert isinstance(result, IndustrialPoI)
        assert result.name == None

    def test_industrialpoi_toDict(self) -> None:
        """IndustrialPoI.toDict() should return correct dict."""
        waypoint = {
            "id": 402,
            "tags": {
                "name": "Factory",
                "landuse": "industrial",
            }
        }
        result = transformWaypointToPoi(waypoint)
        result_dict = result.toDict()
        assert result_dict["osm_id"] == 402
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
        result = transformWaypointToPoi(waypoint)
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
        result = transformWaypointToPoi(waypoint)
        assert isinstance(result, NaturalPoI)
        assert not isinstance(result, IndustrialPoI)


class TestSelectBestPoi:
    """Tests for the filterWaypointsForCache function."""
    def test_filterWaypointsForCache_returns_peak_over_natural(self) -> None:
        """filterWaypointsForCache should return peak when both exist."""
        elements = [
            {
                "id": 100,
                "tags": {
                    "name": "Park",
                    "leisure": "park"
                }
            },
            {
                "id": 200,
                "tags": {
                    "name": "Peak",
                    "natural": "peak"
                }
            },
        ]
        result, tileType = filterWaypointsForCache(elements)
        assert tileType == "peak"
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "Peak"

    def test_filterWaypointsForCache_returns_natural_over_industrial(self) -> None:
        """filterWaypointsForCache should return natural when both exist."""
        elements = [
            {
                "id": 100,
                "tags": {
                    "name": "Factory",
                    "landuse": "industrial"
                }
            },
            {
                "id": 200,
                "tags": {
                    "name": "Park",
                    "leisure": "park"
                }
            },
        ]
        result, tileType = filterWaypointsForCache(elements)
        assert tileType == "natural"
        assert result == []

    def test_filterWaypointsForCache_returns_first_by_id_on_tie(self) -> None:
        """filterWaypointsForCache should return lowest ID when types match."""
        elements = [
            {
                "id": 200,
                "tags": {
                    "name": "Second Peak",
                    "natural": "peak"
                }
            },
            {
                "id": 100,
                "tags": {
                    "name": "First Peak",
                    "natural": "peak"
                }
            },
        ]
        result, tileType = filterWaypointsForCache(elements)
        assert tileType == "peak"
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "First Peak"

    def test_filterWaypointsForCache_returns_none_when_empty(self) -> None:
        """filterWaypointsForCache should return None for empty list."""
        result = filterWaypointsForCache([])
        assert result == ([], None)

    def test_filterWaypointsForCache_returns_none_when_no_match(self) -> None:
        """filterWaypointsForCache should return None when no matching POI type."""
        elements = [
            {
                "id": 100,
                "tags": {
                    "name": "Random POI"
                }
            },
        ]
        result = filterWaypointsForCache(elements)
        assert result == ([], None)


class TestGetPoiByCell:
    """E2E tests for the /poi/bycell endpoint."""

    @pytest.mark.asyncio
    async def test_bycell_returns_400_for_invalid_h3_cell(self, authenticated_client) -> None:
        """GET /poi/bycell should return 400 for invalid H3 cell."""
        response = await authenticated_client.get("/poi/bycell?h3Cell=invalid")
        assert response.status_code == 400
        assert "Invalid H3 cell" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_bycell_returns_404_for_uncached_cell(self, authenticated_client) -> None:
        """GET /poi/bycell should return 404 for valid but uncached cell."""
        response = await authenticated_client.get("/poi/bycell?h3Cell=8a1f96334daffff")
        assert response.status_code == 404
        assert "POI data not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_bycell_returns_200_for_cached_cell_with_poi(
        self, authenticated_client, cache_with_data
    ) -> None:
        """GET /poi/bycell should return 200 for cached cell with POI data."""
        cache_with_data("8a1f96334daffff", "peak", [{"osm_id": 1, "name": "Test Peak", "lat": 45.0, "lon": 3.0}])
        response = await authenticated_client.get("/poi/bycell?h3Cell=8a1f96334daffff")
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "peak"
        assert data["count"] == 1
        assert data["poi"]["name"] == "Test Peak"

    @pytest.mark.asyncio
    async def test_bycell_returns_404_for_cached_cell_no_poi(
        self, authenticated_client, cache_with_data
    ) -> None:
        """GET /poi/bycell should return 404 for cached cell with no POI data."""
        cache_with_data("8a1f96334daffff", None, [])
        response = await authenticated_client.get("/poi/bycell?h3Cell=8a1f96334daffff")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_bycell_returns_natural_type(
        self, authenticated_client, cache_with_data
    ) -> None:
        """GET /poi/bycell should return correct type for natural POI."""
        cache_with_data("8a1f96334daffff", "natural", [{"osm_id": 2, "name": "Test Park", "lat": 45.0, "lon": 3.0}])
        response = await authenticated_client.get("/poi/bycell?h3Cell=8a1f96334daffff")
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "natural"
        assert data["count"] == 1

    @pytest.mark.asyncio
    async def test_bycell_returns_industrial_type(
        self, authenticated_client, cache_with_data
    ) -> None:
        """GET /poi/bycell should return correct type for industrial POI."""
        cache_with_data("8a1f96334daffff", "industrial", [{"osm_id": 3, "name": "Test Factory", "lat": 45.0, "lon": 3.0}])
        response = await authenticated_client.get("/poi/bycell?h3Cell=8a1f96334daffff")
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "industrial"
        assert data["count"] == 1
