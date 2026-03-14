"""
POI (Point of Interest) module for transforming OSM waypoints into in-game POIs.

Provides API endpoints for querying nearby POIs based on location.
"""

import logging

from typing import Any, List, Tuple

try:
    from fastapi import APIRouter, HTTPException, Query, Depends
except ImportError:  # pragma: no cover
    APIRouter = HTTPException = Query = Depends = None
try:
    from fastapi.responses import JSONResponse
except ImportError:  # pragma: no cover

    class _DummyResponse(dict):
        def __init__(self, content: Any):
            super().__init__(content=content)

    JSONResponse = _DummyResponse

from shapely.geometry import Point

from kishin_trails.cache import getTile, setTile
from kishin_trails.config import settings
from kishin_trails.utils import sanitizeValue, pointInH3Hexagon, getH3Circle
from kishin_trails.dependencies import getCurrentUser
from kishin_trails.overpass import loadElementsAt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("PoI")

DEFAULT_CENTER_LAT = settings.DEFAULT_CENTER_LAT
DEFAULT_CENTER_LON = settings.DEFAULT_CENTER_LON
DEFAULT_POI_RADIUS_M = settings.DEFAULT_POI_RADIUS_M

if APIRouter:
    router = APIRouter(prefix="/poi", tags=["poi"], dependencies=[Depends(getCurrentUser)])
else:
    router = None


class PoI:
    """Base class for Points of Interest from OSM data.

    Attributes:
        osmId: OpenStreetMap element ID.
        name: Name of the POI.
        geometry: Shapely Point geometry.
    """
    def __init__(self, osmId: int, name: str | None, geometry: Point):
        self.osmId = osmId
        self.name: str = name
        self.geometry: Point = geometry

    def toDict(self) -> dict[str, Any]:
        """Convert POI to dictionary representation.
        
        Returns:
            Dictionary with osm_id, name, and optionally lat/lon/elevation.
        """
        result = {
            "osm_id": self.osmId,
            "name": self.name,
        }
        if self.geometry is not None:
            if isinstance(self.geometry, Point):
                result["lat"] = self.geometry.y
                result["lon"] = self.geometry.x
            else:
                # FIXME: Ideally, we should return the barycenter of the geometry
                # intersecting the hexagon. For now, we just return the centrer of
                # the bounding box.
                bounds = self.geometry.bounds  # (minx, miny, maxx, maxy)
                result["lat"] = (bounds[1] + bounds[3]) / 2
                result["lon"] = (bounds[0] + bounds[2]) / 2
        return result


class PeakPoI(PoI):
    """Point of Interest for peaks and elevated features.

    Extends PoI with elevation data for mountains, volcanoes, ridges, etc.

    Attributes:
        elevation: Elevation in meters above sea level.
    """
    def __init__(self, osmId: int, name: str | None, geometry: Point, tags: dict):
        super().__init__(osmId, name, geometry)
        self.elevation = tags["ele"] if "ele" in tags and tags["ele"] and int(tags["ele"]) > 0 else None

    def toDict(self) -> dict[str, Any]:
        baseDict = super().toDict()
        if self.elevation:
            baseDict["elevation"] = self.elevation
        return baseDict


class NaturalPoI(PoI):
    """Point of Interest for natural features like parks and forests.

    Represents leisure and landuse areas such as parks, forests, and
    recreation grounds.
    """
    def __init__(self, osmId: int, name: str | None, geometry: Point = None):
        """Initialize Natural POI.
        
        Args:
            osmId: OpenStreetMap element ID.
            name: Name of the POI.
            geometry: Shapely Point geometry.
        """
        super().__init__(osmId, name, geometry)


class IndustrialPoI(PoI):
    """Point of Interest for industrial landuse areas.

    Represents industrial zones and facilities from OSM data.
    """
    def __init__(self, osmId: int, name: str | None, geometry: Point = None):
        """Initialize Industrial POI.
        
        Args:
            osmId: OpenStreetMap element ID.
            name: Name of the POI.
            geometry: Shapely Point geometry.
        """
        super().__init__(osmId, name, geometry)


def transformWaypointToPoi(waypoint: dict) -> PoI:
    """Transform OSM waypoint to POI instance.
    
    Args:
        waypoint: Dictionary with 'id' and 'tags' from OSM data.
        
    Returns:
        PoI, PeakPoI, NaturalPoI, or IndustrialPoI instance based on tags.
    """
    geometry = waypoint.get("tags").get("geometry")
    tags = {
        k: sanitizeValue(v)
        for k, v in waypoint.get("tags", {}).items()
    }
    poiId = waypoint.get("id")
    name = tags.get("name")

    # Peaks
    if tags.get("natural") in ["peak",
                               "volcano",
                               "ridge",
                               "arete",
                               "cliff"] or tags.get("map_type") == "toposcope" or tags.get("tourism") == "viewpoint":
        return PeakPoI(osmId=poiId, name=name, geometry=geometry, tags=tags)

    # Natural features
    if tags.get("leisure") == "park" or tags.get("landuse") in ["forest", "recreation_ground", "education"]:
        return NaturalPoI(osmId=poiId, name=name, geometry=geometry)

    # Industrial features
    if tags.get("landuse") == "industrial":
        return IndustrialPoI(osmId=poiId, name=name, geometry=geometry)

    return PoI(osmId=poiId, name=name, geometry=geometry)


def filterWaypointsForCache(elements: List[dict]) -> Tuple[List[dict], str | None]:
    """Filter waypoints for caching, selecting all POIs of the best type.

    Priority: PeakPoI > NaturalPoI > IndustrialPoI

    Args:
        elements: List of element dicts with 'id' and 'tags'.

    Returns:
        Tuple of (selected_waypoints: List[dict], selected_type: str | None)
    """
    if not elements:
        return [], None

    pois = []
    for elem in elements:
        waypoint = {
            "id": elem.get("id"),
            "tags": elem.get("tags",
                             {}),
        }
        poi = transformWaypointToPoi(waypoint)
        pois.append(poi)

    # Peaks have highest priority. First filter for peaks.
    peaks = [p for p in pois if isinstance(p, PeakPoI) and p.name]
    if len(peaks) == 1:
        return [peaks[0].toDict()], "peak"
    if len(peaks) > 1:
        # Multiple peaks found, choose the one with highest elevation.
        peaks = sorted(peaks, key=lambda p: -int(p.elevation) if p.elevation is not None else p.osmId)
        return [peaks[0].toDict()], "peak"

    # If no peaks, look for natural features.
    if any(isinstance(p, NaturalPoI) for p in pois):
        return [], "natural"

    # If no natural features, look for industrial features.
    if any(isinstance(p, IndustrialPoI) for p in pois):
        return [], "industrial"

    return [], None


def formatPoiFromCache(cachedTile: dict, h3Cell: str, lat: float, lng: float) -> dict:
    """Format cached POI data for API response."""
    pois = cachedTile.get("pois", [])
    if not pois:
        return {
            "h3_cell": h3Cell,
            "type": cachedTile.get("tile_type"),
            "center": {
                "lat": lat,
                "lng": lng
            },
            "count": 0
        }

    poiData = pois[0]
    return {
        "h3_cell": h3Cell,
        "type": cachedTile.get("tile_type"),
        "center": {
            "lat": lat,
            "lng": lng
        },
        "count": len(pois),
        "poi":
            {
                "id": poiData.get("osm_id"),
                "name": poiData.get("name"),
                "geometry": Point(
                    poiData.get(
                        "lon",
                        lng,
                    ),
                    poiData.get(
                        "lat",
                        lat,
                    ),
                ).wkt,
                "elevation": poiData.get("elevation")
            }
    }


if router:

    @router.get(
        "/bycell",
        summary="Get POI for a single H3 cell",
        response_class=JSONResponse,
    )
    def getPoiByCell(h3Cell: str = Query(
        ...,
        description="H3 hexagonal cell identifier (e.g., '851f9633fffffff').",
    )):
        """Get POI data for a specific H3 cell.
        
        Args:
            h3Cell: H3 cell identifier.
            
        Returns:
            JSON response with POI data for the cell.
            
        Raises:
            HTTPException 400: If the H3 cell is invalid.
        """
        try:
            lat, lng, radiusM, _ = getH3Circle(h3Cell, 0)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        cached = getTile(h3Cell)
        if cached:
            return JSONResponse(content=formatPoiFromCache(cached, h3Cell, lat, lng))

        gdf = loadElementsAt(lat, lng, radiusM)

        elements = []
        for _, row in gdf.iterrows():
            tags = dict(row.items())
            geometry = tags.get("geometry")
            if geometry is not None and isinstance(geometry,
                                                   Point) and not pointInH3Hexagon(geometry.y,
                                                                                   geometry.x,
                                                                                   h3Cell):
                # Discard points that are outside the hexagon boundary.
                pass
            elif False:  # FIXME: Placeholder for future polygon handling.
                # In case polygon is in the bounding box but does not intersect
                # the hexagon, we should discard it. This requires more complex
                # geometry checks.
                pass
            else:
                elements.append({
                    "id": row["id"],
                    "tags": dict(row.items())
                })

        waypoints, tileType = filterWaypointsForCache(elements)

        # Cache the results and use the cached data for response formatting to ensure consistency.
        setTile(h3Cell, tileType, waypoints)
        cached = getTile(h3Cell)
        return JSONResponse(content=formatPoiFromCache(cached, h3Cell, lat, lng))
