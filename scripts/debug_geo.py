#!/usr/bin/env python
"""Debug script for geo/H3/Overpass queries."""

import argparse
import sys
import os

import h3
import requests

from kishin_trails.config import settings
from kishin_trails.overpass import OVERPASS_URL, buildBbox, buildQuery
from kishin_trails.utils import getH3Cell, getH3CellRadius, getH3Circle

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    """Main entry point for the debug geo/H3/Overpass utility script.

    Parses command-line arguments and performs requested geo operations:
    - List available debug locations from configuration
    - Convert coordinates to H3 cells
    - Get parent H3 cells at different resolution levels
    - Build and optionally execute Overpass API queries

    The script supports multiple input modes (location name, lat/lng, or H3 cell)
    and can output bounding boxes, Overpass queries, and execute them against the API.
    """
    parser = argparse.ArgumentParser(description="Debug geo/H3/Overpass utilities")
    parser.add_argument("--location", type=str, help="Name of location from DEBUG_LOCATIONS")
    parser.add_argument("--lat", type=float, help="Latitude")
    parser.add_argument("--lng", type=float, help="Longitude")
    parser.add_argument("--h3-cell", type=str, help="H3 cell ID")
    parser.add_argument("--resolution", type=int, default=10, help="H3 resolution (default: 10)")
    parser.add_argument("--level", type=int, default=0, help="H3 parent level for search (default: 0)")
    parser.add_argument("--radius", type=int, help="Radius in meters (overrides H3 cell radius)")
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
            h3Cell = loc.get("h3_res10") or getH3Cell(loc["lat"], loc["lng"], 10)
            print(f"  {name}: lat={loc['lat']}, lng={loc['lng']}, h3_res10={h3Cell}")
        return

    lat, lng, h3CellRes10, searchCell, radiusM = None, None, None, None, None

    if args.location:
        locations = settings.DEBUG_LOCATIONS
        if args.location not in locations:
            print(f"Error: location '{args.location}' not found. Use --list-locations to see available.")
            sys.exit(1)
        loc = locations[args.location]
        lat = loc["lat"]
        lng = loc["lng"]
        h3CellRes10 = loc.get("h3_res10") or getH3Cell(lat, lng, 10)
        _, _, radiusM, searchCell = getH3Circle(h3CellRes10, args.level)
        print(f"Location: {args.location}")

    elif args.h3_cell:
        h3CellRes10 = args.h3_cell
        lat, lng, radiusM, searchCell = getH3Circle(args.h3_cell, args.level)
        print(f"H3 cell: {args.h3_cell}")

    elif args.lat is not None and args.lng is not None:
        lat = args.lat
        lng = args.lng
        h3CellRes10 = getH3Cell(lat, lng, args.resolution)
        _, _, radiusM, searchCell = getH3Circle(h3CellRes10, args.level)

    else:
        parser.print_help()
        sys.exit(1)

    if args.radius:
        radiusM = args.radius

    print("\n--- Coordinates ---")
    print(f"Lat/Lng: lat={lat}, lng={lng}")
    print(f"H3 (res 10): {h3CellRes10}")

    print(f"\n--- Search Cell (level {args.level}) ---")
    print(f"Cell: {searchCell}")
    searchLat, searchLng = h3.cell_to_latlng(searchCell)
    print(f"Center: lat={searchLat}, lng={searchLng}")
    print(f"Radius: {radiusM} m")

    print("\n--- Parent Cells ---")
    res = h3.get_resolution(h3CellRes10)
    for level in range(1, res + 1):
        parent = h3.cell_to_parent(h3CellRes10, res=res - level)
        parentLat, parentLng = h3.cell_to_latlng(parent)
        parentRadius = getH3CellRadius(parent)
        print(
            f"  Level {level} (res {res - level}): {parent} | lat={parentLat:.5f}, lng={parentLng:.5f} | r={parentRadius}m"
        )

    if args.overpass:
        bbox = buildBbox(searchLat, searchLng, radiusM)
        south, west, north, east = bbox
        northWest = (north, west)
        northEast = (north, east)
        southWest = (south, west)
        southEast = (south, east)
        print("\n--- Bounding Box ---")
        print(f"NW/SW/NE/SE: {northWest}, {southWest}, {northEast}, {southEast}")

        query = buildQuery(bbox)
        print("\n--- Overpass Query ---")
        print(query)

        if args.execute:
            print("\n--- Executing query... ---")
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
