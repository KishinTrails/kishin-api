"""Administration from a shell.

Accounts, because the API no longer serves registration — this group is the only way
to create an account:

    kishin user list
    kishin user create alice
    kishin user create alice --password '...'
    kishin user show alice --tiles
    kishin user reset-password alice
    kishin user rename alice alicia
    kishin user delete alice --yes

The database:

    kishin db init
    kishin db stats
    kishin db checkpoint

Importing a recorded trail:

    kishin gpx import activity.gpx --user alice

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

And the server itself:

    kishin run
    kishin run --reload --port 8001
"""

from __future__ import annotations

from typing import Annotated

import typer

from kishin_trails.config import settings

from . import cache, db, geo, gpx, noise, user
from .common import fail

app = typer.Typer(help="Kishin Trails administration.", no_args_is_help=True)
app.add_typer(user.app, name="user")
app.add_typer(db.app, name="db")
app.add_typer(gpx.app, name="gpx")
app.add_typer(cache.app, name="cache")
app.add_typer(geo.app, name="geo")
app.add_typer(noise.app, name="noise")


@app.command("run")
def run(
    host: Annotated[str, typer.Option(help="Address to listen on")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to listen on")] = 8000,
    reload: Annotated[bool, typer.Option("--reload", help="Restart when a source file changes")] = False,
) -> None:
    """Serve the API."""
    if settings.SECRET_KEY == "CHANGE_ME":
        fail("SECRET_KEY is still the default CHANGE_ME; set a real secret before serving.")

    # Imported here so the account commands do not pay for uvicorn's import.
    import uvicorn  # pylint: disable=import-outside-toplevel

    uvicorn.run("kishin_trails.main:app", host=host, port=port, reload=reload)
