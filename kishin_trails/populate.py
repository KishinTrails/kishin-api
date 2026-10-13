"""
Populating the cache with POI data for S2 tiles.

Takes one or more S2 tile IDs, expands them to level 16 tiles, deduplicates the
children, and populates the cache with POI data for each tile. Used by
``kishin cache populate`` (see ``kishin_trails/cli/cache.py``); this module holds the
logic so the CLI command itself stays thin.
"""

from __future__ import annotations

import logging
import time

import requests
from shapely.geometry import MultiPolygon, Point, Polygon
from sqlalchemy import text
from tqdm import tqdm

from kishin_trails import database
from kishin_trails.cache import getAllPostProcessingPois, getTile, getTilesForPostProcessingPoi, setTile
from kishin_trails.models import PostProcessingPoI, Tile
from kishin_trails.overpass import loadElementsAtBounds
from kishin_trails.poi import filterWaypointsForCache
from kishin_trails.utils import (
    getS2CellBounds,
    getS2CellLevel,
    latLngToS2Cell,
    s2CellsFromPolygon,
    s2CellToChildren,
    s2CellToParent,
)

logger = logging.getLogger("populate")


def insertOrGetPostProcessingPoi(osmId: int, name: str | None, tileType: str):
    """Inserts a PostProcessingPoI, or returns the id of the existing one.

    Used for polygon features (forests, parks, industrial zones) that span multiple
    S2 tiles. The POI is stored separately and linked to tiles via a junction table,
    allowing a second pass to fill interior tiles with the correct tile_type.
    """
    session = database.SESSION_LOCAL()
    try:
        existing = session.query(PostProcessingPoI).filter(PostProcessingPoI.osm_id == osmId).first()
        if existing:
            return existing.id
        poi = PostProcessingPoI(osm_id=osmId, name=name, tile_type=tileType)
        session.add(poi)
        session.commit()
        session.refresh(poi)
        return poi.id
    finally:
        session.close()


def insertJunctionEntry(tileS2Cell: str, poiId: int) -> None:
    """Links a polygon POI to a tile, so a later pass can fill its interior tiles."""
    session = database.SESSION_LOCAL()
    try:
        # INSERT OR IGNORE: the same polygon can cover a tile more than once.
        session.execute(
            text(
                "INSERT OR IGNORE INTO tile_post_processing_pois "
                "(tile_s2_cell_id, post_processing_poi_id) VALUES (:tile, :poiId)"
            ),
            {
                "tile": tileS2Cell,
                "poiId": poiId
            },
        )
        session.commit()
    finally:
        session.close()


def setTileType(s2Cell: str, tileType: str) -> None:
    """Sets ``tile_type`` on an existing tile; used to fill polygon interiors."""
    session = database.SESSION_LOCAL()
    try:
        tile = session.query(Tile).filter(Tile.s2_cell_id == s2Cell).first()
        if tile:
            tile.tile_type = tileType
            session.commit()
    finally:
        session.close()


def deletePostProcessingPoiAndJunctions(poiId: int) -> None:
    """Removes a PostProcessingPoI and its junction rows once its interiors are filled."""
    session = database.SESSION_LOCAL()
    try:
        session.execute(
            text("DELETE FROM tile_post_processing_pois WHERE post_processing_poi_id = :poiId"),
            {
                "poiId": poiId
            },
        )
        session.query(PostProcessingPoI).filter(PostProcessingPoI.id == poiId).delete()
        session.commit()
    finally:
        session.close()


def populateCacheForTiles(s2Cells: list[str], skipCached: bool = True, queryResolution: int = 9) -> None:
    """Populates the cache using one Overpass query per parent tile.

    Instead of querying Overpass for each level-16 tile individually, this:

    1. Groups input tiles by their level-9 (or configurable) parent.
    2. Makes one Overpass query per parent tile.
    3. Distributes elements to their correct level-16 tiles based on geometry.
    4. Caches each level-16 tile separately.

    This reduces network calls by roughly 100x for large areas.

    Args:
        s2Cells: Parent S2 cell tokens (level <= 16).
        skipCached: If True, skip tiles that already exist in the database.
        queryResolution: S2 level for grouping queries. Lower means fewer,
            larger queries.
    """
    if queryResolution > 16:
        raise ValueError(f"Query resolution must be <= 16, got {queryResolution}")

    allLevel16Children: list[str] = []
    for parentCell in s2Cells:
        res = getS2CellLevel(parentCell)
        if res > 16:
            logger.warning("S2 cell level must be <= 16, got %d for %s; skipping", res, parentCell)
            continue

        if res < 16:
            allLevel16Children.extend(s2CellToChildren(parentCell, 16))
        else:
            allLevel16Children.append(parentCell)

    uniqueLevel16Children = list(dict.fromkeys(allLevel16Children))
    logger.info("Collected %d level-16 tiles from %d parent tile(s)", len(uniqueLevel16Children), len(s2Cells))

    parentTiles: set[str] = set()
    for childCell in uniqueLevel16Children:
        res = getS2CellLevel(childCell)
        if res > queryResolution:
            parentTiles.add(s2CellToParent(childCell, queryResolution))
        else:
            parentTiles.add(childCell)

    logger.info("Grouped into %d parent tile(s) at level %d for querying", len(parentTiles), queryResolution)

    elementsByTile: dict[str, list[dict]] = {}
    polygonProcessing: list[tuple[int, str | None, str, Polygon | MultiPolygon]] = []

    for parentTile in tqdm(sorted(parentTiles, reverse=True), desc="Querying parent tiles"):
        try:
            bounds = getS2CellBounds(parentTile)
        except ValueError as error:
            logger.warning("Skipping parent tile %s: %s", parentTile, error)
            continue

        retryDelay = 5
        gdf = None
        while True:
            try:
                gdf = loadElementsAtBounds(bounds)
                break
            except requests.exceptions.HTTPError as error:
                if error.response is not None and error.response.status_code in (429, 504):
                    logger.warning(
                        "Overpass API error %s for parent tile %s, retrying in %ds",
                        error.response.status_code,
                        parentTile,
                        retryDelay,
                    )
                    time.sleep(retryDelay)
                    retryDelay *= 2
                else:
                    raise

        if gdf is None:
            continue

        for _, row in gdf.iterrows():
            tags = dict(row.items())
            geometry = tags.get("geometry")
            if geometry is None:
                raise AssertionError("Geometry not present in element!")

            if isinstance(geometry, Point):
                level16Cell = latLngToS2Cell(geometry.y, geometry.x, 16)
                if level16Cell not in uniqueLevel16Children:
                    continue
                elementsByTile.setdefault(level16Cell, []).append({"id": row["id"], "tags": tags})

            elif isinstance(geometry, (MultiPolygon, Polygon)):
                tileType = None
                if tags.get("landuse") == "industrial":
                    tileType = "industrial"
                elif tags.get("landuse") == "forest" or tags.get("leisure") == "park":
                    tileType = "natural"

                if tileType:
                    polygonProcessing.append((row["id"], tags.get("name"), tileType, geometry))
                    for cell in _s2CellsFromGeometry(geometry, 16):
                        if cell in uniqueLevel16Children:
                            elementsByTile.setdefault(cell, []).append({"id": row["id"], "tags": tags})

    logger.info("Processing %d polygon(s) for post-processing...", len(polygonProcessing))
    for osmId, name, tileType, geometry in tqdm(polygonProcessing, desc="Preprocessing polygons"):
        poiId = insertOrGetPostProcessingPoi(osmId, name, tileType)
        for cell in _s2CellsFromGeometry(geometry, 16):
            if cell in uniqueLevel16Children:
                insertJunctionEntry(cell, poiId)

    processed = 0
    skipped = 0
    for level16Cell in tqdm(uniqueLevel16Children, desc="Caching tiles"):
        if skipCached and getTile(level16Cell):
            skipped += 1
            continue
        elements = elementsByTile.get(level16Cell, [])
        waypoints, tileType = filterWaypointsForCache(elements)
        setTile(level16Cell, tileType, waypoints)
        processed += 1

    logger.info("Finished: processed %d tiles, skipped %d tiles", processed, skipped)


def _s2CellsFromGeometry(geometry: Polygon | MultiPolygon, level: int) -> list[str]:
    """S2 cell tokens covering a Polygon or MultiPolygon at the given level."""
    if isinstance(geometry, Polygon):
        return s2CellsFromPolygon(geometry, level)
    cells: list[str] = []
    for poly in geometry.geoms:
        cells.extend(s2CellsFromPolygon(poly, level))
    return cells


def fillPolygonInteriors() -> None:
    """Second pass: fills interior tiles of stored polygon features.

    After the first pass, polygon features (forests, parks, industrial zones) are
    stored separately with links to every S2 cell they cover. This sets ``tile_type``
    on linked tiles that don't have one yet — those that contain only the polygon
    interior, with no boundary feature of their own — then discards the temporary
    polygon data.
    """
    pois = getAllPostProcessingPois()
    logger.info("Found %d polygon(s) to process", len(pois))

    for poi in tqdm(pois, desc="Post-processing PoIs"):
        tiles = getTilesForPostProcessingPoi(poi["id"])
        for tileS2Cell in tiles:
            tile = getTile(tileS2Cell)
            # Only fill tiles that exist and have no type yet; this preserves
            # point-based POIs (peaks), which take priority over the polygon.
            if tile and tile.get("tile_type") is None:
                setTileType(tileS2Cell, poi["tile_type"])
        deletePostProcessingPoiAndJunctions(poi["id"])


def parseS2Cells(s2CellsStr: str) -> list[str]:
    """Parses a comma-separated string of S2 cell tokens, validated at level <= 16."""
    cells = [cell.strip() for cell in s2CellsStr.split(",") if cell.strip()]
    if not cells:
        raise ValueError("No S2 cell IDs provided")

    for cell in cells:
        try:
            res = getS2CellLevel(cell)
        except ValueError as error:
            raise ValueError(f"Invalid S2 cell: {cell}") from error
        if res > 16:
            raise ValueError(f"S2 cell level must be <= 16, got {res} for cell {cell}")

    return cells
