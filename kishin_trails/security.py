"""
Security utilities for password hashing and JWT token management.
"""

import datetime
from typing import Union

import jwt
from pwdlib import PasswordHash
from kishin_trails.config import settings

# Initialize pwdlib with Argon2
PASSWORD_HASH = PasswordHash.recommended()


def verifyPassword(plainPassword: str, hashedPassword: str) -> bool:
    """
    Verify a plain-text password against a hashed version.

    Args:
        plainPassword: The raw password to check.
        hashedPassword: The stored hashed password.

    Returns:
        True if the password matches, False otherwise.
    """
    return PASSWORD_HASH.verify(plainPassword, hashedPassword)


def getPasswordHash(password: str) -> str:
    """
    Hash a password using the configured hashing algorithm.

    Args:
        password: The plain-text password to hash.

    Returns:
        The hashed password string.
    """
    return PASSWORD_HASH.hash(password)


def createAccessToken(data: dict, expiresDelta: Union[datetime.timedelta, None] = None) -> str:
    """
    Create a new JWT access token.

    Args:
        data: The dictionary of data to encode into the token.
        expiresDelta: Optional duration after which the token expires.

    Returns:
        The encoded JWT string.
    """
    toEncode = data.copy()
    if expiresDelta:
        expire = datetime.datetime.now(datetime.UTC) + expiresDelta
    else:
        expire = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    toEncode.update({
        "exp": expire
    })
    encodedJwt = jwt.encode(toEncode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encodedJwt
