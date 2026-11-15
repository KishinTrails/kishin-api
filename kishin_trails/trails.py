"""
Trails module: the S2 cells the player has explored.

Provides API endpoints to list the explored cells and to mark new ones.
"""

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from kishin_trails.database import getDb
from kishin_trails.dependencies import requireLogin
from kishin_trails.models import ExploredTile, Tile
import s2geometry as s2

from kishin_trails.schemas import AddExploredTilesRequest, AddExploredTilesResult, ExploredTilesOut, SkippedCell

logger = logging.getLogger("trails")

if TYPE_CHECKING:
    from fastapi import APIRouter, Depends

try:
    from fastapi import APIRouter, Depends
except ImportError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]

if APIRouter:
    router = APIRouter(prefix="/trails", tags=["trails"], dependencies=[Depends(requireLogin)])
else:
    router = None

if router:

    @router.get(
        "/explored",
        summary="Get the explored tiles",
        response_model=ExploredTilesOut,
    )
    def getExploredTiles(dbSession: Session = Depends(getDb)):
        """
        Retrieve all S2 cells marked as explored.

        The cells come from GPX track imports and from POST /trails/explored.

        Args:
            dbSession: Database session for querying.

        Returns:
            Dictionary containing a list of explored S2 cell identifiers.
        """
        explored = list(dbSession.scalars(select(ExploredTile.s2_cell_id)))
        return {
            "explored": explored
        }

    @router.post(
        "/explored",
        summary="Mark S2 cells as explored",
        response_model=AddExploredTilesResult,
    )
    def addExploredTiles(
        request: AddExploredTilesRequest,
        dbSession: Session = Depends(getDb),
    ):
        """
        Mark S2 cells as explored.

        Validates each cell, filters out already explored ones,
        and only marks tiles that exist in the database.

        Args:
            request: Contains list of S2 cell tokens to mark as explored.
            dbSession: Database session for querying and updating.

        Returns:
            Dictionary with added and skipped cell lists.
        """
        if len(request.cells) > 100:
            request.cells = request.cells[:100]

        added: list[str] = []
        skipped: list[SkippedCell] = []

        for cellToken in request.cells:
            cellId = s2.S2CellId.FromToken(cellToken)
            if not cellId.is_valid() or cellId.id() == 0:
                skipped.append(SkippedCell(cell=cellToken, reason="invalid"))
                continue

            tile = dbSession.query(Tile).filter(Tile.s2_cell_id == cellToken).first()
            if not tile:
                # TODO: temporary. Unknown cells are skipped because creating a tile
                # requires a real-time Overpass query, which is not trusted yet. Hook
                # tile creation here once it is, so runs through unmapped terrain yield
                # normally. See wiki running_stats.md §7 "Unmapped terrain".
                skipped.append(SkippedCell(cell=cellToken, reason="not_found"))
                continue

            if tile.explored is not None:
                continue

            tile.explored = ExploredTile()
            added.append(cellToken)

        dbSession.commit()

        logger.info(
            "POST /trails/explored — added: %d, skipped: %d",
            len(added),
            len(skipped),
        )

        return {
            "added": added,
            "skipped": skipped,
        }
