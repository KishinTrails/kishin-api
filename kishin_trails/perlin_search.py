"""
Grid-searching Perlin noise parameters against S2 cell activation conditions.

Searches a configurable parameter space (scale, threshold, octaves, amplitude decay)
for a combination that satisfies a set of conditions on which S2 cells end up active.
The search is parallelised with ``multiprocessing.Pool``. Used by ``kishin noise
search`` (see ``kishin_trails/cli/noise.py``).

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
process owns its own SQLAlchemy connection pool. Combined with the WAL journal
mode configured in ``database.py``, this avoids ``database is locked`` errors
that arise when many processes write to the cache simultaneously.

The search stops at the *first* satisfying combination found by any worker.
``pool.terminate()`` is deferred until after the solution has been captured,
preventing torn cache writes.
"""

from __future__ import annotations

import json
from multiprocessing import Pool
from typing import Any

from tqdm import tqdm

from kishin_trails.database import Base, engine, init_engine
from kishin_trails.perlin import getNoiseForCell


def loadConfig(configPath: str) -> dict[str, Any]:
    """Loads and parses a JSON configuration file."""
    with open(configPath, "r", encoding="utf-8") as handle:
        return json.load(handle)


def isActive(
    cell: str,
    scale: int,
    threshold: float,
    octaves: int = 3,
    amplitudeDecay: float = 0.5,
) -> bool:
    """Whether an S2 cell's noise value is strictly greater than *threshold*."""
    return getNoiseForCell(cell, scale, octaves, amplitudeDecay) > threshold


def checkCondition(
    condition: dict[str, Any],
    scale: int,
    threshold: float,
    octaves: int = 3,
    amplitudeDecay: float = 0.5,
) -> tuple[bool, str]:
    """Evaluates a single condition against the given noise parameters.

    Returns:
        ``(satisfied, message)`` — a boolean result and a human-readable
        description of the outcome.

    Raises:
        ValueError: If ``condition["type"]`` is not a recognised type.
    """
    conditionType = condition["type"]

    aggregateTypes = {"min_active", "max_active", "exactly_active", "interval_active", "percentage_active"}
    if conditionType in aggregateTypes:
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
            minCount, maxCount = condition["min"], condition["max"]
            satisfied = minCount <= activeCount <= maxCount
            message = f"interval_active: {activeCount}/{len(cells)} active (need {minCount}-{maxCount})"
        else:  # percentage_active
            percentage = condition["percentage"]
            actualPct = (activeCount / len(cells)) * 100
            satisfied = actualPct >= percentage
            message = f"percentage_active: {actualPct:.1f}% active (need >= {percentage}%)"

        return satisfied, message

    if conditionType == "cell_must_be_active":
        cells = condition["cells"]
        inactive = [cell for cell in cells if not isActive(cell, scale, threshold, octaves, amplitudeDecay)]
        satisfied = len(inactive) == 0
        message = f"cell_must_be_active: {len(cells) - len(inactive)}/{len(cells)} active" + (
            f" (inactive: {inactive})" if inactive else ""
        )
        return satisfied, message

    if conditionType == "cell_must_be_inactive":
        cells = condition["cells"]
        active = [cell for cell in cells if isActive(cell, scale, threshold, octaves, amplitudeDecay)]
        satisfied = len(active) == 0
        message = f"cell_must_be_inactive: {len(cells) - len(active)}/{len(cells)} inactive" + (
            f" (still active: {active})" if active else ""
        )
        return satisfied, message

    raise ValueError(f"Unknown condition type: {conditionType!r}")


def testParameters(
    conditions: list[dict[str, Any]],
    scale: int,
    threshold: float,
    octaves: int = 3,
    amplitudeDecay: float = 0.5,
) -> tuple[bool, list[str], list[str | None]]:
    """Evaluates every condition and returns an aggregate result.

    Returns:
        ``(allSatisfied, messages, comments)`` — ``allSatisfied`` is ``True``
        only when every condition passes; ``comments`` carries each
        condition's optional ``"comment"`` field (``None`` if absent).
    """
    messages: list[str] = []
    comments: list[str | None] = []
    allSatisfied = True

    for condition in conditions:
        satisfied, message = checkCondition(condition, scale, threshold, octaves, amplitudeDecay)
        messages.append(message)
        comments.append(condition.get("comment"))
        if not satisfied:
            allSatisfied = False

    return allSatisfied, messages, comments


def testCombination(
    args: tuple[list[dict[str, Any]], int, float, int, float],
) -> tuple[bool, list[str], list[str | None], int, float, int, float]:
    """Worker function: evaluates one parameter combination.

    Designed for ``multiprocessing.Pool.imap_unordered``. Each worker calls
    ``init_engine()`` in its Pool initializer (see ``search``), so this can
    safely write to the SQLite cache without sharing connections across
    processes.
    """
    conditions, scale, threshold, octaves, amplitudeDecay = args
    satisfied, messages, comments = testParameters(conditions, scale, threshold, octaves, amplitudeDecay)
    return satisfied, messages, comments, scale, threshold, octaves, amplitudeDecay


def generateStateSpace(stateSpace: dict[str, dict[str, float]]) -> list[tuple[int, float, int, float]]:
    """Enumerates every ``(scale, threshold, octaves, amplitudeDecay)`` combination.

    Ranges are ``{"min": ..., "max": ..., "step": ...}`` dictionaries in
    *stateSpace*. ``octaves`` and ``amplitudeDecay`` are optional and default to
    a single value (3 and 0.5 respectively) when absent.
    """
    def intRange(cfg: dict, defaultStep: int = 1) -> list[int]:
        return list(range(int(cfg["min"]), int(cfg["max"]) + 1, int(cfg.get("step", defaultStep))))

    def floatRange(cfg: dict, defaultStep: float = 0.05) -> list[float]:
        values: list[float] = []
        step = float(cfg.get("step", defaultStep))
        current = float(cfg["min"])
        upper = float(cfg["max"])
        # A small epsilon avoids dropping the final value to floating-point error.
        while current <= upper + 1e-9:
            values.append(round(current, 10))
            current += step
        return values

    scaleValues = intRange(stateSpace["scale"])
    thresholdValues = floatRange(stateSpace["threshold"])
    octavesValues = intRange(stateSpace.get("octaves", {"min": 3, "max": 3, "step": 1}))
    amplitudeDecayValues = floatRange(stateSpace.get("amplitudeDecay", {"min": 0.5, "max": 0.5, "step": 0.1}))

    return [
        (scale, threshold, octaves, amplitudeDecay)
        for scale in scaleValues
        for threshold in thresholdValues
        for octaves in octavesValues
        for amplitudeDecay in amplitudeDecayValues
    ]


def search(configPath: str) -> tuple[dict[str, Any] | None, int]:
    """Runs the grid search described by the config file at *configPath*.

    Ensures the cache table exists before forking workers, then distributes the
    state space across a ``Pool``, stopping at the first combination that
    satisfies every condition.

    Returns:
        ``(solution, total)`` — ``solution`` is ``None`` if nothing in the
        state space satisfies every condition, otherwise a dict with the
        winning ``scale``/``threshold``/``octaves``/``amplitudeDecay`` plus
        the per-condition ``messages`` and ``comments``. ``total`` is the
        number of combinations in the searched state space.
    """
    # Ensure the cache table exists before forking workers.
    Base.metadata.create_all(bind=engine)

    config = loadConfig(configPath)
    conditions: list[dict[str, Any]] = config["conditions"]
    stateSpace: dict = config["state_space"]

    combinations = generateStateSpace(stateSpace)
    total = len(combinations)
    workItems = [(conditions, scale, threshold, octaves, amplitudeDecay)
                 for scale, threshold, octaves, amplitudeDecay in combinations]

    solution: dict[str, Any] | None = None

    # Each worker calls init_engine() so it owns its own SQLAlchemy connection
    # pool, which combined with WAL mode (database.py) prevents "database is
    # locked" errors from concurrent cache writes.
    with Pool(initializer=init_engine) as pool:
        for satisfied, messages, comments, scale, threshold, octaves, amplitudeDecay in tqdm(
            pool.imap_unordered(testCombination, workItems),
            total=total,
            desc="Testing parameters",
        ):
            if satisfied and solution is None:
                solution = {
                    "scale": scale,
                    "threshold": threshold,
                    "octaves": octaves,
                    "amplitudeDecay": amplitudeDecay,
                    "messages": messages,
                    "comments": comments,
                }
                # Terminate only after capturing the solution, to avoid torn writes.
                pool.terminate()
                break

    return solution, total
