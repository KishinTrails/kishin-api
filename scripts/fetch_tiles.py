"""
fetch_tiles.py — Download OSM raster tile PNGs covering a bounding box into cache/.

Usage:
    poetry run python scripts/fetch_tiles.py \\
        --sw 45.68 2.95 --ne 45.82 3.20 --zoom 14

    # Use Stamen Toner (high-contrast, better text rendering):
    poetry run python scripts/fetch_tiles.py \\
        --sw 45.68 2.95 --ne 45.82 3.20 --zoom 14 --source toner

    # Custom tile source:
    poetry run python scripts/fetch_tiles.py \\
        --sw 45.68 2.95 --ne 45.82 3.20 --zoom 14 --tile-url "https://example.com/{z}/{x}/{y}.png"

    # Stitch downloaded tiles into one image:
    poetry run python scripts/fetch_tiles.py \\
        --sw 45.68 2.95 --ne 45.82 3.20 --zoom 14 --stitch output.png

    # Stitch with ukiyo-e effect applied to each tile:
    poetry run python scripts/fetch_tiles.py \\
        --sw 45.68 2.95 --ne 45.82 3.20 --zoom 14 --stitch output.png --ukiyo-e

Tiles are saved as cache/{z}_{x}_{y}.{source}.png. Already-present tiles are skipped.
"""

import argparse
import math
import sys
import time
from pathlib import Path

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))

CACHE_DIR = Path(__file__).parent.parent / "cache"
TILE_SIZE = 256
USER_AGENT = "KishinTrails/dev"
REQUEST_DELAY = 0.2  # seconds between requests — OSM tile usage policy

TILE_SOURCES: dict[str, str] = {
    "osm":   "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "toner": "https://tiles.stadiamaps.com/tiles/stamen_toner/{z}/{x}/{y}.png",
}


def latLngToTile(lat: float, lng: float, zoom: int) -> tuple[int, int]:
    """Convert a lat/lng coordinate to the OSM tile (x, y) at the given zoom level.

    @param lat:  Latitude in degrees.
    @param lng:  Longitude in degrees.
    @param zoom: OSM zoom level.
    @returns:    (x, y) tile indices.
    """
    n = 2 ** zoom
    x = int((lng + 180) / 360 * n)
    y = int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def fetchTile(z: int, x: int, y: int, session: requests.Session, tileUrl: str, apiKey: str | None = None) -> bytes:
    """Download a single tile PNG from the given tile server URL template.

    @param z:       Zoom level.
    @param x:       Tile x index.
    @param y:       Tile y index.
    @param session: Requests session with User-Agent set.
    @param tileUrl: URL template with {z}, {x}, {y} placeholders.
    @param apiKey:  Optional API key appended as ?api_key=... query parameter.
    @returns:       Raw PNG bytes.
    """
    url = tileUrl.format(z=z, x=x, y=y)
    params = {"api_key": apiKey} if apiKey else None
    resp = session.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.content


def stitchTiles(
    xMin: int, xMax: int,
    yMin: int, yMax: int,
    zoom: int,
    output: Path,
    source: str = "osm",
    ukiyo_e: bool = False,
) -> None:
    """Stitch cached tiles for the given tile range into a single image.

    When ukiyo_e is True, applies the ukiyo-e effect to each tile before
    pasting by delegating to ukiyo_e.apply_ukiyo_e — ukiyo_e.py is not
    modified and remains fully standalone.

    @param xMin:    Minimum tile x index.
    @param xMax:    Maximum tile x index.
    @param yMin:    Minimum tile y index.
    @param yMax:    Maximum tile y index.
    @param zoom:    OSM zoom level.
    @param output:  Destination path for the stitched image.
    @param source:  Tile source name, used to resolve cached filenames.
    @param ukiyo_e: Apply ukiyo-e effect to each tile before stitching.
    """
    if ukiyo_e:
        from ukiyo_e import apply_ukiyo_e as applyEffect
    else:
        applyEffect = None

    totalX = xMax - xMin + 1
    totalY = yMax - yMin + 1
    canvas = Image.new("RGB", (totalX * TILE_SIZE, totalY * TILE_SIZE))

    for iy, y in enumerate(range(yMin, yMax + 1)):
        for ix, x in enumerate(range(xMin, xMax + 1)):
            tilePath = CACHE_DIR / f"{zoom}_{x}_{y}.{source}.png"
            if not tilePath.exists():
                print(f"  warning: missing tile {tilePath.name}, leaving blank", file=sys.stderr)
                continue

            if applyEffect:
                tmp = tilePath.with_suffix(".ukiyo_e.tmp.png")
                applyEffect(str(tilePath), str(tmp))
                tile = Image.open(tmp).convert("RGB")
                tmp.unlink()
            else:
                tile = Image.open(tilePath).convert("RGB")

            canvas.paste(tile, (ix * TILE_SIZE, iy * TILE_SIZE))

    canvas.save(output)
    print(f"Stitched {totalX}×{totalY} tiles → {output}")


def fetchTilesInBbox(
    sw: tuple[float, float],
    ne: tuple[float, float],
    zoom: int,
    source: str = "osm",
    apiKey: str | None = None,
    force: bool = False,
    stitch: Path | None = None,
    ukiyo_e: bool = False,
) -> None:
    """Download all tiles covering the given bounding box at the specified zoom.

    Skips tiles already present in cache/ unless --force is passed.
    Optionally stitches the result into a single image after downloading.

    @param sw:      (lat, lng) of the south-west corner.
    @param ne:      (lat, lng) of the north-east corner.
    @param zoom:    OSM zoom level (0–19).
    @param source:  Tile source name (key in TILE_SOURCES) or a raw URL template.
    @param apiKey:  Optional API key passed as ?api_key= query parameter (required for e.g. Stadia/toner).
    @param force:   Re-download tiles even if already cached.
    @param stitch:  If set, stitch all tiles into this output image path.
    @param ukiyo_e: Apply ukiyo-e effect per tile when stitching (requires --stitch).
    """
    CACHE_DIR.mkdir(exist_ok=True)

    tileUrl = TILE_SOURCES.get(source, source)

    xMin, yMax = latLngToTile(sw[0], sw[1], zoom)  # SW → top-left in tile coords (y inverted)
    xMax, yMin = latLngToTile(ne[0], ne[1], zoom)  # NE → bottom-right

    totalX = xMax - xMin + 1
    totalY = yMax - yMin + 1
    total = totalX * totalY

    print(f"Bounding box: x=[{xMin}..{xMax}] y=[{yMin}..{yMax}] → {total} tiles at zoom {zoom} (source: {source})")

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    downloaded = skipped = failed = 0

    for y in range(yMin, yMax + 1):
        for x in range(xMin, xMax + 1):
            dest = CACHE_DIR / f"{zoom}_{x}_{y}.{source}.png"

            if dest.exists() and not force:
                skipped += 1
                continue

            try:
                data = fetchTile(zoom, x, y, session, tileUrl, apiKey)
                dest.write_bytes(data)
                downloaded += 1
                print(f"  [{downloaded + skipped + failed}/{total}] saved {dest.name}")
                time.sleep(REQUEST_DELAY)
            except requests.HTTPError as e:
                failed += 1
                print(f"  [{downloaded + skipped + failed}/{total}] FAILED {zoom}/{x}/{y}: {e}", file=sys.stderr)

    print(f"\nDone — {downloaded} downloaded, {skipped} skipped, {failed} failed.")

    if stitch:
        stitchTiles(xMin, xMax, yMin, yMax, zoom, stitch, source=source, ukiyo_e=ukiyo_e)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch OSM tile PNGs into cache/")
    parser.add_argument("--sw", nargs=2, type=float, metavar=("LAT", "LNG"), required=True,
                        help="South-west corner (lat lng)")
    parser.add_argument("--ne", nargs=2, type=float, metavar=("LAT", "LNG"), required=True,
                        help="North-east corner (lat lng)")
    parser.add_argument("--zoom", type=int, required=True, help="OSM zoom level (0–19)")
    parser.add_argument("--source", choices=list(TILE_SOURCES.keys()), default="osm",
                        help="Tile source preset (default: osm)")
    parser.add_argument("--tile-url", type=str, metavar="URL",
                        help="Custom tile URL template, overrides --source (use {z}/{x}/{y} placeholders)")
    parser.add_argument("--api-key", type=str, metavar="KEY",
                        help="API key passed as ?api_key= (required for Stadia/toner)")
    parser.add_argument("--force", action="store_true", help="Re-download already cached tiles")
    parser.add_argument("--stitch", type=Path, metavar="OUTPUT",
                        help="Stitch all tiles into a single image at this path")
    parser.add_argument("--ukiyo-e", action="store_true",
                        help="Apply ukiyo-e effect per tile when stitching (requires --stitch)")
    args = parser.parse_args()

    if not (0 <= args.zoom <= 19):
        print("Error: zoom must be between 0 and 19", file=sys.stderr)
        sys.exit(1)

    if args.ukiyo_e and not args.stitch:
        print("Error: --ukiyo-e requires --stitch", file=sys.stderr)
        sys.exit(1)

    source = args.tile_url if args.tile_url else args.source

    fetchTilesInBbox(
        sw=(args.sw[0], args.sw[1]),
        ne=(args.ne[0], args.ne[1]),
        zoom=args.zoom,
        source=source,
        apiKey=args.api_key,
        force=args.force,
        stitch=args.stitch,
        ukiyo_e=args.ukiyo_e,
    )


if __name__ == "__main__":
    main()
