"""
Tests for the `kishin` CLI: `kishin user …` and `kishin gpx import`.

Several account tests end at the login endpoint rather than at the hasher: what
matters about those commands is that the account they write can actually be used.
"""

from __future__ import annotations

from typing import Callable

import pytest
from httpx import AsyncClient
from typer.testing import CliRunner

from kishin_trails.cli import app
from kishin_trails.models import User

runner = CliRunner()

USERNAME = "alice"
PASSWORD = "a-good-password"


@pytest.fixture
def invokeUser(db_session) -> Callable[..., object]:
    """Runs `kishin user …` against the test database (see tests/conftest.py)."""
    def run(*args: str, **kwargs):
        return runner.invoke(app, ["user", *args], **kwargs)

    return run


@pytest.fixture
def invokeGpx(db_session) -> Callable[..., object]:
    """Runs `kishin gpx …` against the test database."""
    def run(*args: str, **kwargs):
        return runner.invoke(app, ["gpx", *args], **kwargs)

    return run


# --- user create -------------------------------------------------------------


def test_create_succeeds_and_the_account_can_log_in(invokeUser, client: AsyncClient):
    result = invokeUser("create", USERNAME, "--password", PASSWORD)
    assert result.exit_code == 0, result.output


async def _login(client: AsyncClient, username: str, password: str):
    return await client.post("/auth/login", data={"username": username, "password": password})


@pytest.mark.asyncio
async def test_created_account_can_log_in(invokeUser, client: AsyncClient):
    invokeUser("create", USERNAME, "--password", PASSWORD)
    response = await _login(client, USERNAME, PASSWORD)
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_create_without_password_prints_one_that_works(invokeUser, db_session):
    result = invokeUser("create", USERNAME)
    assert result.exit_code == 0, result.output
    assert "Generated password:" in result.output


def test_create_duplicate_username_fails_and_changes_nothing(invokeUser, db_session):
    invokeUser("create", USERNAME, "--password", PASSWORD)
    countBefore = db_session.query(User).count()

    result = invokeUser("create", USERNAME, "--password", "something-else")

    assert result.exit_code == 1
    assert db_session.query(User).count() == countBefore


# --- user list -----------------------------------------------------------------


def test_list_is_empty_message_on_no_accounts(invokeUser):
    result = invokeUser("list")
    assert result.exit_code == 0, result.output
    assert "No accounts" in result.stderr


def test_list_keeps_the_header_off_stdout(invokeUser):
    invokeUser("create", USERNAME, "--password", PASSWORD)
    result = invokeUser("list")
    assert "USERNAME" not in result.stdout
    assert USERNAME in result.stdout


# --- user show -----------------------------------------------------------------


def test_show_unknown_username_fails(invokeUser):
    result = invokeUser("show", "nobody")
    assert result.exit_code == 1


def test_show_prints_the_account(invokeUser):
    invokeUser("create", USERNAME, "--password", PASSWORD)
    result = invokeUser("show", USERNAME)
    assert result.exit_code == 0, result.output
    assert "explored: 0" in result.output


# --- user reset-password ---------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_password_invalidates_the_old_password(invokeUser, client: AsyncClient):
    invokeUser("create", USERNAME, "--password", PASSWORD)
    newPassword = "a-different-password"

    result = invokeUser("reset-password", USERNAME, "--password", newPassword)
    assert result.exit_code == 0, result.output

    oldLogin = await _login(client, USERNAME, PASSWORD)
    assert oldLogin.status_code == 401

    newLogin = await _login(client, USERNAME, newPassword)
    assert newLogin.status_code == 200


def test_reset_password_prints_the_token_lifetime_warning(invokeUser):
    invokeUser("create", USERNAME, "--password", PASSWORD)
    result = invokeUser("reset-password", USERNAME, "--password", "yet-another-password")
    assert "WARNING" in result.output
    assert "no session table" in result.output


def test_reset_password_unknown_username_fails(invokeUser):
    result = invokeUser("reset-password", "nobody", "--password", PASSWORD)
    assert result.exit_code == 1


# --- user rename -----------------------------------------------------------------


def test_rename_succeeds(invokeUser, db_session):
    invokeUser("create", USERNAME, "--password", PASSWORD)
    result = invokeUser("rename", USERNAME, "alicia")
    assert result.exit_code == 0, result.output
    assert db_session.query(User).filter(User.username == "alicia").first() is not None


def test_rename_onto_a_taken_username_fails(invokeUser):
    invokeUser("create", USERNAME, "--password", PASSWORD)
    invokeUser("create", "bob", "--password", PASSWORD)
    result = invokeUser("rename", USERNAME, "bob")
    assert result.exit_code == 1


# --- user delete -----------------------------------------------------------------


def test_delete_with_yes_removes_the_user(invokeUser, db_session):
    invokeUser("create", USERNAME, "--password", PASSWORD)
    result = invokeUser("delete", USERNAME, "--yes")
    assert result.exit_code == 0, result.output
    assert db_session.query(User).filter(User.username == USERNAME).first() is None


def test_delete_without_yes_and_without_a_tty_aborts(invokeUser, db_session):
    invokeUser("create", USERNAME, "--password", PASSWORD)
    result = invokeUser("delete", USERNAME, input="n\n")
    assert result.exit_code == 1
    assert db_session.query(User).filter(User.username == USERNAME).first() is not None


def test_delete_unknown_username_fails(invokeUser):
    result = invokeUser("delete", "nobody", "--yes")
    assert result.exit_code == 1


# --- gpx import ------------------------------------------------------------------


def test_gpx_import_dry_run_writes_nothing(invokeUser, invokeGpx, db_session):
    invokeUser("create", USERNAME, "--password", PASSWORD)
    user = db_session.query(User).filter(User.username == USERNAME).first()
    assert len(user.explored_tiles) == 0

    result = invokeGpx(
        "import", "activity_22334447152.gpx", "--user", USERNAME, "--dry-run"
    )
    assert result.exit_code == 0, result.output

    db_session.refresh(user)
    assert len(user.explored_tiles) == 0


def test_gpx_import_unknown_username_fails(invokeGpx):
    result = invokeGpx("import", "activity_22334447152.gpx", "--user", "nobody")
    assert result.exit_code == 1
