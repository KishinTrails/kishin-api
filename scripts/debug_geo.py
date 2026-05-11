#!/usr/bin/env python
"""Debug script for geo/S2/Overpass queries."""

import argparse
import sys
import os

import requests

from kishin_trails.s2_utils import (
    latLngToS2Cell,
    s2CellIdToHex,
    s2CellIdFromHex,
    s2CellIdToLatLng,
    getS2CellLevel,
    s2CellToParent,
    getS2CellBounds,
    getS2CellCenter,
    getS2EdgeLength,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    """Main entry point for the debug geo/S2/Overpass utility script.

    Parses command-line arguments and performs requested geo operations:
    - List available debug locations from configuration
    - Convert coordinates to S2 cells
    - Get parent S2 cells at different resolution levels
    - Build and optionally execute Overpass API queries

    The script supports multiple input modes (location name, lat/lng, or S2 cell)
    and can output bounding boxes, Overpass queries, and execute them against the API.
    """
    from kishin_trails.config import settings
    from kishin_trails.overpass import buildQuery

    parser = argparse.ArgumentParser(description="Debug geo/S2/Overpass utilities")
    parser.add_argument("--location", type=str, help="Name of location from DEBUG_LOCATIONS")
    parser.add_argument("--lat", type=float, help="Latitude")
    parser.add_argument("--lng", type=float, help="Longitude")
    parser.add_argument("--s2-cell", type=str, help="S2 cell ID (decimal or hex)")
    parser.add_argument("--resolution", type=int, default=16, help="S2 level (default: 16)")
    parser.add_argument("--parent-level", type=int, default=0, help="S2 parent level for search (default: 0)")
    parser.add_argument("--overpass", action="store_true", help="Output Overpass query")
    parser.add_argument("--execute", action="store_true", help="Execute the Overpass query")
    parser.add_argument("--list-locations", action="store_true", help="List available debug locations")

    args = parser.parse_args()

    if args.list_locations:
        locations = settings.DEBUG_LOCATIONS
        if not locations:
            print("No DEBUG_LOCATIONS defined. Add to .env:")
            print('  DEBUG_LOCATIONS=\'{"home": {"lat": 48.85, "lng": 2.34}}\'')
            return
        print("Available locations:")
        for name, loc in locations.items():
            s2Cell = loc.get("s2_res16") or latLngToS2Cell(loc["lat"], loc["lng"], 16)
            print(f"  {name}: lat={loc['lat']}, lng={loc['lng']}, s2_res16={s2Cell}")
        return

    lat, lng, s2CellRes16, searchCellId = None, None, None, None

    if args.location:
        locations = settings.DEBUG_LOCATIONS
        if args.location not in locations:
            print(f"Error: location '{args.location}' not found. Use --list-locations to see available.")
            sys.exit(1)
        loc = locations[args.location]
        lat = loc["lat"]
        lng = loc["lng"]
        s2CellRes16 = loc.get("s2_res16") or latLngToS2Cell(lat, lng, 16)
        if args.parent_level > 0:
            searchCellId = s2CellToParent(s2CellRes16, getS2CellLevel(s2CellRes16) - args.parent_level)
        else:
            searchCellId = s2CellRes16
        print(f"Location: {args.location}")

    elif args.s2_cell is not None:
        if args.s2_cell.startswith("0x") or any(c in args.s2_cell.lower() for c in "abcdef"):
            s2CellRes16 = s2CellIdFromHex(args.s2_cell.replace("0x", ""))
        else:
            s2CellRes16 = int(args.s2_cell)
        lat, lng = s2CellIdToLatLng(s2CellRes16)
        if args.parent_level > 0:
            searchCellId = s2CellToParent(s2CellRes16, getS2CellLevel(s2CellRes16) - args.parent_level)
        else:
            searchCellId = s2CellRes16
        print(f"S2 cell: {s2CellRes16} / {s2CellIdToHex(s2CellRes16)}")

    elif args.lat is not None and args.lng is not None:
        lat = args.lat
        lng = args.lng
        s2CellRes16 = latLngToS2Cell(lat, lng, args.resolution)
        if args.parent_level > 0:
            searchCellId = s2CellToParent(s2CellRes16, args.resolution - args.parent_level)
        else:
            searchCellId = s2CellRes16

    else:
        parser.print_help()
        sys.exit(1)

    print("\n--- Coordinates ---")
    print(f"Lat/Lng: lat={lat}, lng={lng}")
    print(f"S2 (res 16): {s2CellRes16} / {s2CellIdToHex(s2CellRes16)}")

    print(f"\n--- Search Cell (parent level {args.parent_level}) ---")
    print(f"Cell: {searchCellId} / {s2CellIdToHex(searchCellId)}")
    print(f"Level: {getS2CellLevel(searchCellId)}")
    centerLat, centerLng = getS2CellCenter(searchCellId)
    print(f"Center: lat={centerLat}, lng={centerLng}")
    loLat, loLng, hiLat, hiLng = getS2CellBounds(searchCellId)
    print(f"Bounds: lo=({loLat:.6f}, {loLng:.6f}), hi=({hiLat:.6f}, {hiLng:.6f})")
    print(f"Edge length: {getS2EdgeLength(searchCellId):.1f} m")

    print("\n--- Parent Cells ---")
    res = getS2CellLevel(searchCellId)
    for level in range(1, res):
        parent = s2CellToParent(searchCellId, res - level)
        parentLat, parentLng = getS2CellCenter(parent)
        parentEdge = getS2EdgeLength(parent)
        print(
            f"  Level {res - level} (lvl {level}): {parent} / {s2CellIdToHex(parent)} | lat={parentLat:.5f}, lng={parentLng:.5f} | edge={parentEdge:.1f}m"
        )

    if args.overpass:
        south, west, north, east = loLat, loLng, hiLat, hiLng
        northWest = (north, west)
        northEast = (north, east)
        southWest = (south, west)
        southEast = (south, east)
        print("\n--- Bounding Box ---")
        print(f"NW/SW/NE/SE: {northWest}, {southWest}, {northEast}, {southEast}")

        bbox = (south, west, north, east)
        query = buildQuery(bbox)
        print("\n--- Overpass Query ---")
        print(query)

        if args.execute:
            print("\n--- Executing query... ---")
            from kishin_trails.overpass import OVERPASS_URL
            response = requests.post(
                OVERPASS_URL,
                data={
                    "data": query
                },
                timeout=90
            )
            response.raise_for_status()
            data = response.json()
            count = len(data.get("elements", []))
            print(f"Got {count} elements")
            for elem in data.get("elements", []):
                print(elem)


if __name__ == "__main__":
    main()
