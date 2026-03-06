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
    def __init__(self, id: int, name: str | None):
        self.id: int = id
        self.name: str = name or f"POI {id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
        }


class PeakPoI(PoI):
    def __init__(self, id: int, name: str | None, tags):
        self.tags = tags
        super().__init__(id, name)


# class NaturalPoI(PoI):
#     def __init__(self, id: int, name: str | None):
#         super().__init__(id, name)


def transform_waypoint_to_poi(waypoint: dict) -> PoI:
    tags = {
        k: sanitize_value(v)
        for k, v in waypoint.get("tags", {}).items()
    }
    poi_id = waypoint.get("id")
    name = tags.get("name")

    # Peaks
    # if tags.get("natural") in ["peak",
    #                            "volcano",
    #                            "ridge",
    #                            "arete",
    #                            "cliff"] or tags.get("map_type") == "toposcope" or tags.get("tourism") == "viewpoint":
    #     return PeakPoI(id=poi_id, name=name)

    # Parks
    # if tags.get("leisure") == "park":
    #     return NaturalPoI(id=poi_id, name=name)

    return PoI(id=poi_id, name=name)


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
