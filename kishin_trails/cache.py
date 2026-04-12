"""
Tile caching module for storing and retrieving H3 tiles with POI data.

Provides in-database caching for tiles and their associated Points of Interest
to avoid repeated Overpass API queries.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import joinedload

from kishin_trails.database import SESSION_LOCAL, engine, Base
from kishin_trails.models import PostProcessingPoI, Tile, POI
from kishin_trails.perlin import isCellActive

logger = logging.getLogger("cache")

CHUNK_SIZE = 1000


def initDb() -> None:
    """Initialize the cache database tables.
    
    Creates all necessary tables in the database if they don't exist.
    """
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


def _queryTilesOrm(session, h3Cells: List[str]) -> Dict[str, Dict[str, Any] | None]:
    """Query tiles using SQLAlchemy ORM with joined POI loading.

    Args:
        session: The database session.
        h3Cells: List of H3 cell identifiers to query.

    Returns:
        Dictionary mapping H3 cells to their tile data and POIs.
    """
    tiles = session.query(Tile).options(joinedload(Tile.pois)).filter(Tile.h3_cell.in_(h3Cells)).all()

    results: Dict[str,
                  Dict[str,
                       Any] | None] = {
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
        tileType = tile.tile_type if tile.active or tile.tile_type == 'peak' else None
        results[tile.h3_cell] = {
            "h3_cell": tile.h3_cell,
            "tile_type": tileType,
            "pois": pois
        }
    return results


def _queryTilesSql(session, h3Cells: List[str]) -> Dict[str, Dict[str, Any] | None]:
    """Query tiles using raw SQL with chunked execution.

    Args:
        session: The database session.
        h3Cells: List of H3 cell identifiers to query.

    Returns:
        Dictionary mapping H3 cells to their tile data and POIs.
    """
    if not h3Cells:
        return {}

    results: Dict[str,
                  Dict[str,
                       Any] | None] = {
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
                CASE 
                    WHEN t.tile_type = 'peak' THEN t.tile_type
                    WHEN t.active = 1 THEN t.tile_type
                    ELSE NULL
                END as tile_type,
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
            tileData: Dict[str, Any] | None = results.get(h3CellKey)
            if tileData is None:
                tileData = {
                    "h3_cell": h3CellKey,
                    "tile_type": row[1],
                    "pois": []
                }
                results[h3CellKey] = tileData
            if row[2] is not None:
                tileData["pois"].append(
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


def getTiles(h3Cells: List[str]) -> Dict[str, Dict[str, Any] | None]:
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

    This function is idempotent:
    - If tile exists with NULL tile_type, it is updated (completes partial tiles)
    - If tile exists with non-NULL tile_type, it is preserved
    - Only missing POIs are inserted (by osm_id)
    - Existing POIs are never modified or deleted

    Args:
        h3Cell: The H3 cell identifier.
        tileType: Type of POI in the tile (e.g., 'peak', 'natural', 'industrial').
        pois: List of POI dictionaries to store.
    """
    session = SESSION_LOCAL()
    try:
        isActive = isCellActive(h3Cell)

        tile = session.query(Tile).filter(Tile.h3_cell == h3Cell).first()
        if tile:
            # Update tile_type only if currently NULL (completes partial tiles)
            if tile.tile_type is None and tileType is not None:
                tile.tile_type = tileType
            tile.active = isActive
        else:
            tile = Tile(h3_cell=h3Cell, tile_type=tileType, active=isActive)
            session.add(tile)

        existingOsmIds = {poi.osm_id
                          for poi in session.query(POI.osm_id).filter(POI.h3_cell == h3Cell).all()}

        for poiData in pois:
            if poiData["osm_id"] not in existingOsmIds:
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
        logger.debug("Cached tile %s with %d pois", h3Cell, len(pois))
    finally:
        session.close()


def getPostProcessingPoiByOsmId(osmId: int) -> Optional[Dict[str, Any]]:
    """Get PostProcessingPoI by OSM ID.

    Args:
        osmId: The OSM element ID.

    Returns:
        Dictionary with id, osm_id, name, tile_type or None if not found.
    """
    session = SESSION_LOCAL()
    try:
        poi = session.query(PostProcessingPoI).filter(PostProcessingPoI.osm_id == osmId).first()
        if poi is None:
            return None
        return {
            "id": poi.id,
            "osm_id": poi.osm_id,
            "name": poi.name,
            "tile_type": poi.tile_type
        }
    finally:
        session.close()


def getAllPostProcessingPois() -> List[Dict[str, Any]]:
    """Get all PostProcessingPoI entries.

    Returns:
        List of dictionaries with id, osm_id, name, tile_type.
    """
    session = SESSION_LOCAL()
    try:
        pois = session.query(PostProcessingPoI).all()
        return [{
            "id": poi.id,
            "osm_id": poi.osm_id,
            "name": poi.name,
            "tile_type": poi.tile_type
        } for poi in pois]
    finally:
        session.close()


def getTilesForPostProcessingPoi(poiId: int) -> List[str]:
    """Get all tile h3_cells linked to a PostProcessingPoI.

    Args:
        poiId: The PostProcessingPoI ID.

    Returns:
        List of H3 cell identifiers.
    """
    session = SESSION_LOCAL()
    try:
        result = session.execute(
            text("SELECT tile_h3_cell FROM tile_post_processing_pois WHERE post_processing_poi_id = :poiId"),
            {
                "poiId": poiId
            }
        )
        return [row[0] for row in result.fetchall()]
    finally:
        session.close()


initDb()
