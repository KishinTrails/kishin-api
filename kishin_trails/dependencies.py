"""
Shared dependencies for the Kishin API.
"""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from kishin_trails.config import settings
from kishin_trails.database import getDb
from kishin_trails.models import User
from kishin_trails.schemas import TokenData

# Token location is /auth/login (to be defined in auth.py)
oauth2Scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def getCurrentUser(
    token: Annotated[str, Depends(oauth2Scheme)],
    dbSession: Annotated[Session, Depends(getDb)],
) -> User:
    """
    Authenticate a user by verifying their JWT token.

    Args:
        token: The JWT access token.
        dbSession: The database session.

    Returns:
        The authenticated User model instance.

    Raises:
        HTTPException 401: If the token is invalid or the user is not found.
    """
    credentialsException = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentialsException
        tokenData = TokenData(username=username)
    except jwt.PyJWTError:
        raise credentialsException

    user = dbSession.query(User).filter(User.username == tokenData.username).first()
    if user is None:
        raise credentialsException
    return user
