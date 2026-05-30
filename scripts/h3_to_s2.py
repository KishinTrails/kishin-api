#!/usr/bin/env python
"""Convert H3 cell identifiers to S2 cells based on cell center."""

import json
import sys
import os

import h3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kishin_trails.utils import latLngToS2Cell


def h3ToS2Cell(h3Cell: str) -> str:
    lat, lng = h3.cell_to_latlng(h3Cell)
    return latLngToS2Cell(lat, lng, 16)


def convertConfig(inputPath: str, outputPath: str) -> None:
    with open(inputPath) as f:
        config = json.load(f)

    for condition in config.get("conditions", []):
        condition["cells"] = [h3ToS2Cell(c) for c in condition["cells"]]

    with open(outputPath, "w") as f:
        json.dump(config, f, indent=2)

    print(f"Converted {inputPath} -> {outputPath}")


if __name__ == "__main__":
    inputPath = sys.argv[1] if len(sys.argv) > 1 else "scripts/perlin_config.json"
    outputPath = sys.argv[2] if len(sys.argv) > 2 else "scripts/perlin_config_s2.json"
    convertConfig(inputPath, outputPath)