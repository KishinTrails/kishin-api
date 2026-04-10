#!/usr/bin/env python
"""Test Perlin noise parameters against H3 cells with configurable conditions."""

import argparse
import json
import sys
from typing import Any

from tqdm import tqdm

from kishin_trails.noise_cache import load_cache, clear_cache
from kishin_trails.perlin import get_noise_for_cell


def load_config(config_path: str) -> dict[str, Any]:
    """Load configuration from JSON file."""
    with open(config_path, "r") as f:
        return json.load(f)


def is_active(cell: str, scale: int, threshold: float) -> bool:
    """Check if a cell is active (noise value > threshold)."""
    noise_value = get_noise_for_cell(cell, scale)
    return noise_value > threshold


def check_condition(
    condition: dict[str, Any],
    scale: int,
    threshold: float
) -> tuple[bool, str]:
    """
    Check if a condition is satisfied.
    
    Returns:
        Tuple of (is_satisfied, message)
    """
    condition_type = condition["type"]
    
    if condition_type in ["min_active", "max_active", "exactly_active", "percentage_active"]:
        cells = condition["cells"]
        active_count = sum(1 for cell in cells if is_active(cell, scale, threshold))
        
        if condition_type == "min_active":
            count = condition["count"]
            satisfied = active_count >= count
            message = f"min_active: {active_count}/{len(cells)} active (need >= {count})"
        elif condition_type == "max_active":
            count = condition["count"]
            satisfied = active_count <= count
            message = f"max_active: {active_count}/{len(cells)} active (need <= {count})"
        elif condition_type == "exactly_active":
            count = condition["count"]
            satisfied = active_count == count
            message = f"exactly_active: {active_count}/{len(cells)} active (need == {count})"
        else:
            percentage = condition["percentage"]
            actual_percentage = (active_count / len(cells)) * 100
            satisfied = actual_percentage >= percentage
            message = f"percentage_active: {actual_percentage:.1f}% active (need >= {percentage}%)"
        
        return satisfied, message
    
    elif condition_type == "cell_must_be_active":
        cells = condition["cells"]
        cell = cells[0]
        active = is_active(cell, scale, threshold)
        satisfied = active
        message = f"cell_must_be_active: {cell} is {'active' if active else 'inactive'}"
        return satisfied, message
    
    elif condition_type == "cell_must_be_inactive":
        cells = condition["cells"]
        cell = cells[0]
        active = is_active(cell, scale, threshold)
        satisfied = not active
        message = f"cell_must_be_inactive: {cell} is {'inactive' if not active else 'active'}"
        return satisfied, message
    
    else:
        raise ValueError(f"Unknown condition type: {condition_type}")


def test_parameters(
    conditions: list[dict[str, Any]],
    scale: int,
    threshold: float
) -> tuple[bool, list[str]]:
    """
    Test if all conditions are satisfied for given parameters.
    
    Returns:
        Tuple of (all_satisfied, list of condition messages)
    """
    results = []
    all_satisfied = True
    
    for condition in conditions:
        satisfied, message = check_condition(condition, scale, threshold)
        results.append(message)
        if not satisfied:
            all_satisfied = False
    
    return all_satisfied, results


def generate_state_space(state_space: dict[str, dict[str, float]]) -> list[tuple[int, float]]:
    """Generate all (scale, threshold) combinations from state space config."""
    scale_config = state_space["scale"]
    threshold_config = state_space["threshold"]
    
    scale_min = int(scale_config["min"])
    scale_max = int(scale_config["max"])
    scale_step = int(scale_config.get("step", 1))
    
    threshold_min = float(threshold_config["min"])
    threshold_max = float(threshold_config["max"])
    threshold_step = float(threshold_config.get("step", 0.05))
    
    combinations = []
    scale_values = list(range(scale_min, scale_max + 1, scale_step))
    threshold_values = []
    current = threshold_min
    while current <= threshold_max + 1e-9:
        threshold_values.append(round(current, 10))
        current += threshold_step
    
    for scale in scale_values:
        for threshold in threshold_values:
            combinations.append((scale, threshold))
    
    return combinations


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test Perlin noise parameters against H3 cells with configurable conditions"
    )
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to JSON configuration file"
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear the noise cache before running"
    )
    
    args = parser.parse_args()
    
    if args.clear_cache:
        clear_cache()
        print("Cache cleared")
    
    load_cache()
    
    config = load_config(args.config)
    conditions = config["conditions"]
    state_space = config["state_space"]
    
    all_cells = set()
    for condition in conditions:
        if "cells" in condition:
            all_cells.update(condition["cells"])
    
    combinations = generate_state_space(state_space)
    total = len(combinations)
    
    print(f"Testing {len(all_cells)} cells with {len(conditions)} conditions")
    print(f"State space: {total} parameter combinations")
    print()
    
    for scale, threshold in tqdm(combinations, desc="Testing parameters"):
        satisfied, messages = test_parameters(conditions, scale, threshold)
        
        if satisfied:
            print(f"\n✓ Found solution!")
            print(f"  scale: {scale}")
            print(f"  threshold: {threshold}")
            print()
            print("Condition results:")
            for msg in messages:
                print(f"  ✓ {msg}")
            print()
            print("Cell details:")
            for cell in sorted(all_cells):
                noise_value = get_noise_for_cell(cell, scale)
                active = noise_value > threshold
                status = "ACTIVE" if active else "inactive"
                print(f"  {cell}: {noise_value:.4f} ({status})")
            return
    
    print("\n✗ No solution found")
    print(f"Tested {total} parameter combinations")
    print("Consider adjusting state_space or conditions")


if __name__ == "__main__":
    main()
