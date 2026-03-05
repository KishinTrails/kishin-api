"""Utility functions for data processing."""

from typing import Any

import h3


def sanitize_value(v: Any) -> str | None:
    """Sanitize a value for JSON serialization.
    
    Args:
        v: Value to sanitize.
        
    Returns:
        String version of the value, or None if the value is NaN/inf.
    """
    if isinstance(v, float) and (v != v or v == float("inf") or v == float("-inf")):
        return None
    if isinstance(v, str):
        return v
    return str(v)


def get_h3_cell_radius(h3_cell: str) -> int:
    """Calculate the approximate radius of an H3 cell in meters.
    
    For a hexagonal cell, the radius (center to vertex) equals the edge length.
    The diameter (vertex to opposite vertex) is 2 * edge_length.
    
    Args:
        h3_cell: H3 cell identifier.
        
    Returns:
        Approximate radius in meters (diameter of the hexagon).
    """
    res = h3.get_resolution(h3_cell)
    edge_length = h3.average_hexagon_edge_length(res, unit="m")
    return int(edge_length * 2)


def get_h3_circle(h3_cell: str, parent_level: int = 0) -> tuple[float, float, int, str]:
    """Get center coordinates and radius for an H3 cell at a given parent level.
    
    Args:
        h3_cell: H3 cell identifier.
        parent_level: Level of parent cell (0 = current cell, 1 = first parent, etc.).
        
    Returns:
        Tuple of (lat, lng, radius_m, search_cell).
        
    Raises:
        ValueError: If parent_level exceeds cell resolution.
    """
    cell_res = h3.get_resolution(h3_cell)
    
    if parent_level > 0:
        target_res = cell_res - parent_level
        if target_res < 0:
            raise ValueError(f"Parent level {parent_level} exceeds cell resolution {cell_res}")
        search_cell = h3.cell_to_parent(h3_cell, res=target_res)
    else:
        search_cell = h3_cell
    
    lat, lng = h3.cell_to_latlng(search_cell)
    radius_m = get_h3_cell_radius(search_cell)
    
    return lat, lng, radius_m, search_cell
