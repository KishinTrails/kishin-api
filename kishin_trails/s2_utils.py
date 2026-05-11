"""Utility functions for S2 geometry operations."""

import math

import s2geometry as s2

EARTH_RADIUS = 6371000


def latLngToS2Cell(lat: float, lng: float, level: int = 16) -> int:
    """Get S2 cell ID from coordinates.

    Args:
        lat: Latitude in decimal degrees.
        lng: Longitude in decimal degrees.
        level: S2 level (0-30). Default is 16.

    Returns:
        S2 cell ID as integer.
    """
    coord = s2.S2LatLng.FromDegrees(lat, lng)
    return s2.S2CellId(coord).parent(level).id()


def s2CellIdToHex(cellId: int) -> str:
    """Get hexadecimal representation of an S2 cell ID.

    Args:
        cellId: S2 cell ID as integer.

    Returns:
        Hex string without 0x prefix, no trailing zeros.
    """
    return format(cellId, 'x').rstrip('0')


def s2CellIdFromHex(hexStr: str) -> int:
    """Get S2 cell ID from hexadecimal string.

    Args:
        hexStr: Hex string (with or without 0x prefix).

    Returns:
        S2 cell ID as integer.
    """
    return s2.S2CellId.FromToken(hexStr).id()


def s2CellIdToLatLng(cellId: int) -> tuple[float, float]:
    """Get center coordinates of an S2 cell.

    Args:
        cellId: S2 cell ID as integer.

    Returns:
        Tuple of (lat, lng).
    """
    cellId = s2.S2CellId(cellId)
    latLng = cellId.ToLatLng()
    return latLng.lat().degrees(), latLng.lng().degrees()


def getS2CellLevel(cellId: int) -> int:
    """Get the level of an S2 cell.

    Args:
        cellId: S2 cell ID as integer.

    Returns:
        Level of the cell (0-30).
    """
    return s2.S2CellId(cellId).level()


def s2CellToParent(cellId: int, level: int) -> int:
    """Get parent cell at a specific level.

    Args:
        cellId: S2 cell ID as integer.
        level: Target parent level (0-30).

    Returns:
        Parent cell ID as integer.
    """
    return s2.S2CellId(cellId).parent(level).id()


def getS2CellBounds(cellId: int) -> tuple[float, float, float, float]:
    """Get bounding rectangle of an S2 cell.

    Args:
        cellId: S2 cell ID as integer.

    Returns:
        Tuple of (lo_lat, lo_lng, hi_lat, hi_lng).
    """
    cell = s2.S2Cell(s2.S2CellId(cellId))
    rect = cell.GetRectBound()
    return (rect.lo().lat().degrees(), rect.lo().lng().degrees(), rect.hi().lat().degrees(), rect.hi().lng().degrees())


def getS2CellCenter(cellId: int) -> tuple[float, float]:
    """Get center coordinates of an S2 cell.

    Args:
        cellId: S2 cell ID as integer.

    Returns:
        Tuple of (lat, lng).
    """
    latLo, lngLo, latHi, lngHi = getS2CellBounds(cellId)
    return (latLo+latHi) / 2, (lngLo+lngHi) / 2


def getS2EdgeLength(cellId: int) -> float:
    """Get edge length of an S2 cell in meters.

    Args:
        cellId: S2 cell ID as integer.

    Returns:
        Edge length in meters.
    """
    latLo, lngLo, latHi, lngHi = getS2CellBounds(cellId)
    latSpan = (latHi-latLo) * math.pi / 180 * EARTH_RADIUS
    centerLat = (latLo+latHi) / 2
    lngSpan = (lngHi-lngLo) * math.pi / 180 * EARTH_RADIUS * math.cos(math.radians(centerLat))
    return max(latSpan, lngSpan)


def pointInS2Cell(lat: float, lng: float, cellId: int) -> bool:
    """Check if a point is inside an S2 cell.

    Args:
        lat: Latitude in decimal degrees.
        lng: Longitude in decimal degrees.
        cellId: S2 cell ID as integer.

    Returns:
        True if the point is inside the cell, False otherwise.
    """
    latLo, lngLo, latHi, lngHi = getS2CellBounds(cellId)
    return latLo <= lat <= latHi and lngLo <= lng <= lngHi

