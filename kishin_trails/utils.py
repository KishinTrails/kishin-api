"""Utility functions for data processing."""

from typing import Any

import h3
from shapely import Point, Polygon


def sanitizeValue(val: Any) -> str | None:
    """Sanitize a value for JSON serialization.

    Args:
        val: Value to sanitize.

    Returns:
        String version of the value, or None if the value is NaN/inf.
    """
    if isinstance(val, float) and (val != val or val == float("inf") or val == float("-inf")):
        return None
    if isinstance(val, str):
        return val
    return str(val)


def getH3CellRadius(h3Cell: str) -> int:
    """Calculate the approximate radius of an H3 cell in meters.

    For a hexagonal cell, the radius (center to vertex) equals the edge length.
    The diameter (vertex to opposite vertex) is 2 * edgeLength.

    Args:
        h3Cell: H3 cell identifier.

    Returns:
        Approximate radius in meters (diameter of the hexagon).
    """
    res = h3.get_resolution(h3Cell)
    edgeLength = h3.average_hexagon_edge_length(res, unit="m")
    return int(edgeLength * 1)


def getH3Circle(h3Cell: str, parentLevel: int = 0) -> tuple[float, float, int, str]:
    """Get center coordinates and radius for an H3 cell at a given parent level.

    Args:
        h3Cell: H3 cell identifier.
        parentLevel: Level of parent cell (0 = current cell, 1 = first parent, etc.).

    Returns:
        Tuple of (lat, lng, radiusM, searchCell).

    Raises:
        ValueError: If parentLevel exceeds cell resolution.
    """
    cellRes = h3.get_resolution(h3Cell)

    if parentLevel > 0:
        targetRes = cellRes - parentLevel
        if targetRes < 0:
            raise ValueError(f"Parent level {parentLevel} exceeds cell resolution {cellRes}")
        searchCell = h3.cell_to_parent(h3Cell, res=targetRes)
    else:
        searchCell = h3Cell

    lat, lng = h3.cell_to_latlng(searchCell)
    radiusM = getH3CellRadius(searchCell)

    return lat, lng, radiusM, searchCell


def getH3Cell(lat: float, lng: float, resolution: int) -> str:
    """Get H3 cell identifier from coordinates and resolution.

    Args:
        lat: Latitude in decimal degrees.
        lng: Longitude in decimal degrees.
        resolution: H3 resolution level (0-15).

    Returns:
        H3 cell identifier.
    """
    return h3.latlng_to_cell(lat, lng, resolution)


def pointInH3Hexagon(lat: float, lng: float, h3Cell: str) -> bool:
    """Check if a point is inside an H3 hexagon cell.

    Args:
        lat: Latitude in decimal degrees.
        lng: Longitude in decimal degrees.
        h3Cell: H3 cell identifier.

    Returns:
        True if the point is inside the hexagon, False otherwise.
    """
    boundary = h3.cell_to_boundary(h3Cell)
    coords = [(lng, lat) for lat, lng in boundary]
    polygon = Polygon(coords)
    point = Point(lng, lat)
    return point.within(polygon)
