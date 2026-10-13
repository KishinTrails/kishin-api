"""
``kishin db`` — schema and maintenance operations on the live database.

    kishin db init
    kishin db stats
    kishin db checkpoint
"""

from __future__ import annotations

import typer
from sqlalchemy import func, select, text

from kishin_trails import database
from kishin_trails.cache import initDb as initCacheDb
from kishin_trails.models import POI, NoiseCache, PostProcessingPoI, Tile, User

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
            "users": session.scalar(select(func.count()).select_from(User)),  # pylint: disable=not-callable
            "tiles": session.scalar(select(func.count()).select_from(Tile)),  # pylint: disable=not-callable
            "active tiles": session.scalar(select(func.count()).select_from(Tile).where(Tile.active.is_(True))),  # pylint: disable=not-callable
            "pois": session.scalar(select(func.count()).select_from(POI)),  # pylint: disable=not-callable
            "post-processing pois": session.scalar(select(func.count()).select_from(PostProcessingPoI)),  # pylint: disable=not-callable
            "noise cache entries": session.scalar(select(func.count()).select_from(NoiseCache)),  # pylint: disable=not-callable
        }

        width = max(len(name) for name in counts)
        for name, count in counts.items():
            typer.echo(f"{name:<{width}}  {count}")


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
