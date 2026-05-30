#!/usr/bin/env python
"""
Search for Perlin noise parameters satisfying user-defined activation conditions.

This script performs a grid search over a configurable parameter space
(scale, threshold, octaves, amplitude decay) and evaluates each combination
against a set of conditions that specify desired S2 cell activation patterns.
The search is parallelised with ``multiprocessing.Pool``.

Configuration file format (JSON)
---------------------------------
::

    {
        "conditions": [
            {
                "type": "cell_must_be_active",
                "cells": ["<s2_token>"],
                "comment": "optional human-readable note"
            },
            {
                "type": "interval_active",
                "cells": ["<token1>", "<token2>", ...],
                "min": 3,
                "max": 7,
                "comment": "between 3 and 7 of these cells must be active"
            }
        ],
        "state_space": {
            "scale":         {"min": 100, "max": 200, "step": 5},
            "threshold":     {"min": 0.5,  "max": 0.9,  "step": 0.05},
            "octaves":       {"min": 3,    "max": 5,    "step": 1},
            "amplitudeDecay":{"min": 0.4,  "max": 0.8,  "step": 0.1}
        }
    }

Supported condition types
--------------------------
* ``min_active``           — at least *count* cells in *cells* must be active.
* ``max_active``           — at most *count* cells in *cells* must be active.
* ``exactly_active``       — exactly *count* cells in *cells* must be active.
* ``interval_active``      — active count must be in [*min*, *max*].
* ``percentage_active``    — at least *percentage* % of *cells* must be active.
* ``cell_must_be_active``  — the single cell in *cells* must be active.
* ``cell_must_be_inactive``— the single cell in *cells* must be inactive.

Parallel execution and SQLite cache
-------------------------------------
Each worker process calls ``init_engine()`` in its initializer so that every
process owns its own SQLAlchemy connection pool.  Combined with the WAL
journal mode configured in ``database.py``, this avoids ``database is locked``
errors that arise when many processes write to the cache simultaneously.

The search stops at the *first* satisfying combination found by any worker.
``pool.terminate()`` is deferred until after the solution has been captured,
preventing torn cache writes.
"""

import argparse
import json
from multiprocessing import Pool
from typing import Any

from tqdm import tqdm

from kishin_trails.database import Base, engine, init_engine
from kishin_trails.perlin import getNoiseForCell

# ---------------------------------------------------------------------------
# Configuration loading
# ---------------------------------------------------------------------------


def loadConfig(configPath: str) -> dict[str, Any]:
    """
    Load and parse a JSON configuration file.

    Args:
        configPath: Filesystem path to the JSON configuration file.

    Returns:
        Parsed configuration dictionary with ``conditions`` and
        ``state_space`` keys.

    Raises:
        FileNotFoundError: If *configPath* does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    with open(configPath, "r") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# Activation helpers
# ---------------------------------------------------------------------------


def isActive(
    cell: str,
    scale: int,
    threshold: float,
    octaves: int = 3,
    amplitudeDecay: float = 0.5,
) -> bool:
    """
    Return whether an S2 cell's noise value exceeds *threshold*.

    Args:
        cell: S2 cell hex token.
        scale: Noise scale parameter.
        threshold: Activation threshold in [0, 1].
        octaves: Number of noise octaves.
        amplitudeDecay: Per-octave amplitude multiplier.

    Returns:
        ``True`` if the cell's noise value is strictly greater than
        *threshold*.
    """
    noise_value = getNoiseForCell(cell, scale, octaves, amplitudeDecay)
    return noise_value > threshold


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------


def checkCondition(
    condition: dict[str,
                    Any],
    scale: int,
    threshold: float,
    octaves: int = 3,
    amplitudeDecay: float = 0.5,
) -> tuple[bool,
           str]:
    """
    Evaluate a single condition against the given noise parameters.

    Args:
        condition: Condition specification dictionary (see module docstring).
        scale: Noise scale parameter.
        threshold: Activation threshold in [0, 1].
        octaves: Number of noise octaves.
        amplitudeDecay: Per-octave amplitude multiplier.

    Returns:
        ``(satisfied, message)`` — a boolean result and a human-readable
        description of the outcome.

    Raises:
        ValueError: If ``condition["type"]`` is not a recognised type.
    """
    condition_type = condition["type"]

    # ------------------------------------------------------------------
    # Aggregate conditions (operate on a collection of cells)
    # ------------------------------------------------------------------
    aggregate_types = {
        "min_active",
        "max_active",
        "exactly_active",
        "interval_active",
        "percentage_active",
    }
    if condition_type in aggregate_types:
        cells = condition["cells"]
        active_count = sum(1 for cell in cells if isActive(cell, scale, threshold, octaves, amplitudeDecay))

        if condition_type == "min_active":
            count = condition["count"]
            satisfied = active_count >= count
            message = (f"min_active: {active_count}/{len(cells)} active "
                       f"(need >= {count})")
        elif condition_type == "max_active":
            count = condition["count"]
            satisfied = active_count <= count
            message = (f"max_active: {active_count}/{len(cells)} active "
                       f"(need <= {count})")
        elif condition_type == "exactly_active":
            count = condition["count"]
            satisfied = active_count == count
            message = (f"exactly_active: {active_count}/{len(cells)} active "
                       f"(need == {count})")
        elif condition_type == "interval_active":
            min_count = condition["min"]
            max_count = condition["max"]
            satisfied = min_count <= active_count <= max_count
            message = (f"interval_active: {active_count}/{len(cells)} active "
                       f"(need {min_count}–{max_count})")
        else:  # percentage_active
            percentage = condition["percentage"]
            actual_pct = (active_count / len(cells)) * 100
            satisfied = actual_pct >= percentage
            message = (f"percentage_active: {actual_pct:.1f}% active "
                       f"(need >= {percentage}%)")

        return satisfied, message

    # ------------------------------------------------------------------
    # All-cells conditions
    # ------------------------------------------------------------------
    if condition_type == "cell_must_be_active":
        cells = condition["cells"]
        inactive = [c for c in cells if not isActive(c, scale, threshold, octaves, amplitudeDecay)]
        satisfied = len(inactive) == 0
        message = (
            f"cell_must_be_active: {len(cells) - len(inactive)}/{len(cells)} active" +
            (f" (inactive: {inactive})" if inactive else "")
        )
        return satisfied, message

    if condition_type == "cell_must_be_inactive":
        cells = condition["cells"]
        active = [c for c in cells if isActive(c, scale, threshold, octaves, amplitudeDecay)]
        satisfied = len(active) == 0
        message = (
            f"cell_must_be_inactive: {len(cells) - len(active)}/{len(cells)} inactive" +
            (f" (still active: {active})" if active else "")
        )
        return satisfied, message

    raise ValueError(f"Unknown condition type: {condition_type!r}")


# ---------------------------------------------------------------------------
# Parameter testing
# ---------------------------------------------------------------------------


def testParameters(
    conditions: list[dict[str,
                          Any]],
    scale: int,
    threshold: float,
    octaves: int = 3,
    amplitudeDecay: float = 0.5,
) -> tuple[bool,
           list[str],
           list[str | None]]:
    """
    Evaluate all conditions and return an aggregate result.

    Args:
        conditions: List of condition specification dictionaries.
        scale: Noise scale parameter.
        threshold: Activation threshold in [0, 1].
        octaves: Number of noise octaves.
        amplitudeDecay: Per-octave amplitude multiplier.

    Returns:
        ``(all_satisfied, messages, comments)`` where *all_satisfied* is
        ``True`` only when every condition passes, *messages* is a list of
        per-condition result strings, and *comments* is the optional
        ``"comment"`` field from each condition (``None`` if absent).
    """
    messages: list[str] = []
    comments: list[str | None] = []
    all_satisfied = True

    for condition in conditions:
        satisfied, message = checkCondition(condition, scale, threshold, octaves, amplitudeDecay)
        messages.append(message)
        comments.append(condition.get("comment"))
        if not satisfied:
            all_satisfied = False

    return all_satisfied, messages, comments


def testCombination(
    args: tuple[list[dict[str,
                          Any]],
                int,
                float,
                int,
                float],
) -> tuple[bool,
           list[str],
           list[str | None],
           int,
           float,
           int,
           float]:
    """
    Worker function: evaluate one parameter combination.

    Designed for use with ``multiprocessing.Pool.imap_unordered``.  Each
    worker process calls ``init_engine()`` in its Pool initializer (see
    ``main``), so this function can safely write to the SQLite cache without
    sharing connections across processes.

    Args:
        args: ``(conditions, scale, threshold, octaves, amplitudeDecay)``
            packed into a single tuple for ``imap_unordered`` compatibility.

    Returns:
        ``(satisfied, messages, comments, scale, threshold, octaves,
        amplitudeDecay)`` — the full parameter set is echoed back so the
        caller can identify the winning combination without maintaining
        external state.
    """
    conditions, scale, threshold, octaves, amplitude_decay = args
    satisfied, messages, comments = testParameters(conditions, scale, threshold, octaves, amplitude_decay)
    return satisfied, messages, comments, scale, threshold, octaves, amplitude_decay


# ---------------------------------------------------------------------------
# State-space generation
# ---------------------------------------------------------------------------


def generateStateSpace(state_space: dict[str, dict[str, float]],) -> list[tuple[int, float, int, float]]:
    """
    Enumerate all ``(scale, threshold, octaves, amplitudeDecay)`` combinations.

    Ranges are specified as ``{"min": …, "max": …, "step": …}`` dictionaries
    in *state_space*.  The *octaves* and *amplitudeDecay* axes are optional;
    they default to a single value (3 and 0.5, respectively) when absent.

    A small epsilon (1e-9) is added to the upper bound of floating-point
    ranges before comparison to avoid dropping the final value due to
    accumulated floating-point error.

    Args:
        state_space: Dictionary with ``"scale"``, ``"threshold"``, and
            optionally ``"octaves"`` and ``"amplitudeDecay"`` range configs.

    Returns:
        List of ``(scale, threshold, octaves, amplitudeDecay)`` tuples
        representing the full Cartesian product of the configured ranges.
    """
    def _int_range(cfg: dict, default_step: int = 1) -> list[int]:
        return list(range(
            int(cfg["min"]),
            int(cfg["max"]) + 1,
            int(cfg.get("step",
                        default_step)),
        ))

    def _float_range(cfg: dict, default_step: float = 0.05) -> list[float]:
        values: list[float] = []
        step = float(cfg.get("step", default_step))
        current = float(cfg["min"])
        upper = float(cfg["max"])
        while current <= upper + 1e-9:
            values.append(round(current, 10))
            current += step
        return values

    scale_values = _int_range(state_space["scale"])
    threshold_values = _float_range(state_space["threshold"])
    octaves_values = _int_range(state_space.get("octaves",
                                                {
                                                    "min": 3,
                                                    "max": 3,
                                                    "step": 1
                                                }))
    amplitude_decay_values = _float_range(state_space.get("amplitudeDecay",
                                                          {
                                                              "min": 0.5,
                                                              "max": 0.5,
                                                              "step": 0.1
                                                          }))

    return [
        (scale,
         threshold,
         octaves,
         amplitude_decay)
        for scale in scale_values
        for threshold in threshold_values
        for octaves in octaves_values
        for amplitude_decay in amplitude_decay_values
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """
    Orchestrate the parameter search.

    Steps:

    1. Parse CLI arguments.
    2. Load the JSON configuration file.
    3. Ensure the SQLite cache schema exists (main-process engine).
    4. Generate the full Cartesian product of parameter combinations.
    5. Distribute work across a ``Pool`` of worker processes, each with its
       own SQLAlchemy engine (see ``init_engine``).
    6. Consume results via ``imap_unordered``; stop on the first satisfying
       combination, then terminate the pool.
    7. Print the solution or a failure summary.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Grid-search Perlin noise parameters against S2 cell activation "
            "conditions defined in a JSON configuration file."
        )
    )
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to the JSON configuration file.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Skip reading from and writing to the noise cache.",
    )

    args = parser.parse_args()

    # Ensure cache table exists before forking workers.
    Base.metadata.create_all(bind=engine)

    config = loadConfig(args.config)
    conditions: list[dict[str, Any]] = config["conditions"]
    state_space: dict = config["state_space"]

    all_cells: set[str] = set()
    for condition in conditions:
        if "cells" in condition:
            all_cells.update(condition["cells"])

    combinations = generateStateSpace(state_space)
    total = len(combinations)

    print(f"Testing {len(all_cells)} cells with {len(conditions)} conditions")
    print(f"State space: {total} parameter combinations\n")

    work_items = [
        (conditions,
         scale,
         threshold,
         octaves,
         amplitude_decay) for scale, threshold, octaves, amplitude_decay in combinations
    ]

    solution: dict[str, Any] | None = None

    # Each worker calls init_engine() so it owns its own SQLAlchemy connection
    # pool.  Combined with WAL mode (set in database.py), this prevents
    # "database is locked" errors from concurrent cache writes.
    with Pool(initializer=init_engine) as pool:
        for (
            satisfied,
            messages,
            comments,
            scale,
            threshold,
            octaves,
            amplitude_decay,
        ) in tqdm(
            pool.imap_unordered(testCombination,
                                work_items),
            total=total,
            desc="Testing parameters",
        ):
            if satisfied and solution is None:
                solution = {
                    "scale": scale,
                    "threshold": threshold,
                    "octaves": octaves,
                    "amplitudeDecay": amplitude_decay,
                    "messages": messages,
                    "comments": comments,
                }
                # Terminate after capturing the solution to avoid torn writes.
                pool.terminate()
                break

    if solution:
        print("\n✓ Found solution!")
        print(f"  scale:         {solution['scale']}")
        print(f"  threshold:     {solution['threshold']}")
        print(f"  octaves:       {solution['octaves']}")
        print(f"  amplitudeDecay:{solution['amplitudeDecay']}")
        print("\nCondition results:")
        for msg, comment in zip(solution["messages"], solution["comments"]):
            suffix = f" — {comment}" if comment else ""
            print(f"  ✓ {msg}{suffix}")
    else:
        print(f"\n✗ No solution found in {total} combinations.")
        print("Consider widening state_space or relaxing conditions.")


if __name__ == "__main__":
    main()
