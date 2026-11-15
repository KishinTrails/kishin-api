"""Administration from a shell.

The password of the only account (its username is the setting KISHIN_USERNAME):

    kishin password dev-secrets/KISHIN_PASSWORD_HASH

The database:

    kishin db init
    kishin db stats
    kishin db checkpoint
    kishin db drop-legacy-tables --yes

Importing a recorded trail:

    kishin gpx import activity.gpx

The POI cache:

    kishin cache populate 89c25a221,89c25a223
    kishin cache show 89c25a221

S2/H3/Overpass debugging:

    kishin geo cell 48.85 2.35
    kishin geo info 89c25a221
    kishin geo overpass 89c25a221 --execute

The Perlin noise fog-of-war gate:

    kishin noise cell 89c25a221
    kishin noise search --config scripts/perlin_config_s2.json

Training plans, imported from a local JSON file:

    kishin plan import plan.json --start 2026-11-16
    kishin plan show

Reading the health-sync measurement database (read-only):

    kishin health activities --days 30
    kishin health cells 12345678901
    kishin health measures

And the server itself:

    kishin run
    kishin run --reload --port 8001
"""

from __future__ import annotations

from typing import Annotated

import typer

from kishin_trails.config import settings

from . import cache, db, geo, gpx, health, noise, password, plan
from .common import fail

app = typer.Typer(help="Kishin Trails administration.", no_args_is_help=True)
app.command("password")(password.setPassword)
app.add_typer(db.app, name="db")
app.add_typer(gpx.app, name="gpx")
app.add_typer(cache.app, name="cache")
app.add_typer(geo.app, name="geo")
app.add_typer(noise.app, name="noise")
app.add_typer(health.app, name="health")
app.add_typer(plan.app, name="plan")


@app.command("run")
def run(
    host: Annotated[str, typer.Option(help="Address to listen on")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to listen on")] = 8000,
    reload: Annotated[bool, typer.Option("--reload", help="Restart when a source file changes")] = False,
) -> None:
    """Serve the API."""
    if settings.SECRET_KEY == "CHANGE_ME":
        fail("SECRET_KEY is still the default CHANGE_ME; set a real secret before serving.")
    if not settings.KISHIN_USERNAME or not settings.KISHIN_PASSWORD_HASH:
        fail("Set KISHIN_USERNAME and KISHIN_PASSWORD_HASH (see `kishin password`) before serving.")

    # Imported here so the other commands do not pay for uvicorn's import.
    import uvicorn  # pylint: disable=import-outside-toplevel

    uvicorn.run("kishin_trails.main:app", host=host, port=port, reload=reload)
