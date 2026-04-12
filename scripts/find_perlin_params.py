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

from multiprocessing import Pool
from tqdm import tqdm

from kishin_trails.perlin import getNoiseForCell
from kishin_trails.database import engine, Base


def loadConfig(configPath: str) -> dict[str, Any]:
    """
    Load configuration from a JSON file.

    Args:
        configPath: Path to the JSON configuration file.

    Returns:
        Dictionary containing configuration with conditions and state_space.
    """
    with open(configPath, "r") as handle:
        return json.load(handle)


def isActive(cell: str, scale: int, threshold: float, octaves: int = 3, amplitudeDecay: float = 0.5) -> bool:
    """
    Determine if an H3 cell is considered 'active' based on its noise value.

    A cell is active when its Perlin noise value exceeds the threshold.

    Args:
        cell: H3 cell identifier.
        scale: Noise scale parameter.
        threshold: Threshold value for activation (0-1 range).
        octaves: Number of noise octaves.
        amplitudeDecay: Amplitude decay factor per octave.

    Returns:
        True if noise value exceeds threshold, False otherwise.
    """
    noiseValue = getNoiseForCell(cell, scale, octaves, amplitudeDecay)
    return noiseValue > threshold


def checkCondition(
    condition: dict[str,
                    Any],
    scale: int,
    threshold: float,
    octaves: int = 3,
    amplitudeDecay: float = 0.5
) -> tuple[bool,
           str]:
    """
    Check if a condition is satisfied.

    Returns:
        Tuple of (is_satisfied, message)
    """
    conditionType = condition["type"]

    if conditionType in ["min_active", "max_active", "exactly_active", "interval_active", "percentage_active"]:
        cells = condition["cells"]
        activeCount = sum(1 for cell in cells if isActive(cell, scale, threshold, octaves, amplitudeDecay))

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
        elif conditionType == "interval_active":
            minCount = condition["min"]
            maxCount = condition["max"]
            satisfied = minCount <= activeCount <= maxCount
            message = f"interval_active: {activeCount}/{len(cells)} active (need {minCount}-{maxCount})"
        else:
            percentage = condition["percentage"]
            actualPercentage = (activeCount / len(cells)) * 100
            satisfied = actualPercentage >= percentage
            message = f"percentage_active: {actualPercentage:.1f}% active (need >= {percentage}%)"

        return satisfied, message

    if conditionType == "cell_must_be_active":
        cells = condition["cells"]
        cell = cells[0]
        active = isActive(cell, scale, threshold, octaves, amplitudeDecay)
        satisfied = active
        message = f"cell_must_be_active: {cell} is {'active' if active else 'inactive'}"
        return satisfied, message

    if conditionType == "cell_must_be_inactive":
        cells = condition["cells"]
        cell = cells[0]
        active = isActive(cell, scale, threshold, octaves, amplitudeDecay)
        satisfied = not active
        message = f"cell_must_be_inactive: {cell} is {'inactive' if not active else 'active'}"
        return satisfied, message

    raise ValueError(f"Unknown condition type: {conditionType}")


def testParameters(
    conditions: list[dict[str,
                          Any]],
    scale: int,
    threshold: float,
    octaves: int = 3,
    amplitudeDecay: float = 0.5
) -> tuple[bool,
           list[str],
           list[str | None]]:
    """
    Evaluate all conditions against the given scale and threshold parameters.

    Args:
        conditions: List of condition dictionaries to evaluate.
        scale: Noise scale parameter to test.
        threshold: Noise threshold value to test.
        octaves: Number of noise octaves.
        amplitudeDecay: Amplitude decay factor per octave.

    Returns:
        Tuple of (all_satisfied, list of condition result messages, list of comments).
        all_satisfied is True only if every condition passes.
        Comments are None if not provided in the condition.
    """
    results = []
    comments = []
    allSatisfied = True

    for condition in conditions:
        satisfied, message = checkCondition(condition, scale, threshold, octaves, amplitudeDecay)
        results.append(message)
        comments.append(condition.get("comment"))
        if not satisfied:
            allSatisfied = False

    return allSatisfied, results, comments


def testCombination(
    args: tuple[list[dict[str,
                          Any]],
                int,
                float,
                int,
                float]
) -> tuple[bool,
           list[str],
           list[str | None],
           int,
           float,
           int,
           float]:
    """
    Worker function for multiprocessing.

    Each worker uses its own per-process SQLite engine (WAL mode) so cache
    reads and writes don't contend across processes.

    Args:
        args: Tuple of (conditions, scale, threshold, octaves, amplitudeDecay)

    Returns:
        Tuple of (satisfied, messages, comments, scale, threshold, octaves, amplitudeDecay)
    """
    conditions, scale, threshold, octaves, amplitudeDecay = args
    satisfied, messages, comments = testParameters(conditions, scale, threshold, octaves, amplitudeDecay)
    return satisfied, messages, comments, scale, threshold, octaves, amplitudeDecay


def generateStateSpace(stateSpace: dict[str, dict[str, float]]) -> list[tuple[int, float, int, float]]:
    """
    Generate all parameter combinations from the state space configuration.

    Creates a grid of (scale, threshold, octaves, amplitudeDecay) tuples by iterating through the
    configured ranges with specified step sizes.

    Args:
        stateSpace: Dictionary with 'scale', 'threshold', 'octaves', and 'amplitudeDecay' range configs,
                    each containing 'min', 'max', and optional 'step'.

    Returns:
        List of (scale, threshold, octaves, amplitudeDecay) tuples representing all combinations.
    """
    scaleConfig = stateSpace["scale"]
    thresholdConfig = stateSpace["threshold"]
    octavesConfig = stateSpace.get("octaves",
                                   {
                                       "min": 3,
                                       "max": 3,
                                       "step": 1
                                   })
    amplitudeDecayConfig = stateSpace.get("amplitudeDecay",
                                          {
                                              "min": 0.5,
                                              "max": 0.5,
                                              "step": 0.1
                                          })

    scaleMin = int(scaleConfig["min"])
    scaleMax = int(scaleConfig["max"])
    scaleStep = int(scaleConfig.get("step", 1))

    thresholdMin = float(thresholdConfig["min"])
    thresholdMax = float(thresholdConfig["max"])
    thresholdStep = float(thresholdConfig.get("step", 0.05))

    octavesMin = int(octavesConfig["min"])
    octavesMax = int(octavesConfig["max"])
    octavesStep = int(octavesConfig.get("step", 1))

    amplitudeDecayMin = float(amplitudeDecayConfig["min"])
    amplitudeDecayMax = float(amplitudeDecayConfig["max"])
    amplitudeDecayStep = float(amplitudeDecayConfig.get("step", 0.1))

    combinations = []
    scaleValues = list(range(scaleMin, scaleMax + 1, scaleStep))
    thresholdValues = []
    current = thresholdMin
    while current <= thresholdMax + 1e-9:
        thresholdValues.append(round(current, 10))
        current += thresholdStep

    octavesValues = list(range(octavesMin, octavesMax + 1, octavesStep))
    amplitudeDecayValues = []
    current = amplitudeDecayMin
    while current <= amplitudeDecayMax + 1e-9:
        amplitudeDecayValues.append(round(current, 10))
        current += amplitudeDecayStep

    for scale in scaleValues:
        for threshold in thresholdValues:
            for octaves in octavesValues:
                for amplitudeDecay in amplitudeDecayValues:
                    combinations.append((scale, threshold, octaves, amplitudeDecay))

    return combinations


def main():
    """
    Main entry point for the Perlin noise parameter testing script.

    Orchestrates the parameter search process:
    1. Parses command-line arguments
    2. Loads configuration from JSON file
    3. Generates state space of parameter combinations
    4. Tests each combination against all conditions in parallel workers
    5. Reports the first satisfying combination or indicates no solution found
    """
    parser = argparse.ArgumentParser(
        description="Test Perlin noise parameters against H3 cells with configurable conditions"
    )
    parser.add_argument("--config", type=str, required=True, help="Path to JSON configuration file")
    parser.add_argument("--no-cache", action="store_true", help="Run without using or saving to cache")

    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)

    config = loadConfig(args.config)
    conditions = config["conditions"]
    stateSpace = config["state_space"]

    allCells: set[str] = set()
    for condition in conditions:
        if "cells" in condition:
            allCells.update(condition["cells"])

    combinations = generateStateSpace(stateSpace)
    total = len(combinations)

    print(f"Testing {len(allCells)} cells with {len(conditions)} conditions")
    print(f"State space: {total} parameter combinations")
    print()

    workItems = [
        (conditions,
         scale,
         threshold,
         octaves,
         amplitudeDecay) for scale, threshold, octaves, amplitudeDecay in combinations
    ]

    solution = None
    with Pool() as pool:
        for satisfied, messages, comments, scale, threshold, octaves, amplitudeDecay in tqdm(
            pool.imap_unordered(testCombination, workItems),
            total=len(workItems),
            desc="Testing parameters",
        ):
            if satisfied:
                pool.terminate()
                solution = {
                    "scale": scale,
                    "threshold": threshold,
                    "octaves": octaves,
                    "amplitudeDecay": amplitudeDecay,
                    "messages": messages,
                    "comments": comments,
                }
                break

    if solution:
        print(f"\n✓ Found solution!")
        print(f"  scale: {solution['scale']}")
        print(f"  threshold: {solution['threshold']}")
        print(f"  octaves: {solution['octaves']}")
        print(f"  amplitudeDecay: {solution['amplitudeDecay']}")
        print()
        print("Condition results:")
        for i, msg in enumerate(solution["messages"]):
            comment = solution["comments"][i]
            if comment:
                print(f"  ✓ {msg} — {comment}")
            else:
                print(f"  ✓ {msg}")
    else:
        print("\n✗ No solution found")
        print(f"Tested {total} parameter combinations")
        print("Consider adjusting state_space or conditions")


if __name__ == "__main__":
    main()
