"""
Willpower earning and the Willpower cap multiplier.

The formulas follow the wiki page "Athlete Integration" (§8 and §9). Constants
the wiki does not fix (the fat axis weight, the decay per missed day, the partial
adherence bonus) are parameters without defaults.
"""

from __future__ import annotations

from collections.abc import Iterable

from kishin_trails.training_types import TrainingType

BASELINE = 1.0
GAIN = 0.5
MULTIPLIER_MIN = 0.0
MULTIPLIER_MAX = 1.5

FULL_BONUS = 1.5
NO_BONUS = 1.0
WILLPOWER_PER_KM = 10

#: Highest RPE of each adherence band: (full bonus, partial bonus). Above the
#: partial bound there is no bonus. The bands start at RPE 3.
RPE_BANDS = {
    TrainingType.EXPLORATORY_LONG_RUN: (5, 7),
    TrainingType.FUNDAMENTAL_RUN: (5, 6),
}
LOWEST_BANDED_RPE = 3


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


def targetMultiplier(fatProgress: float | None, muscleProgress: float | None, wFat: float) -> float:
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


def dailyMultipliers(targets: Iterable[float | None], initial: float, decay: float) -> list[float]:
    """Cap multiplier of each day.

    Args:
        targets: One entry per day: the target multiplier on a day with a
            measurement, None on a day without one.
        initial: The multiplier before the first day.
        decay: ``DECAY_PER_MISSED_DAY``, in ``[0, 1]``.

    Returns:
        One multiplier per day, each clamped to ``[MULTIPLIER_MIN, MULTIPLIER_MAX]``.
    """
    if not 0 <= decay <= 1:
        raise ValueError(f"decay must be in [0, 1], got {decay}")

    multipliers: list[float] = []
    previous = initial
    for target in targets:
        multiplier = target if target is not None else previous * (1 - decay)
        previous = clamp(multiplier, MULTIPLIER_MIN, MULTIPLIER_MAX)
        multipliers.append(previous)
    return multipliers


def adherenceBonus(trainingType: TrainingType, rpe: int, partialBonus: float) -> float:
    """Adherence bonus of a run for the RPE the player entered.

    Raises:
        ValueError: for a training type without RPE bands, or an RPE below 3,
            which the §8 table does not cover.
    """
    if trainingType not in RPE_BANDS:
        raise ValueError(f"{trainingType.value} earns no Willpower by itself")
    if not 1 <= rpe <= 10:
        raise ValueError(f"RPE must be in 1-10, got {rpe}")
    if rpe < LOWEST_BANDED_RPE:
        raise ValueError(f"RPE {rpe} is below the bands of the Willpower table")

    fullMax, partialMax = RPE_BANDS[trainingType]
    if rpe <= fullMax:
        return FULL_BONUS
    if rpe <= partialMax:
        return partialBonus
    return NO_BONUS


def earnedWillpower(distanceKm: float, trainingType: TrainingType, rpe: int, partialBonus: float) -> float:
    """``Distance_KM × 10 × Adherence_Bonus``."""
    return distanceKm * WILLPOWER_PER_KM * adherenceBonus(trainingType, rpe, partialBonus)
