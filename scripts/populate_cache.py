"""
Script to populate the cache with POI data for H3 tiles.

Takes an H3 tile ID as argument, uncompacts it to level 10 tiles,
and populates the cache with POI data for each tile.
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


def populateCacheForTile(h3Cell: str, skipCached: bool = True) -> None:
    """Populate cache for a single H3 tile.
    
    Args:
        h3Cell: H3 cell identifier.
        skipCached: If True, skip tiles that already exist in database.
                   If False, re-process all tiles (for --no-cache mode).
    """
    res = h3.get_resolution(h3Cell)
    if res > 10:
        logger.error("H3 cell resolution must be >= 10, got %d", res)
        return

    # Get level 10 children
    if res < 10:
        children = h3.cell_to_children(h3Cell, res=10)
    else:
        children = [h3Cell]

    logger.info("Processing %d level 10 tiles for parent %s", len(children), h3Cell)

    for childCell in tqdm(children, desc="Populating cache"):
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

    logger.info("Finished populating cache for %s", h3Cell)


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


def main() -> None:
    """Main entry point for the cache population script.

    Populates the cache with POI data for H3 tiles by:
    1. Uncompacting H3 tiles to level 10
    2. Querying the Overpass API for each tile
    3. Filtering and caching POI data

    Supports optional polygon interior filling to propagate tile types
    to interior cells of polygon areas (forests, parks, industrial zones).
    """
    parser = argparse.ArgumentParser(description="Populate cache with POI data for H3 tiles")
    parser.add_argument("h3_cell", nargs="?", help="H3 cell ID (resolution >= 10)")
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

    h3Cell = args.h3_cell

    if not h3Cell:
        logger.error("h3_cell argument is required (unless using --fill-only)")
        sys.exit(1)

    if not h3.is_valid_cell(h3Cell):
        logger.error("Invalid H3 cell: %s", h3Cell)
        sys.exit(1)

    res = h3.get_resolution(h3Cell)
    if res > 10:
        logger.error("H3 cell resolution must be <= 10, got %d", res)
        sys.exit(1)

    logger.info("Starting cache population for H3 cell: %s (resolution %d)", h3Cell, res)

    if args.dry_run:
        if res < 10:
            children = h3.cell_to_children(h3Cell, res=10)
        else:
            children = [h3Cell]
        logger.info("Dry run: would process %d level 10 tiles", len(children))
    else:
        skipCached = not args.no_cache
        populateCacheForTile(h3Cell, skipCached=skipCached)

    if args.fill_polygons:
        fillPolygonInteriors()


if __name__ == "__main__":
    main()
