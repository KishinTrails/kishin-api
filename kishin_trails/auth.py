"""
Authentication routes for the Kishin API.
"""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from kishin_trails.config import settings
from kishin_trails.database import get_db
from kishin_trails.models import User
from kishin_trails.schemas import Token, UserCreate, User as UserSchema
from kishin_trails.security import (
    create_access_token,
    get_password_hash,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserSchema, summary="Register a new user")
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user in the system.

    Args:
        user: The user creation schema containing username and password.
        db: The database session.

    Returns:
        The created user record.

    Raises:
        HTTPException 400: If the username is already registered.
    """
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    hashed_password = get_password_hash(user.password)
    db_user = User(username=user.username, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@router.post("/login", response_model=Token, summary="Login to receive a JWT")
def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db),
):
    """
    Authenticate a user and return an access token.

    Args:
        form_data: Standard OAuth2 password request form (username and password).
        db: The database session.

    Returns:
        A dictionary containing the access token and its type.

    Raises:
        HTTPException 401: If authentication fails.
    """
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}
