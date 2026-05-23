#!/usr/bin/env python
"""Debug script for geo/S2/Overpass queries."""

import argparse
import sys
import os

import requests

import h3

from kishin_trails.utils import (
    latLngToS2Cell,
    s2CellIdToLatLng,
    getS2CellLevel,
    s2CellToParent,
    getS2CellBounds,
    getS2CellCenter,
    getS2EdgeLength,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

S2_TO_H3 = {0:0, 1:0, 2:0, 3:0, 4:1, 5:2, 6:2, 7:3, 8:4, 9:5, 10:5, 11:6, 12:7, 13:7, 14:8, 15:9, 16:10, 17:10, 18:11, 19:12, 20:12, 21:13, 22:14, 23:15, 24:15, 25:15, 26:15, 27:15, 28:15, 29:15, 30:15}
H3_TO_S2 = {v: k for k, v in S2_TO_H3.items()}


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
    cell_group = parser.add_mutually_exclusive_group()
    cell_group.add_argument("--s2-cell", type=str, help="S2 cell ID")
    cell_group.add_argument("--h3-cell", type=str, help="H3 cell ID")
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

    lat, lng, s2CellRes16, searchCellId, h3Cell = None, None, None, None, None

    if args.location:
        locations = settings.DEBUG_LOCATIONS
        if args.location not in locations:
            print(f"Error: location '{args.location}' not found. Use --list-locations to see available.")
            sys.exit(1)
        loc = locations[args.location]
        lat = loc["lat"]
        lng = loc["lng"]
        s2CellRes16 = loc.get("s2_res16") or latLngToS2Cell(lat, lng, 16)
        s2Level = getS2CellLevel(s2CellRes16)
        h3Res = S2_TO_H3[s2Level]
        h3Cell = h3.latlng_to_cell(lat, lng, h3Res)
        if args.parent_level > 0:
            searchCellId = s2CellToParent(s2CellRes16, s2Level - args.parent_level)
        else:
            searchCellId = s2CellRes16
        print(f"Location: {args.location}")

    elif args.s2_cell is not None:
        s2CellRes16 = args.s2_cell
        lat, lng = s2CellIdToLatLng(s2CellRes16)
        s2Level = getS2CellLevel(s2CellRes16)
        h3Res = S2_TO_H3[s2Level]
        h3Cell = h3.latlng_to_cell(lat, lng, h3Res)
        if args.parent_level > 0:
            searchCellId = s2CellToParent(s2CellRes16, s2Level - args.parent_level)
        else:
            searchCellId = s2CellRes16
        print(f"S2 cell: {s2CellRes16}")

    elif args.h3_cell is not None:
        h3Res = h3.get_resolution(args.h3_cell)
        h3Lat, h3Lng = h3.cell_to_latlng(args.h3_cell)
        lat, lng = h3Lat, h3Lng
        s2Level = H3_TO_S2[h3Res]
        s2CellRes16 = latLngToS2Cell(lat, lng, s2Level)
        if args.parent_level > 0:
            searchCellId = s2CellToParent(s2CellRes16, s2Level - args.parent_level)
        else:
            searchCellId = s2CellRes16
        h3Cell = args.h3_cell
        print(f"H3 cell: {args.h3_cell}")

    elif args.lat is not None and args.lng is not None:
        lat = args.lat
        lng = args.lng
        s2CellRes16 = latLngToS2Cell(lat, lng, args.resolution)
        s2Level = getS2CellLevel(s2CellRes16)
        h3Res = S2_TO_H3[s2Level]
        h3Cell = h3.latlng_to_cell(lat, lng, h3Res)
        if args.parent_level > 0:
            searchCellId = s2CellToParent(s2CellRes16, s2Level - args.parent_level)
        else:
            searchCellId = s2CellRes16

    else:
        parser.print_help()
        sys.exit(1)

    s2Level = getS2CellLevel(s2CellRes16)
    h3Res = h3.get_resolution(h3Cell)

    print("\n--- Coordinates ---")
    print(f"Lat/Lng: lat={lat}, lng={lng}")
    print(f"S2 (lvl {s2Level}): {s2CellRes16}")
    print(f"H3 (res {h3Res}): {h3Cell}")

    print(f"\n--- Search Cell (parent level {args.parent_level}) ---")
    print(f"S2: {searchCellId} (lvl {getS2CellLevel(searchCellId)})")
    print(f"H3: {h3Cell} (res {h3Res})")
    centerLat, centerLng = getS2CellCenter(searchCellId)
    print(f"Center: lat={centerLat}, lng={centerLng}")
    loLat, loLng, hiLat, hiLng = getS2CellBounds(searchCellId)
    print(f"Bounds: lo=({loLat:.6f}, {loLng:.6f}), hi=({hiLat:.6f}, {hiLng:.6f})")
    print(f"S2 edge: {getS2EdgeLength(searchCellId):.1f} m")
    print(f"H3 edge: {h3.average_hexagon_edge_length(h3Res) * 1000:.1f} m")

    print("\n--- Parent Cells ---")
    res = getS2CellLevel(searchCellId)
    for level in range(1, res):
        parent = s2CellToParent(searchCellId, res - level)
        h3Parent = h3.latlng_to_cell(*getS2CellCenter(parent), S2_TO_H3[res - level])
        parentLat, parentLng = getS2CellCenter(parent)
        parentEdge = getS2EdgeLength(parent)
        print(
            f"  Level {res - level} (lvl {level}): S2 {parent} | H3 {h3Parent} | lat={parentLat:.5f}, lng={parentLng:.5f} | edge={parentEdge:.1f}m"
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
