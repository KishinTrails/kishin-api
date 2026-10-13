"""
``kishin gpx`` — importing recorded trails.

    kishin gpx import activity.gpx --user alice
    kishin gpx import activity.gpx --user alice --resolution 16 --dry-run
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import gpx
import typer
from sqlalchemy import select

from kishin_trails.models import Tile, User
from kishin_trails.utils import latLngToS2Cell

from .common import fail, openSession

app = typer.Typer(help="Importing recorded trails.", no_args_is_help=True)


def _getOrCreateTile(session, s2Cell: str) -> Tile:
    """Gets the existing tile for an S2 cell, or creates a bare one."""
    tile = session.scalar(select(Tile).where(Tile.s2_cell_id == s2Cell))
    if tile is None:
        tile = Tile(s2_cell_id=s2Cell)
        session.add(tile)
        session.flush()
    return tile


@app.command("import")
def importGpx(
    gpxFile: Annotated[Path, typer.Argument(help="Path to the GPX file", exists=True, dir_okay=False)],
    user: Annotated[str, typer.Option("--user", "-u", help="Username to mark the tiles explored for")],
    resolution: Annotated[int, typer.Option("--resolution", "-r", help="S2 level (0-30)")] = 16,
    dryRun: Annotated[bool, typer.Option("--dry-run", help="Print the tiles without touching the database")] = False,
) -> None:
    """Mark every S2 cell a GPX track passes through as explored for a user."""
    if not 0 <= resolution <= 30:
        fail(f"Invalid S2 level: {resolution} (must be 0-30).")

    gpxData = gpx.read_gpx(str(gpxFile))

    tiles: set[str] = set()
    for track in gpxData.trk:
        for segment in track.trkseg:
            for point in segment.trkpt:
                tiles.add(latLngToS2Cell(float(point.lat), float(point.lon), resolution))

    typer.secho(f"Found {len(tiles)} unique tile(s) in the GPX file.", fg=typer.colors.BLUE, err=True)

    if dryRun:
        for tile in sorted(tiles):
            typer.echo(tile)
        return

    with openSession() as session:
        account = session.scalar(select(User).where(User.username == user))
        if account is None:
            fail(f'No account found for "{user}".')
            return  # unreachable; fail() exits, and this tells the type checker so

        for s2Cell in tiles:
            tile = _getOrCreateTile(session, s2Cell)
            if tile not in account.explored_tiles:
                account.explored_tiles.append(tile)

        session.commit()

    typer.secho(f"[OK] Marked {len(tiles)} tile(s) as explored by {user}.", fg=typer.colors.GREEN)
