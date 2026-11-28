"""
Shared dependencies for the Kishin API.
"""

import hmac
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from kishin_trails.config import settings
from kishin_trails.security import ALGORITHM, PASSWORD_CLAIM, passwordFingerprint

# Token location is /api/auth/login (auth.py, under main.py's /api router)
oauth2Scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def requireLogin(token: Annotated[str, Depends(oauth2Scheme)]) -> None:
    """
    Accept a request only with a valid JWT issued to the configured account.

    Args:
        token: The JWT access token.

    Raises:
        HTTPException 401: If the token is invalid or expired, its subject is not ``KISHIN_USERNAME``,
            or it was issued for another password hash than ``KISHIN_PASSWORD_HASH``.
    """
    credentialsException = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError as error:
        raise credentialsException from error

    subject = payload.get("sub")
    if not settings.KISHIN_USERNAME or not isinstance(subject, str):
        raise credentialsException
    if not hmac.compare_digest(subject.encode(), settings.KISHIN_USERNAME.encode()):
        raise credentialsException

    fingerprint = payload.get(PASSWORD_CLAIM)
    if not isinstance(fingerprint, str):
        raise credentialsException
    if not hmac.compare_digest(fingerprint.encode(), passwordFingerprint(settings.KISHIN_PASSWORD_HASH).encode()):
        raise credentialsException
