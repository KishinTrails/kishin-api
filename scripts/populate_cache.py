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
from tqdm import tqdm

from kishin_trails.cache import setTile, getTile
from kishin_trails.overpass import loadElementsAt
from kishin_trails.poi import filterWaypointsForCache
from kishin_trails.utils import getH3Circle, pointInH3Hexagon

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("populate_cache")


def populate_cache_for_tile(h3Cell: str) -> None:
    """Populate cache for a single H3 tile.
    
    Args:
        h3Cell: H3 cell identifier.
    """
    res = h3.get_resolution(h3Cell)
    if res > 10:
        logger.error("H3 cell resolution must be <= 10, got %d", res)
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
        if existing:
            logger.debug("Tile %s already cached, skipping", childCell)
            continue

        # Get center and radius for the child cell
        try:
            lat, lng, radiusM, _ = getH3Circle(childCell, 0)
        except ValueError as e:
            logger.warning("Skipping tile %s: %s", childCell, e)
            continue

        # Load OSM elements with retry logic for 504 errors
        retry_delay = 5
        while True:
            try:
                gdf = loadElementsAt(lat, lng, radiusM)
                break
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code in (429, 504):
                    logger.warning(
                        "Overpass API error %s for tile %s, retrying in %ds",
                        e.response.status_code, childCell, retry_delay
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    raise
            except Exception as e:
                logger.warning("Error loading elements for tile %s: %s", childCell, e)
                gdf = None
                break

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
            elif False:
                # FIXME: Placeholder for future polygon handling
                continue
            elements.append({
                "id": row["id"],
                "tags": dict(row.items())
            })

        # Filter waypoints and cache
        waypoints, tileType = filterWaypointsForCache(elements)
        setTile(childCell, tileType, waypoints)

    logger.info("Finished populating cache for %s", h3Cell)


def main() -> None:
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Populate cache with POI data for H3 tiles")
    parser.add_argument("h3_cell", help="H3 cell ID (resolution >= 10)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without actually caching")

    args = parser.parse_args()

    h3Cell = args.h3_cell

    # Validate H3 cell
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
        populate_cache_for_tile(h3Cell)


if __name__ == "__main__":
    main()
