"""
Authentication routes for the Kishin API.
"""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from kishin_trails.config import settings
from kishin_trails.database import getDb
from kishin_trails.models import User
from kishin_trails.schemas import Token, UserCreate, User as UserSchema
from kishin_trails.security import (
    createAccessToken,
    getPasswordHash,
    verifyPassword,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserSchema, summary="Register a new user")
def registerUser(user: UserCreate, dbSession: Session = Depends(getDb)):
    """
    Register a new user in the system.

    Args:
        user: The user creation schema containing username and password.
        dbSession: The database session.

    Returns:
        The created user record.

    Raises:
        HTTPException 400: If the username is already registered.
    """
    dbUser = dbSession.query(User).filter(User.username == user.username).first()
    if dbUser:
        raise HTTPException(status_code=400, detail="Username already registered")

    hashedPassword = getPasswordHash(user.password)
    dbUser = User(username=user.username, hashed_password=hashedPassword)
    dbSession.add(dbUser)
    dbSession.commit()
    dbSession.refresh(dbUser)
    return dbUser


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
    if not user or not verifyPassword(formData.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    accessTokenExpires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    accessToken = createAccessToken(
        data={"sub": user.username}, expiresDelta=accessTokenExpires
    )
    return {"access_token": accessToken, "token_type": "bearer"}
