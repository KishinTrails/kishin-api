#!/usr/bin/env python
"""Import GPX file and register explored tiles for a user."""

import argparse
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gpx import read_gpx

from kishin_trails.database import SESSION_LOCAL
from kishin_trails.models import Tile, User
from kishin_trails.utils import getH3Cell

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("import_gpx")


def getOrCreateTile(session, h3Cell: str) -> Tile:
    """Get existing tile or create new one."""
    tile = session.query(Tile).filter(Tile.h3_cell == h3Cell).first()
    if not tile:
        tile = Tile(h3_cell=h3Cell)
        session.add(tile)
        session.flush()
    return tile


def importGpx(gpxPath: str, username: str, resolution: int = 10, dryRun: bool = False) -> None:
    """Import GPX file and mark tiles as explored by user."""
    gpx = read_gpx(gpxPath)

    tiles: set[str] = set()
    for track in gpx.trk:
        for segment in track.segments:
            for point in segment.points:
                lat = float(point.lat)
                lng = float(point.lon)
                h3Cell = getH3Cell(lat, lng, resolution)
                tiles.add(h3Cell)

    logger.info("Found %d unique tiles in GPX file", len(tiles))

    if dryRun:
        logger.info("Dry run - tiles that would be marked:")
        for tile in sorted(tiles):
            logger.info("  %s", tile)
        return

    session = SESSION_LOCAL()
    try:
        user = session.query(User).filter(User.username == username).first()
        if not user:
            logger.error("User '%s' not found", username)
            sys.exit(1)

        for h3Cell in tiles:
            tile = getOrCreateTile(session, h3Cell)
            if tile not in user.explored_tiles:
                user.explored_tiles.append(tile)

        session.commit()
        logger.info("Successfully marked %d tiles as explored by user '%s'", len(tiles), username)

    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import GPX file and register explored tiles")
    parser.add_argument("gpx_file", help="Path to GPX file")
    parser.add_argument("--user", "-u", required=True, help="Username to associate explored tiles with")
    parser.add_argument("--resolution", "-r", type=int, default=10, help="H3 resolution (default: 10)")
    parser.add_argument("--dry-run", action="store_true", help="Print tiles without updating database")

    args = parser.parse_args()

    if not os.path.isfile(args.gpx_file):
        logger.error("GPX file not found: %s", args.gpx_file)
        sys.exit(1)

    importGpx(args.gpx_file, args.user, args.resolution, args.dry_run)


if __name__ == "__main__":
    main()