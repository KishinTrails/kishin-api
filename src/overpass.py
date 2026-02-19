"""
OSM/Overpass data fetcher + FastAPI server.

Fetches OpenStreetMap geographic features (natural landmarks, viewpoints,
parks, forests, industrial and recreational areas) from the Overpass API,
reconstructs multipolygon relation geometries, removes redundant ways already
covered by relations, and exposes the results through a REST API.

Endpoints:
    GET /elements               — full element catalogue (ways + relations)
    GET /elements/{element_id}  — single element by OSM numeric id
    GET /elements/nearby        — elements intersecting a radius around a point
"""

import json
import hashlib
import logging
from pathlib import Path
from typing import Any, Optional

import requests
import geopandas as gpd
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pyproj import Geod
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import linemerge, polygonize, unary_union

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("overpass")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

CACHE_DIR = Path("./cache")
CACHE_DIR.mkdir(exist_ok=True)

DEFAULT_CENTER_LAT = 45.689125611
DEFAULT_CENTER_LON = 2.976995577
DEFAULT_RADIUS_M = 10_000
NEARBY_DEFAULT_RADIUS_M = 30.0

# ---------------------------------------------------------------------------
# Bounding box
# ---------------------------------------------------------------------------


def build_bbox(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    """Compute a geographic bounding box around a central point.

    Walks ``radius_m`` metres in each cardinal direction along the WGS-84
    ellipsoid and returns the extreme coordinates, producing a tight bbox
    suitable for Overpass queries.

    Args:
        lat: Latitude of the centre point, in decimal degrees.
        lon: Longitude of the centre point, in decimal degrees.
        radius_m: Radius of the area of interest, in metres.

    Returns:
        A ``(south, west, north, east)`` tuple of decimal-degree coordinates,
        matching the Overpass bounding-box argument order.
    """
    geod = Geod(ellps="WGS84")
    _, north_lat, _ = geod.fwd(lon, lat, 0, radius_m)
    _, south_lat, _ = geod.fwd(lon, lat, 180, radius_m)
    east_lon, _, _ = geod.fwd(lon, lat, 90, radius_m)
    west_lon, _, _ = geod.fwd(lon, lat, 270, radius_m)
    return south_lat, west_lon, north_lat, east_lon


# ---------------------------------------------------------------------------
# Overpass query builder
# ---------------------------------------------------------------------------


def build_query(bbox: tuple[float, float, float, float]) -> str:
    """Build the Overpass QL query string for the given bounding box.

    The query collects three categories of OSM features:

    * **Point features** — natural landmarks (peaks, volcanoes, ridges, arêtes,
      cliffs), toposcopes, and tourism viewpoints.
    * **Area relations** — multipolygon relations tagged as parks, forests,
      recreation grounds, education land, or industrial land.
    * **Standalone ways** — ways carrying the same area tags as the relations
      above, but that are *not* members of any fetched relation (to avoid
      returning geometry twice).

    All features filter out ``access=private`` and ``access=no`` to exclude
    restricted land.  The ``out body; >; out body qt;`` output strategy
    returns full tags and resolves way nodes in a single round-trip.

    Args:
        bbox: ``(south, west, north, east)`` bounding box in decimal degrees,
            as returned by :func:`build_bbox`.

    Returns:
        A complete Overpass QL query string ready to POST to the API.
    """
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
# Overpass HTTP client with file-based cache
# ---------------------------------------------------------------------------


def run_overpass(query: str) -> dict:
    """Execute an Overpass QL query, serving from a file cache when available.

    The cache key is the MD5 hash of the raw query string.  This ensures that
    structurally identical queries always hit the cache while any change to
    the query (bbox, filters, …) produces a fresh request.

    Args:
        query: A complete Overpass QL query string.

    Returns:
        The parsed JSON response as returned by the Overpass API, with the
        top-level structure ``{"version": …, "elements": […]}``.

    Raises:
        requests.HTTPError: If the Overpass API returns a non-2xx status code.
    """
    hash_key = hashlib.md5(query.encode()).hexdigest()
    cache_file = CACHE_DIR / f"{hash_key}.json"

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
# Relation → Shapely geometry reconstruction
# ---------------------------------------------------------------------------


def reconstruct_multipolygons(osm_json: dict) -> list[dict]:
    """Reconstruct Shapely polygon geometries for OSM multipolygon relations.

    OSM multipolygon relations store their boundary as an unordered collection
    of way members with ``role=outer`` (exterior ring) or ``role=inner``
    (holes).  This function handles the outer rings only: it assembles the
    individual way segments into continuous ``LineString`` s, merges them with
    :func:`shapely.ops.linemerge` to stitch shared endpoints, and converts
    the closed rings into ``Polygon`` / ``MultiPolygon`` geometries via
    :func:`shapely.ops.polygonize`.

    Inner rings (holes) are intentionally ignored — for the purpose of this
    application (area categorisation and proximity queries) the distinction
    is not required and the added complexity is not justified.

    Args:
        osm_json: Raw Overpass JSON response dict containing an ``"elements"``
            list with nodes, ways, and relations.

    Returns:
        A list of dicts, one per successfully reconstructed relation::

            {
                "id":       <int>   OSM relation id,
                "geometry": <Polygon | MultiPolygon>,
                # all OSM tags from the relation, spread as top-level keys
            }

        Relations whose outer ways cannot be polygonized (e.g. because node
        references are missing from the response) are silently skipped and
        logged at DEBUG level.
    """
    elements: list[dict] = osm_json["elements"]

    nodes: dict[int,
                tuple[float,
                      float]] = {
                          el["id"]: (el["lon"],
                                     el["lat"])
                          for el in elements
                          if el["type"] == "node"
                      }
    ways: dict[int,
               dict] = {
                   el["id"]: el
                   for el in elements
                   if el["type"] == "way"
               }
    relations = [
        el for el in elements if el["type"] == "relation" and el.get("tags", {}).get("type") == "multipolygon"
    ]

    results: list[dict] = []

    for rel in relations:
        outer_lines: list[LineString] = []

        for member in rel.get("members", []):
            if member["type"] != "way" or member["role"] != "outer":
                continue
            way = ways.get(member["ref"])
            if not way:
                continue
            coords = [nodes[nid] for nid in way.get("nodes", []) if nid in nodes]
            if len(coords) >= 2:
                outer_lines.append(LineString(coords))

        if not outer_lines:
            continue

        merged = linemerge(outer_lines)
        # linemerge returns a LineString when it produces a single line,
        # or a MultiLineString when segments cannot be fully merged.
        line_iter = [merged] if merged.geom_type == "LineString" else list(merged.geoms)
        polygons = list(polygonize(line_iter))

        if not polygons:
            logger.debug("Relation %d: could not polygonize outer rings", rel["id"])
            continue

        geom = polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
        results.append({
            "id": rel["id"],
            "geometry": geom,
            **rel.get("tags",
                      {})
        })

    return results


# ---------------------------------------------------------------------------
# OSM JSON → GeoDataFrames
# ---------------------------------------------------------------------------


def osm_to_geodataframes(osm_json: dict) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Parse a raw Overpass JSON response into two typed GeoDataFrames.

    Ways are converted to either a ``Polygon`` (when their node list forms a
    closed ring) or a ``LineString`` (open way).  Ways with fewer than two
    resolvable nodes are degenerate and are discarded.

    Relations are recorded with ``geometry=None`` at this stage; their
    geometries must be patched in afterwards with the output of
    :func:`reconstruct_multipolygons`.  This two-pass design keeps geometry
    reconstruction separate from raw data parsing.

    All OSM tags for each element are spread as top-level columns alongside
    the mandatory ``id`` and ``geometry`` columns.  Tag key collisions across
    elements within the same GeoDataFrame are handled naturally by pandas
    (missing values become ``NaN``).

    Args:
        osm_json: Raw Overpass JSON response dict with an ``"elements"`` list.

    Returns:
        A ``(ways_gdf, relations_gdf)`` pair of GeoDataFrames, both in
        ``EPSG:4326`` (WGS-84 geographic coordinates).
    """
    elements: list[dict] = osm_json["elements"]

    nodes: dict[int,
                dict] = {
                    el["id"]: el
                    for el in elements
                    if el["type"] == "node"
                }
    ways_rows: list[dict] = []
    relations_rows: list[dict] = []

    for el in elements:
        if el["type"] == "way":
            coords = [(nodes[nid]["lon"], nodes[nid]["lat"]) for nid in el.get("nodes", []) if nid in nodes]
            if len(coords) >= 3 and coords[0] == coords[-1]:
                geom: LineString | Polygon = Polygon(coords)
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

    ways_gdf = gpd.GeoDataFrame(ways_rows, crs="EPSG:4326")
    relations_gdf = gpd.GeoDataFrame(relations_rows, crs="EPSG:4326")
    return ways_gdf, relations_gdf


# ---------------------------------------------------------------------------
# Deduplication: remove ways fully contained in relation polygons
# ---------------------------------------------------------------------------


def remove_ways_inside_relations(
    ways_gdf: gpd.GeoDataFrame,
    relations_gdf: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Drop ways whose geometry lies entirely within a relation polygon.

    When a relation and a standalone way describe the same area, keeping
    both would result in duplicate features in the output.  This function
    unions all relation polygons into a single geometry and discards any way
    that is fully contained within it, using Shapely's ``within`` predicate.

    Ways that only *partially* overlap a relation (e.g. a road that crosses
    a forest boundary) are preserved.

    Args:
        ways_gdf: GeoDataFrame of OSM ways, as produced by
            :func:`osm_to_geodataframes`.
        relations_gdf: GeoDataFrame of OSM relations with reconstructed
            Shapely geometries in the ``geometry`` column.

    Returns:
        A filtered copy of ``ways_gdf`` with fully-contained ways removed.
        If ``relations_gdf`` contains no valid geometries the input is
        returned unchanged.
    """
    valid_geoms = [g for g in relations_gdf.geometry if g is not None]
    if not valid_geoms:
        return ways_gdf

    relation_union = unary_union(valid_geoms)
    mask = ways_gdf.geometry.apply(lambda g: not g.within(relation_union))
    return ways_gdf[mask].copy()


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


def load_elements(
    center_lat: float = DEFAULT_CENTER_LAT,
    center_lon: float = DEFAULT_CENTER_LON,
    radius_m: float = DEFAULT_RADIUS_M,
) -> gpd.GeoDataFrame:
    """Execute the full OSM processing pipeline and return a unified GeoDataFrame.

    Orchestrates the following steps in order:

    1. Compute the bounding box from centre + radius.
    2. Build and execute the Overpass query (with caching).
    3. Reconstruct multipolygon geometries for all area relations.
    4. Parse raw elements into typed GeoDataFrames.
    5. Patch relation geometries with the reconstructed polygons.
    6. Remove ways fully covered by a relation polygon.
    7. Tag every row with its OSM element type (``"way"`` / ``"relation"``).
    8. Merge ways and relations into a single ``EPSG:4326`` GeoDataFrame.

    This function is intended to be called once at application startup; its
    result should be cached in memory (see :func:`get_elements`).

    Args:
        center_lat: Latitude of the area centre, in decimal degrees.
        center_lon: Longitude of the area centre, in decimal degrees.
        radius_m: Radius of the area of interest, in metres.

    Returns:
        A ``GeoDataFrame`` in ``EPSG:4326`` with columns ``id``, ``geometry``,
        ``osm_type``, and all OSM tag keys found across the fetched elements.
    """
    bbox = build_bbox(center_lat, center_lon, radius_m)
    query = build_query(bbox)
    osm_data = run_overpass(query)

    reconstructed = reconstruct_multipolygons(osm_data)
    ways_gdf, relations_gdf = osm_to_geodataframes(osm_data)

    geom_by_id = {
        r["id"]: r["geometry"]
        for r in reconstructed
    }
    relations_gdf["geometry"] = relations_gdf["id"].map(lambda rid: geom_by_id.get(rid))
    relations_gdf = relations_gdf.set_geometry("geometry")

    ways_gdf = remove_ways_inside_relations(ways_gdf, relations_gdf)

    ways_gdf = ways_gdf.copy()
    ways_gdf["osm_type"] = "way"
    relations_gdf = relations_gdf.copy()
    relations_gdf["osm_type"] = "relation"

    combined: gpd.GeoDataFrame = gpd.pd.concat([ways_gdf, relations_gdf], ignore_index=True)
    combined = gpd.GeoDataFrame(combined, crs="EPSG:4326")

    logger.info(
        "Pipeline complete — %d ways, %d relations (%d total, %d with geometry)",
        len(ways_gdf),
        len(relations_gdf),
        len(combined),
        combined.geometry.notna().sum(),
    )
    return combined


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _gdf_to_features(gdf: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    """Serialise a GeoDataFrame to a list of GeoJSON Feature dicts.

    Uses GeoPandas' native ``to_json()`` path to ensure correct geometry
    serialisation (including ``null`` geometries), then parses the JSON string
    once to extract the ``features`` array.

    Args:
        gdf: Any GeoDataFrame in a geographic CRS.

    Returns:
        A list of GeoJSON Feature dicts, one per row.
    """
    return json.loads(gdf.to_json())["features"]


def _row_to_feature(row: gpd.GeoDataFrame) -> dict[str, Any]:
    """Serialise a single-row GeoDataFrame slice to a GeoJSON Feature dict.

    Args:
        row: A one-row GeoDataFrame slice (e.g. ``gdf.iloc[:1]``).

    Returns:
        A single GeoJSON Feature dict.
    """
    return json.loads(row.to_json())["features"][0]


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Kishin Trails — OSM Elements API",
    description="Serve OpenStreetMap area/point features pre-processed from Overpass.",
    version="1.0.0",
)

# Populated on the first request and reused for the lifetime of the process.
# Replace with a proper async cache or background refresh task if periodic
# invalidation is needed.
_elements_cache: Optional[gpd.GeoDataFrame] = None


def get_elements() -> gpd.GeoDataFrame:
    """Return the in-memory element cache, running the pipeline on first call.

    Acts as a lazy singleton: the full :func:`load_elements` pipeline runs
    exactly once per process and its result is kept in ``_elements_cache``
    for all subsequent requests.

    Returns:
        The unified GeoDataFrame produced by :func:`load_elements`.
    """
    global _elements_cache
    if _elements_cache is None:
        _elements_cache = load_elements()
    return _elements_cache


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get(
    "/elements",
    summary="List all OSM elements",
    response_class=JSONResponse,
)
def list_elements(
    osm_type: Optional[str] = Query(
        default=None,
        description="Filter by OSM element type: 'way' or 'relation'.",
    ),
) -> JSONResponse:
    """Return all pre-processed OSM elements as a GeoJSON FeatureCollection.

    By default the response contains both ways and relations.  Pass
    ``?osm_type=way`` or ``?osm_type=relation`` to restrict to one category.

    Args:
        osm_type: Optional filter on the ``osm_type`` column.  Must be
            ``"way"`` or ``"relation"`` if provided.

    Returns:
        A GeoJSON ``FeatureCollection`` with one Feature per OSM element.

    Raises:
        HTTPException 400: If ``osm_type`` is provided but not a recognised value.
    """
    gdf = get_elements()

    if osm_type is not None:
        if osm_type not in ("way", "relation"):
            raise HTTPException(
                status_code=400,
                detail="osm_type must be 'way' or 'relation'",
            )
        gdf = gdf[gdf["osm_type"] == osm_type]

    return JSONResponse(content={
        "type": "FeatureCollection",
        "features": _gdf_to_features(gdf),
    })


@app.get(
    "/elements/nearby",
    summary="Elements within a radius of a point",
    response_class=JSONResponse,
)
def elements_nearby(
    lat: float = Query(...,
                       description="Latitude of the query point, in decimal degrees."),
    lon: float = Query(...,
                       description="Longitude of the query point, in decimal degrees."),
    radius_m: float = Query(
        default=NEARBY_DEFAULT_RADIUS_M,
        ge=1,
        le=50_000,
        description="Search radius in metres.  Defaults to 30 m, capped at 50 km.",
    ),
) -> JSONResponse:
    """Return all OSM elements whose geometry intersects a circular search area.

    The proximity test is performed in ``EPSG:3857`` (Web Mercator) to ensure
    that the radius is interpreted in metres rather than degrees.  Results are
    reprojected back to ``EPSG:4326`` before serialisation.

    Elements with a ``null`` geometry (e.g. relations whose outer ways were
    not included in the Overpass response) are excluded from the spatial
    filter but will appear in :func:`list_elements`.

    Args:
        lat: Latitude of the search centre.
        lon: Longitude of the search centre.
        radius_m: Search radius in metres (1 – 50 000).

    Returns:
        A GeoJSON ``FeatureCollection`` augmented with a ``count`` field
        reflecting the number of matching elements.
    """
    gdf = get_elements()

    point_mercator = (
        gpd.GeoDataFrame(geometry=[Point(lon,
                                         lat)],
                         crs="EPSG:4326").to_crs("EPSG:3857").geometry.iloc[0]
    )
    search_circle = point_mercator.buffer(radius_m)

    gdf_mercator = gdf[gdf.geometry.notna()].to_crs("EPSG:3857")
    nearby = gdf_mercator[gdf_mercator.geometry.intersects(search_circle)].to_crs("EPSG:4326")

    return JSONResponse(
        content={
            "type": "FeatureCollection",
            "count": len(nearby),
            "features": _gdf_to_features(nearby),
        }
    )


@app.get(
    "/elements/{element_id}",
    summary="Get a single element by OSM id",
    response_class=JSONResponse,
)
def get_element(element_id: int) -> JSONResponse:
    """Return a single OSM element identified by its numeric OSM id.

    .. note::
        Way and relation id spaces overlap in OSM (a way and a relation can
        share the same integer id).  When both exist in the dataset, the way
        is returned.  Append ``?osm_type=relation`` on :func:`list_elements`
        and filter client-side if disambiguation is required.

    Args:
        element_id: Numeric OSM id of the element to retrieve.

    Returns:
        A GeoJSON Feature dict for the matched element.

    Raises:
        HTTPException 404: If no element with the given id exists in the dataset.
    """
    gdf = get_elements()
    matches = gdf[gdf["id"] == element_id]

    if matches.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No element found with id={element_id}",
        )

    return JSONResponse(content=_row_to_feature(matches.iloc[:1]))


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "overpass:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
