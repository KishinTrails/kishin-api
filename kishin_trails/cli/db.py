"""
``kishin db`` — schema and maintenance operations on the live database.

    kishin db init
    kishin db stats
    kishin db copy-from-sqlite cache/kishin.db
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy import Connection, MetaData, Table, create_engine, func, inspect, select, text

from kishin_trails import database
from kishin_trails.cache import initDb as initCacheDb
from kishin_trails.models import POI, ExploredTile, NoiseCache, PostProcessingPoI, Tile
from kishin_trails.training import Plan, TrainingCompletion

from .common import fail, openSession

app = typer.Typer(help="Schema and maintenance operations.", no_args_is_help=True)

#: Rows read from the SQLite file and inserted at a time by copy-from-sqlite.
COPY_BATCH_ROWS = 5000


@app.command("init")
def init() -> None:
    """Create any missing tables — the same pair run at server startup."""
    with openSession() as session:
        database.Base.metadata.create_all(bind=session.get_bind())
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


def copyTables(source: Connection, target: Connection) -> list[tuple[str, int | None]]:
    """Copies the rows of every current table from ``source`` (a SQLite file) to ``target``.

    Tables are copied in dependency order, with the columns both databases have.
    A table missing from ``source`` is reported with ``None`` and skipped; tables
    of ``source`` that are not current, such as the multi-account ``users``, are
    ignored. Each ``id`` sequence of ``target`` is then set past the copied ids.

    Returns:
        ``(table name, rows copied or None)`` for every current table.
    """
    sourceTables = set(inspect(source).get_table_names())
    copied: list[tuple[str, int | None]] = []
    for table in database.Base.metadata.sorted_tables:
        if table.name not in sourceTables:
            copied.append((table.name, None))
            continue
        old = Table(table.name, MetaData(), autoload_with=source)
        names = [column.name for column in table.columns if column.name in old.columns]
        result = source.execute(select(*(old.columns[name] for name in names)))
        count = 0
        while batch := result.fetchmany(COPY_BATCH_ROWS):
            target.execute(table.insert(), [dict(zip(names, row)) for row in batch])
            count += len(batch)
        copied.append((table.name, count))

    for table in database.Base.metadata.sorted_tables:
        if "id" in table.columns and table.columns["id"].primary_key:
            target.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
                    f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {table.name}"
                )
            )
    return copied


@app.command("copy-from-sqlite")
def copyFromSqlite(
    file: Annotated[Path, typer.Argument(help="SQLite database file (kishin.db)", exists=True, dir_okay=False)],
) -> None:
    """Copy the tiles, POIs, noise cache, explored tiles and plans of a SQLite file into the database.

    The file is opened read-only. The PostgreSQL tables must be empty: the copy
    runs in one transaction and changes nothing when it fails.
    """
    sourceEngine = create_engine(f"sqlite:///file:{file.resolve()}?mode=ro&uri=true")
    with openSession() as session:
        database.Base.metadata.create_all(bind=session.get_bind())
        session.commit()
        filled = [
            table.name
            for table in database.Base.metadata.sorted_tables
            if session.execute(select(func.count()).select_from(table)).scalar()  # pylint: disable=not-callable
        ]
        if filled:
            fail(f"These tables already hold rows: {', '.join(filled)}. The copy needs empty tables.")

        with sourceEngine.connect() as source:
            copied = copyTables(source, session.connection())
        session.commit()
    sourceEngine.dispose()

    width = max(len(name) for name, _ in copied)
    for name, count in copied:
        typer.echo(f"{name:<{width}}  {'not in the file, skipped' if count is None else count}")
    typer.secho(f"[OK] Copied {file}.", fg=typer.colors.GREEN)
