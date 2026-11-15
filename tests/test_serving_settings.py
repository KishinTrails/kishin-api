"""
Tests for the settings the server refuses to start without: SECRET_KEY,
KISHIN_USERNAME and KISHIN_PASSWORD_HASH.
"""

import pytest
from typer.testing import CliRunner

from kishin_trails.cli import app as cliApp
from kishin_trails.config import MIN_SECRET_KEY_LENGTH, servingProblems, settings
from kishin_trails.main import app, lifespan

runner = CliRunner()

VALID_KEY = "k" * MIN_SECRET_KEY_LENGTH


@pytest.fixture
def configured(monkeypatch):
    """Every setting the server needs is set."""
    monkeypatch.setattr(settings, "SECRET_KEY", VALID_KEY)
    monkeypatch.setattr(settings, "KISHIN_USERNAME", "foo")
    monkeypatch.setattr(settings, "KISHIN_PASSWORD_HASH", "$argon2id$example")


def test_no_problem_when_configured(configured):
    assert not servingProblems(settings)


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("SECRET_KEY", "", "SECRET_KEY is not set"),
        ("SECRET_KEY", "k" * (MIN_SECRET_KEY_LENGTH - 1), "SECRET_KEY is shorter than"),
        ("KISHIN_USERNAME", "", "KISHIN_USERNAME is not set"),
        ("KISHIN_PASSWORD_HASH", "", "KISHIN_PASSWORD_HASH is not set"),
    ],
)
def test_each_missing_setting_is_reported(configured, monkeypatch, name, value, expected):
    monkeypatch.setattr(settings, name, value)
    problems = servingProblems(settings)
    assert len(problems) == 1
    assert expected in problems[0]


@pytest.mark.asyncio
async def test_lifespan_refuses_to_start_without_secret_key(configured, monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "")
    with pytest.raises(RuntimeError, match="SECRET_KEY is not set"):
        async with lifespan(app):
            pass


def test_run_refuses_to_start_without_secret_key(configured, monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "")
    result = runner.invoke(cliApp, ["run"])
    assert result.exit_code == 1
    assert "SECRET_KEY is not set" in result.output
