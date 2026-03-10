import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import joinedload

from kishin_trails.database import SessionLocal
from kishin_trails.models import Tile, POI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("cache")

CHUNK_SIZE = 1000


def init_db() -> None:
    from kishin_trails.database import engine
    from kishin_trails.database import Base
    Base.metadata.create_all(bind=engine)
    logger.info("POI cache tables initialized")


def has_tile(h3_cell: str) -> bool:
    session = SessionLocal()
    try:
        exists = session.query(Tile.h3_cell).filter(Tile.h3_cell == h3_cell).first()
        return exists is not None
    finally:
        session.close()


def _query_tiles_orm(session, h3_cells: List[str]) -> Dict[str, Dict[str, Any]]:
    tiles = session.query(Tile).options(joinedload(Tile.pois)).filter(
        Tile.h3_cell.in_(h3_cells)
    ).all()

    results = {h3: None for h3 in h3_cells}
    for tile in tiles:
        pois = []
        for poi in tile.pois:
            pois.append({
                "osm_id": poi.osm_id,
                "name": poi.name,
                "lat": poi.lat,
                "lon": poi.lon,
                "elevation": poi.elevation
            })
        results[tile.h3_cell] = {
            "h3_cell": tile.h3_cell,
            "tile_type": tile.tile_type,
            "pois": pois
        }
    return results


def _query_tiles_sql(session, h3_cells: List[str]) -> Dict[str, Dict[str, Any]]:
    if not h3_cells:
        return {}

    results = {h3: None for h3 in h3_cells}

    for i in range(0, len(h3_cells), CHUNK_SIZE):
        chunk = h3_cells[i:i + CHUNK_SIZE]
        placeholders = ",".join("?" * len(chunk))

        result = session.execute(text(f"""
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
        """), chunk)

        rows = result.fetchall()

        for row in rows:
            h3 = row[0]
            if results[h3] is None:
                results[h3] = {
                    "h3_cell": h3,
                    "tile_type": row[1],
                    "pois": []
                }
            if row[2] is not None:
                results[h3]["pois"].append({
                    "osm_id": row[2],
                    "name": row[3],
                    "lat": row[4],
                    "lon": row[5],
                    "elevation": row[6]
                })

    return results


def get_tile(h3_cell: str) -> Optional[Dict[str, Any]]:
    session = SessionLocal()
    try:
        results = _query_tiles_orm(session, [h3_cell])
        return results.get(h3_cell)
    finally:
        session.close()


def get_tiles(h3_cells: List[str]) -> Dict[str, Dict[str, Any]]:
    if not h3_cells:
        return {}

    session = SessionLocal()
    try:
        return _query_tiles_orm(session, h3_cells)
    finally:
        session.close()


def set_tile(h3_cell: str, tile_type: Optional[str], pois: List[Dict[str, Any]]) -> None:
    session = SessionLocal()
    try:
        tile = session.query(Tile).filter(Tile.h3_cell == h3_cell).first()
        if tile:
            tile.tile_type = tile_type
        else:
            tile = Tile(h3_cell=h3_cell, tile_type=tile_type)
            session.add(tile)

        session.query(POI).filter(POI.h3_cell == h3_cell).delete()

        for poi_data in pois:
            poi = POI(
                h3_cell=h3_cell,
                osm_id=poi_data["osm_id"],
                name=poi_data.get("name"),
                lat=poi_data["lat"],
                lon=poi_data["lon"],
                elevation=poi_data.get("elevation")
            )
            session.add(poi)

        session.commit()
        logger.info("Cached tile %s with %d pois", h3_cell, len(pois))
    finally:
        session.close()


init_db()