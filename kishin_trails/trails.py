"""
Trails module for user exploration tracking.

Provides API endpoints for managing and retrieving user-explored H3 tiles,
allowing users to track their exploration progress across the map.
"""

import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from kishin_trails.database import getDb
from kishin_trails.dependencies import getCurrentUser
from kishin_trails.models import User
from kishin_trails.schemas import ExploredTilesOut

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
        Retrieve all H3 cells marked as explored by the authenticated user.

        This endpoint returns the complete list of H3 hexagonal cell identifiers
        that the user has explored, typically populated via GPX track imports.

        Args:
            currentUser: The authenticated user from JWT token.
            _dbSession: Database session for querying.

        Returns:
            Dictionary containing a list of explored H3 cell identifiers.
        """
        explored = [tile.h3_cell for tile in currentUser.explored_tiles]
        return {
            "explored": explored
        }

    @router.post(
        "/explored",
        summary="Log explored tiles request",
    )
    def logExploredTilesRequest(
        currentUser: User = Depends(getCurrentUser),
        _dbSession: Session = Depends(getDb),
        cell: str | None = None,
    ):
        logger.info("POST /trails/explored — user: %s, cell: %s", currentUser.username, cell)
        return None
