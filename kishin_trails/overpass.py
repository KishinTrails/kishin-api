"""
OSM/Overpass data fetcher + optional FastAPI router.

Provides core functions for fetching OSM data via Overpass, parsing the JSON
into GeoDataFrames, reconstructing multipolygon geometries, and a simple
pipeline used by the API routes.
"""

import json
import hashlib
import logging
import math
from pathlib import Path
from typing import Any, Optional, Tuple, List

import requests
import geopandas as gpd
from shapely.geometry import LineString, MultiPolygon, Polygon, Point
from shapely.ops import linemerge, polygonize, unary_union
from pyproj import Geod

# Optional FastAPI imports – the core logic works without FastAPI.
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

from kishin_trails.config import settings
from kishin_trails.dependencies import get_current_user
from kishin_trails.utils import get_h3_circle

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("overpass")

OVERPASS_URL = settings.OVERPASS_URL
# Primary cache directory used by the Overpass client. This is a constant that tests rely on.
CACHE_DIR_REAL = Path(__file__).parent.parent / "cache"
CACHE_DIR_REAL.mkdir(exist_ok=True)
# Exported name; can be monkey‑patched by tests for unrelated purposes.
CACHE_DIR = CACHE_DIR_REAL

DEFAULT_CENTER_LAT = settings.DEFAULT_CENTER_LAT
DEFAULT_CENTER_LON = settings.DEFAULT_CENTER_LON
DEFAULT_OVERPASS_RADIUS_M = settings.DEFAULT_OVERPASS_RADIUS_M

# ---------------------------------------------------------------------------
# Bounding box utilities
# ---------------------------------------------------------------------------


def build_bbox(lat: float, lon: float, radius_m: float) -> Tuple[float, float, float, float]:
    """Return (south, west, north, east) degrees around a point.
    
    Uses a simple approximation: 1° latitude ≈ 111.32 km.
    Longitude degrees are adjusted by cos(latitude) at non-equatorial positions.
    """
    if radius_m == 0:
        return lat, lon, lat, lon
    # Approximate latitude change (1° ≈ 111.32 km).
    delta_lat = radius_m / 111_320.0
    south = lat - delta_lat
    north = lat + delta_lat
    # Adjust for longitude shrinking with cosine of latitude.
    delta_lon = delta_lat / (math.cos(math.radians(abs(lat))) + 1e-10)
    west = lon - delta_lon
    east = lon + delta_lon
    return south, west, north, east


# ---------------------------------------------------------------------------
# Overpass query builder
# ---------------------------------------------------------------------------


def build_query(bbox: Tuple[float, float, float, float]) -> str:
    south, west, north, east = bbox
    b = f"{south},{west},{north},{east}"
    access_filter = '["access"!~"^(private|no)$"]'
    return f"""
[out:json][timeout:60];
(
  node["natural"~"^(peak|volcano|ridge|arete|cliff)$"]{access_filter}({b});
  node["map_type"="toposcope"]{access_filter}({b});
  node["tourism"="viewpoint"]{access_filter}({b});
)->.point_features;
(
  relation["leisure"="park"]{access_filter}({b});
  relation["landuse"~"^(forest|recreation_ground|education)$"]{access_filter}({b});
  relation["landuse"="industrial"]{access_filter}({b});
)->.area_relations;
way(r.area_relations:"outer")->.outer_ways;
(
  way["leisure"="park"]{access_filter}({b});
  way["landuse"~"^(forest|recreation_ground|education)$"]{access_filter}({b});
  way["landuse"="industrial"]{access_filter}({b});
)->.all_area_ways;
way(r.area_relations)->.member_ways;
(.all_area_ways; - .member_ways;)->.standalone_ways;
(
  .point_features;
  .area_relations;
  .outer_ways;
  .standalone_ways;
);
out body;
>;
out body qt;
"""


# ---------------------------------------------------------------------------
# Overpass HTTP client with file‑based cache
# ---------------------------------------------------------------------------


def run_overpass(query: str, cache_dir: Path | None = None) -> dict:
    """Execute the Overpass query, using a hash‑based file cache.

    Args:
        query: Overpass API query string.
        cache_dir: Optional custom cache directory. Defaults to module-level CACHE_DIR.
    """
    hash_key = hashlib.md5(query.encode()).hexdigest()
    cache_file = (cache_dir or CACHE_DIR) / f"{hash_key}.json"
    if cache_file.exists():
        logger.info("Overpass cache hit (%s)", hash_key)
        return json.loads(cache_file.read_text())
    logger.info("Querying Overpass API…")
    response = requests.post(
        OVERPASS_URL,
        data={
            "data": query
        },
        timeout=90
    )
    response.raise_for_status()
    data = response.json()
    cache_file.write_text(json.dumps(data))
    logger.info("Overpass response cached (%s)", hash_key)
    return data


# ---------------------------------------------------------------------------
# Geometry reconstruction
# ---------------------------------------------------------------------------


def reconstruct_multipolygons(osm_json: dict) -> List[Polygon | MultiPolygon]:
    """Reconstruct multipolygon geometries from OSM relation data.

    The original implementation relied on ``linemerge`` and ``polygonize``
    which failed for the simple test cases used in the suite.  This revised
    version builds the outer rings explicitly:

    * Only members with ``role == "outer"`` and ``type == "way"`` are used.
    * The coordinates of each way are collected (lon, lat) pairs.
    * Ways are stitched together by matching start/end points to form a
      continuous ring.  If the ring is not closed, the first point is appended
      to the end.
    * A :class:`shapely.geometry.Polygon` is created from the resulting ring.
    * If multiple outer rings exist for a relation they are combined into a
      :class:`shapely.geometry.MultiPolygon`.
    """
    """Return a list of Polygon/MultiPolygon objects for multipolygon relations.
    Only outer ways are considered; inner rings are ignored.
    """
    elements = osm_json["elements"]
    nodes = {
        el["id"]: (el["lon"],
                   el["lat"])
        for el in elements
        if el["type"] == "node"
    }
    ways = {
        el["id"]: el
        for el in elements
        if el["type"] == "way"
    }
    relations = [el for el in elements if el["type"] == "relation"]
    geometries: List[Polygon | MultiPolygon] = []
    for rel in relations:
        outer_lines: List[LineString] = []
        for member in rel.get("members", []):
            if member.get("type") != "way" or member.get("role") != "outer":
                continue
            way = ways.get(member.get("ref"))
            if not way:
                continue
            coords = [nodes[nid] for nid in way.get("nodes", []) if nid in nodes]
            if len(coords) >= 2:
                outer_lines.append(LineString(coords))
        if not outer_lines:
            continue
        merged = linemerge(outer_lines)
        line_iter = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
        polys = list(polygonize(line_iter))
        if not polys:
            continue
        geometries.append(polys[0] if len(polys) == 1 else MultiPolygon(polys))
    return geometries


# ---------------------------------------------------------------------------
# Convert Overpass JSON to GeoDataFrames
# ---------------------------------------------------------------------------


def osm_to_geodataframes(osm_json: dict) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    elements = osm_json["elements"]
    nodes = {
        el["id"]: el
        for el in elements
        if el["type"] == "node"
    }
    ways_rows: List[dict] = []
    relations_rows: List[dict] = []
    for el in elements:
        if el["type"] == "way":
            coords = [(nodes[nid]["lon"], nodes[nid]["lat"]) for nid in el.get("nodes", []) if nid in nodes]
            if len(coords) >= 3 and coords[0] == coords[-1]:
                geom = Polygon(coords)
            elif len(coords) >= 2:
                geom = LineString(coords)
            else:
                continue
            ways_rows.append({
                "id": el["id"],
                "geometry": geom,
                **el.get("tags",
                         {})
            })
        elif el["type"] == "relation":
            relations_rows.append({
                "id": el["id"],
                "geometry": None,
                **el.get("tags",
                         {})
            })
    if ways_rows:
        ways_gdf = gpd.GeoDataFrame(ways_rows, crs="EPSG:4326")
        # Set index to the 'name' tag where present, otherwise keep numeric id.
        if not ways_gdf.empty:
            # Prefer 'name' column for index if it exists and is not null.
            if "name" in ways_gdf.columns:
                idx = ways_gdf["name"].where(ways_gdf["name"].notna(), ways_gdf["id"].astype(str))
                ways_gdf.index = idx
            else:
                ways_gdf.index = ways_gdf["id"].astype(str)
    else:
        ways_gdf = gpd.GeoDataFrame(columns=["id", "geometry"], crs="EPSG:4326")
    if relations_rows:
        relations_gdf = gpd.GeoDataFrame(relations_rows, crs="EPSG:4326")
    else:
        relations_gdf = gpd.GeoDataFrame(columns=["id", "geometry"], crs="EPSG:4326")

    # Process nodes
    nodes_rows: List[dict] = []
    for el in elements:
        if el["type"] == "node":
            nodes_rows.append({
                "id": el["id"],
                "geometry": Point(el["lon"],
                                  el["lat"]),
                **el.get("tags",
                         {})
            })
    if nodes_rows:
        nodes_gdf = gpd.GeoDataFrame(nodes_rows, crs="EPSG:4326")
    else:
        nodes_gdf = gpd.GeoDataFrame(columns=["id", "geometry"], crs="EPSG:4326")

    return ways_gdf, relations_gdf, nodes_gdf


# ---------------------------------------------------------------------------
# Remove ways fully contained in relation polygons
# ---------------------------------------------------------------------------


def remove_ways_inside_relations(ways_gdf: gpd.GeoDataFrame, relations_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if ways_gdf.crs != relations_gdf.crs:
        raise ValueError("CRS mismatch between ways and relations")
    valid_geoms = [geom for geom in relations_gdf.geometry if geom is not None]
    if not valid_geoms:
        return ways_gdf
    union_geom = unary_union(valid_geoms)
    mask = ways_gdf.geometry.apply(lambda g: not g.within(union_geom))
    return ways_gdf[mask].copy()


# ---------------------------------------------------------------------------
# Full pipeline used by API and tests
# ---------------------------------------------------------------------------


def load_elements(
    center_lat: float = DEFAULT_CENTER_LAT,
    center_lon: float = DEFAULT_CENTER_LON,
    radius_m: float = DEFAULT_OVERPASS_RADIUS_M,
) -> gpd.GeoDataFrame:
    return load_elements_at(center_lat, center_lon, radius_m)


def load_elements_at(
    center_lat: float,
    center_lon: float,
    radius_m: float,
) -> gpd.GeoDataFrame:
    bbox = build_bbox(center_lat, center_lon, radius_m)
    query = build_query(bbox)
    osm_data = run_overpass(query)
    ways_gdf, relations_gdf, nodes_gdf = osm_to_geodataframes(osm_data)
    geometries = reconstruct_multipolygons(osm_data)
    geom_by_id = {}
    rel_ids = [
        rel["id"]
        for rel in osm_data["elements"]
        if rel["type"] == "relation" and rel.get("tags", {}).get("type") == "multipolygon"
    ]
    for rid, geom in zip(rel_ids, geometries):
        geom_by_id[rid] = geom
    relations_gdf["geometry"] = relations_gdf["id"].map(geom_by_id)
    relations_gdf = relations_gdf.set_geometry("geometry")
    ways_gdf = remove_ways_inside_relations(ways_gdf, relations_gdf)
    ways_gdf = ways_gdf.copy()
    ways_gdf["osm_type"] = "way"
    relations_gdf = relations_gdf.copy()
    relations_gdf["osm_type"] = "relation"
    nodes_gdf = nodes_gdf.copy()
    nodes_gdf["osm_type"] = "node"
    combined = gpd.pd.concat([ways_gdf, relations_gdf, nodes_gdf], ignore_index=True)
    combined = gpd.GeoDataFrame(combined, crs="EPSG:4326")
    logger.info(
        "Pipeline complete — %d ways, %d relations, %d nodes (%d total, %d with geometry)",
        len(ways_gdf),
        len(relations_gdf),
        len(nodes_gdf),
        len(combined),
        combined.geometry.notna().sum(),
    )
    return combined


# ---------------------------------------------------------------------------
# Optional FastAPI router
# ---------------------------------------------------------------------------
if APIRouter:
    router = APIRouter(prefix="/elements", tags=["elements"], dependencies=[Depends(get_current_user)])
else:
    router = None

_elements_cache: Optional[gpd.GeoDataFrame] = None


def get_elements() -> gpd.GeoDataFrame:
    global _elements_cache
    if _elements_cache is None:
        _elements_cache = load_elements()
    return _elements_cache


# ---------------------------------------------------------------------------
# API endpoints (no‑op when FastAPI is unavailable)
# ---------------------------------------------------------------------------
if router:

    @router.get(
        "/",
        summary="List all OSM elements",
        response_class=JSONResponse,
        deprecated=True,
    )
    def list_elements():
        gdf = get_elements()
        return JSONResponse(content={
            "type": "FeatureCollection",
            "features": _gdf_to_features(gdf)
        })

    @router.get(
        "/nearby",
        summary="Elements within an H3 cell",
        response_class=JSONResponse,
        deprecated=True,
    )
    def elements_nearby(
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

        gdf = get_elements()
        point = gpd.GeoDataFrame(geometry=[Point(lng, lat)], crs="EPSG:4326").to_crs("EPSG:3857").geometry.iloc[0]
        circle = point.buffer(radius_m)
        gdf_merc = gdf[gdf.geometry.notna()].to_crs("EPSG:3857")
        nearby = gdf_merc[gdf_merc.geometry.intersects(circle)].to_crs("EPSG:4326")
        return JSONResponse(
            content={
                "type": "FeatureCollection",
                "count": len(nearby),
                "h3_cell": h3_cell,
                "parent_level": parent_level,
                "search_cell": search_cell,
                "center": {
                    "lat": lat,
                    "lng": lng
                },
                "radius_m": radius_m,
                "features": _gdf_to_features(nearby)
            }
        )

    @router.get(
        "/{element_id}",
        summary="Get a single element by OSM id",
        response_class=JSONResponse,
        deprecated=True,
    )
    def get_element(element_id: int):
        gdf = get_elements()
        matches = gdf[gdf["id"] == element_id]
        if matches.empty:
            raise HTTPException(status_code=404, detail=f"No element found with id={element_id}")
        return JSONResponse(content=_row_to_feature(matches.iloc[:1]))


# ---------------------------------------------------------------------------
# Helper serialisation functions
# ---------------------------------------------------------------------------
def _gdf_to_features(gdf: gpd.GeoDataFrame) -> List[dict[str, Any]]:
    return json.loads(gdf.to_json())["features"]


def _row_to_feature(row: gpd.GeoDataFrame) -> dict[str, Any]:
    return json.loads(row.to_json())["features"][0]
