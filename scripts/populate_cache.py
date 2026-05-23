"""
Script to populate the cache with POI data for S2 tiles.

Takes one or more S2 tile IDs as argument, expands them to level 10 tiles,
deduplicates the children, and populates the cache with POI data for each tile.
"""

import argparse
import logging
import sys
import time

import requests
from shapely.geometry import MultiPolygon, Polygon, Point
from sqlalchemy import text
from tqdm import tqdm

from kishin_trails.cache import setTile, getTile, getAllPostProcessingPois, getTilesForPostProcessingPoi
from kishin_trails.database import SESSION_LOCAL
from kishin_trails.models import PostProcessingPoI, Tile
from kishin_trails.overpass import loadElementsAtBounds
from kishin_trails.poi import filterWaypointsForCache
from kishin_trails.utils import (
    latLngToS2Cell,
    pointInS2Cell,
    s2CellToChildren,
    s2CellToParent,
    getS2CellCenter,
    getS2CellBounds,
    getS2CellLevel,
    s2CellsFromPolygon,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("populate_cache")


def insertOrGetPostProcessingPoi(osmId: int, name: str | None, tileType: str):
    """Insert or get existing PostProcessingPoI. Returns the ID.
    
    This is used for polygon features (forests, parks, industrial zones) that span
    multiple S2 tiles. The POI is stored separately and linked to tiles via a junction
    table, allowing a second pass to fill interior tiles with the correct tile_type.
    """
    session = SESSION_LOCAL()
    try:
        # Check if POI already exists to avoid duplicates
        existing = session.query(PostProcessingPoI).filter(PostProcessingPoI.osm_id == osmId).first()
        if existing:
            return existing.id
        # Create new POI entry for post-processing
        poi = PostProcessingPoI(osm_id=osmId, name=name, tile_type=tileType)
        session.add(poi)
        session.commit()
        session.refresh(poi)
        return poi.id
    finally:
        session.close()


def insertJunctionEntry(tileS2Cell: str, poiId: int) -> None:
    """Insert into junction table (INSERT OR IGNORE).
    
    Creates a many-to-many relationship between polygon POIs and S2 tiles.
    This allows tracking which tiles are covered by a polygon feature, so
    interior tiles can be filled in the second pass (fillPolygonInteriors).
    """
    session = SESSION_LOCAL()
    try:
        # INSERT OR IGNORE prevents duplicates if the same polygon covers a tile multiple times
        session.execute(
            text(
                "INSERT OR IGNORE INTO tile_post_processing_pois (tile_s2_cell_id, post_processing_poi_id) VALUES (:tile, :poiId)"
            ),
            {
                "tile": tileS2Cell,
                "poiId": poiId
            }
        )
        session.commit()
    finally:
        session.close()


def setTileType(s2Cell: str, tileType: str) -> None:
    """Update tile_type for a tile.
    
    Used in the second pass (fillPolygonInteriors) to set the tile_type for
    interior tiles of polygon features. Only updates tiles that already exist
    in the database.
    """
    session = SESSION_LOCAL()
    try:
        tile = session.query(Tile).filter(Tile.s2_cell_id == s2Cell).first()
        if tile:
            tile.tile_type = tileType
            session.commit()
    finally:
        session.close()


def deletePostProcessingPoiAndJunctions(poiId: int) -> None:
    """Delete PostProcessingPoI and its junction entries.
    
    Cleanup function called after polygon interior filling is complete.
    Removes the temporary POI record and all its tile associations from
    the junction table, as they are no longer needed.
    """
    session = SESSION_LOCAL()
    try:
        # First delete all junction entries linking this POI to tiles
        session.execute(
            text("DELETE FROM tile_post_processing_pois WHERE post_processing_poi_id = :poiId"),
            {
                "poiId": poiId
            }
        )
        # Then delete the POI itself
        session.query(PostProcessingPoI).filter(PostProcessingPoI.id == poiId).delete()
        session.commit()
    finally:
        session.close()


def populateCacheForTilesOld(s2Cells: list[str], skipCached: bool = True) -> None:
    """Populate cache for multiple S2 tiles with unified progress tracking.

    Args:
        s2Cells: List of parent S2 cell IDs.
        skipCached: If True, skip tiles that already exist in database.
                    If False, re-process all tiles (for --no-cache mode).
    """
    # Expand all parent tiles to level 16 children for consistent granularity
    # Level 16 provides a good balance between detail and performance
    allChildren: list[str] = []
    for parentCell in s2Cells:
        res = getS2CellLevel(parentCell)
        if res > 16:
            logger.error("S2 cell level must be >= 16, got %d for %s", res, parentCell)
            continue

        # Uncompact lower-resolution tiles to level 16 children
        if res < 16:
            children = s2CellToChildren(parentCell, 16)
            allChildren.extend(children)
        else:
            # Already at level 16, use as-is
            allChildren.append(parentCell)

    # Remove duplicates that occur when parent tiles overlap or share children
    initialCount = len(allChildren)
    uniqueChildren = list(dict.fromkeys(allChildren))
    deduplicatedCount = initialCount - len(uniqueChildren)

    logger.info("Collected %d level-16 tiles from %d parent tile(s)", len(uniqueChildren), len(s2Cells))
    if deduplicatedCount > 0:
        logger.info("Removed %d duplicate tile(s)", deduplicatedCount)

    for childCell in tqdm(uniqueChildren, desc="Populating cache"):
        # Check if already cached to avoid redundant API calls
        existing = getTile(childCell)
        if existing and skipCached:
            logger.debug("Tile %s already cached, skipping", childCell)
            continue

        # Get bounds for the child cell to define search area
        try:
            bounds = getS2CellBounds(childCell)
        except ValueError as e:
            logger.warning("Skipping tile %s: %s", childCell, e)
            continue

        # Load OSM elements with exponential backoff retry for rate limiting/timeout errors
        # Overpass API may return 429 (rate limit) or 504 (timeout) under load
        retryDelay = 5
        while True:
            try:
                gdf = loadElementsAtBounds(bounds)
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
                    retryDelay *= 2  # Exponential backoff: 5s, 10s, 20s, 40s...
                else:
                    # Other HTTP errors are not retried
                    raise

        # Skip to next tile if gdf is None (error occurred)
        if gdf is None:
            continue
        elements = []
        for _, row in gdf.iterrows():
            tags = dict(row.items())
            geometry = tags.get("geometry")
            if geometry is None:
                assert False, "Geometry not present in element!"
            elif isinstance(geometry, Point) and not pointInS2Cell(childCell, geometry.y, geometry.x):
                # Skip points that fall outside this S2 cell (may be in adjacent tile)
                continue
            elif isinstance(geometry, (MultiPolygon, Polygon)):
                # Handle polygon features (forests, parks, industrial zones) that span multiple tiles
                # These require post-processing to fill interior tiles
                tileType = None
                if tags.get('landuse') == 'industrial':
                    tileType = 'industrial'
                elif tags.get('landuse') == 'forest':
                    tileType = 'natural'
                elif tags.get('leisure') == 'park':
                    tileType = 'natural'

                if tileType:
                    # Convert polygon to S2 cells at level 16
                    allCells = []
                    if isinstance(geometry, Polygon):
                        allCells = s2CellsFromPolygon(geometry, 16)
                    elif isinstance(geometry, MultiPolygon):
                        for poly in geometry.geoms:
                            allCells.extend(s2CellsFromPolygon(poly, 16))

                    # Store POI for post-processing (second pass will fill interior tiles)
                    poiId = insertOrGetPostProcessingPoi(row['id'], tags.get('name'), tileType)

                    # Link this POI to all S2 cells it covers
                    for cell in allCells:
                        insertJunctionEntry(cell, poiId)

            # Add element to cache regardless of type
            elements.append({
                "id": row["id"],
                "tags": dict(row.items())
            })

        # Filter waypoints to select the most important POI type for this tile
        # Priority: PeakPoI > NaturalPoI > IndustrialPoI (only one type per tile)
        waypoints, tileType = filterWaypointsForCache(elements)
        # Store tile and its POIs in the database cache
        setTile(childCell, tileType, waypoints)

    logger.info("Finished populating cache for %d tile(s)", len(uniqueChildren))


def populateCacheForTiles(s2Cells: list[str], skipCached: bool = True, queryResolution: int = 9) -> None:
    """Populate cache using efficient single-query-per-parent approach.

    Instead of querying Overpass for each level-16 tile individually, this function:
    1. Groups input tiles by their level-5 (or configurable) parent
    2. Makes ONE Overpass query per parent tile
    3. Distributes elements to their correct level-16 tiles based on geometry
    4. Caches each level-16 tile separately

    This reduces network calls by ~100x for large areas.

    Args:
        s2Cells: List of parent S2 cell IDs (level <= 16).
        skipCached: If True, skip tiles that already exist in database.
        queryResolution: S2 cell level for grouping queries (default 5).
                        Lower = fewer queries but larger result sets.
    """
    if queryResolution > 16:
        logger.error("Query resolution must be <= 16, got %d", queryResolution)
        return

    allLevel16Children: list[str] = []
    for parentCell in s2Cells:
        res = getS2CellLevel(parentCell)
        if res > 16:
            logger.error("S2 cell level must be <= 16, got %d for %s", res, parentCell)
            continue

        if res < 16:
            children = s2CellToChildren(parentCell, 16)
            allLevel16Children.extend(children)
        else:
            allLevel16Children.append(parentCell)

    initialCount = len(allLevel16Children)
    uniqueLevel16Children = list(dict.fromkeys(allLevel16Children))
    deduplicatedCount = initialCount - len(uniqueLevel16Children)

    logger.info("Collected %d level-16 tiles from %d parent tile(s)", len(uniqueLevel16Children), len(s2Cells))
    if deduplicatedCount > 0:
        logger.info("Removed %d duplicate level-16 tile(s)", deduplicatedCount)

    parentTiles: set[str] = set()
    for childCell in uniqueLevel16Children:
        res = getS2CellLevel(childCell)
        if res > queryResolution:
            parent = s2CellToParent(childCell, queryResolution)
            parentTiles.add(parent)
        else:
            parentTiles.add(childCell)

    logger.info("Grouped into %d parent tile(s) at level %d for querying", len(parentTiles), queryResolution)

    elementsByTile: dict[str,
                         list[dict]] = {}
    polygonProcessing: list[tuple[int, str | None, str, Polygon | MultiPolygon]] = []

    logger.info("Querying Overpass API for %d parent tile(s)...", len(parentTiles))
    for parentTile in parentTiles:
        try:
            bounds = getS2CellBounds(parentTile)
        except ValueError as e:
            logger.warning("Skipping parent tile %s: %s", parentTile, e)
            continue

        retryDelay = 5
        gdf = None
        while True:
            try:
                gdf = loadElementsAtBounds(bounds)
                break
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code in (429, 504):
                    logger.warning(
                        "Overpass API error %s for parent tile %s, retrying in %ds",
                        e.response.status_code,
                        parentTile,
                        retryDelay
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
                assert False, "Geometry not present in element!"

            if isinstance(geometry, Point):
                pointLat, pointLng = geometry.y, geometry.x
                level16Cell = latLngToS2Cell(pointLat, pointLng, 16)

                if level16Cell not in uniqueLevel16Children:
                    continue

                if level16Cell not in elementsByTile:
                    elementsByTile[level16Cell] = []

                elementsByTile[level16Cell].append({
                    "id": row["id"],
                    "tags": dict(row.items())
                })

            elif isinstance(geometry, (MultiPolygon, Polygon)):
                tileType = None
                if tags.get('landuse') == 'industrial':
                    tileType = 'industrial'
                elif tags.get('landuse') == 'forest':
                    tileType = 'natural'
                elif tags.get('leisure') == 'park':
                    tileType = 'natural'

                if tileType:
                    polygonProcessing.append((row['id'], tags.get('name'), tileType, geometry))

                    allCells = []
                    if isinstance(geometry, Polygon):
                        allCells = s2CellsFromPolygon(geometry, 16)
                    elif isinstance(geometry, MultiPolygon):
                        for poly in geometry.geoms:
                            allCells.extend(s2CellsFromPolygon(poly, 16))

                    for cell in allCells:
                        if cell in uniqueLevel16Children:
                            if cell not in elementsByTile:
                                elementsByTile[cell] = []
                            elementsByTile[cell].append({
                                "id": row["id"],
                                "tags": dict(row.items())
                            })

    logger.info("Processing %d polygon(s) for post-processing...", len(polygonProcessing))
    for osmId, name, tileType, geometry in polygonProcessing:
        poiId = insertOrGetPostProcessingPoi(osmId, name, tileType)

        allCells = []
        if isinstance(geometry, Polygon):
            allCells = s2CellsFromPolygon(geometry, 16)
        elif isinstance(geometry, MultiPolygon):
            for poly in geometry.geoms:
                allCells.extend(s2CellsFromPolygon(poly, 16))

        for cell in allCells:
            if cell in uniqueLevel16Children:
                insertJunctionEntry(cell, poiId)

    totalTilesProcessed = 0
    totalTilesSkipped = 0

    logger.info("Caching %d level-16 tile(s)...", len(uniqueLevel16Children))
    for level16Cell in tqdm(uniqueLevel16Children, desc="Caching tiles"):
        if skipCached and getTile(level16Cell):
            totalTilesSkipped += 1
            continue

        elements = elementsByTile.get(level16Cell, [])
        waypoints, tileType = filterWaypointsForCache(elements)
        setTile(level16Cell, tileType, waypoints)
        totalTilesProcessed += 1

    logger.info("Finished: processed %d tiles, skipped %d tiles", totalTilesProcessed, totalTilesSkipped)


def fillPolygonInteriors() -> None:
    """Fill interior tiles based on stored polygons.
    
    Second pass of the cache population process. After initial tile processing,
    polygon features (forests, parks, industrial zones) are stored in a separate
    table with links to all S2 cells they cover. This function:
    1. Retrieves all stored polygon POIs
    2. For each polygon, gets all linked S2 tiles
    3. Sets the tile_type for tiles that don't have one yet (interior tiles)
    4. Cleans up the temporary polygon data and junction entries
    
    This ensures that interior tiles of large polygon features get the correct
    tile_type even if they only contain the polygon interior without boundary features.
    """
    logger.info("Starting polygon interior filling...")

    # Get all polygon POIs that were stored during first pass
    pois = getAllPostProcessingPois()
    logger.info("Found %d polygons to process", len(pois))

    for poi in tqdm(pois, desc="Post-processing PoIs"):
        # Get all S2 tiles linked to this polygon via junction table
        tiles = getTilesForPostProcessingPoi(poi['id'])
        logger.debug("Processing polygon %d with %d linked tiles", poi['id'], len(tiles))

        # Set tile_type for all tiles covered by this polygon
        for tileS2Cell in tiles:
            tile = getTile(tileS2Cell)
            # Only update tiles that exist and don't have a type yet
            # This preserves point-based POIs (peaks) that take priority
            if tile and tile.get('tile_type') is None:
                setTileType(tileS2Cell, poi['tile_type'])
                logger.debug("Set tile %s to type %s", tileS2Cell, poi['tile_type'])

        # Remove temporary polygon data - no longer needed after filling interiors
        deletePostProcessingPoiAndJunctions(poi['id'])
        logger.debug("Cleaned up polygon %d", poi['id'])

    logger.info("Finished polygon interior filling")


def parseS2Cells(s2CellsStr: str) -> list[str]:
    """Parse comma-separated S2 cell IDs into a list.

    Args:
        s2CellsStr: Comma-separated string of S2 cell IDs.

    Returns:
        List of validated S2 cell IDs.

    Raises:
        ValueError: If any cell ID is invalid or has level > 16.
    """
    cells = [cell.strip() for cell in s2CellsStr.split(",")]
    cells = [cell for cell in cells if cell]

    if not cells:
        raise ValueError("No S2 cell IDs provided")

    for cell in cells:
        try:
            res = getS2CellLevel(cell)
        except ValueError:
            raise ValueError(f"Invalid S2 cell: {cell}")
        if res > 16:
            raise ValueError(f"S2 cell level must be <= 16, got {res} for cell {cell}")

    return cells


def main() -> None:
    """Main entry point for the cache population script.

    Populates the cache with POI data for S2 tiles by:
    1. Uncompacting S2 tiles to level 16
    2. Querying the Overpass API for each tile
    3. Filtering and caching POI data
    4. Optionally filling polygon interiors (second pass)

    Supports multiple S2 tiles via comma-separated input. All provided
    tiles are processed with the same flags applied.

    Two-pass approach:
    - First pass (populateCacheForTiles): Processes tiles, stores polygon features
    - Second pass (fillPolygonInteriors): Fills interior tiles of polygons
    """
    parser = argparse.ArgumentParser(description="Populate cache with POI data for S2 tiles")
    parser.add_argument(
        "s2_cells",
        nargs="?",
        help="Comma-separated S2 cell IDs (level <= 16), e.g., 'tile1,tile2,tile3'"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without actually caching")
    parser.add_argument(
        "--fill-polygons",
        action="store_true",
        help="Run polygon interior filling after processing tiles (second pass)"
    )
    parser.add_argument("--fill-only", action="store_true", help="Only run polygon filling, skip tile processing")
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Re-process all tiles, inserting only missing POIs (preserve existing data)"
    )

    args = parser.parse_args()

    # Special case: only run the second pass (polygon filling) without processing new tiles
    if args.fill_only:
        fillPolygonInteriors()
        return

    s2CellsStr = args.s2_cells

    if not s2CellsStr:
        logger.error("s2_cells argument is required (unless using --fill-only)")
        sys.exit(1)

    try:
        s2Cells = parseS2Cells(s2CellsStr)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info("Starting cache population for %d S2 cell(s)", len(s2Cells))

    if args.dry_run:
        # Simulate processing to show how many tiles would be affected
        allChildren: list[str] = []
        for parentCell in s2Cells:
            res = getS2CellLevel(parentCell)
            if res < 16:
                children = s2CellToChildren(parentCell, 16)
                allChildren.extend(children)
            else:
                allChildren.append(parentCell)
        uniqueChildren = list(dict.fromkeys(allChildren))
        logger.info("Dry run: would process %d level-16 tiles", len(uniqueChildren))
    else:
        skipCached = not args.no_cache
        populateCacheForTiles(s2Cells, skipCached=skipCached, queryResolution=5)
        logger.info("Successfully processed %d S2 parent tile(s)", len(s2Cells))

    # Second pass: fill interior tiles of polygon features
    if args.fill_polygons:
        fillPolygonInteriors()


if __name__ == "__main__":
    main()
