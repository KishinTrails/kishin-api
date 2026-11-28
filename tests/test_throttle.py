"""
Tests for the login throttle: the class itself and its use by POST /auth/login.
"""

import threading

import pytest
from httpx import ASGITransport, AsyncClient

from kishin_trails.auth import LOGIN_THROTTLE
from kishin_trails.config import settings
from kishin_trails.main import app
from kishin_trails.security import getPasswordHash
from kishin_trails.throttle import LoginThrottle

TEST_USERNAME = "foo"
TEST_PASSWORD = "testpassword"


# --- LoginThrottle -------------------------------------------------------------------


def test_refuses_once_the_limit_is_reached():
    throttle = LoginThrottle(maxAttempts=2, interval=60)
    assert throttle.tryAttempt("a", now=0)
    assert throttle.tryAttempt("a", now=1)
    assert not throttle.tryAttempt("a", now=2)


def test_accepts_again_after_the_interval():
    throttle = LoginThrottle(maxAttempts=1, interval=60)
    assert throttle.tryAttempt("a", now=0)
    assert not throttle.tryAttempt("a", now=59)
    assert throttle.tryAttempt("a", now=60)


def test_a_refused_attempt_is_not_counted():
    throttle = LoginThrottle(maxAttempts=1, interval=60)
    assert throttle.tryAttempt("a", now=0)
    for second in range(1, 50):
        assert not throttle.tryAttempt("a", now=second)
    assert throttle.tryAttempt("a", now=60)


def test_keys_are_counted_separately():
    throttle = LoginThrottle(maxAttempts=1, interval=60)
    assert throttle.tryAttempt("a", now=0)
    assert throttle.tryAttempt("b", now=0)


def test_reset_clears_a_key():
    throttle = LoginThrottle(maxAttempts=1, interval=60)
    throttle.tryAttempt("a", now=0)
    throttle.reset("a")
    assert throttle.tryAttempt("a", now=1)


def test_zero_attempts_disables_it():
    throttle = LoginThrottle(maxAttempts=0, interval=60)
    assert all(throttle.tryAttempt("a", now=0) for _ in range(100))


def test_parallel_attempts_do_not_pass_the_limit():
    throttle = LoginThrottle(maxAttempts=5, interval=60)
    accepted = []
    barrier = threading.Barrier(40)

    def attempt():
        barrier.wait()
        accepted.append(throttle.tryAttempt("a"))

    threads = [threading.Thread(target=attempt) for _ in range(40)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert accepted.count(True) == 5


# --- POST /auth/login ----------------------------------------------------------------


@pytest.fixture
def account(monkeypatch):
    """Configures the account foo / testpassword and a limit of 3 attempts."""
    monkeypatch.setattr(settings, "KISHIN_USERNAME", TEST_USERNAME)
    monkeypatch.setattr(settings, "KISHIN_PASSWORD_HASH", getPasswordHash(TEST_PASSWORD))
    monkeypatch.setattr(LOGIN_THROTTLE, "maxAttempts", 3)


async def _login(address: str, password: str) -> int:
    transport = ASGITransport(app=app, client=(address, 12345))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/auth/login", data={"username": TEST_USERNAME, "password": password})
    return response.status_code


@pytest.mark.asyncio
async def test_login_refused_after_too_many_failures(account):
    for _ in range(3):
        assert await _login("192.0.2.1", "wrongpassword") == 401
    assert await _login("192.0.2.1", TEST_PASSWORD) == 429


@pytest.mark.asyncio
async def test_other_address_is_not_refused(account):
    for _ in range(3):
        await _login("192.0.2.1", "wrongpassword")
    assert await _login("192.0.2.2", TEST_PASSWORD) == 200


@pytest.mark.asyncio
async def test_success_clears_the_count(account):
    for _ in range(2):
        await _login("192.0.2.1", "wrongpassword")
    assert await _login("192.0.2.1", TEST_PASSWORD) == 200
    for _ in range(2):
        assert await _login("192.0.2.1", "wrongpassword") == 401
    assert await _login("192.0.2.1", TEST_PASSWORD) == 200
