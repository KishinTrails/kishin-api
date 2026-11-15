"""
``kishin db`` — schema and maintenance operations on the live database.

    kishin db init
    kishin db stats
    kishin db checkpoint
    kishin db drop-legacy-tables --yes
"""

from __future__ import annotations

from typing import Annotated

import typer
from sqlalchemy import func, inspect, select, text

from kishin_trails import database
from kishin_trails.cache import initDb as initCacheDb
from kishin_trails.models import POI, ExploredTile, NoiseCache, PostProcessingPoI, Tile
from kishin_trails.training import Plan, TrainingCompletion

from .common import openSession

app = typer.Typer(help="Schema and maintenance operations.", no_args_is_help=True)


@app.command("init")
def init() -> None:
    """Create any missing tables — the same pair run at server startup."""
    database.Base.metadata.create_all(bind=database.engine)
    initCacheDb()
    typer.secho("[OK] Tables created.", fg=typer.colors.GREEN)


@app.command("stats")
def stats() -> None:
    """Print row counts for every table."""
    with openSession() as session:
        counts = {
            "tiles": session.scalar(select(func.count()).select_from(Tile)),  # pylint: disable=not-callable
            "active tiles": session.scalar(select(func.count()).select_from(Tile).where(Tile.active.is_(True))),  # pylint: disable=not-callable
            "explored tiles": session.scalar(select(func.count()).select_from(ExploredTile)),  # pylint: disable=not-callable
            "pois": session.scalar(select(func.count()).select_from(POI)),  # pylint: disable=not-callable
            "post-processing pois": session.scalar(select(func.count()).select_from(PostProcessingPoI)),  # pylint: disable=not-callable
            "noise cache entries": session.scalar(select(func.count()).select_from(NoiseCache)),  # pylint: disable=not-callable
            "plans": session.scalar(select(func.count()).select_from(Plan)),  # pylint: disable=not-callable
            "training completions": session.scalar(select(func.count()).select_from(TrainingCompletion)),  # pylint: disable=not-callable
        }

        width = max(len(name) for name in counts)
        for name, count in counts.items():
            typer.echo(f"{name:<{width}}  {count}")


#: Tables of the multi-account schema, in an order that drops a table before the tables it references.
LEGACY_ACCOUNT_TABLES = ("user_explored_tiles", "user_active_plans")
LEGACY_PLAN_TABLES = ("training_completions", "segments", "trainings", "plan_weeks", "plans")
LEGACY_USER_TABLE = "users"


def legacyTables(connection) -> list[str]:
    """The tables of the multi-account schema present in the database, in drop order.

    The plan tables are listed only when ``plans`` still has the ``owner_id``
    column; otherwise they are the current ones.
    """
    inspector = inspect(connection)
    present = set(inspector.get_table_names())
    tables = [name for name in LEGACY_ACCOUNT_TABLES if name in present]
    if "plans" in present and "owner_id" in {column["name"] for column in inspector.get_columns("plans")}:
        tables += [name for name in LEGACY_PLAN_TABLES if name in present]
    if LEGACY_USER_TABLE in present:
        tables.append(LEGACY_USER_TABLE)
    return tables


@app.command("drop-legacy-tables")
def dropLegacyTables(
    yes: Annotated[bool, typer.Option("--yes", help="Do not ask for confirmation")] = False,
) -> None:
    """Drop the tables of the multi-account schema, then create the current ones.

    Drops the users, the per-account explored tiles and active plans, and the
    plan tables when they still have an owner column. Tiles, POIs and the noise
    cache are kept.
    """
    with openSession() as session:
        tables = legacyTables(session.connection())
        if not tables:
            typer.echo("No legacy tables.")
            return
        if not yes:
            typer.confirm(f"Drop {', '.join(tables)} and their rows?", abort=True)
        for name in tables:
            session.execute(text(f'DROP TABLE "{name}"'))
        session.commit()
        database.Base.metadata.create_all(bind=session.get_bind())
    typer.secho(f"[OK] Dropped {', '.join(tables)}; current tables created.", fg=typer.colors.GREEN)


@app.command("checkpoint")
def checkpoint() -> None:
    """Run a WAL checkpoint now, instead of waiting for the 24-hour loop in main.py.

    No-op on backends other than SQLite, since ``PRAGMA wal_checkpoint`` is
    SQLite-specific.
    """
    if not database.SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
        typer.secho(
            "[WARNING] Not a SQLite database; nothing to checkpoint.",
            fg=typer.colors.YELLOW,
        )
        return

    with database.engine.connect() as connection:
        connection.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
    typer.secho("[OK] WAL checkpoint complete.", fg=typer.colors.GREEN)
