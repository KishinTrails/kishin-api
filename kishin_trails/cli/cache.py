"""
``kishin cache`` — the POI tile cache.

    kishin cache populate 89c25a221,89c25a223
    kishin cache populate 89c25a221 --dry-run
    kishin cache populate 89c25a221 --fill-polygons
    kishin cache populate --fill-only
    kishin cache show 89c25a221
"""

from __future__ import annotations

from typing import Annotated

import typer

from kishin_trails import cache as cache_module
from kishin_trails import populate
from kishin_trails.utils import getS2CellLevel, s2CellToChildren

from .common import fail

app = typer.Typer(help="The POI tile cache.", no_args_is_help=True)


@app.command("populate")
def populateCache(
    s2Cells: Annotated[
        str | None,
        typer.Argument(help="Comma-separated S2 cell tokens (level <= 16). Required unless --fill-only."),
    ] = None,
    dryRun: Annotated[bool, typer.Option("--dry-run", help="Only show how many tiles would be processed")] = False,
    fillPolygons: Annotated[
        bool, typer.Option("--fill-polygons", help="Also run the polygon-interior second pass afterwards")
    ] = False,
    fillOnly: Annotated[
        bool, typer.Option("--fill-only", help="Only run the polygon-interior second pass, skip tile processing")
    ] = False,
    noCache: Annotated[
        bool, typer.Option("--no-cache", help="Re-process tiles already in cache, inserting only missing POIs")
    ] = False,
) -> None:
    """Populate the cache with POI data for one or more S2 tiles."""
    if fillOnly:
        populate.fillPolygonInteriors()
        typer.secho("[OK] Polygon interiors filled.", fg=typer.colors.GREEN)
        return

    if not s2Cells:
        fail("S2CELLS is required unless --fill-only is given.")
        return  # unreachable; fail() exits, and this tells the type checker so

    try:
        cells = populate.parseS2Cells(s2Cells)
    except ValueError as error:
        fail(str(error))
        return  # unreachable; fail() exits, and this tells the type checker so

    if dryRun:
        children: list[str] = []
        for parentCell in cells:
            res = getS2CellLevel(parentCell)
            children.extend(s2CellToChildren(parentCell, 16) if res < 16 else [parentCell])
        uniqueChildren = list(dict.fromkeys(children))
        typer.echo(f"Would process {len(uniqueChildren)} level-16 tile(s).")
    else:
        populate.populateCacheForTiles(cells, skipCached=not noCache, queryResolution=9)
        typer.secho(f"[OK] Processed {len(cells)} S2 parent tile(s).", fg=typer.colors.GREEN)

    if fillPolygons:
        populate.fillPolygonInteriors()
        typer.secho("[OK] Polygon interiors filled.", fg=typer.colors.GREEN)


@app.command("show")
def show(s2Cell: Annotated[str, typer.Argument(help="S2 cell token")]) -> None:
    """Show a cached tile's type, active flag, and POIs."""
    tile = cache_module.getTile(s2Cell)
    if tile is None:
        fail(f'No cached tile for "{s2Cell}".')
        return  # unreachable; fail() exits, and this tells the type checker so

    typer.secho(f"s2_cell: {s2Cell}", fg=typer.colors.BLUE, err=True)
    typer.echo(f"  tile_type: {tile['tile_type']}")
    typer.echo(f"  pois: {len(tile['pois'])}")
    for poi in tile["pois"]:
        typer.echo(f"    {poi['osm_id']}  {poi['name']}  ({poi['lat']}, {poi['lon']})")
