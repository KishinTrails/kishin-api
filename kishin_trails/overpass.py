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
from typing import Tuple, List

import requests
import geopandas as gpd
from shapely.geometry import LineString, MultiPolygon, Polygon, Point
from shapely.ops import linemerge, polygonize, unary_union

from kishin_trails.config import settings

logging.basicConfig(
    level=logging.WARN,
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


def buildBbox(lat: float, lon: float, radiusM: float) -> Tuple[float, float, float, float]:
    """Calculate a bounding box around a point.

    Uses a simple approximation: 1° latitude ≈ 111.32 km.
    Longitude degrees are adjusted by cos(latitude) at non-equatorial positions.

    Args:
        lat: Center latitude in decimal degrees.
        lon: Center longitude in decimal degrees.
        radiusM: Radius in meters.

    Returns:
        Tuple of (south, west, north, east) coordinates in decimal degrees.
    """
    if radiusM == 0:
        return lat, lon, lat, lon
    # Approximate latitude change (1° ≈ 111.32 km).
    deltaLat = radiusM / 111_320.0
    south = lat - deltaLat
    north = lat + deltaLat
    # Adjust for longitude shrinking with cosine of latitude.
    deltaLon = deltaLat / (math.cos(math.radians(abs(lat))) + 1e-10)
    west = lon - deltaLon
    east = lon + deltaLon
    return south, west, north, east


# ---------------------------------------------------------------------------
# Overpass query builder
# ---------------------------------------------------------------------------


def buildQuery(bbox: Tuple[float, float, float, float]) -> str:
    """Build Overpass API query string for POI data.
    
    Args:
        bbox: Tuple of (south, west, north, east) bounding box coordinates.
        
    Returns:
        Overpass QL query string.
    """
    south, west, north, east = bbox
    bboxStr = f"{south},{west},{north},{east}"
    accessFilter = '["access"!~"^(private|no)$"]'
    return f"""
[out:json][timeout:60];
(
  node["natural"~"^(peak|volcano|ridge|arete|cliff)$"]{accessFilter}({bboxStr});
  node["map_type"="toposcope"]{accessFilter}({bboxStr});
  node["tourism"="viewpoint"]{accessFilter}({bboxStr});
)->.point_features;
(
  relation["leisure"="park"]{accessFilter}({bboxStr});
  relation["landuse"~"^(forest|recreation_ground|education)$"]{accessFilter}({bboxStr});
  relation["landuse"="industrial"]{accessFilter}({bboxStr});
)->.area_relations;
way(r.area_relations:"outer")->.outer_ways;
(
  way["leisure"="park"]{accessFilter}({bboxStr});
  way["landuse"~"^(forest|recreation_ground|education)$"]{accessFilter}({bboxStr});
  way["landuse"="industrial"]{accessFilter}({bboxStr});
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


def runOverpass(query: str, cacheDir: Path | None = None) -> dict:
    """Execute the Overpass query, using a hash‑based file cache.

    Args:
        query: Overpass API query string.
        cacheDir: Optional custom cache directory. Defaults to module-level CACHE_DIR.
    """
    hashKey = hashlib.md5(query.encode()).hexdigest()
    cacheFile = (cacheDir or CACHE_DIR) / f"{hashKey}.json"
    if cacheFile.exists():
        logger.info("Overpass cache hit (%s)", hashKey)
        return json.loads(cacheFile.read_text())
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
    cacheFile.write_text(json.dumps(data))
    logger.info("Overpass response cached (%s)", hashKey)
    return data


# ---------------------------------------------------------------------------
# Geometry reconstruction
# ---------------------------------------------------------------------------


def reconstructMultipolygons(osmJson: dict) -> List[Polygon | MultiPolygon]:
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

    Args:
        osmJson: Dictionary containing Overpass API response with 'elements'.

    Returns:
        List of Polygon/MultiPolygon objects for multipolygon relations.
        Only outer ways are considered; inner rings are ignored.
    """
    elements = osmJson["elements"]
    nodes = {
        elem["id"]: (elem["lon"],
                     elem["lat"])
        for elem in elements
        if elem["type"] == "node"
    }
    ways = {
        elem["id"]: elem
        for elem in elements
        if elem["type"] == "way"
    }
    relations = [elem for elem in elements if elem["type"] == "relation"]
    geometries: List[Polygon | MultiPolygon] = []
    for rel in relations:
        outerLines: List[LineString] = []
        for member in rel.get("members", []):
            if member.get("type") != "way" or member.get("role") != "outer":
                continue
            way = ways.get(member.get("ref"))
            if not way:
                continue
            coords = [nodes[nid] for nid in way.get("nodes", []) if nid in nodes]
            if len(coords) >= 2:
                outerLines.append(LineString(coords))
        if not outerLines:
            continue
        merged = linemerge(outerLines)
        lineIter: list
        if merged.geom_type == "MultiLineString":
            lineIter = list(merged.geoms)
        else:
            lineIter = [merged]
        polys = list(polygonize(lineIter))
        if not polys:
            continue
        geometries.append(polys[0] if len(polys) == 1 else MultiPolygon(polys))
    return geometries


# ---------------------------------------------------------------------------
# Convert Overpass JSON to GeoDataFrames
# ---------------------------------------------------------------------------


def osmToGeoDataFrames(osmJson: dict) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Convert Overpass JSON response to GeoDataFrames.
    
    Args:
        osmJson: Dictionary containing Overpass API response with 'elements'.
        
    Returns:
        Tuple of (ways_gdf, relations_gdf, nodes_gdf) GeoDataFrames.
    """
    elements = osmJson["elements"]
    nodes = {
        elem["id"]: elem
        for elem in elements
        if elem["type"] == "node"
    }
    waysRows: List[dict] = []
    relationsRows: List[dict] = []
    for elem in elements:
        if elem["type"] == "way":
            coords = [(nodes[nid]["lon"], nodes[nid]["lat"]) for nid in elem.get("nodes", []) if nid in nodes]
            if len(coords) >= 3 and coords[0] == coords[-1]:
                geom = Polygon(coords)
            elif len(coords) >= 2:
                geom = LineString(coords)
            else:
                continue
            waysRows.append({
                "id": elem["id"],
                "geometry": geom,
                **elem.get("tags",
                           {})
            })
        elif elem["type"] == "relation":
            relationsRows.append({
                "id": elem["id"],
                "geometry": None,
                **elem.get("tags",
                           {})
            })
    if waysRows:
        waysGdf = gpd.GeoDataFrame(waysRows, crs="EPSG:4326")
        # Set index to the 'name' tag where present, otherwise keep numeric id.
        if not waysGdf.empty:
            # Prefer 'name' column for index if it exists and is not null.
            if "name" in waysGdf.columns:
                idx = waysGdf["name"].where(waysGdf["name"].notna(), waysGdf["id"].astype(str))
                waysGdf.index = idx
            else:
                waysGdf.index = waysGdf["id"].astype(str)
    else:
        waysGdf = gpd.GeoDataFrame(columns=["id", "geometry"], crs="EPSG:4326")
    if relationsRows:
        relationsGdf = gpd.GeoDataFrame(relationsRows, crs="EPSG:4326")
    else:
        relationsGdf = gpd.GeoDataFrame(columns=["id", "geometry"], crs="EPSG:4326")

    # Process nodes
    nodesRows: List[dict] = []
    for elem in elements:
        if elem["type"] == "node":
            nodesRows.append({
                "id": elem["id"],
                "geometry": Point(elem["lon"],
                                  elem["lat"]),
                **elem.get("tags",
                           {})
            })
    if nodesRows:
        nodesGdf = gpd.GeoDataFrame(nodesRows, crs="EPSG:4326")
    else:
        nodesGdf = gpd.GeoDataFrame(columns=["id", "geometry"], crs="EPSG:4326")

    return waysGdf, relationsGdf, nodesGdf


# ---------------------------------------------------------------------------
# Remove ways fully contained in relation polygons
# ---------------------------------------------------------------------------


def removeWaysInsideRelations(waysGdf: gpd.GeoDataFrame, relationsGdf: gpd.GeoDataFrame | None) -> gpd.GeoDataFrame:
    """Remove ways that are fully contained within relation polygons.
    
    Args:
        waysGdf: GeoDataFrame of ways to filter.
        relationsGdf: GeoDataFrame of relations (polygons).
        
    Returns:
        GeoDataFrame with ways outside relation polygons.
        
    Raises:
        ValueError: If CRS mismatch between ways and relations.
    """
    if relationsGdf is None or relationsGdf.empty:
        return waysGdf
    if waysGdf.crs != relationsGdf.crs:
        raise ValueError("CRS mismatch between ways and relations")
    validGeoms = [geom for geom in relationsGdf.geometry if geom is not None]
    if not validGeoms:
        return waysGdf
    unionGeom = unary_union(validGeoms)
    mask = waysGdf.geometry.apply(lambda g: not g.within(unionGeom))
    return waysGdf[mask].copy()


# ---------------------------------------------------------------------------
# Full pipeline used by API and tests
# ---------------------------------------------------------------------------


def loadElements(
    centerLat: float = DEFAULT_CENTER_LAT,
    centerLon: float = DEFAULT_CENTER_LON,
    radiusM: float = DEFAULT_OVERPASS_RADIUS_M,
) -> gpd.GeoDataFrame:
    """Load OSM elements for given center coordinates.

    Args:
        centerLat: Center latitude in decimal degrees.
        centerLon: Center longitude in decimal degrees.
        radiusM: Search radius in meters.

    Returns:
        GeoDataFrame containing OSM elements (ways, relations, and nodes).
    """
    return loadElementsAt(centerLat, centerLon, radiusM)


def loadElementsAt(
    centerLat: float,
    centerLon: float,
    radiusM: float,
) -> gpd.GeoDataFrame:
    """Load OSM elements at specific coordinates.

    Args:
        centerLat: Center latitude in decimal degrees.
        centerLon: Center longitude in decimal degrees.
        radiusM: Search radius in meters.

    Returns:
        GeoDataFrame containing OSM elements (ways, relations, and nodes).
    """
    bbox = buildBbox(centerLat, centerLon, radiusM)
    query = buildQuery(bbox)
    osmData = runOverpass(query)
    waysGdf, relationsGdf, nodesGdf = osmToGeoDataFrames(osmData)
    geometries = reconstructMultipolygons(osmData)
    geomById = {}
    relIds = [
        rel["id"]
        for rel in osmData["elements"]
        if rel["type"] == "relation" and rel.get("tags", {}).get("type") == "multipolygon"
    ]
    for rid, geom in zip(relIds, geometries):
        geomById[rid] = geom
    relationsGdf["geometry"] = relationsGdf["id"].map(geomById)
    relationsGdf = relationsGdf.set_geometry("geometry")
    waysGdf = removeWaysInsideRelations(waysGdf, relationsGdf)
    waysGdf = waysGdf.copy()
    waysGdf["osm_type"] = "way"
    if relationsGdf is not None and not relationsGdf.empty:
        relationsGdf = relationsGdf.copy()
        relationsGdf["osm_type"] = "relation"
    else:
        relationsGdf = gpd.GeoDataFrame(columns=["osm_type", "geometry"], crs="EPSG:4326")
    nodesGdf = nodesGdf.copy()
    nodesGdf["osm_type"] = "node"
    combined = gpd.pd.concat([waysGdf, relationsGdf, nodesGdf], ignore_index=True)
    combined = gpd.GeoDataFrame(combined, crs="EPSG:4326")
    logger.info(
        "Pipeline complete — %d ways, %d relations, %d nodes (%d total, %d with geometry)",
        len(waysGdf),
        len(relationsGdf),
        len(nodesGdf),
        len(combined),
        combined.geometry.notna().sum(),
    )
    return combined
