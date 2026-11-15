"""
Authentication routes for the Kishin API.

The application has one account: ``KISHIN_USERNAME`` and the password hash in
``KISHIN_PASSWORD_HASH`` (see ``config.py``). ``kishin password`` writes that hash.
Logins are throttled per client address (see ``throttle.py``).
"""

import hmac
import logging
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from kishin_trails.config import settings
from kishin_trails.schemas import Token
from kishin_trails.security import PASSWORD_CLAIM, createAccessToken, passwordFingerprint, verifyPassword
from kishin_trails.throttle import LoginThrottle

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

LOGIN_THROTTLE = LoginThrottle(settings.LOGIN_MAX_ATTEMPTS, settings.LOGIN_INTERVAL)


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
def loginForAccessToken(formData: Annotated[OAuth2PasswordRequestForm, Depends()], request: Request):
    """
    Authenticate the account and return an access token.

    Args:
        formData: Standard OAuth2 password request form (username and password).
        request: The request, whose client address keys the login throttle.

    Returns:
        A dictionary containing the access token and its type.

    Raises:
        HTTPException 401: If the username or password is wrong, or the account is not configured.
        HTTPException 429: If the client address reached LOGIN_MAX_ATTEMPTS within LOGIN_INTERVAL.
    """
    clientKey = request.client.host if request.client else "unknown"
    # Checked before the password, so a refused request costs no Argon2 hash.
    if not LOGIN_THROTTLE.tryAttempt(clientKey):
        logger.warning("Login refused for %s: too many attempts.", clientKey)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts; try again later.",
        )

    if not credentialsMatch(formData.username, formData.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    LOGIN_THROTTLE.reset(clientKey)
    accessToken = createAccessToken(
        data={
            "sub": settings.KISHIN_USERNAME,
            PASSWORD_CLAIM: passwordFingerprint(settings.KISHIN_PASSWORD_HASH),
        },
        expiresDelta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": accessToken, "token_type": "bearer"}
