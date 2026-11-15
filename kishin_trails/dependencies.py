"""
Shared dependencies for the Kishin API.
"""

import hmac
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from kishin_trails.config import settings

# Token location is /auth/login (see auth.py)
oauth2Scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def requireLogin(token: Annotated[str, Depends(oauth2Scheme)]) -> None:
    """
    Accept a request only with a valid JWT issued to the configured account.

    Args:
        token: The JWT access token.

    Raises:
        HTTPException 401: If the token is invalid or expired, or its subject is not ``KISHIN_USERNAME``.
    """
    credentialsException = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.PyJWTError as error:
        raise credentialsException from error

    subject = payload.get("sub")
    if not settings.KISHIN_USERNAME or not isinstance(subject, str):
        raise credentialsException
    if not hmac.compare_digest(subject.encode(), settings.KISHIN_USERNAME.encode()):
        raise credentialsException
