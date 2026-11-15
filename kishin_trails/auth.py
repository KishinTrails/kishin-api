"""
Authentication routes for the Kishin API.

The application has one account: ``KISHIN_USERNAME`` and the password hash in
``KISHIN_PASSWORD_HASH`` (see ``config.py``). ``kishin password`` writes that hash.
"""

import hmac
import logging
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from kishin_trails.config import settings
from kishin_trails.schemas import Token
from kishin_trails.security import createAccessToken, verifyPassword

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def credentialsMatch(username: str, password: str) -> bool:
    """Whether a username and password are those of the configured account.

    False when the account is not configured (empty username or hash).
    """
    if not settings.KISHIN_USERNAME or not settings.KISHIN_PASSWORD_HASH:
        logger.error("Login refused: KISHIN_USERNAME or KISHIN_PASSWORD_HASH is not set.")
        return False
    usernameMatches = hmac.compare_digest(username.encode(), settings.KISHIN_USERNAME.encode())
    passwordMatches = verifyPassword(password, settings.KISHIN_PASSWORD_HASH.strip())
    return usernameMatches and passwordMatches


@router.post("/login", response_model=Token, summary="Login to receive a JWT")
def loginForAccessToken(formData: Annotated[OAuth2PasswordRequestForm, Depends()]):
    """
    Authenticate the account and return an access token.

    Args:
        formData: Standard OAuth2 password request form (username and password).

    Returns:
        A dictionary containing the access token and its type.

    Raises:
        HTTPException 401: If the username or password is wrong, or the account is not configured.
    """
    if not credentialsMatch(formData.username, formData.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    accessToken = createAccessToken(
        data={"sub": settings.KISHIN_USERNAME},
        expiresDelta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": accessToken, "token_type": "bearer"}
