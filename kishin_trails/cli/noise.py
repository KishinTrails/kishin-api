"""
``kishin noise`` — the Perlin noise fog-of-war gate.

    kishin noise cell 89c25a221
    kishin noise cell 89c25a221 --scale 100 --octaves 4
    kishin noise search --config scripts/perlin_config_s2.json
    kishin noise clear-cache --yes
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from kishin_trails import noise_cache
from kishin_trails.perlin import getNoiseForCell, isCellActive
from kishin_trails.perlin_search import search as runSearch

app = typer.Typer(help="The Perlin noise fog-of-war gate.", no_args_is_help=True)


@app.command("cell")
def cell(
    s2Cell: Annotated[str, typer.Argument(help="S2 cell token")],
    scale: Annotated[int | None, typer.Option("--scale", help="Overrides settings.NOISE_SCALE")] = None,
    octaves: Annotated[int | None, typer.Option("--octaves", help="Overrides settings.NOISE_OCTAVES")] = None,
    amplitudeDecay: Annotated[
        float | None, typer.Option("--amplitude-decay", help="Overrides settings.NOISE_AMPLITUDE_DECAY")
    ] = None,
) -> None:
    """Show an S2 cell's Perlin noise value and whether it is active."""
    value = getNoiseForCell(s2Cell, scale, octaves, amplitudeDecay)
    active = isCellActive(s2Cell, scale, octaves, amplitudeDecay)
    typer.echo(f"noise: {value:.6f}")
    typer.echo(f"active: {active}")


@app.command("search")
def search(
    config: Annotated[Path, typer.Option("--config", help="Path to the JSON condition/state-space file", exists=True, dir_okay=False)],
) -> None:
    """Grid-search noise parameters against the conditions in a config file.

    See ``kishin_trails/perlin_search.py`` for the config file format.
    """
    solution, total = runSearch(str(config))

    if solution is None:
        typer.secho(f"\n[ERROR] No solution found in {total} combination(s).", fg=typer.colors.RED, err=True)
        typer.echo("Consider widening state_space or relaxing conditions.", err=True)
        raise typer.Exit(code=1)

    typer.secho("\n[OK] Found solution.", fg=typer.colors.GREEN)
    typer.echo(f"  scale:          {solution['scale']}")
    typer.echo(f"  threshold:      {solution['threshold']}")
    typer.echo(f"  octaves:        {solution['octaves']}")
    typer.echo(f"  amplitudeDecay: {solution['amplitudeDecay']}")
    typer.echo("\nCondition results:")
    for message, comment in zip(solution["messages"], solution["comments"]):
        suffix = f" -- {comment}" if comment else ""
        typer.echo(f"  {message}{suffix}")


@app.command("clear-cache")
def clearCache(
    yes: Annotated[bool, typer.Option("--yes", help="Skip the confirmation prompt")] = False,
) -> None:
    """Delete every entry in the noise cache. Purely a recomputation cost — not destructive to user data."""
    if not yes:
        confirmed = typer.confirm("Clear the entire noise cache?")
        if not confirmed:
            raise typer.Exit(code=1)

    noise_cache.clearCache()
    typer.secho("[OK] Noise cache cleared.", fg=typer.colors.GREEN)
