"""
POI (Point of Interest) module for transforming OSM waypoints into in-game POIs.

Provides API endpoints for querying nearby POIs based on location.
"""

import logging

from typing import Any, List

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

import h3
import geopandas as gpd
from shapely.geometry import Point, Polygon

from kishin_trails.config import settings
from kishin_trails.utils import get_h3_circle
from kishin_trails.dependencies import get_current_user
from kishin_trails.utils import sanitize_value
from kishin_trails.overpass import load_elements_at

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("PoI")

DEFAULT_CENTER_LAT = settings.DEFAULT_CENTER_LAT
DEFAULT_CENTER_LON = settings.DEFAULT_CENTER_LON
DEFAULT_POI_RADIUS_M = settings.DEFAULT_POI_RADIUS_M

if APIRouter:
    router = APIRouter(prefix="/poi", tags=["poi"], dependencies=[Depends(get_current_user)])
else:
    router = None


class PoI:
    def __init__(self, id: int, name: str | None, geometry: Point):
        self.id: int = id
        self.name: str = name or f"POI {id}"
        self.geometry: Point = geometry

    def to_dict(self) -> dict[str, Any]:
        result = {
            "id": self.id,
            "name": self.name,
        }
        if self.geometry is not None:
            result["geometry"] = str(self.geometry)
        return result


class PeakPoI(PoI):
    def __init__(self, id: int, name: str | None, geometry: Point, tags: dict):
        super().__init__(id, name, geometry)
        self.elevation = tags["ele"] if "ele" in tags and tags["ele"] and int(tags["ele"]) > 0 else None

    def to_dict(self) -> dict[str, Any]:
        base_dict = super().to_dict()
        if self.elevation:
            base_dict["elevation"] = self.elevation
        return base_dict


class NaturalPoI(PoI):
    def __init__(self, id: int, name: str | None, geometry: Point = None):
        super().__init__(id, name, geometry)


class IndustrialPoI(PoI):
    def __init__(self, id: int, name: str | None, geometry: Point = None):
        super().__init__(id, name, geometry)


def transform_waypoint_to_poi(waypoint: dict) -> PoI:
    geometry = waypoint.get("tags").get("geometry")
    tags = {
        k: sanitize_value(v)
        for k, v in waypoint.get("tags", {}).items()
    }
    poi_id = waypoint.get("id")
    name = tags.get("name")

    # Peaks
    if tags.get("natural") in ["peak",
                               "volcano",
                               "ridge",
                               "arete",
                               "cliff"] or tags.get("map_type") == "toposcope" or tags.get("tourism") == "viewpoint":
        return PeakPoI(id=poi_id, name=name, geometry=geometry, tags=tags)

    # Natural features
    if tags.get("leisure") == "park" or tags.get("landuse") in ["forest", "recreation_ground", "education"]:
        return NaturalPoI(id=poi_id, name=name, geometry=geometry)

    # Industrial features
    if tags.get("landuse") == "industrial":
        return IndustrialPoI(id=poi_id, name=name, geometry=geometry)

    return PoI(id=poi_id, name=name, geometry=geometry)


def select_best_poi(elements: List[dict]) -> dict | None:
    """Select the best POI from a list of elements based on priority.
    
    Priority: PeakPoI > NaturalPoI > IndustrialPoI
    Tie-breaker: Lowest ID first
    
    Args:
        elements: List of element dicts with 'id' and 'tags'.
        
    Returns:
        Dict with 'type' (poi type string) and 'poi' (poi data dict), or None if no match.
    """
    if not elements:
        return None

    # Convert all elements to PoI objects
    pois = []
    for elem in elements:
        waypoint = {
            "id": elem.get("id"),
            "tags": elem.get("tags",
                             {})
        }
        poi = transform_waypoint_to_poi(waypoint)
        pois.append(poi)

    # Apply priority: Peak > Natural > Industrial
    for ptype_class in [PeakPoI, NaturalPoI, IndustrialPoI]:
        matching = [p for p in pois if isinstance(p, ptype_class)]
        if matching:
            # Sort by ID and return first
            matching.sort(key=lambda p: p.id)
            selected = matching[0]
            type_name = ptype_class.__name__.replace("PoI", "").lower()
            return {
                "type": type_name,
                "poi": selected.to_dict()
            }

    return None


def find_nearby_waypoints(gdf: gpd.GeoDataFrame, lat: float, lng: float, radius_m: float) -> List[dict[str, Any]]:
    if gdf.empty:
        return []

    pois = []
    for _, row in gdf.iterrows():
        waypoint = {
            "id": row["id"],
            "tags": {
                k: v
                for k, v in row.items()
            },
        }
        poi = transform_waypoint_to_poi(waypoint)
        pois.append(poi.to_dict())

    return pois


if router:

    @router.get(
        "/",
        summary="Get all POIs",
        response_class=JSONResponse,
        deprecated=True,
    )
    def get_all_pois():
        gdf = load_elements_at(DEFAULT_CENTER_LAT, DEFAULT_CENTER_LON, DEFAULT_POI_RADIUS_M)
        pois = find_nearby_waypoints(gdf, DEFAULT_CENTER_LAT, DEFAULT_CENTER_LON, DEFAULT_POI_RADIUS_M)

        return JSONResponse(
            content={
                "type": "FeatureCollection",
                "count": len(pois),
                "radius_m": DEFAULT_POI_RADIUS_M,
                "center": {
                    "lat": DEFAULT_CENTER_LAT,
                    "lng": DEFAULT_CENTER_LON
                },
                "features": pois,
            }
        )

    @router.get(
        "/nearby",
        summary="Get nearby POIs",
        response_class=JSONResponse,
    )
    def get_nearby_pois(
        h3_cell: str = Query(...,
                             description="H3 hexagonal cell identifier (e.g., '851f9633fffffff')."),
        parent_level: int = Query(
            0,
            ge=0,
            le=5,
            description="Level of parent cell to search. 0 = current cell, 1 = first parent, etc.",
        ),
    ):
        try:
            lat, lng, radius_m, search_cell = get_h3_circle(h3_cell, parent_level)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        gdf = load_elements_at(lat, lng, radius_m)
        pois = find_nearby_waypoints(gdf, lat, lng, radius_m)

        return JSONResponse(
            content={
                "type": "FeatureCollection",
                "count": len(pois),
                "radius_m": radius_m,
                "center": {
                    "lat": lat,
                    "lng": lng
                },
                "h3_cell": h3_cell,
                "parent_level": parent_level,
                "search_cell": search_cell,
                "features": pois,
            }
        )

    @router.get(
        "/bycell",
        summary="Get POI for a single H3 cell",
        response_class=JSONResponse,
    )
    def get_poi_by_cell(
        h3_cell: str = Query(...,
                             description="H3 hexagonal cell identifier (e.g., '851f9633fffffff').")
    ):
        try:
            lat, lng, radius_m, _ = get_h3_circle(h3_cell, 0)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        gdf = load_elements_at(lat, lng, radius_m)

        elements = []
        for _, row in gdf.iterrows():
            elements.append({
                "id": row["id"],
                "tags": dict(row.items())
            })

        result = select_best_poi(elements)

        if result is None:
            return JSONResponse(content={
                "h3_cell": h3_cell,
                "center": {
                    "lat": lat,
                    "lng": lng
                },
                "count": 0
            })

        return JSONResponse(
            content={
                "h3_cell": h3_cell,
                "center": {
                    "lat": lat,
                    "lng": lng
                },
                "type": result["type"],
                "count": 1,
                "poi": result["poi"]
            }
        )
