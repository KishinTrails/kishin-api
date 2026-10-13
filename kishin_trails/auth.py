"""
Authentication routes for the Kishin API.

Registration is not served over HTTP; accounts are created with `kishin user create`
(see `kishin_trails/cli/user.py`), which is the only path by which a `User` row comes
into existence.
"""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from kishin_trails.config import settings
from kishin_trails.database import getDb
from kishin_trails.models import User
from kishin_trails.schemas import Token
from kishin_trails.security import (
    createAccessToken,
    verifyPassword,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token, summary="Login to receive a JWT")
def loginForAccessToken(
    formData: Annotated[OAuth2PasswordRequestForm, Depends()],
    dbSession: Session = Depends(getDb),
):
    """
    Authenticate a user and return an access token.

    Args:
        formData: Standard OAuth2 password request form (username and password).
        dbSession: The database session.

    Returns:
        A dictionary containing the access token and its type.

    Raises:
        HTTPException 401: If authentication fails.
    """
    user = dbSession.query(User).filter(User.username == formData.username).first()
    if not user or not verifyPassword(formData.password, str(user.hashed_password)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    accessTokenExpires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    accessToken = createAccessToken(
        data={
            "sub": user.username
        }, expiresDelta=accessTokenExpires
    )
    return {
        "access_token": accessToken,
        "token_type": "bearer"
    }
