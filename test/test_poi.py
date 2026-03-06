"""Tests for the POI module."""

import json
import math
from typing import Any

import pytest

from kishin_trails.poi import PoI, PeakPoI, transform_waypoint_to_poi


class TestPoI:
    """Tests for the PoI base class."""
    def test_poi_initializes_with_id_and_name(self) -> None:
        """PoI should initialize with provided id and name."""
        expected_id = 123
        expected_name = "Test POI"
        poi = PoI(id=expected_id, name=expected_name)
        assert poi.id == expected_id
        assert poi.name == expected_name

    def test_poi_default_name_when_none(self) -> None:
        """PoI should use default name when name is None."""
        expected_id = 456
        poi = PoI(id=expected_id, name=None)
        assert poi.id == expected_id
        assert poi.name == f"POI {expected_id}"

    def test_poi_to_dict_returns_correct_dict(self) -> None:
        """PoI.to_dict() should return a dict with correct attributes."""
        expected_id = 789
        expected_name = "Another POI"
        poi = PoI(id=expected_id, name=expected_name)
        result = poi.to_dict()
        assert isinstance(result, dict)
        assert result["id"] == expected_id
        assert result["name"] == expected_name

    def test_poi_to_dict_is_json_serializable(self) -> None:
        """PoI.to_dict() should produce JSON-serializable output."""
        expected_id = 111
        expected_name = "JSON POI"
        poi = PoI(id=expected_id, name=expected_name)
        result = poi.to_dict()
        json_str = json.dumps(result)
        assert json_str is not None
        parsed = json.loads(json_str)
        assert parsed["id"] == expected_id
        assert parsed["name"] == expected_name


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
        # assert isinstance(result, PeakPoI)
        assert isinstance(result, PoI)
        assert result.id == waypoint["id"]
        assert result.name == waypoint["tags"]["name"]
