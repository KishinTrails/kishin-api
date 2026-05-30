"""
Trails module for user exploration tracking.

Provides API endpoints for managing and retrieving user-explored S2 cells,
allowing users to track their exploration progress across the map.
"""

import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from kishin_trails.database import getDb
from kishin_trails.dependencies import getCurrentUser
from kishin_trails.models import User
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
    router = APIRouter(prefix="/trails", tags=["trails"], dependencies=[Depends(getCurrentUser)])
else:
    router = None

if router:

    @router.get(
        "/explored",
        summary="Get explored tiles for current user",
        response_model=ExploredTilesOut,
    )
    def getExploredTiles(
        currentUser: User = Depends(getCurrentUser),
        _dbSession: Session = Depends(getDb),
    ):
        """
        Retrieve all S2 cells marked as explored by the authenticated user.

        This endpoint returns the complete list of S2 cell identifiers
        that the user has explored, typically populated via GPX track imports.

        Args:
            currentUser: The authenticated user from JWT token.
            _dbSession: Database session for querying.

        Returns:
            Dictionary containing a list of explored S2 cell identifiers.
        """
        explored = [tile.s2_cell_id for tile in currentUser.explored_tiles]
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
        currentUser: User = Depends(getCurrentUser),
        dbSession: Session = Depends(getDb),
    ):
        """
        Mark S2 cells as explored by the authenticated user.

        Validates each cell, filters out already explored ones,
        and only marks tiles that exist in the database.

        Args:
            request: Contains list of S2 cell tokens to mark as explored.
            currentUser: The authenticated user from JWT token.
            dbSession: Database session for querying and updating.

        Returns:
            Dictionary with added and skipped cell lists.
        """
        if len(request.cells) > 100:
            request.cells = request.cells[:100]

        from kishin_trails.models import Tile

        added: list[str] = []
        skipped: list[SkippedCell] = []

        for cellToken in request.cells:
            cellId = s2.S2CellId.FromToken(cellToken)
            if not cellId.is_valid() or cellId.id() == 0:
                skipped.append(SkippedCell(cell=cellToken, reason="invalid"))
                continue

            tile = dbSession.query(Tile).filter(Tile.s2_cell_id == cellToken).first()
            if not tile:
                skipped.append(SkippedCell(cell=cellToken, reason="not_found"))
                continue

            if tile in currentUser.explored_tiles:
                continue

            currentUser.explored_tiles.append(tile)
            added.append(cellToken)

        dbSession.commit()

        logger.info(
            "POST /trails/explored — user: %s, added: %d, skipped: %d",
            currentUser.username,
            len(added),
            len(skipped),
        )

        return {
            "added": added,
            "skipped": skipped,
        }
