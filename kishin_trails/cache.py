"""
Tile caching module for storing and retrieving H3 tiles with POI data.

Provides in-database caching for tiles and their associated Points of Interest
to avoid repeated Overpass API queries.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import joinedload

from kishin_trails.database import SESSION_LOCAL
from kishin_trails.models import Tile, POI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("cache")

CHUNK_SIZE = 1000


def initDb() -> None:
    """Initialize the cache database tables.
    
    Creates all necessary tables in the database if they don't exist.
    """
    from kishin_trails.database import engine
    from kishin_trails.database import Base
    Base.metadata.create_all(bind=engine)
    logger.info("POI cache tables initialized")


def hasTile(h3Cell: str) -> bool:
    """Check if a tile exists in the cache.

    Args:
        h3Cell: The H3 cell identifier.

    Returns:
        True if the tile exists in cache, False otherwise.
    """
    session = SESSION_LOCAL()
    try:
        exists = session.query(Tile.h3_cell).filter(Tile.h3_cell == h3Cell).first()
        return exists is not None
    finally:
        session.close()


def _queryTilesOrm(session, h3Cells: List[str]) -> Dict[str, Dict[str, Any]]:
    """Query tiles using SQLAlchemy ORM with joined POI loading.

    Args:
        session: The database session.
        h3Cells: List of H3 cell identifiers to query.

    Returns:
        Dictionary mapping H3 cells to their tile data and POIs.
    """
    tiles = session.query(Tile).options(joinedload(Tile.pois)).filter(Tile.h3_cell.in_(h3Cells)).all()

    results = {
        h3Cell: None
        for h3Cell in h3Cells
    }
    for tile in tiles:
        pois = []
        for poi in tile.pois:
            pois.append(
                {
                    "osm_id": poi.osm_id,
                    "name": poi.name,
                    "lat": poi.lat,
                    "lon": poi.lon,
                    "elevation": poi.elevation
                }
            )
        results[tile.h3_cell] = {
            "h3_cell": tile.h3_cell,
            "tile_type": tile.tile_type,
            "pois": pois
        }
    return results


def _queryTilesSql(session, h3Cells: List[str]) -> Dict[str, Dict[str, Any]]:
    """Query tiles using raw SQL with chunked execution.

    Args:
        session: The database session.
        h3Cells: List of H3 cell identifiers to query.

    Returns:
        Dictionary mapping H3 cells to their tile data and POIs.
    """
    if not h3Cells:
        return {}

    results = {
        h3Cell: None
        for h3Cell in h3Cells
    }

    for i in range(0, len(h3Cells), CHUNK_SIZE):
        chunk = h3Cells[i:i + CHUNK_SIZE]
        placeholders = ",".join("?" * len(chunk))

        result = session.execute(
            text(
                f"""
            SELECT
                t.h3_cell,
                t.tile_type,
                p.osm_id,
                p.name,
                p.lat,
                p.lon,
                p.elevation
            FROM tiles t
            LEFT JOIN pois p ON t.h3_cell = p.h3_cell
            WHERE t.h3_cell IN ({placeholders})
        """
            ),
            chunk
        )

        rows = result.fetchall()

        for row in rows:
            h3CellKey = row[0]
            if results[h3CellKey] is None:
                results[h3CellKey] = {
                    "h3_cell": h3CellKey,
                    "tile_type": row[1],
                    "pois": []
                }
            if row[2] is not None:
                results[h3CellKey]["pois"].append(
                    {
                        "osm_id": row[2],
                        "name": row[3],
                        "lat": row[4],
                        "lon": row[5],
                        "elevation": row[6]
                    }
                )

    return results


def getTile(h3Cell: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single tile from cache.

    Args:
        h3Cell: The H3 cell identifier.

    Returns:
        Tile data dictionary or None if not found.
    """
    session = SESSION_LOCAL()
    try:
        results = _queryTilesOrm(session, [h3Cell])
        return results.get(h3Cell)
    finally:
        session.close()


def getTiles(h3Cells: List[str]) -> Dict[str, Dict[str, Any]]:
    """Retrieve multiple tiles from cache.

    Args:
        h3Cells: List of H3 cell identifiers.

    Returns:
        Dictionary mapping H3 cells to their tile data.
    """
    if not h3Cells:
        return {}

    session = SESSION_LOCAL()
    try:
        return _queryTilesOrm(session, h3Cells)
    finally:
        session.close()


def setTile(h3Cell: str, tileType: Optional[str], pois: List[Dict[str, Any]]) -> None:
    """Store a tile and its POIs in the cache.

    Args:
        h3Cell: The H3 cell identifier.
        tileType: Type of POI in the tile (e.g., 'peak', 'natural', 'industrial').
        pois: List of POI dictionaries to store.
    """
    session = SESSION_LOCAL()
    try:
        tile = session.query(Tile).filter(Tile.h3_cell == h3Cell).first()
        if tile:
            tile.tile_type = tileType
        else:
            tile = Tile(h3_cell=h3Cell, tile_type=tileType)
            session.add(tile)

        session.query(POI).filter(POI.h3_cell == h3Cell).delete()

        for poiData in pois:
            poi = POI(
                h3_cell=h3Cell,
                osm_id=poiData["osm_id"],
                name=poiData.get("name"),
                lat=poiData["lat"],
                lon=poiData["lon"],
                elevation=poiData.get("elevation")
            )
            session.add(poi)

        session.commit()
        logger.info("Cached tile %s with %d pois", h3Cell, len(pois))
    finally:
        session.close()
