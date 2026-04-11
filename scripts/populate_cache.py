"""
Script to populate the cache with POI data for H3 tiles.

Takes one or more H3 tile IDs as argument, uncompacts them to level 10 tiles,
deduplicates the children, and populates the cache with POI data for each tile.
"""

import argparse
import logging
import sys
import time

import h3
import requests
from shapely.geometry import Point
from sqlalchemy import text
from tqdm import tqdm

from kishin_trails.cache import setTile, getTile, getAllPostProcessingPois, getTilesForPostProcessingPoi
from kishin_trails.database import SESSION_LOCAL
from kishin_trails.models import PostProcessingPoI, Tile
from kishin_trails.overpass import loadElementsAt
from kishin_trails.poi import filterWaypointsForCache
from kishin_trails.utils import getH3Circle, pointInH3Hexagon

logging.basicConfig(
    level=logging.WARN,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("populate_cache")


def insertOrGetPostProcessingPoi(osmId: int, name: str | None, tileType: str):
    """Insert or get existing PostProcessingPoI. Returns the ID."""
    session = SESSION_LOCAL()
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


def insertJunctionEntry(tileH3Cell: str, poiId: int) -> None:
    """Insert into junction table (INSERT OR IGNORE)."""
    session = SESSION_LOCAL()
    try:
        session.execute(
            text(
                "INSERT OR IGNORE INTO tile_post_processing_pois (tile_h3_cell, post_processing_poi_id) VALUES (:tile, :poiId)"
            ),
            {
                "tile": tileH3Cell,
                "poiId": poiId
            }
        )
        session.commit()
    finally:
        session.close()


def setTileType(h3Cell: str, tileType: str) -> None:
    """Update tile_type for a tile."""
    session = SESSION_LOCAL()
    try:
        tile = session.query(Tile).filter(Tile.h3_cell == h3Cell).first()
        if tile:
            tile.tile_type = tileType
            session.commit()
    finally:
        session.close()


def deletePostProcessingPoiAndJunctions(poiId: int) -> None:
    """Delete PostProcessingPoI and its junction entries."""
    session = SESSION_LOCAL()
    try:
        session.execute(
            text("DELETE FROM tile_post_processing_pois WHERE post_processing_poi_id = :poiId"),
            {
                "poiId": poiId
            }
        )
        session.query(PostProcessingPoI).filter(PostProcessingPoI.id == poiId).delete()
        session.commit()
    finally:
        session.close()


def populateCacheForTiles(h3Cells: list[str], skipCached: bool = True) -> None:
    """Populate cache for multiple H3 tiles with unified progress tracking.

    Args:
        h3Cells: List of parent H3 cell IDs.
        skipCached: If True, skip tiles that already exist in database.
                   If False, re-process all tiles (for --no-cache mode).
    """
    allChildren: list[str] = []
    for parentCell in h3Cells:
        res = h3.get_resolution(parentCell)
        if res > 10:
            logger.error("H3 cell resolution must be >= 10, got %d for %s", res, parentCell)
            continue

        if res < 10:
            children = h3.cell_to_children(parentCell, res=10)
            allChildren.extend(children)
        else:
            allChildren.append(parentCell)

    initialCount = len(allChildren)
    uniqueChildren = list(dict.fromkeys(allChildren))
    deduplicatedCount = initialCount - len(uniqueChildren)

    logger.info("Collected %d level-10 tiles from %d parent tile(s)", len(uniqueChildren), len(h3Cells))
    if deduplicatedCount > 0:
        logger.info("Removed %d duplicate tile(s)", deduplicatedCount)

    for childCell in tqdm(uniqueChildren, desc="Populating cache"):
        # Check if already cached
        existing = getTile(childCell)
        if existing and skipCached:
            logger.debug("Tile %s already cached, skipping", childCell)
            continue

        # Get center and radius for the child cell
        try:
            lat, lng, radiusM, _ = getH3Circle(childCell, 0)
        except ValueError as e:
            logger.warning("Skipping tile %s: %s", childCell, e)
            continue

        # Load OSM elements with retry logic for 504 errors
        retryDelay = 5
        while True:
            try:
                gdf = loadElementsAt(lat, lng, radiusM)
                break
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code in (429, 504):
                    logger.warning(
                        "Overpass API error %s for tile %s, retrying in %ds",
                        e.response.status_code,
                        childCell,
                        retryDelay
                    )
                    time.sleep(retryDelay)
                    retryDelay *= 2
                else:
                    raise

        # Skip to next tile if gdf is None (error occurred)
        if gdf is None:
            continue
        elements = []
        for _, row in gdf.iterrows():
            tags = dict(row.items())
            geometry = tags.get("geometry")
            if geometry is not None and isinstance(geometry, Point):
                if not pointInH3Hexagon(geometry.y, geometry.x, childCell):
                    continue
            elif geometry is not None and hasattr(geometry,
                                                  'geom_type') and geometry.geom_type in ('Polygon',
                                                                                          'MultiPolygon'):
                tileType = None
                if tags.get('landuse') == 'forest':
                    tileType = 'natural'
                elif tags.get('landuse') == 'industrial':
                    tileType = 'industrial'
                elif tags.get('leisure') == 'park':
                    tileType = 'natural'

                if tileType:
                    allCells = []
                    if geometry.geom_type == 'Polygon':
                        coords = list(geometry.exterior.coords)
                        h3Polygon = h3.LatLngPoly([(lat, lng) for lng, lat in coords])
                        allCells = h3.polygon_to_cells(h3Polygon, res=10)
                    elif geometry.geom_type == 'MultiPolygon':
                        for poly in geometry.geoms:
                            coords = list(poly.exterior.coords)
                            h3Polygon = h3.LatLngPoly([(lat, lng) for lng, lat in coords])
                            allCells.extend(h3.polygon_to_cells(h3Polygon, res=10))

                    poiId = insertOrGetPostProcessingPoi(int(row['id']), tags.get('name'), tileType)

                    for cell in allCells:
                        insertJunctionEntry(cell, poiId)
            elements.append({
                "id": row["id"],
                "tags": dict(row.items())
            })

        # Filter waypoints and cache
        waypoints, tileType = filterWaypointsForCache(elements)
        setTile(childCell, tileType, waypoints)

    logger.info("Finished populating cache for %d tile(s)", len(uniqueChildren))


def fillPolygonInteriors() -> None:
    """Fill interior tiles based on stored polygons."""
    logger.info("Starting polygon interior filling...")

    pois = getAllPostProcessingPois()
    logger.info("Found %d polygons to process", len(pois))

    for poi in pois:
        tiles = getTilesForPostProcessingPoi(poi['id'])
        logger.debug("Processing polygon %d with %d linked tiles", poi['id'], len(tiles))

        for tileH3Cell in tiles:
            tile = getTile(tileH3Cell)
            if tile and tile.get('tile_type') is None:
                setTileType(tileH3Cell, poi['tile_type'])
                logger.debug("Set tile %s to type %s", tileH3Cell, poi['tile_type'])

        deletePostProcessingPoiAndJunctions(poi['id'])
        logger.debug("Cleaned up polygon %d", poi['id'])

    logger.info("Finished polygon interior filling")


def parseH3Cells(h3CellsStr: str) -> list[str]:
    """Parse comma-separated H3 cell IDs into a list.

    Args:
        h3CellsStr: Comma-separated string of H3 cell IDs.

    Returns:
        List of validated H3 cell IDs.

    Raises:
        ValueError: If any cell ID is invalid or has resolution > 10.
    """
    cells = [cell.strip() for cell in h3CellsStr.split(",")]
    cells = [cell for cell in cells if cell]

    if not cells:
        raise ValueError("No H3 cell IDs provided")

    for cell in cells:
        if not h3.is_valid_cell(cell):
            raise ValueError(f"Invalid H3 cell: {cell}")
        res = h3.get_resolution(cell)
        if res > 10:
            raise ValueError(f"H3 cell resolution must be <= 10, got {res} for cell {cell}")

    return cells


def main() -> None:
    """Main entry point for the cache population script.

    Populates the cache with POI data for H3 tiles by:
    1. Uncompacting H3 tiles to level 10
    2. Querying the Overpass API for each tile
    3. Filtering and caching POI data

    Supports multiple H3 tiles via comma-separated input. All provided
    tiles are processed with the same flags applied.

    Supports optional polygon interior filling to propagate tile types
    to interior cells of polygon areas (forests, parks, industrial zones).
    """
    parser = argparse.ArgumentParser(description="Populate cache with POI data for H3 tiles")
    parser.add_argument(
        "h3_cells",
        nargs="?",
        help="Comma-separated H3 cell IDs (resolution <= 10), e.g., 'tile1,tile2,tile3'"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without actually caching")
    parser.add_argument(
        "--fill-polygons",
        action="store_true",
        help="Run polygon interior filling after processing tiles"
    )
    parser.add_argument("--fill-only", action="store_true", help="Only run polygon filling, skip tile processing")
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Re-process all tiles, inserting only missing POIs (preserve existing data)"
    )

    args = parser.parse_args()

    if args.fill_only:
        fillPolygonInteriors()
        return

    h3CellsStr = args.h3_cells

    if not h3CellsStr:
        logger.error("h3_cells argument is required (unless using --fill-only)")
        sys.exit(1)

    try:
        h3Cells = parseH3Cells(h3CellsStr)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info("Starting cache population for %d H3 cell(s)", len(h3Cells))

    if args.dry_run:
        allChildren: list[str] = []
        for parentCell in h3Cells:
            res = h3.get_resolution(parentCell)
            if res < 10:
                children = h3.cell_to_children(parentCell, res=10)
                allChildren.extend(children)
            else:
                allChildren.append(parentCell)
        uniqueChildren = list(dict.fromkeys(allChildren))
        logger.info("Dry run: would process %d level-10 tiles", len(uniqueChildren))
    else:
        skipCached = not args.no_cache
        populateCacheForTiles(h3Cells, skipCached=skipCached)
        logger.info("Successfully processed %d H3 parent tile(s)", len(h3Cells))

    if args.fill_polygons:
        fillPolygonInteriors()


if __name__ == "__main__":
    main()
