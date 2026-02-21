"""
Security utilities for password hashing and JWT token management.
"""

import datetime
from typing import Any, Union

import jwt
from pwdlib import PasswordHash
from kishin_trails.config import settings

# Initialize pwdlib with Argon2
password_hash = PasswordHash.recommended()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain-text password against a hashed version.

    Args:
        plain_password: The raw password to check.
        hashed_password: The stored hashed password.

    Returns:
        True if the password matches, False otherwise.
    """
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Hash a password using the configured hashing algorithm.

    Args:
        password: The plain-text password to hash.

    Returns:
        The hashed password string.
    """
    return password_hash.hash(password)


def create_access_token(data: dict, expires_delta: Union[datetime.timedelta, None] = None) -> str:
    """
    Create a new JWT access token.

    Args:
        data: The dictionary of data to encode into the token.
        expires_delta: Optional duration after which the token expires.

    Returns:
        The encoded JWT string.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.now(datetime.UTC) + expires_delta
    else:
        expire = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({
        "exp": expire
    })
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt
