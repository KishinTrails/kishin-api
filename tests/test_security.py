"""
Security and Authentication tests for Kishin API.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from kishin_trails.models import User
from kishin_trails.security import getPasswordHash

TEST_USERNAME = "testuser"
TEST_PASSWORD = "testpassword"

# Fixtures 'client' and 'db_session' are automatically loaded from conftest.py


def createUser(db_session: Session, username: str, password: str) -> User:
    user = User(username=username, hashed_password=getPasswordHash(password))
    db_session.add(user)
    db_session.commit()
    return user


@pytest.mark.asyncio
async def test_login_succeeds(client: AsyncClient, db_session: Session):
    createUser(db_session, TEST_USERNAME, TEST_PASSWORD)
    response = await client.post(
        "/auth/login",
        data={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert "access_token" in result


@pytest.mark.asyncio
async def test_login_fails_invalid_credentials(client: AsyncClient, db_session: Session):
    createUser(db_session, TEST_USERNAME, TEST_PASSWORD)
    response = await client.post(
        "/auth/login",
        data={
            "username": TEST_USERNAME,
            "password": "wrongpassword"
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_requires_auth(client: AsyncClient):
    response = await client.get("/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_succeeds_with_token(client: AsyncClient, db_session: Session):
    createUser(db_session, TEST_USERNAME, TEST_PASSWORD)
    login_res = await client.post(
        "/auth/login",
        data={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        },
    )
    token = login_res.json()["access_token"]

    response = await client.get(
        "/me",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["username"] == TEST_USERNAME


@pytest.mark.asyncio
async def test_registration_is_restricted(client: AsyncClient):
    response = await client.post(
        "/auth/register",
        json={
            "username": "intruder",
            "password": "somepassword"
        },
    )
    assert response.status_code == 404
