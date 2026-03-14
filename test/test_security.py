"""
Security and Authentication tests for Kishin API.
"""

import pytest
from httpx import AsyncClient

TEST_USERNAME = "testuser"
TEST_PASSWORD = "testpassword"
TEST_USERNAME_ALT = "intruder"
TEST_PASSWORD_ALT = "somepassword"

# Fixtures 'client' and 'db_session' are automatically loaded from conftest.py


@pytest.mark.asyncio
async def test_registration_succeeds(client: AsyncClient):
    response = await client.post(
        "/auth/register",
        json={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["username"] == TEST_USERNAME


@pytest.mark.asyncio
async def test_registration_fails_duplicate(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        },
    )
    response = await client.post(
        "/auth/register",
        json={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_login_succeeds(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        },
    )
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
async def test_login_fails_invalid_credentials(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        },
    )
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
async def test_protected_route_succeeds_with_token(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        },
    )
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


@pytest.mark.xfail(reason="registration is restricted to authorized users only")
@pytest.mark.asyncio
async def test_registration_is_restricted(client: AsyncClient):
    response = await client.post(
        "/auth/register",
        json={
            "username": TEST_USERNAME_ALT,
            "password": TEST_PASSWORD_ALT
        },
    )
    assert response.status_code in (403, 401)
