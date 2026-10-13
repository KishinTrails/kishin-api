"""
``kishin user`` — account administration.

The only way to create an account, now that ``POST /auth/register`` is gone (see
``kishin_trails/auth.py``): this group is the sole path by which a ``User`` row comes
into existence.

    kishin user list
    kishin user create alice
    kishin user create alice --password '...'
    kishin user show alice --tiles
    kishin user reset-password alice
    kishin user rename alice alicia
    kishin user delete alice --yes
"""

from __future__ import annotations

from typing import Annotated

import typer
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from kishin_trails.config import settings
from kishin_trails.models import User, user_explored_tiles
from kishin_trails.security import getPasswordHash

from .common import checkPassword, column, fail, generatePassword, openSession

app = typer.Typer(help="Account administration.", no_args_is_help=True)

UsernameArgument = Annotated[str, typer.Argument(help="Username of the account")]
PasswordOption = Annotated[
    str | None,
    typer.Option("--password", "-p", help="Omit to generate a random one and print it."),
]


@app.command("list")
def listUsers() -> None:
    """List the accounts, with how many S2 cells each has explored."""
    with openSession() as session:
        accounts = session.scalars(select(User).order_by(User.username)).all()
        if not accounts:
            typer.secho(
                "No accounts. Create one with `kishin user create`.",
                fg=typer.colors.YELLOW,
                err=True,
            )
            return

        explored = dict(
            session.execute(
                select(
                    user_explored_tiles.c.user_id,
                    func.count(),  # pylint: disable=not-callable
                ).group_by(user_explored_tiles.c.user_id)
            ).all()
        )

        # Padded to the longest username so the columns line up, and separated by
        # two spaces so a reader can still cut on whitespace.
        width = column([account.username for account in accounts] + ["USERNAME"])
        typer.secho(f"{'USERNAME':<{width}}  EXPLORED", fg=typer.colors.BLUE, err=True)
        for account in accounts:
            typer.echo(f"{account.username:<{width}}  {explored.get(account.id, 0)}")


@app.command("create")
def create(
    username: UsernameArgument,
    password: PasswordOption = None,
) -> None:
    """Create an account."""
    username = username.strip()
    if not username:
        fail("Username must not be empty.")

    generated = password is None
    if password is None:
        password = generatePassword()
    checkPassword(password)

    with openSession() as session:
        if session.scalar(select(User).where(User.username == username)) is not None:
            fail(f'An account already exists for "{username}".')

        account = User(username=username, hashed_password=getPasswordHash(password))
        session.add(account)
        try:
            session.commit()
        except IntegrityError:
            # The lookup above races with a concurrent run; the unique index on
            # username is what actually guarantees it.
            session.rollback()
            fail(f'An account already exists for "{username}".')

        typer.secho(f"[OK] Created {username}.", fg=typer.colors.GREEN)
        if generated:
            # The only time this password is visible. It is stored only as a hash.
            typer.echo(f"  Generated password: {password}")


@app.command("show")
def show(
    username: UsernameArgument,
    tiles: Annotated[
        bool,
        typer.Option("--tiles", help="Also print every explored S2 cell, one per line."),
    ] = False,
) -> None:
    """Show one account's id and how many S2 cells it has explored."""
    with openSession() as session:
        account = session.scalar(select(User).where(User.username == username))
        if account is None:
            fail(f'No account found for "{username}".')
            return  # unreachable; fail() exits, and this tells the type checker so

        typer.secho(f"username: {account.username}", fg=typer.colors.BLUE, err=True)
        typer.echo(f"  id: {account.id}")
        typer.echo(f"  explored: {len(account.explored_tiles)}")
        if tiles:
            for tile in sorted(cell.s2_cell_id for cell in account.explored_tiles):
                typer.echo(tile)


@app.command("reset-password")
def resetPassword(
    username: UsernameArgument,
    password: PasswordOption = None,
) -> None:
    """Set an account's password."""
    generated = password is None
    if password is None:
        password = generatePassword()
    checkPassword(password)

    with openSession() as session:
        account = session.scalar(select(User).where(User.username == username))
        if account is None:
            fail(f'No account found for "{username}".')
            return  # unreachable; fail() exits, and this tells the type checker so

        account.hashed_password = getPasswordHash(password)
        session.commit()

        typer.secho(f"[OK] Password updated for {username}.", fg=typer.colors.GREEN)
        if generated:
            typer.echo(f"  Generated password: {password}")
        # Unlike inkspire, kishin's JWTs carry no server-side session table to
        # revoke: a token issued before this reset keeps working for up to
        # ACCESS_TOKEN_EXPIRE_MINUTES after it was issued, reset or not.
        typer.secho(
            "[WARNING] Tokens issued before this reset remain valid for up to "
            f"{settings.ACCESS_TOKEN_EXPIRE_MINUTES} more minutes — there is no "
            "session table to revoke them from.",
            fg=typer.colors.YELLOW,
        )


@app.command("rename")
def rename(
    username: UsernameArgument,
    newUsername: Annotated[str, typer.Argument(help="New username")],
) -> None:
    """Rename an account."""
    newUsername = newUsername.strip()
    if not newUsername:
        fail("New username must not be empty.")

    with openSession() as session:
        account = session.scalar(select(User).where(User.username == username))
        if account is None:
            fail(f'No account found for "{username}".')
            return  # unreachable; fail() exits, and this tells the type checker so

        if session.scalar(select(User).where(User.username == newUsername)) is not None:
            fail(f'An account already exists for "{newUsername}".')

        account.username = newUsername
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            fail(f'An account already exists for "{newUsername}".')

        typer.secho(f"[OK] Renamed {username} to {newUsername}.", fg=typer.colors.GREEN)


@app.command("delete")
def delete(
    username: UsernameArgument,
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Skip the confirmation prompt."),
    ] = False,
) -> None:
    """Delete an account and its explored-tile history.

    Unlike every other command in this CLI, this one asks for confirmation
    first (unless ``--yes`` is given): a user's exploration history cannot be
    recovered afterwards, whereas the ``Tile``/``POI`` rows themselves are
    shared and stay in place.
    """
    with openSession() as session:
        account = session.scalar(select(User).where(User.username == username))
        if account is None:
            fail(f'No account found for "{username}".')
            return  # unreachable; fail() exits, and this tells the type checker so

        exploredCount = len(account.explored_tiles)
        if not yes:
            confirmed = typer.confirm(
                f'Delete "{username}" and its {exploredCount} explored tile(s)? '
                "This cannot be undone."
            )
            if not confirmed:
                raise typer.Exit(code=1)

        session.delete(account)
        session.commit()

        typer.secho(
            f"[OK] Deleted {username} ({exploredCount} explored tile(s) lost).",
            fg=typer.colors.GREEN,
        )
