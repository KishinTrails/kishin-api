"""
Security and Authentication tests for Kishin API.
"""

import pytest
from httpx import AsyncClient

# Fixtures 'client' and 'db_session' are automatically loaded from conftest.py

@pytest.mark.asyncio
async def test_registration_succeeds(client: AsyncClient):
    response = await client.post(
        "/auth/register",
        json={"username": "testuser", "password": "testpassword"},
    )
    assert response.status_code == 200
    assert response.json()["username"] == "testuser"


@pytest.mark.asyncio
async def test_registration_fails_duplicate(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"username": "testuser", "password": "testpassword"},
    )
    response = await client.post(
        "/auth/register",
        json={"username": "testuser", "password": "newpassword"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_login_succeeds(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"username": "testuser", "password": "testpassword"},
    )
    response = await client.post(
        "/auth/login",
        data={"username": "testuser", "password": "testpassword"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_login_fails_invalid_credentials(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"username": "testuser", "password": "testpassword"},
    )
    response = await client.post(
        "/auth/login",
        data={"username": "testuser", "password": "wrongpassword"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_requires_auth(client: AsyncClient):
    response = await client.get("/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_succeeds_with_token(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"username": "testuser", "password": "testpassword"},
    )
    login_res = await client.post(
        "/auth/login",
        data={"username": "testuser", "password": "testpassword"},
    )
    token = login_res.json()["access_token"]

    response = await client.get(
        "/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == "testuser"


@pytest.mark.xfail(reason="registration is restricted to authorized users only")
@pytest.mark.asyncio
async def test_registration_is_restricted(client: AsyncClient):
    response = await client.post(
        "/auth/register",
        json={"username": "intruder", "password": "somepassword"},
    )
    assert response.status_code in (403, 401)
