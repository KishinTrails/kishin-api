"""
Shared helpers for the ``kishin`` CLI command groups.
"""

from __future__ import annotations

import secrets

import typer
from sqlalchemy.orm import Session

from kishin_trails import database

#: Bytes of randomness behind a generated password. Hex-encoded, so 24 characters.
GENERATED_PASSWORD_BYTES = 12

MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 4096


def fail(message: str) -> None:
    """Prints an error to stderr and exits non-zero."""
    typer.secho(f"[ERROR] {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def openSession() -> Session:
    """Opens a session from the live session factory.

    Reads ``database.SESSION_LOCAL`` off the module rather than importing the
    name directly, so both ``init_engine()``'s rebinding and the test suite's
    replacement of ``SESSION_LOCAL`` (see ``tests/conftest.py``) take effect —
    an import-time ``from kishin_trails.database import SESSION_LOCAL`` would
    bind to whichever factory existed when this module was first imported.
    """
    return database.SESSION_LOCAL()


def generatePassword() -> str:
    """A random password, shown once and stored only as a hash."""
    return secrets.token_hex(GENERATED_PASSWORD_BYTES)


def checkPassword(password: str) -> None:
    """Rejects a password outside the accepted length range.

    The upper bound is a policy limit; pwdlib/Argon2 has no 72-byte truncation
    the way bcrypt does, but a bound still guards against pathological input.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        fail(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        fail(f"Password must be at most {MAX_PASSWORD_LENGTH} characters.")


def column(rows: list[str]) -> int:
    """Width to pad a column to, so aligned output lines up with the data it holds."""
    return max((len(row) for row in rows), default=0)
