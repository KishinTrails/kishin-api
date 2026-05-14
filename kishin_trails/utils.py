"""Utility functions for data processing and S2 geometry operations.

This module provides a comprehensive suite of S2 cell geometry utilities designed
to work exclusively with hexadecimal string representations of S2 cell IDs. The
s2geometry library uses two distinct representations for S2 cells:

    1. Hexadecimal Token (str): A compact, human-readable representation where
       trailing zeros are stripped. Example: "89c25a221"

    2. Cell ID (uint64): The raw 64-bit unsigned integer identifier.
       Example: 9926595631021817856 (decimal), 0x89c25a2210000000 (hex)

The token is NOT simply the hex representation of the cell ID - it's a compact
format where trailing zero nibbles are omitted. This means:
    - Token: "89c25a221"
    - Cell ID: 9926595631021817856
    - Cell ID hex: 0x89c25a2210000000 (with trailing zeros)

All public API functions in this module accept and return hexadecimal strings
(tokens) exclusively. Use s2CellIdToHex() and s2CellIdFromHex() for conversion
between representations when needed.

The module uses the official Google s2geometry library, which provides the
following key classes:
    - S2CellId: Represents an S2 cell identifier with various factory/instance methods
    - S2Cell: Represents a cell with geometric properties (bounds, area, etc.)
    - S2LatLng: Represents a point on the sphere via latitude/longitude
    - S2RegionCoverer: Computes cell coverings of arbitrary spherical regions
    - S2Loop, S2Polygon: Represent spherical polygon boundaries

Important s2geometry API notes:
    - S2CellId(token) constructor accepts uint64 int, NOT hex string
    - S2CellId.FromToken(str) accepts hex string token, NOT int
    - S2CellId.id() returns the raw uint64 integer
    - S2CellId.ToToken() returns the compact hex token string
"""

from __future__ import annotations

import math
from functools import wraps
from typing import Any, Callable, TypeVar

import s2geometry as s2
from shapely.geometry import MultiPolygon

EARTH_RADIUS = 6371000

F = TypeVar("F", bound=Callable[..., Any])


def _normalizeS2Cell(func: F) -> F:
    """Decorator that normalizes S2 cell input: strips 0x prefix, validates, and passes S2CellId to function.

    This decorator handles both input normalization and validation, ensuring consistent
    behavior across all functions that accept S2 cell identifiers. It:
    1. Accepts either a string token or an already-normalized S2CellId
    2. For strings: strips '0x' or '0X' prefix if present
    3. Creates and validates an S2CellId
    4. Passes the S2CellId object to the decorated function

    This allows decorated functions to call each other without re-normalizing.

    Args:
        func: Function whose first parameter is an S2 cell string or S2CellId.

    Returns:
        Wrapped function that normalizes input and passes S2CellId to original.

    Example:
        @_normalizeS2Cell
        def s2CellIdToLatLng(cellId: s2.S2CellId) -> tuple[float, float]:
            latLng = cellId.ToLatLng()
            return latLng.lat().degrees(), latLng.lng().degrees()

        s2CellIdToLatLng("89c25a221")  # Works
        s2CellIdToLatLng("0x89c25a221")  # Also works (0x stripped)
        s2CellIdToLatLng("invalid")  # Raises ValueError
    """

    @wraps(func)
    def wrapper(s2Cell: str | s2.S2CellId, *args: Any, **kwargs: Any) -> Any:
        if isinstance(s2Cell, s2.S2CellId):
            cellId = s2Cell
        else:
            normalized = s2Cell[2:] if s2Cell.startswith(("0x", "0X")) else s2Cell
            cellId = s2.S2CellId.FromToken(normalized)
            if not cellId.is_valid():
                raise ValueError(f"Invalid S2 cell token: {s2Cell}")
        return func(cellId, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


def sanitizeValue(val: Any) -> str | None:
    """Sanitize a value for JSON serialization.

    Handles special float values (NaN, Infinity) by converting them to None,
    ensuring JSON-safe output. Other types are converted to strings.

    Args:
        val: Value to sanitize. Can be any type.

    Returns:
        String representation of the value, or None if val is NaN or infinity.

    Examples:
        >>> sanitizeValue("hello")
        'hello'
        >>> sanitizeValue(42)
        '42'
        >>> sanitizeValue(float('nan'))
        None
        >>> sanitizeValue(float('inf'))
        None
    """
    if isinstance(val, float) and (val != val or val == float("inf") or val == float("-inf")):
        return None
    if isinstance(val, str):
        return val
    return str(val)


def s2CellIdToHex(cellId: int) -> str:
    """Convert a raw S2 cell ID to its compact hexadecimal token.

    Takes a raw 64-bit unsigned integer cell ID and returns the compact hex
    token representation used throughout this API. The token format strips
    trailing zeros, making it more human-readable than the full hex representation.

    Args:
        cellId: Raw S2 cell identifier as a 64-bit unsigned integer.

    Returns:
        Compact hexadecimal token string with trailing zeros omitted.

    Example:
        >>> s2CellIdToHex(9926595631021817856)
        '89c25a221'

    Note:
        This is the inverse of s2CellIdFromHex(). The hex token "89c25a221"
        represents cell ID 9926595631021817856, which in full hex would be
        0x89c25a2210000000 (note the trailing zeros).
    """
    return s2.S2CellId(cellId).ToToken()


@_normalizeS2Cell
def s2CellIdFromHex(cellId: s2.S2CellId) -> int:
    """Convert a hexadecimal token string to its raw S2 cell ID (uint64).

    Parses a compact hexadecimal token (as returned by s2CellIdToHex) and
    returns the corresponding raw 64-bit unsigned integer cell ID. This
    function normalizes input by stripping any '0x' or '0X' prefix before
    conversion.

    Args:
        hexStr: S2 cell token as a hexadecimal string. May optionally include
            a '0x' or '0X' prefix which will be automatically stripped.

    Returns:
        Raw S2 cell identifier as a 64-bit unsigned integer.

    Example:
        >>> s2CellIdFromHex("89c25a221")
        9926595631021817856
        >>> s2CellIdFromHex("0x89c25a221")
        9926595631021817856

    Note:
        This is the inverse of s2CellIdToHex(). The token "89c25a221" represents
        cell ID 9926595631021817856 (decimal) or 0x89c25a2210000000 (full hex).
    """
    return cellId.id()


def latLngToS2Cell(lat: float, lng: float, level: int = 16) -> str:
    """Get S2 cell token from coordinates.

    Args:
        lat: Latitude in decimal degrees.
        lng: Longitude in decimal degrees.
        level: S2 level (0-30). Default is 16.

    Returns:
        S2 cell ID as hex token string.
    """
    coord = s2.S2LatLng.FromDegrees(lat, lng)
    return s2.S2CellId(coord).parent(level).ToToken()


@_normalizeS2Cell
def s2CellIdToLatLng(cellId: s2.S2CellId) -> tuple[float, float]:
    """Get center coordinates of an S2 cell.

    Args:
        cellId: S2 cell object (receives normalized token from decorator).

    Returns:
        Tuple of (lat, lng).
    """
    latLng = cellId.ToLatLng()
    return latLng.lat().degrees(), latLng.lng().degrees()


@_normalizeS2Cell
def getS2CellLevel(cellId: s2.S2CellId) -> int:
    """Get the level of an S2 cell.

    Args:
        cellId: S2 cell object (receives normalized token from decorator).

    Returns:
        Level of the cell (0-30).
    """
    return cellId.level()


@_normalizeS2Cell
def s2CellToParent(cellId: s2.S2CellId, level: int) -> str:
    """Get parent cell token at a specific level.

    Args:
        cellId: S2 cell object (receives normalized token from decorator).
        level: Target parent level (0-30).

    Returns:
        Parent cell hex token.
    """
    return cellId.parent(level).ToToken()


@_normalizeS2Cell
def getS2CellBounds(cellId: s2.S2CellId) -> tuple[float, float, float, float]:
    """Get bounding rectangle of an S2 cell.

    Args:
        cellId: S2 cell object (receives normalized token from decorator).

    Returns:
        Tuple of (lo_lat, lo_lng, hi_lat, hi_lng).
    """
    cell = s2.S2Cell(cellId)
    rect = cell.GetRectBound()
    return (rect.lo().lat().degrees(), rect.lo().lng().degrees(), rect.hi().lat().degrees(), rect.hi().lng().degrees())


@_normalizeS2Cell
def getS2CellCenter(cellId: s2.S2CellId) -> tuple[float, float]:
    """Get center coordinates of an S2 cell.

    Args:
        cellId: S2 cell object (receives normalized token from decorator).

    Returns:
        Tuple of (lat, lng).
    """
    latLo, lngLo, latHi, lngHi = getS2CellBounds(cellId)
    return (latLo+latHi) / 2, (lngLo+lngHi) / 2


@_normalizeS2Cell
def getS2EdgeLength(cellId: s2.S2CellId) -> float:
    """Get edge length of an S2 cell in meters.

    Args:
        cellId: S2 cell object (receives normalized token from decorator).

    Returns:
        Edge length in meters.
    """
    latLo, lngLo, latHi, lngHi = getS2CellBounds(cellId)
    latSpan = (latHi-latLo) * math.pi / 180 * EARTH_RADIUS
    centerLat = (latLo+latHi) / 2
    lngSpan = (lngHi-lngLo) * math.pi / 180 * EARTH_RADIUS * math.cos(math.radians(centerLat))
    return max(latSpan, lngSpan)


@_normalizeS2Cell
def pointInS2Cell(cellId: s2.S2CellId, lat: float, lng: float) -> bool:
    """Check if a point is inside an S2 cell.

    Args:
        cellId: S2 cell object (receives normalized token from decorator).
        lat: Latitude in decimal degrees.
        lng: Longitude in decimal degrees.

    Returns:
        True if the point is inside the cell, False otherwise.
    """
    latLo, lngLo, latHi, lngHi = getS2CellBounds(cellId)
    return latLo <= lat <= latHi and lngLo <= lng <= lngHi


def s2CellsFromPolygon(geometry: Any, level: int = 10) -> list[str]:
    """Get all S2 cell tokens at a given level that intersect a shapely polygon.

    Args:
        geometry: Shapely Polygon or MultiPolygon.
        level: S2 cell level (0-30). Default is 10.

    Returns:
        List of S2 cell tokens.
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
        s2Points = [s2.S2LatLng.FromDegrees(lat, lng).ToPoint() for lat, lng in coords]

        loop = s2.S2Loop()
        loop.Init(s2Points)
        loop.Normalize()

        s2poly = s2.S2Polygon()
        s2poly.InitNested([loop])

        covering = coverer.GetCovering(s2poly)
        allCells.extend(cell.ToToken() for cell in covering)

    return allCells


@_normalizeS2Cell
def s2CellToChildren(cellId: s2.S2CellId, level: int) -> list[str]:
    """Get all child cell tokens at a specific level.

    Args:
        cellId: S2 cell object (receives normalized token from decorator).
        level: Target level for children (must be > parent cell level).

    Returns:
        List of child cell hex tokens.

    Raises:
        ValueError: If level is not greater than parent cell level.
    """
    parentLevel = cellId.level()

    if level <= parentLevel:
        raise ValueError(f"Target level {level} must be greater than parent level {parentLevel}")

    childBegin = cellId.child_begin(level)
    childEnd = cellId.child_end(level)

    children = []
    curr = childBegin
    while curr != childEnd:
        children.append(curr.ToToken())
        curr = curr.next()

    return children
