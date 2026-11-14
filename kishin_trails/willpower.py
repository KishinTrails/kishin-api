"""
Willpower earning and the Willpower cap multiplier.

The formulas and constants follow the wiki page "Athlete Integration" (§8 and §9).
"""

from __future__ import annotations

from collections.abc import Iterable

BASELINE = 1.0
GAIN = 0.5
MULTIPLIER_MIN = 0.0
MULTIPLIER_MAX = 1.5

#: Weight of the fat axis; the muscle axis weighs ``1 - W_FAT``.
W_FAT = 0.5

#: Linear decay per day without a fat ratio or muscle mass reading: from 1.0 to
#: 0.5 in 14 days, to 0 in 28 days.
DECAY_PER_MISSED_DAY = 0.5 / 14

#: Multiplier on the plan's first day when that day has no reading. It equals
#: the target multiplier of a reading on that day, whose progress is 0.
START_MULTIPLIER = BASELINE

#: Willpower cap at a multiplier of 1.0.
BASE_CAP = 500

#: Moving average weights of the fat ratio and of the muscle mass.
FAT_ALPHA = 0.30
MUSCLE_ALPHA = 0.10

WILLPOWER_PER_KM = 10


def clamp(value: float, low: float, high: float) -> float:
    """``value`` limited to ``[low, high]``."""
    return max(low, min(high, value))


def ema(values: Iterable[float], alpha: float) -> list[float]:
    """Exponential moving average of ``values``, one output per input.

    The first output is the first value.
    """
    if not 0 < alpha <= 1:
        raise ValueError(f"alpha must be in (0, 1], got {alpha}")

    averages: list[float] = []
    for value in values:
        averages.append(value if not averages else alpha * value + (1 - alpha) * averages[-1])
    return averages


def axisProgress(start: float, current: float, target: float | None) -> float | None:
    """Progress from ``start`` towards ``target``, clamped to ``[-1, 1]``.

    ``(current - start) / (target - start)``. For the fat axis this equals
    ``(fat_start - fat_ema) / (fat_start - fat_target)``.

    Returns:
        None when there is no target or when the target equals the start, so the
        axis takes no part in the multiplier.
    """
    if target is None or target == start:
        return None
    return clamp((current - start) / (target - start), -1.0, 1.0)


def targetMultiplier(fatProgress: float | None, muscleProgress: float | None, wFat: float = W_FAT) -> float:
    """``BASELINE + GAIN × composition``, between 0.5 and 1.5.

    ``composition = wFat × fatProgress + (1 - wFat) × muscleProgress``. When one
    axis is None, the other takes the full weight. When both are None, the
    composition is 0.
    """
    if not 0 <= wFat <= 1:
        raise ValueError(f"wFat must be in [0, 1], got {wFat}")

    if fatProgress is None and muscleProgress is None:
        composition = 0.0
    elif fatProgress is None:
        composition = muscleProgress or 0.0
    elif muscleProgress is None:
        composition = fatProgress
    else:
        composition = wFat * fatProgress + (1 - wFat) * muscleProgress
    return BASELINE + GAIN * composition


def dailyMultipliers(
    targets: Iterable[float | None],
    initial: float = START_MULTIPLIER,
    decay: float = DECAY_PER_MISSED_DAY,
) -> list[float]:
    """Cap multiplier of each day.

    Args:
        targets: One entry per day: the target multiplier on a day with a
            reading, None on a day without one.
        initial: The multiplier before the first day.
        decay: Amount subtracted on each day without a reading.

    Returns:
        One multiplier per day, each clamped to ``[MULTIPLIER_MIN, MULTIPLIER_MAX]``.
    """
    if decay < 0:
        raise ValueError(f"decay must be at least 0, got {decay}")

    multipliers: list[float] = []
    previous = initial
    for target in targets:
        multiplier = target if target is not None else previous - decay
        previous = clamp(multiplier, MULTIPLIER_MIN, MULTIPLIER_MAX)
        multipliers.append(previous)
    return multipliers


def earnedWillpower(distanceKm: float) -> float:
    """``Distance_KM × 10``."""
    return distanceKm * WILLPOWER_PER_KM
