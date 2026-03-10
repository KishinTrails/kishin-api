"""
Pydantic schemas for data validation and serialisation.
"""

from typing import List

from pydantic import BaseModel, ConfigDict


class UserBase(BaseModel):
    """
    Base user schema sharing common attributes.
    """

    username: str


class UserCreate(UserBase):
    """
    Schema for creating a new user, including the plain-text password.
    """

    password: str


class User(UserBase):
    """
    Schema for returning user data, excluding sensitive fields.
    """

    id: int
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    """
    Schema for the JWT access token response.
    """

    access_token: str
    token_type: str


class TokenData(BaseModel):
    """
    Schema for the data payload encoded within the JWT.
    """

    username: str | None = None


class POIBase(BaseModel):
    osm_id: int
    name: str | None
    lat: float
    lon: float
    elevation: int | None


class POIOut(POIBase):
    model_config = ConfigDict(from_attributes=True)


class TileOut(BaseModel):
    h3_cell: str
    tile_type: str | None
    pois: List[POIOut] = []

    model_config = ConfigDict(from_attributes=True)
