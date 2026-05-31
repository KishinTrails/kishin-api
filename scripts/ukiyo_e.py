"""
ukiyo_e.py — Apply a Japanese woodblock print (ukiyo-e) effect to a map tile image.

Usage:
    python ukiyo_e.py <input> <output>
    python ukiyo_e.py <input> <output> --fix-stipple --paper-texture --paper-tint 8333 5844 14

Requires: pillow, numpy
"""

import sys
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance, ImageOps

# yapf:disable

# (R, G, B) — washi paper, sumi ink, prussian blue, moss green, ochre, vermillion, shadow
PALETTE = [
    (232, 213, 163),
    ( 26,  43,  77),
    ( 74, 107, 138),
    ( 91, 122,  91),
    (139, 105,  20),
    (139,  32,  32),
    (180, 160, 110),
]


def collapse_stipple(img: Image.Image) -> Image.Image:
    """Replace isolated light pixels surrounded by dark neighbours with sumi ink.

    Scans every pixel: if it is the washi-paper colour and all 8 neighbours are
    the sumi-ink colour, it is converted to sumi ink. Applied after palette mapping
    so comparisons are against exact palette RGB values.

    @param img: Palette-mapped RGB image.
    @returns:   Image with isolated washi-paper pixels collapsed to sumi ink.
    """
    arr = np.array(img, dtype=np.uint8)
    paper = np.array(PALETTE[0], dtype=np.uint8)
    ink   = np.array(PALETTE[1], dtype=np.uint8)

    is_paper = np.all(arr == paper, axis=2)
    is_ink   = np.all(arr == ink,   axis=2)

    # True where all 8 neighbours are sumi ink (computed on inner pixels only)
    all_neighbours_ink = (
        is_ink[0:-2, 0:-2] & is_ink[0:-2, 1:-1] & is_ink[0:-2, 2:  ] &
        is_ink[1:-1, 0:-2] &                       is_ink[1:-1, 2:  ] &
        is_ink[2:,   0:-2] & is_ink[2:,   1:-1] & is_ink[2:,   2:  ]
    )

    mask = is_paper[1:-1, 1:-1] & all_neighbours_ink
    result = arr.copy()
    result[1:-1, 1:-1][mask] = ink
    return Image.fromarray(result)

# yapf:enable


def apply_paper_texture(img: Image.Image, std: float = 50.0, blob_radius: int = 3) -> Image.Image:
    """Add a washi paper surface texture by blurring noise into soft blobs.

    Generates per-channel Gaussian noise and blurs it to produce irregular
    patches (3–5 px) that read as paper surface irregularity rather than
    digital film grain.

    @param img:         Input RGB image.
    @param std:         Standard deviation of the base noise (higher = stronger texture).
    @param blob_radius: BoxBlur radius applied to the noise to form surface blobs.
    @returns:           Image with paper texture added.
    """
    arr = np.array(img, dtype=np.int32)
    h, w, _ = arr.shape

    raw_noise = np.random.normal(0, std, (h, w))

    # Blur into blobs, then broadcast across all three channels so the texture
    # shifts brightness only — no colour variation introduced.
    blurred = np.array(
        Image.fromarray(
            (raw_noise + 128).clip(0, 255).astype(np.uint8)
        ).filter(ImageFilter.BoxBlur(blob_radius)),
        dtype=np.float32,
    ) - 128
    blobs = np.stack([blurred, blurred, blurred], axis=2)

    return Image.fromarray(np.clip(arr + blobs.astype(np.int32), 0, 255).astype(np.uint8))


def apply_paper_tint(img: Image.Image, tile_x: int, tile_y: int, tile_z: int, strength: float = 18.0) -> Image.Image:
    """Overlay a slow large-scale colour gradient to simulate uneven paper aging.

    The gradient is seeded from the tile's (x, y, z) coordinates so that
    adjacent tiles produce seamlessly continuous variation across tile boundaries.
    Only light (washi-paper) areas are tinted — dark ink areas are left unchanged.

    @param img:      Input RGB image.
    @param tile_x:   OSM tile x index (used to seed and position the gradient).
    @param tile_y:   OSM tile y index.
    @param tile_z:   OSM tile zoom level.
    @param strength: Maximum tint offset in pixel intensity (higher = stronger aging).
    @returns:        Image with paper tint applied.
    """
    arr = np.array(img, dtype=np.float32)
    h, w, _ = arr.shape

    # Use a low-frequency sine wave whose phase is derived from the tile coordinates,
    # so the gradient continues smoothly across neighbouring tiles.
    freq = 2 * np.pi / (256*4)  # one full cycle every 4 tiles
    x_phase = tile_x * 256 * freq
    y_phase = tile_y * 256 * freq

    xs = np.linspace(x_phase, x_phase + 256*freq, w)
    ys = np.linspace(y_phase, y_phase + 256*freq, h)
    gx, gy = np.meshgrid(xs, ys)

    # Combine two sine waves for a more organic, non-directional variation
    gradient = (np.sin(gx) + np.sin(gy)) / 2  # range [-1, 1]

    # Warm shift: push toward ochre (+R, +G) on positive, toward shadow (-R, -G, -B) on negative
    tint = np.zeros((h, w, 3), dtype=np.float32)
    tint[:, :, 0] = gradient * strength  # red channel
    tint[:, :, 1] = gradient * strength * 0.6  # green channel (less shift for warmth)
    tint[:, :, 2] = gradient * strength * -0.3  # blue channel (inverse for warm/cool contrast)

    # Only tint pixels that are closer to washi paper than to sumi ink
    grey = arr.mean(axis=2)
    light_mask = grey > 128
    tint[~light_mask] = 0

    return Image.fromarray(np.clip(arr + tint, 0, 255).astype(np.uint8))


def apply_ukiyo_e(
    input_path: str,
    output_path: str,
    fix_stipple: bool = False,
    paper_texture: bool = False,
    paper_tint: tuple[int,
                      int,
                      int] | None = None,
) -> None:
    """Apply the full ukiyo-e pipeline to a single map tile.

    @param input_path:    Path to the source tile PNG.
    @param output_path:   Destination path for the processed tile PNG.
    @param fix_stipple:   Collapse isolated light pixels surrounded by dark neighbours.
    @param paper_texture: Add blob-shaped surface noise to simulate washi paper grain.
    @param paper_tint:    If set, (tile_x, tile_y, tile_z) — apply a seeded large-scale
                          colour gradient to simulate uneven paper aging.
    """
    img = Image.open(input_path).convert("RGB")

    # Flatten gradients
    img = ImageOps.posterize(img, 2)

    # Map every pixel to the nearest palette colour (vectorised)
    arr = np.array(img, dtype=np.int32)
    h, w, _ = arr.shape
    flat = arr.reshape(-1, 3)
    palette_arr = np.array(PALETTE, dtype=np.int32)
    diffs = flat[:, None, :] - palette_arr[None, :, :]
    indices = (diffs**2).sum(axis=2).argmin(axis=1)
    mapped = Image.fromarray(palette_arr[indices].astype(np.uint8).reshape(h, w, 3))

    if fix_stipple:
        mapped = collapse_stipple(mapped)

    # Extract and threshold edges
    edges = img.convert("L").filter(ImageFilter.FIND_EDGES)
    edges = ImageEnhance.Contrast(edges).enhance(4.0).point(lambda p: 255 if p > 20 else 0)

    # Burn sumi-ink edges onto the palette image
    ink = Image.new("RGB", mapped.size, PALETTE[1])
    result = Image.composite(ink, mapped, edges.convert("L"))

    if paper_texture:
        result = apply_paper_texture(result)

    if paper_tint is not None:
        result = apply_paper_tint(result, *paper_tint)

    result.save(output_path)
    print(f"Saved → {output_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Apply ukiyo-e effect to a map tile")
    parser.add_argument("input", help="Input image path")
    parser.add_argument("output", help="Output image path")
    parser.add_argument(
        "--fix-stipple",
        action="store_true",
        help="Collapse isolated light pixels surrounded by dark neighbours"
    )
    parser.add_argument(
        "--paper-texture",
        action="store_true",
        help="Add blob-shaped noise to simulate washi paper grain"
    )
    parser.add_argument(
        "--paper-tint",
        nargs=3,
        type=int,
        metavar=("X",
                 "Y",
                 "Z"),
        help="Apply seeded large-scale colour gradient (tile x y z)"
    )
    args = parser.parse_args()
    apply_ukiyo_e(
        args.input,
        args.output,
        fix_stipple=args.fix_stipple,
        paper_texture=args.paper_texture,
        paper_tint=tuple(args.paper_tint) if args.paper_tint else None,
    )
