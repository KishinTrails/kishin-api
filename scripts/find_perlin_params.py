#!/usr/bin/env python
"""
Test Perlin noise parameters against H3 cells with configurable conditions.

This script helps find optimal Perlin noise parameters (scale and threshold)
that satisfy specific activation patterns across a set of H3 cells. It tests
combinations of parameters against user-defined conditions to find configurations
that produce desired noise activation patterns.
"""

import argparse
import json
from typing import Any

from tqdm import tqdm

from kishin_trails.noise_cache import loadCache, clearCache
from kishin_trails.perlin import getNoiseForCell


def loadConfig(configPath: str) -> dict[str, Any]:
    """
    Load configuration from a JSON file.

    Args:
        configPath: Path to the JSON configuration file.

    Returns:
        Dictionary containing configuration with conditions and state_space.
    """
    with open(configPath, "r") as f:
        return json.load(f)


def isActive(cell: str, scale: int, threshold: float) -> bool:
    """
    Determine if an H3 cell is considered 'active' based on its noise value.

    A cell is active when its Perlin noise value exceeds the threshold.

    Args:
        cell: H3 cell identifier.
        scale: Noise scale parameter.
        threshold: Threshold value for activation (0-1 range).

    Returns:
        True if noise value exceeds threshold, False otherwise.
    """
    noiseValue = getNoiseForCell(cell, scale)
    return noiseValue > threshold


def checkCondition(condition: dict[str, Any], scale: int, threshold: float) -> tuple[bool, str]:
    """
    Check if a condition is satisfied.
  
    Returns:
        Tuple of (is_satisfied, message)
    """
    conditionType = condition["type"]

    if conditionType in ["min_active", "max_active", "exactly_active", "percentage_active"]:
        cells = condition["cells"]
        activeCount = sum(1 for cell in cells if isActive(cell, scale, threshold))

        if conditionType == "min_active":
            count = condition["count"]
            satisfied = activeCount >= count
            message = f"min_active: {activeCount}/{len(cells)} active (need >= {count})"
        elif conditionType == "max_active":
            count = condition["count"]
            satisfied = activeCount <= count
            message = f"max_active: {activeCount}/{len(cells)} active (need <= {count})"
        elif conditionType == "exactly_active":
            count = condition["count"]
            satisfied = activeCount == count
            message = f"exactly_active: {activeCount}/{len(cells)} active (need == {count})"
        else:
            percentage = condition["percentage"]
            actualPercentage = (activeCount / len(cells)) * 100
            satisfied = actualPercentage >= percentage
            message = f"percentage_active: {actualPercentage:.1f}% active (need >= {percentage}%)"

        return satisfied, message

    elif conditionType == "cell_must_be_active":
        cells = condition["cells"]
        cell = cells[0]
        active = isActive(cell, scale, threshold)
        satisfied = active
        message = f"cell_must_be_active: {cell} is {'active' if active else 'inactive'}"
        return satisfied, message

    elif conditionType == "cell_must_be_inactive":
        cells = condition["cells"]
        cell = cells[0]
        active = isActive(cell, scale, threshold)
        satisfied = not active
        message = f"cell_must_be_inactive: {cell} is {'inactive' if not active else 'active'}"
        return satisfied, message

    else:
        raise ValueError(f"Unknown condition type: {conditionType}")


def testParameters(conditions: list[dict[str, Any]], scale: int, threshold: float) -> tuple[bool, list[str]]:
    """
    Evaluate all conditions against the given scale and threshold parameters.

    Iterates through each condition and checks if it's satisfied by the
    current parameter combination.

    Args:
        conditions: List of condition dictionaries to evaluate.
        scale: Noise scale parameter to test.
        threshold: Noise threshold value to test.

    Returns:
        Tuple of (all_satisfied, list of condition result messages).
        all_satisfied is True only if every condition passes.
    """
    results = []
    allSatisfied = True

    for condition in conditions:
        satisfied, message = checkCondition(condition, scale, threshold)
        results.append(message)
        if not satisfied:
            allSatisfied = False

    return allSatisfied, results


def generateStateSpace(stateSpace: dict[str, dict[str, float]]) -> list[tuple[int, float]]:
    """
    Generate all parameter combinations from the state space configuration.

    Creates a grid of (scale, threshold) pairs by iterating through the
    configured ranges with specified step sizes.

    Args:
        stateSpace: Dictionary with 'scale' and 'threshold' range configs,
                    each containing 'min', 'max', and optional 'step'.

    Returns:
        List of (scale, threshold) tuples representing all combinations.
    """
    scaleConfig = stateSpace["scale"]
    thresholdConfig = stateSpace["threshold"]

    scaleMin = int(scaleConfig["min"])
    scaleMax = int(scaleConfig["max"])
    scaleStep = int(scaleConfig.get("step", 1))

    thresholdMin = float(thresholdConfig["min"])
    thresholdMax = float(thresholdConfig["max"])
    thresholdStep = float(thresholdConfig.get("step", 0.05))

    combinations = []
    scaleValues = list(range(scaleMin, scaleMax + 1, scaleStep))
    thresholdValues = []
    current = thresholdMin
    while current <= thresholdMax + 1e-9:
        thresholdValues.append(round(current, 10))
        current += thresholdStep

    for scale in scaleValues:
        for threshold in thresholdValues:
            combinations.append((scale, threshold))

    return combinations


def main():
    """
    Main entry point for the Perlin noise parameter testing script.

    Orchestrates the parameter search process:
    1. Parses command-line arguments
    2. Loads configuration from JSON file
    3. Generates state space of parameter combinations
    4. Tests each combination against all conditions
    5. Reports the first satisfying combination or indicates no solution found
    """
    parser = argparse.ArgumentParser(
        description="Test Perlin noise parameters against H3 cells with configurable conditions"
    )
    parser.add_argument("--config", type=str, required=True, help="Path to JSON configuration file")
    parser.add_argument("--clear-cache", action="store_true", help="Clear the noise cache before running")

    args = parser.parse_args()

    if args.clear_cache:
        clearCache()
        print("Cache cleared")

    loadCache()

    config = loadConfig(args.config)
    conditions = config["conditions"]
    stateSpace = config["state_space"]

    allCells = set()
    for condition in conditions:
        if "cells" in condition:
            allCells.update(condition["cells"])

    combinations = generateStateSpace(stateSpace)
    total = len(combinations)

    print(f"Testing {len(allCells)} cells with {len(conditions)} conditions")
    print(f"State space: {total} parameter combinations")
    print()

    for scale, threshold in tqdm(combinations, desc="Testing parameters"):
        satisfied, messages = testParameters(conditions, scale, threshold)

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
            for cell in sorted(allCells):
                noiseValue = getNoiseForCell(cell, scale)
                active = noiseValue > threshold
                status = "ACTIVE" if active else "inactive"
                print(f"  {cell}: {noiseValue:.4f} ({status})")
            return

    print("\n✗ No solution found")
    print(f"Tested {total} parameter combinations")
    print("Consider adjusting state_space or conditions")


if __name__ == "__main__":
    main()
