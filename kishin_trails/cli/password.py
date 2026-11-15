"""
``kishin password`` — the password of the application's only account.

    kishin password /srv/secrets/kishin_password_hash
    kishin password dev-secrets/KISHIN_PASSWORD_HASH

Prompts for the password twice and writes its Argon2 hash to FILE, readable by
its owner only. The server reads the hash from the setting KISHIN_PASSWORD_HASH:
mount FILE at /run/secrets/KISHIN_PASSWORD_HASH, or keep it in dev-secrets/ for
a local run. The username is the setting KISHIN_USERNAME.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer

from kishin_trails.config import settings
from kishin_trails.security import getPasswordHash

from .common import checkPassword, fail

#: Permissions of the hash file: read and write for its owner only.
HASH_FILE_MODE = 0o600


def setPassword(
    file: Annotated[Path, typer.Argument(help="File to write the password hash to", dir_okay=False)],
) -> None:
    """Write the hash of a new password to FILE."""
    if not file.parent.is_dir():
        fail(f"{file.parent} is not a directory.")
    password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    checkPassword(password)

    descriptor = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, HASH_FILE_MODE)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(getPasswordHash(password))
    os.chmod(file, HASH_FILE_MODE)

    typer.secho(f"[OK] Password hash written to {file}.", fg=typer.colors.GREEN)
    typer.secho(
        "[WARNING] The server reads the hash at startup: restart it. Tokens issued before stay valid for up to "
        f"{settings.ACCESS_TOKEN_EXPIRE_MINUTES} minutes; change SECRET_KEY to end them now.",
        fg=typer.colors.YELLOW,
    )
