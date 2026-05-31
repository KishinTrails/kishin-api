"""
ukiyo_e.py — Apply a Japanese woodblock print (ukiyo-e) effect to a map tile image.

Usage:
    python ukiyo_e.py <input> <output>
    python ukiyo_e.py <input> <output> --fix-stipple   # collapse isolated light pixels first

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


def apply_ukiyo_e(input_path: str, output_path: str, fix_stipple: bool = False) -> None:
    img = Image.open(input_path).convert("RGB")

    # Flatten gradients
    img = ImageOps.posterize(img, 2)
    # img = img.filter(ImageFilter.SMOOTH_MORE)

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

    # Subtle washi paper noise
    noise = np.random.normal(0, 6, (h, w, 3)).astype(np.int32)
    result = Image.fromarray(np.clip(np.array(result, dtype=np.int32) + noise, 0, 255).astype(np.uint8))

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
    args = parser.parse_args()
    apply_ukiyo_e(args.input, args.output, fix_stipple=args.fix_stipple)
