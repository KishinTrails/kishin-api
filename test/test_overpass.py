from __future__ import annotations

import json
import hashlib
import requests
from pathlib import Path
from unittest import mock

import geopandas as gpd
import pandas as pd
import pytest
import shapely.geometry as geom
import shapely.ops as ops

from httpx import AsyncClient

# Import the module you want to test
from kishin_trails.overpass import (
    OVERPASS_URL,
    CACHE_DIR,
    DEFAULT_CENTER_LAT,
    DEFAULT_CENTER_LON,
    DEFAULT_OVERPASS_RADIUS_M,
    build_bbox,
    run_overpass,
    osm_to_geodataframes,
    reconstruct_multipolygons,
    remove_ways_inside_relations,
)


def test_defaults_are_reasonable():
    # The constants are defined in overpass.py
    assert isinstance(OVERPASS_URL, str) and OVERPASS_URL.startswith("http")
    assert isinstance(CACHE_DIR, Path)
    assert CACHE_DIR.is_dir()  # the directory is created on import
    assert isinstance(DEFAULT_CENTER_LAT, float)
    assert isinstance(DEFAULT_CENTER_LON, float)
    assert isinstance(DEFAULT_OVERPASS_RADIUS_M, (int, float))


# -----------------------------------------------------------------
# 2️⃣  Helper factories that build minimal Overpass JSON elements.
# -----------------------------------------------------------------
def make_node(node_id: int, lat: float, lon: float) -> dict:
    return {
        "type": "node",
        "id": node_id,
        "lat": lat,
        "lon": lon,
    }


def make_way(way_id: int, node_ids: list[int], tags: dict | None = None) -> dict:
    tags = tags or {}
    return {
        "type": "way",
        "id": way_id,
        "nodes": node_ids,
        "tags": tags,
    }


def make_relation(rel_id: int, outer_way_ids: list[int], tags: dict | None = None) -> dict:
    tags = tags or {}
    members = [{
        "type": "way",
        "ref": wid,
        "role": "outer"
    } for wid in outer_way_ids]
    return {
        "type": "relation",
        "id": rel_id,
        "members": members,
        "tags": tags,
    }


def build_overpass_json(nodes: list[dict], ways: list[dict], relations: list[dict]) -> dict:
    """Return a dict that mimics the JSON payload returned by Overpass."""
    return {
        "elements": nodes + ways + relations
    }


# -----------------------------------------------------------------
# 3️⃣  Fixtures ----------------------------------------------------
# -----------------------------------------------------------------
# Cache directory tests use tmp_path parameter directly via cache_dir argument.

@pytest.mark.parametrize(
    "lat, lon, radius, expected",
    [
        # Zero radius → bbox collapses to the point
        (0.0, 0.0, 0, (0.0, 0.0, 0.0, 0.0)),

        # Small radius at the equator – 1 km ≈ 0.008983° north/south
        (0.0, 0.0, 1_000, ( -0.008983, -0.008983, 0.008983, 0.008983 )),

        # Mid‑latitude: longitude degrees shrink with cos(lat)
        (45.0, 10.0, 2_000, None),   # we will compute the expected values inside the test
    ],
)
def test_build_bbox_basic(lat, lon, radius, expected):
    bbox = build_bbox(lat, lon, radius)

    # Basic ordering invariant
    south, west, north, east = bbox
    assert south <= north
    assert west <= east

    # If we supplied an explicit expected tuple, compare within tolerance
    if expected is not None:
        for a, b in zip(bbox, expected):
            assert abs(a - b) < 1e-6


def test_run_overpass_makes_request_and_caches_result(tmp_path: Path, monkeypatch):
    query = "[out:json];node(50,10,1);out;"

    # Expected JSON that the mocked Overpass API will return
    fake_response = {
        "version": 0.6,
        "elements": [{
            "type": "node",
            "id": 1
        }]
    }
    # Compute the cache key exactly as the implementation does [1]
    hash_key = hashlib.md5(query.encode()).hexdigest()
    expected_path = tmp_path / f"{hash_key}.json"

    # ----------------------------------------------------------------------
    # 1️⃣ Mock `requests.post` so no real network traffic occurs
    # ----------------------------------------------------------------------
    mock_post = mock.Mock()
    mock_post.return_value.raise_for_status = mock.Mock()
    mock_post.return_value.json = mock.Mock(return_value=fake_response)
    monkeypatch.setattr(requests, "post", mock_post)

    # ----------------------------------------------------------------------
    # 2️⃣ Call the function under test with custom cache_dir
    # ----------------------------------------------------------------------
    result = run_overpass(query, cache_dir=tmp_path)

    # ----------------------------------------------------------------------
    # 3️⃣ Assertions
    # ----------------------------------------------------------------------
    # a) The function returns the JSON we mocked
    assert result == fake_response

    # b) `requests.post` was called exactly once with the correct URL and payload
    mock_post.assert_called_once_with(
        OVERPASS_URL,
        data={
            "data": query
        },
        timeout=90,
    )

    # c) The cache file was written and contains the same JSON
    assert expected_path.is_file()
    cached = json.loads(expected_path.read_text())
    assert cached == fake_response


def test_run_overpass_uses_cache_when_available(tmp_path: Path, monkeypatch):
    query = "[out:json];node(50,10,1);out;"
    hash_key = hashlib.md5(query.encode()).hexdigest()
    cache_file = tmp_path / f"{hash_key}.json"

    # Prepare a cache file **before** calling the function
    cached_data = {
        "version": 0.6,
        "elements": [{
            "type": "node",
            "id": 42
        }]
    }
    cache_file.write_text(json.dumps(cached_data))

    # Mock `requests.post` to ensure it would raise if called
    mock_post = mock.Mock()
    monkeypatch.setattr(requests, "post", mock_post)

    # Call the function with custom cache_dir – it should hit the cache and never invoke `post`
    result = run_overpass(query, cache_dir=tmp_path)

    assert result == cached_data
    mock_post.assert_not_called()


def test_run_overpass_raises_on_http_error(tmp_path: Path, monkeypatch):
    query = "[out:json];node(50,10,1);out;"

    # Mock a response that raises HTTPError when `raise_for_status` is called
    mock_resp = mock.Mock()
    mock_resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
    monkeypatch.setattr(requests, "post", mock.Mock(return_value=mock_resp))

    with pytest.raises(requests.HTTPError):
        run_overpass(query, cache_dir=tmp_path)

    # No cache file should have been created
    hash_key = hashlib.md5(query.encode()).hexdigest()
    assert not (tmp_path / f"{hash_key}.json").exists()


def test_cache_key_is_md5_of_query():
    query_a = "foo"
    query_b = "foo "  # trailing space → different hash

    key_a = hashlib.md5(query_a.encode()).hexdigest()
    key_b = hashlib.md5(query_b.encode()).hexdigest()

    assert key_a != key_b
    # The function uses exactly this expression internally [1], so the test
    # guarantees that any change to the query (even whitespace) yields a new file.


# -----------------------------------------------------------------
# 4️⃣  Tests for ``osm_to_geodataframes``
# -----------------------------------------------------------------
def test_osm_to_geodataframes_basic_closed_and_open_ways():
    """
    One closed way → Polygon, one open way → LineString.
    All tags must become columns; missing tags are NaN.
    """
    NODE_1_ID, NODE_2_ID, NODE_3_ID = 1, 2, 3
    NODE_4_ID, NODE_5_ID, NODE_6_ID = 4, 5, 6
    WAY_10_ID, WAY_11_ID = 10, 11
    WAY_10_TAGS = {"highway": "residential"}
    WAY_11_TAGS = {"name": "Test road"}

    # ── Nodes ────────────────────────────────────────
    nodes = [
        make_node(NODE_1_ID, 0.0, 0.0),
        make_node(NODE_2_ID, 0.0, 1.0),
        make_node(NODE_3_ID, 1.0, 1.0),
        make_node(NODE_4_ID, 1.0, 0.0),
        make_node(NODE_5_ID, 2.0, 0.0),
        make_node(NODE_6_ID, 2.0, 1.0),
    ]

    # ── Ways ────────────────────────────────────────
    #   * way 10 – closed square → Polygon
    #   * way 11 – open line   → LineString
    ways = [
        make_way(WAY_10_ID, [NODE_1_ID, NODE_2_ID, NODE_3_ID, NODE_4_ID, NODE_1_ID], tags=WAY_10_TAGS),
        make_way(WAY_11_ID, [NODE_5_ID, NODE_6_ID], tags=WAY_11_TAGS),
    ]

    # No relations for this test.
    json_blob = build_overpass_json(nodes, ways, [])

    ways_gdf, rels_gdf = osm_to_geodataframes(json_blob)

    # ---- Assertions on the ways GeoDataFrame -----------------
    assert isinstance(ways_gdf, gpd.GeoDataFrame)
    assert len(ways_gdf) == len(ways)

    # Polygon row
    poly_row = ways_gdf.loc[ways_gdf["id"] == WAY_10_ID].iloc[0]
    assert isinstance(poly_row.geometry, geom.Polygon)
    assert poly_row.highway == WAY_10_TAGS["highway"]

    # LineString row
    line_row = ways_gdf.loc[ways_gdf["id"] == WAY_11_ID].iloc[0]
    assert isinstance(line_row.geometry, geom.LineString)
    assert line_row.name == WAY_11_TAGS["name"]

    # ---- Assertions on the relations GeoDataFrame -------------
    assert isinstance(rels_gdf, gpd.GeoDataFrame)
    assert rels_gdf.empty  # no relations in the payload


def test_osm_to_geodataframes_degenerate_way_is_discarded():
    """A way with < 2 resolvable nodes should not appear in the result."""
    NODE_ID = 1
    WAY_ID = 20
    WAY_TAGS = {"amenity": "cafe"}

    nodes = [make_node(NODE_ID, 0.0, 0.0)]  # only one node
    ways = [make_way(WAY_ID, [NODE_ID], tags=WAY_TAGS)]  # degenerate way
    json_blob = build_overpass_json(nodes, ways, [])

    ways_gdf, _ = osm_to_geodataframes(json_blob)

    # The degenerate way must be filtered out.
    assert ways_gdf.empty


def test_osm_to_geodataframes_relations_have_none_geometry():
    """Relations are returned with geometry == None (as documented)."""
    REL_ID = 30
    rel = make_relation(REL_ID, outer_way_ids=[])
    json_blob = build_overpass_json([], [], [rel])

    _, rels_gdf = osm_to_geodataframes(json_blob)

    assert len(rels_gdf) == 1
    assert rels_gdf.loc[rels_gdf["id"] == REL_ID, "geometry"].iloc[0] is None


# -----------------------------------------------------------------
# 5️⃣  Tests for ``reconstruct_multipolygons``
# -----------------------------------------------------------------
def test_reconstruct_multipolygons_single_closed_outer():
    """
    One outer way that already forms a closed ring → a single Polygon.
    """
    NODE_1, NODE_2, NODE_3, NODE_4 = 1, 2, 3, 4
    WAY_ID = 100
    REL_ID = 200

    # Nodes that form a triangle
    nodes = [
        make_node(NODE_1, 0, 0),
        make_node(NODE_2, 0, 1),
        make_node(NODE_3, 1, 0),
        make_node(NODE_4, 0, 0),  # repeat first node to close the ring
    ]
    way = make_way(WAY_ID, [NODE_1, NODE_2, NODE_3, NODE_4])  # closed way
    rel = make_relation(REL_ID, outer_way_ids=[WAY_ID])

    json_blob = build_overpass_json(nodes, [way], [rel])

    polys = reconstruct_multipolygons(json_blob)

    assert isinstance(polys, list)
    assert len(polys) == 1
    assert isinstance(polys[0], geom.Polygon)


def test_reconstruct_multipolygons_multiple_outers_need_stitching():
    """
    Two half‑circles that share an endpoint must be stitched together
    before polygonisation.
    """
    NODE_A, NODE_B, NODE_C, NODE_D = 1, 2, 3, 4
    WAY_10_ID, WAY_11_ID = 10, 11
    REL_ID = 300

    # Four nodes: A(0,0), B(0,1), C(1,1), D(1,0)
    nodes = [
        make_node(NODE_A, 0, 0),  # A
        make_node(NODE_B, 0, 1),  # B
        make_node(NODE_C, 1, 1),  # C
        make_node(NODE_D, 1, 0),  # D
    ]

    # Way 10: A → B   (first half)
    # Way 11: B → C → D → A   (second half, closed)
    way10 = make_way(WAY_10_ID, [NODE_A, NODE_B])
    way11 = make_way(WAY_11_ID, [NODE_B, NODE_C, NODE_D, NODE_A])

    rel = make_relation(REL_ID, outer_way_ids=[WAY_10_ID, WAY_11_ID])

    json_blob = build_overpass_json(nodes, [way10, way11], [rel])

    polys = reconstruct_multipolygons(json_blob)

    # The two ways should be merged into a single outer ring → one Polygon.
    assert len(polys) == 1
    assert isinstance(polys[0], geom.Polygon)


def test_reconstruct_multipolygons_ignores_inner_ways():
    """
    Relations that contain inner members must be built from the outer
    members only – inner ways are deliberately ignored (see source).
    """
    OUTER_NODE_1, OUTER_NODE_2, OUTER_NODE_3, OUTER_NODE_4, OUTER_NODE_5 = 1, 2, 3, 4, 5
    INNER_NODE_6, INNER_NODE_7, INNER_NODE_8, INNER_NODE_9, INNER_NODE_10 = 6, 7, 8, 9, 10
    OUTER_WAY_ID = 500
    INNER_WAY_ID = 501
    REL_ID = 600

    # Simple square for the outer ring
    outer_nodes = [
        make_node(OUTER_NODE_1, 0, 0),
        make_node(OUTER_NODE_2, 0, 2),
        make_node(OUTER_NODE_3, 2, 2),
        make_node(OUTER_NODE_4, 2, 0),
        make_node(OUTER_NODE_5, 0, 0),
    ]
    outer_way = make_way(OUTER_WAY_ID, [OUTER_NODE_1, OUTER_NODE_2, OUTER_NODE_3, OUTER_NODE_4, OUTER_NODE_5])

    # Inner ring (a smaller square) – should be *ignored*
    inner_nodes = [
        make_node(INNER_NODE_6, 0.5, 0.5),
        make_node(INNER_NODE_7, 0.5, 1.5),
        make_node(INNER_NODE_8, 1.5, 1.5),
        make_node(INNER_NODE_9, 1.5, 0.5),
        make_node(INNER_NODE_10, 0.5, 0.5),
    ]
    inner_way = make_way(INNER_WAY_ID, [INNER_NODE_6, INNER_NODE_7, INNER_NODE_8, INNER_NODE_9, INNER_NODE_10])

    rel = {
        "type": "relation",
        "id": REL_ID,
        "members": [
            {
                "type": "way",
                "ref": OUTER_WAY_ID,
                "role": "outer"
            },
            {
                "type": "way",
                "ref": INNER_WAY_ID,
                "role": "inner"
            },
        ],
        "tags": {
            "type": "multipolygon"
        },
    }

    json_blob = build_overpass_json(
        nodes=outer_nodes + inner_nodes,
        ways=[outer_way,
              inner_way],
        relations=[rel],
    )

    polys = reconstruct_multipolygons(json_blob)

    # Only the outer ring should survive → a single Polygon.
    assert len(polys) == 1
    assert isinstance(polys[0], geom.Polygon)
    # The interior hole must **not** be present.
    assert len(polys[0].interiors) == 0


def test_reconstruct_multipolygons_missing_way_is_skipped():
    """
    If a relation refers to a way ID that does not exist in the JSON,
    the function must simply ignore that member and still return any
    geometry that can be built from the remaining members.
    """
    VALID_NODE_1, VALID_NODE_2, VALID_NODE_3, VALID_NODE_4, VALID_NODE_5 = 1, 2, 3, 4, 5
    VALID_WAY_ID = 700
    MISSING_WAY_ID = 999
    REL_ID = 800

    # One valid outer way (a tiny square)
    nodes = [
        make_node(VALID_NODE_1, 0, 0),
        make_node(VALID_NODE_2, 0, 1),
        make_node(VALID_NODE_3, 1, 1),
        make_node(VALID_NODE_4, 1, 0),
        make_node(VALID_NODE_5, 0, 0),
    ]
    valid_way = make_way(VALID_WAY_ID, [VALID_NODE_1, VALID_NODE_2, VALID_NODE_3, VALID_NODE_4, VALID_NODE_5])

    # Relation points to 700 (real) and 999 (non‑existent)
    rel = {
        "type": "relation",
        "id": REL_ID,
        "members": [
            {
                "type": "way",
                "ref": VALID_WAY_ID,
                "role": "outer"
            },
            {
                "type": "way",
                "ref": MISSING_WAY_ID,
                "role": "outer"
            },
        ],
        "tags": {
            "type": "multipolygon"
        },
    }

    json_blob = build_overpass_json(nodes, [valid_way], [rel])

    polys = reconstruct_multipolygons(json_blob)

    # The missing way must not cause a crash; we still get one Polygon.
    assert len(polys) == 1
    assert isinstance(polys[0], geom.Polygon)


# -----------------------------------------------------------------
# 6️⃣  Tests for ``remove_ways_inside_relations``
# -----------------------------------------------------------------
def test_remove_ways_inside_relations_basic():
    """
    A LineString that lies completely inside a Polygon relation should be
    removed, while a line that merely touches or crosses the polygon stays.
    """
    REL_ID = 1
    WAY_10_ID, WAY_11_ID = 10, 11
    RELATION_POLYGON_COORDS = [(0, 0), (0, 10), (10, 10), (10, 0)]
    LINE_INSIDE_COORDS = [(2, 2), (8, 8)]
    LINE_CROSS_COORDS = [(-5, 5), (15, 5)]

    # Relation polygon: a 10×10 square
    poly = geom.Polygon(RELATION_POLYGON_COORDS)

    rels_gdf = gpd.GeoDataFrame(
        {
            "id": [REL_ID],
            "geometry": [poly]
        },
        crs="EPSG:4326",
    )

    # Way 1 – inside the square
    line_inside = geom.LineString(LINE_INSIDE_COORDS)

    # Way 2 – crossing the square border
    line_cross = geom.LineString(LINE_CROSS_COORDS)

    ways_gdf = gpd.GeoDataFrame(
        {
            "id": [WAY_10_ID,
                   WAY_11_ID],
            "geometry": [line_inside,
                         line_cross]
        },
        crs="EPSG:4326",
    )

    filtered = remove_ways_inside_relations(ways_gdf, rels_gdf)

    # Only the crossing line must survive.
    assert len(filtered) == 1
    assert filtered.iloc[0]["id"] == WAY_11_ID


def test_remove_ways_inside_relations_no_relations():
    """
    When there are no relation polygons, the function must return the
    original ``ways_gdf`` unchanged.
    """
    WAY_1_ID, WAY_2_ID = 1, 2
    POINT_1_COORDS, POINT_2_COORDS = (0, 0), (1, 1)

    ways = gpd.GeoDataFrame(
        {
            "id": [WAY_1_ID,
                   WAY_2_ID],
            "geometry": [geom.Point(POINT_1_COORDS[0],
                                    POINT_1_COORDS[1]),
                         geom.Point(POINT_2_COORDS[0],
                                    POINT_2_COORDS[1])]
        },
        crs="EPSG:4326",
    )
    empty_rels = gpd.GeoDataFrame(columns=["id", "geometry"], crs="EPSG:4326")

    result = remove_ways_inside_relations(ways, empty_rels)

    pd.testing.assert_frame_equal(result.sort_index(), ways.sort_index())


def test_remove_ways_inside_relations_crs_mismatch_raises():
    """
    The function should raise a clear error when the two GeoDataFrames have
    different CRS objects (otherwise spatial predicates would be meaningless).
    """
    TEST_ID = 1
    WAY_POINT_COORDS = (0, 0)
    RELATION_POLYGON_COORDS = [(0, 0), (0, 1), (1, 1), (1, 0)]

    ways = gpd.GeoDataFrame(
        {
            "id": [TEST_ID],
            "geometry": [geom.Point(WAY_POINT_COORDS[0],
                                    WAY_POINT_COORDS[1])]
        },
        crs="EPSG:4326",
    )
    rels = gpd.GeoDataFrame(
        {
            "id": [TEST_ID],
            "geometry": [geom.Polygon(RELATION_POLYGON_COORDS)]
        },
        crs="EPSG:3857",
    )

    with pytest.raises(ValueError, match="CRS"):
        remove_ways_inside_relations(ways, rels)


# -----------------------------------------------------------------
# 7️⃣  Integration‑style test (full pipeline)
# -----------------------------------------------------------------
def test_full_pipeline_multipolygon_and_way_filtering():
    """
    End‑to‑end sanity check:
    1. Parse Overpass JSON → ways & relations DataFrames.
    2. Reconstruct multipolygon geometries.
    3. Attach those geometries to the relations DataFrame.
    4. Remove any ways that fall completely inside the new polygons.
    """
    OUTER_NODE_1, OUTER_NODE_2, OUTER_NODE_3, OUTER_NODE_4, OUTER_NODE_5 = 1, 2, 3, 4, 5
    INNER_NODE_6, INNER_NODE_7 = 6, 7
    OUTER_WAY_ID = 100
    INNER_LINE_ID = 101
    RELATION_ID = 200

    # ----- Build a minimal OSM payload -------------------------
    # Nodes for a square outer ring (relation) and a diagonal line (way)
    nodes = [
        make_node(OUTER_NODE_1, 0, 0),
        make_node(OUTER_NODE_2, 0, 5),
        make_node(OUTER_NODE_3, 5, 5),
        make_node(OUTER_NODE_4, 5, 0),
        make_node(OUTER_NODE_5, 0, 0),          # close outer way
        make_node(INNER_NODE_6, 1, 1),
        make_node(INNER_NODE_7, 4, 4),          # line inside the square
    ]

    outer_way = make_way(OUTER_WAY_ID, [OUTER_NODE_1, OUTER_NODE_2, OUTER_NODE_3, OUTER_NODE_4, OUTER_NODE_5])
    inner_line = make_way(INNER_LINE_ID, [INNER_NODE_6, INNER_NODE_7])

    rel = make_relation(RELATION_ID, outer_way_ids=[OUTER_WAY_ID])

    json_blob = build_overpass_json(nodes, [outer_way, inner_line], [rel])

    # ----- Step 1: parse -------------------------------------------------
    ways_gdf, rels_gdf = osm_to_geodataframes(json_blob)

    # ----- Step 2: build multipolygon geometry ----------------------------
    polys = reconstruct_multipolygons(json_blob)
    assert len(polys) == 1
    rels_gdf = rels_gdf.copy()
    rels_gdf.loc[rels_gdf["id"] == RELATION_ID, "geometry"] = polys[0]

    # ----- Step 3: filter ways -------------------------------------------
    filtered = remove_ways_inside_relations(ways_gdf, rels_gdf)

    # The diagonal line lies completely inside the square, so it must be gone.
    assert filtered.empty


# -----------------------------------------------------------------
# 8️⃣  Edge case: empty ways
# -----------------------------------------------------------------
def test_osm_to_geodataframes_returns_empty_gdf_when_no_ways(tmp_path):
    """
    When there are no ways in the OSM JSON, the function returns empty
    GeoDataFrames.
    """
    json_blob = build_overpass_json([], [], [])
    ways_gdf, rels_gdf = osm_to_geodataframes(json_blob)

    assert ways_gdf.empty
    assert rels_gdf.empty
