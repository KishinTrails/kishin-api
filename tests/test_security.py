"""
Security and Authentication tests for Kishin API: the single account configured
by KISHIN_USERNAME and KISHIN_PASSWORD_HASH.
"""

import datetime

import pytest
from httpx import AsyncClient

from kishin_trails.config import settings
from kishin_trails.security import PASSWORD_CLAIM, createAccessToken, getPasswordHash, passwordFingerprint

TEST_USERNAME = "foo"
TEST_PASSWORD = "testpassword"

PROTECTED_ROUTE = "/trails/explored"

# Fixtures 'client' and 'db_session' are automatically loaded from conftest.py


@pytest.fixture
def account(monkeypatch):
    """Configures the account foo / testpassword."""
    monkeypatch.setattr(settings, "KISHIN_USERNAME", TEST_USERNAME)
    monkeypatch.setattr(settings, "KISHIN_PASSWORD_HASH", getPasswordHash(TEST_PASSWORD))


async def _login(client: AsyncClient, username: str, password: str):
    return await client.post("/auth/login", data={"username": username, "password": password})


@pytest.mark.asyncio
async def test_login_succeeds(client: AsyncClient, account):
    response = await _login(client, TEST_USERNAME, TEST_PASSWORD)
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize(("username", "password"), [(TEST_USERNAME, "wrongpassword"), ("bar", TEST_PASSWORD)])
async def test_login_fails_invalid_credentials(client: AsyncClient, account, username, password):
    response = await _login(client, username, password)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_refused_without_a_configured_account(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "KISHIN_USERNAME", "")
    monkeypatch.setattr(settings, "KISHIN_PASSWORD_HASH", "")
    response = await _login(client, TEST_USERNAME, TEST_PASSWORD)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_password_hash_with_a_trailing_newline(client: AsyncClient, account, monkeypatch):
    monkeypatch.setattr(settings, "KISHIN_PASSWORD_HASH", getPasswordHash(TEST_PASSWORD) + "\n")
    response = await _login(client, TEST_USERNAME, TEST_PASSWORD)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_protected_route_requires_auth(client: AsyncClient):
    response = await client.get(PROTECTED_ROUTE)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_succeeds_with_token(client: AsyncClient, account):
    token = (await _login(client, TEST_USERNAME, TEST_PASSWORD)).json()["access_token"]
    response = await client.get(PROTECTED_ROUTE, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_token_of_another_username_is_refused(client: AsyncClient, account):
    token = createAccessToken({"sub": "bar", PASSWORD_CLAIM: passwordFingerprint(settings.KISHIN_PASSWORD_HASH)})
    response = await client.get(PROTECTED_ROUTE, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_token_after_a_username_change_is_refused(client: AsyncClient, account, monkeypatch):
    token = (await _login(client, TEST_USERNAME, TEST_PASSWORD)).json()["access_token"]
    monkeypatch.setattr(settings, "KISHIN_USERNAME", "bar")
    response = await client.get(PROTECTED_ROUTE, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_expired_token_is_refused(client: AsyncClient, account):
    token = createAccessToken(
        {"sub": TEST_USERNAME, PASSWORD_CLAIM: passwordFingerprint(settings.KISHIN_PASSWORD_HASH)},
        expiresDelta=datetime.timedelta(minutes=-1),
    )
    response = await client.get(PROTECTED_ROUTE, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_token_after_a_password_change_is_refused(client: AsyncClient, account, monkeypatch):
    token = (await _login(client, TEST_USERNAME, TEST_PASSWORD)).json()["access_token"]
    monkeypatch.setattr(settings, "KISHIN_PASSWORD_HASH", getPasswordHash("anotherpassword"))
    response = await client.get(PROTECTED_ROUTE, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_token_without_password_fingerprint_is_refused(client: AsyncClient, account):
    token = createAccessToken({"sub": TEST_USERNAME})
    response = await client.get(PROTECTED_ROUTE, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_password_fingerprint_ignores_a_trailing_newline():
    hashed = getPasswordHash(TEST_PASSWORD)
    assert passwordFingerprint(hashed) == passwordFingerprint(hashed + "\n")


@pytest.mark.asyncio
async def test_registration_is_restricted(client: AsyncClient):
    response = await client.post("/auth/register", json={"username": "bar", "password": "somepassword"})
    assert response.status_code == 404
