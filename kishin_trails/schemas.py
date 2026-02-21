"""
Pydantic schemas for data validation and serialisation.
"""

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
