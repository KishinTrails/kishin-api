"""
Pydantic schemas for data validation and serialisation.

Provides request/response models for the API endpoints.
"""

from typing import List

from pydantic import BaseModel, ConfigDict


class UserBase(BaseModel):
    """Base user schema sharing common attributes.

    Attributes:
        username: The user's unique username.
    """

    username: str


class UserCreate(UserBase):
    """Schema for creating a new user.

    Attributes:
        username: Desired username (must be unique).
        password: Plain-text password (will be hashed).
    """

    password: str


class User(UserBase):
    """Schema for returning user data.

    Attributes:
        id: Unique user identifier.
        username: The user's username.
    """

    id: int
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    """Schema for the JWT access token response.

    Attributes:
        access_token: The JWT token string.
        token_type: The token type (typically 'bearer').
    """

    access_token: str
    token_type: str


class TokenData(BaseModel):
    """Schema for the data payload encoded within the JWT.

    Attributes:
        username: The username from the token subject.
    """

    username: str | None = None


class POIBase(BaseModel):
    """Base schema for Point of Interest data.

    Attributes:
        osm_id: OpenStreetMap element ID.
        name: Name of the POI.
        lat: Latitude coordinate.
        lon: Longitude coordinate.
        elevation: Elevation in meters (optional).
    """

    osm_id: int
    name: str | None
    lat: float
    lon: float
    elevation: int | None


class POIOut(POIBase):
    """Schema for POI responses with ORM model support."""
    model_config = ConfigDict(from_attributes=True)


class TileOut(BaseModel):
    """Schema for tile (H3 cell) responses.

    Attributes:
        h3_cell: The H3 cell identifier.
        tile_type: Type of POI in the tile.
        pois: List of POIs within this tile.
    """

    h3_cell: str
    tile_type: str | None
    pois: List[POIOut] = []

    model_config = ConfigDict(from_attributes=True)


class ExploredTilesOut(BaseModel):
    """Schema for explored tiles response.

    Attributes:
        explored: List of explored H3 cell identifiers.
    """

    explored: List[str]


class NoiseRequest(BaseModel):
    """Request model for noise calculation."""

    cells: List[str]
    scale: int = 50


class NoiseResponse(BaseModel):
    """Response model for single cell noise value."""

    cell: str
    noise: float
