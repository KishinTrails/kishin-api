#!/usr/bin/env python
"""Debug script for geo/H3/Overpass queries."""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import h3
import requests

from kishin_trails.config import settings
from kishin_trails.overpass import OVERPASS_URL, build_bbox, build_query
from kishin_trails.utils import get_h3_cell, get_h3_cell_radius, get_h3_circle


def main():
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
            h3_cell = loc.get("h3_res10") or get_h3_cell(loc["lat"], loc["lng"], 10)
            print(f"  {name}: lat={loc['lat']}, lng={loc['lng']}, h3_res10={h3_cell}")
        return

    lat, lng, h3_cell_res10, search_cell, radius_m = None, None, None, None, None

    if args.location:
        locations = settings.DEBUG_LOCATIONS
        if args.location not in locations:
            print(f"Error: location '{args.location}' not found. Use --list-locations to see available.")
            sys.exit(1)
        loc = locations[args.location]
        lat = loc["lat"]
        lng = loc["lng"]
        h3_cell_res10 = loc.get("h3_res10") or get_h3_cell(lat, lng, 10)
        _, _, radius_m, search_cell = get_h3_circle(h3_cell_res10, args.level)
        print(f"Location: {args.location}")

    elif args.h3_cell:
        h3_cell_res10 = args.h3_cell
        lat, lng, radius_m, search_cell = get_h3_circle(args.h3_cell, args.level)
        print(f"H3 cell: {args.h3_cell}")

    elif args.lat is not None and args.lng is not None:
        lat = args.lat
        lng = args.lng
        h3_cell_res10 = get_h3_cell(lat, lng, args.resolution)
        _, _, radius_m, search_cell = get_h3_circle(h3_cell_res10, args.level)

    else:
        parser.print_help()
        sys.exit(1)

    if args.radius:
        radius_m = args.radius

    print(f"\n--- Coordinates ---")
    print(f"Lat/Lng: lat={lat}, lng={lng}")
    print(f"H3 (res 10): {h3_cell_res10}")

    print(f"\n--- Search Cell (level {args.level}) ---")
    print(f"Cell: {search_cell}")
    search_lat, search_lng = h3.cell_to_latlng(search_cell)
    print(f"Center: lat={search_lat}, lng={search_lng}")
    print(f"Radius: {radius_m} m")

    print(f"\n--- Parent Cells ---")
    res = h3.get_resolution(h3_cell_res10)
    for level in range(1, res + 1):
        parent = h3.cell_to_parent(h3_cell_res10, res=res - level)
        parent_lat, parent_lng = h3.cell_to_latlng(parent)
        parent_radius = get_h3_cell_radius(parent)
        print(
            f"  Level {level} (res {res - level}): {parent} | lat={parent_lat:.5f}, lng={parent_lng:.5f} | r={parent_radius}m"
        )

    if args.overpass:
        bbox = build_bbox(search_lat, search_lng, radius_m)
        query = build_query(bbox)
        print(f"\n--- Overpass Query ---")
        print(query)

        if args.execute:
            print(f"\n--- Executing query... ---")
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

