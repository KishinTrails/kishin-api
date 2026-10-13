"""
``kishin geo`` — S2/H3/Overpass debugging.

    kishin geo cell 48.85 2.35
    kishin geo info 89c25a221
    kishin geo h3 8a1fb46622dffff
    kishin geo locations
    kishin geo locations --location home
    kishin geo overpass 89c25a221 --execute
"""

from __future__ import annotations

from typing import Annotated

import h3
import requests
import typer

from kishin_trails.config import settings
from kishin_trails.overpass import OVERPASS_URL, buildQuery
from kishin_trails.perlin import getNoiseForCell, isCellActive
from kishin_trails.utils import (
    getS2CellBounds,
    getS2CellCenter,
    getS2CellLevel,
    getS2EdgeLength,
    latLngToS2Cell,
    s2CellIdToLatLng,
    s2CellToParent,
)

from .common import fail

app = typer.Typer(help="S2/H3/Overpass debugging.", no_args_is_help=True)

# S2 level -> the closest-matching H3 resolution, by comparable edge length.
S2_TO_H3 = {
    0: 0,
    1: 0,
    2: 0,
    3: 0,
    4: 1,
    5: 2,
    6: 2,
    7: 3,
    8: 4,
    9: 5,
    10: 5,
    11: 6,
    12: 7,
    13: 7,
    14: 8,
    15: 9,
    16: 10,
    17: 10,
    18: 11,
    19: 12,
    20: 12,
    21: 13,
    22: 14,
    23: 15,
    24: 15,
    25: 15,
    26: 15,
    27: 15,
    28: 15,
    29: 15,
    30: 15,
}
H3_TO_S2 = {v: k for k, v in S2_TO_H3.items()}


@app.command("cell")
def cell(
    lat: Annotated[float, typer.Argument(help="Latitude")],
    lng: Annotated[float, typer.Argument(help="Longitude")],
    resolution: Annotated[int, typer.Option("--resolution", help="S2 level")] = 16,
) -> None:
    """Convert coordinates to an S2 cell token."""
    typer.echo(latLngToS2Cell(lat, lng, resolution))


@app.command("info")
def info(
    s2Cell: Annotated[str, typer.Argument(help="S2 cell token")],
    parentLevel: Annotated[
        int, typer.Option("--parent-level", help="Walk the parent ladder down to this many levels above the cell")
    ] = 0,
) -> None:
    """Show a cell's level, center, bounds, edge length, and parent ladder.

    Also prints its Perlin noise value and active verdict when the cell is at
    level 16 — the level the fog-of-war gate actually operates on.
    """
    try:
        level = getS2CellLevel(s2Cell)
    except ValueError as error:
        fail(str(error))
        return  # unreachable; fail() exits, and this tells the type checker so

    lat, lng = s2CellIdToLatLng(s2Cell)
    centerLat, centerLng = getS2CellCenter(s2Cell)
    loLat, loLng, hiLat, hiLng = getS2CellBounds(s2Cell)
    h3Res = S2_TO_H3[level]
    h3Cell = h3.latlng_to_cell(lat, lng, h3Res)

    typer.secho(f"s2: {s2Cell} (level {level})", fg=typer.colors.BLUE, err=True)
    typer.echo(f"  center: lat={centerLat:.6f}, lng={centerLng:.6f}")
    typer.echo(f"  bounds: lo=({loLat:.6f}, {loLng:.6f}), hi=({hiLat:.6f}, {hiLng:.6f})")
    typer.echo(f"  edge: {getS2EdgeLength(s2Cell):.1f} m")
    typer.echo(f"  h3 (res {h3Res}): {h3Cell}")

    if level == 16:
        noiseValue = getNoiseForCell(s2Cell)
        typer.echo(f"  noise: {noiseValue:.6f} (active: {isCellActive(s2Cell)})")

    if parentLevel > 0:
        typer.echo("  parents:")
        for steps in range(1, parentLevel + 1):
            targetLevel = level - steps
            if targetLevel < 0:
                break
            parent = s2CellToParent(s2Cell, targetLevel)
            parentEdge = getS2EdgeLength(parent)
            typer.echo(f"    level {targetLevel}: {parent} (edge {parentEdge:.1f} m)")


@app.command("h3")
def fromH3(
    h3Cell: Annotated[str, typer.Argument(help="H3 cell token")],
) -> None:
    """Convert an H3 cell to the S2 cell at the matching level."""
    h3Res = h3.get_resolution(h3Cell)
    if h3Res not in H3_TO_S2:
        fail(f"No S2 level maps to H3 resolution {h3Res}.")
        return  # unreachable; fail() exits, and this tells the type checker so

    lat, lng = h3.cell_to_latlng(h3Cell)
    typer.echo(latLngToS2Cell(lat, lng, H3_TO_S2[h3Res]))


@app.command("locations")
def locations(
    location: Annotated[
        str | None, typer.Option("--location", help="Resolve a single named location instead of listing all")
    ] = None,
) -> None:
    """List, or resolve, the debug locations configured in DEBUG_LOCATIONS."""
    configured = settings.DEBUG_LOCATIONS
    if not configured:
        typer.secho(
            "No DEBUG_LOCATIONS defined. Add to .env, e.g.:\n"
            '  DEBUG_LOCATIONS=\'{"home": {"lat": 48.85, "lng": 2.34}}\'',
            fg=typer.colors.YELLOW,
            err=True,
        )
        return

    if location is not None:
        if location not in configured:
            fail(f'Location "{location}" not found. Run without --location to see available ones.')
            return  # unreachable; fail() exits, and this tells the type checker so
        loc = configured[location]
        s2Cell = loc.get("s2_res16") or latLngToS2Cell(loc["lat"], loc["lng"], 16)
        typer.echo(s2Cell)
        return

    width = max(len(name) for name in configured)
    for name, loc in configured.items():
        s2Cell = loc.get("s2_res16") or latLngToS2Cell(loc["lat"], loc["lng"], 16)
        typer.echo(f"{name:<{width}}  lat={loc['lat']}, lng={loc['lng']}, s2_res16={s2Cell}")


@app.command("overpass")
def overpass(
    s2Cell: Annotated[str, typer.Argument(help="S2 cell token")],
    execute: Annotated[bool, typer.Option("--execute", help="Also run the query against Overpass")] = False,
) -> None:
    """Build (and optionally run) the Overpass query for an S2 cell's bounds."""
    loLat, loLng, hiLat, hiLng = getS2CellBounds(s2Cell)
    query = buildQuery((loLat, loLng, hiLat, hiLng))
    typer.echo(query)

    if execute:
        response = requests.post(OVERPASS_URL, data={"data": query}, timeout=90)
        response.raise_for_status()
        elements = response.json().get("elements", [])
        typer.secho(f"\n[OK] Got {len(elements)} element(s).", fg=typer.colors.GREEN, err=True)
        for element in elements:
            typer.echo(element)
