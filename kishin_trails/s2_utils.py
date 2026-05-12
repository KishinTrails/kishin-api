"""Utility functions for S2 geometry operations."""

import math

import s2geometry as s2
from shapely.geometry import MultiPolygon

EARTH_RADIUS = 6371000


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


def s2CellsFromPolygon(geometry, level: int = 10) -> list[int]:
    """Get all S2 cells at a given level that intersect a shapely polygon.

    Args:
        geometry: Shapely Polygon or MultiPolygon.
        level: S2 cell level (0-30). Default is 10.

    Returns:
        List of S2 cell IDs.
    """
    coverer = s2.S2RegionCoverer()
    coverer.set_min_level(level)
    coverer.set_max_level(level)
    coverer.set_max_cells(1000000)

    if isinstance(geometry, MultiPolygon):
        geometries = geometry.geoms
    else:
        geometries = [geometry]

    allCells = []
    for geom in geometries:
        coords = list(geom.exterior.coords[:-1])
        s2Points = [s2.S2LatLng.FromDegrees(lat, lng).ToPoint() for lng, lat in coords]

        loop = s2.S2Loop()
        loop.Init(s2Points)
        loop.Normalize()

        s2poly = s2.S2Polygon()
        s2poly.InitNested([loop])

        covering = coverer.GetCovering(s2poly)
        allCells.extend(cell.id() for cell in covering)

    return allCells


def s2CellIdToToken(cellId: int) -> str:
    """Get compact hex token for an S2 cell ID.

    Args:
        cellId: S2 cell ID as integer.

    Returns:
        Compact hex string (no trailing zeros).
    """
    return s2.S2CellId(cellId).ToToken()


def s2CellToChildren(cellId: int, level: int) -> list[int]:
    """Get all child cells at a specific level.

    Args:
        cellId: Parent S2 cell ID.
        level: Target level for children (must be > parent cell level).

    Returns:
        List of child cell IDs.

    Raises:
        ValueError: If level is not greater than parent cell level.
    """
    cellId = s2.S2CellId(cellId)
    parentLevel = cellId.level()

    if level <= parentLevel:
        raise ValueError(f"Target level {level} must be greater than parent level {parentLevel}")

    childPrefix = cellId.child_begin(level).id()
    childEnd = cellId.child_end(level).id()

    children = []
    childId = s2.S2CellId(childPrefix)
    while childId.id() < childEnd:
        children.append(childId.id())
        childId = childId.next()

    return children
