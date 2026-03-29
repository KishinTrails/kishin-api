"""
Trails module for user exploration tracking.

Provides API endpoints for user explored tiles.
"""

from typing import TYPE_CHECKING, List

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from fastapi import APIRouter, Depends

try:
    from fastapi import APIRouter, Depends
except ImportError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]

from kishin_trails.database import getDb
from kishin_trails.dependencies import getCurrentUser
from kishin_trails.models import User
from kishin_trails.schemas import ExploredTilesOut

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
        dbSession: Session = Depends(getDb),
    ):
        """Get list of H3 cell IDs explored by the current user.

        Returns:
            List of explored H3 cell identifiers.
        """
        explored = [tile.h3_cell for tile in currentUser.explored_tiles]
        return {"explored": explored}