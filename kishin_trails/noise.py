"""
Noise API endpoints for Perlin noise calculations.

Provides API endpoints for querying Perlin noise values for H3 cells,
computed server-side with 100% parity to the frontend implementation.
"""

from kishin_trails.perlin import getNoiseForCell
from kishin_trails.dependencies import getCurrentUser
from kishin_trails.schemas import NoiseRequest, NoiseResponse

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from fastapi import APIRouter, HTTPException, Depends
    from fastapi.responses import JSONResponse

try:
    from fastapi import APIRouter, HTTPException, Depends
except ImportError:  # pragma: no cover
    APIRouter = HTTPException = Depends = None  # type: ignore[assignment]

try:
    from fastapi.responses import JSONResponse
except ImportError:  # pragma: no cover
    JSONResponse = None  # type: ignore[assignment]

if APIRouter:
    router = APIRouter(prefix="/noise", tags=["noise"], dependencies=[Depends(getCurrentUser)])
else:
    router = None


@router.post("/cells", response_model=List[NoiseResponse])  # type: ignore[union-attr]
async def getCellNoise(request: NoiseRequest):
    """
    Get Perlin noise values for multiple H3 cells.
    
    Returns the noise value at the center point of each cell.
    Values are in range [0, 1], computed with the same algorithm
    as the frontend for exact parity.
    
    Args:
        request: Request containing list of H3 cells and scale parameter
    
    Returns:
        List of objects with cell index and noise value
    
    Raises:
        HTTPException: If more than 1000 cells are requested
    """
    if not request.cells:
        return []

    # Limit batch size to prevent abuse
    if len(request.cells) > 1000:
        raise HTTPException(status_code=400, detail="Maximum 1000 cells per request")

    results = []
    for cell in request.cells:
        try:
            noiseValue = getNoiseForCell(cell, request.scale)
            results.append({
                "cell": cell,
                "noise": noiseValue
            })
        except Exception:
            # Skip invalid cells, continue with others
            continue

    return results
