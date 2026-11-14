"""
Tests for the Willpower formulas in kishin_trails.willpower.
"""

import pytest

from kishin_trails.training_types import TrainingType
from kishin_trails.willpower import (
    adherenceBonus,
    axisProgress,
    dailyMultipliers,
    earnedWillpower,
    ema,
    targetMultiplier,
)


def test_ema():
    assert ema([10.0, 20.0, 20.0], 0.5) == [10.0, 15.0, 17.5]


def test_ema_alpha_one_follows_values():
    assert ema([1.0, 5.0, 3.0], 1.0) == [1.0, 5.0, 3.0]


def test_ema_empty():
    assert not ema([], 0.3)


@pytest.mark.parametrize("alpha", [0.0, -0.1, 1.1])
def test_ema_rejects_alpha(alpha):
    with pytest.raises(ValueError):
        ema([1.0], alpha)


@pytest.mark.parametrize(
    ("start", "current", "target", "expected"),
    [
        (25.0, 25.0, 20.0, 0.0),  # fat: no change
        (25.0, 22.5, 20.0, 0.5),  # fat: half way down
        (25.0, 20.0, 20.0, 1.0),  # fat: target reached
        (25.0, 18.0, 20.0, 1.0),  # fat: past the target, clamped
        (25.0, 27.5, 20.0, -0.5),  # fat: moving away
        (25.0, 40.0, 20.0, -1.0),  # fat: clamped at -1
        (35.0, 37.0, 40.0, 0.4),  # muscle: up 2 of 5 kg
        (35.0, 34.0, 40.0, -0.2),  # muscle: down 1 kg
    ],
)
def test_axis_progress(start, current, target, expected):
    assert axisProgress(start, current, target) == pytest.approx(expected)


def test_axis_progress_without_target():
    assert axisProgress(25.0, 22.0, None) is None


def test_axis_progress_target_equals_start():
    assert axisProgress(25.0, 22.0, 25.0) is None


@pytest.mark.parametrize(
    ("fat", "muscle", "expected"),
    [
        (0.0, 0.0, 1.0),
        (1.0, 1.0, 1.5),
        (-1.0, -1.0, 0.5),
        (1.0, 0.0, 1.15),  # 1.0 + 0.5 × 0.3
        (0.0, 1.0, 1.35),  # 1.0 + 0.5 × 0.7
        (None, 1.0, 1.5),  # muscle takes the full weight
        (-1.0, None, 0.5),  # fat takes the full weight
        (None, None, 1.0),
    ],
)
def test_target_multiplier(fat, muscle, expected):
    assert targetMultiplier(fat, muscle, wFat=0.3) == pytest.approx(expected)


def test_target_multiplier_rejects_weight():
    with pytest.raises(ValueError):
        targetMultiplier(0.0, 0.0, wFat=1.5)


def test_daily_multipliers_decay_and_restore():
    result = dailyMultipliers([1.2, None, None, 1.3], initial=1.0, decay=0.1)
    assert result == pytest.approx([1.2, 1.08, 0.972, 1.3])


def test_daily_multipliers_start_from_initial():
    assert dailyMultipliers([None], initial=1.0, decay=0.5) == [0.5]


def test_daily_multipliers_decay_to_zero():
    assert dailyMultipliers([None, None], initial=1.0, decay=1.0) == [0.0, 0.0]


def test_daily_multipliers_clamped():
    assert dailyMultipliers([2.0, -1.0], initial=1.0, decay=0.0) == [1.5, 0.0]


def test_daily_multipliers_rejects_decay():
    with pytest.raises(ValueError):
        dailyMultipliers([None], initial=1.0, decay=1.5)


@pytest.mark.parametrize(
    ("trainingType", "rpe", "expected"),
    [
        (TrainingType.EXPLORATORY_LONG_RUN, 3, 1.5),
        (TrainingType.EXPLORATORY_LONG_RUN, 5, 1.5),
        (TrainingType.EXPLORATORY_LONG_RUN, 6, 1.2),
        (TrainingType.EXPLORATORY_LONG_RUN, 7, 1.2),
        (TrainingType.EXPLORATORY_LONG_RUN, 8, 1.0),
        (TrainingType.FUNDAMENTAL_RUN, 5, 1.5),
        (TrainingType.FUNDAMENTAL_RUN, 6, 1.2),
        (TrainingType.FUNDAMENTAL_RUN, 7, 1.0),
        (TrainingType.FUNDAMENTAL_RUN, 10, 1.0),
    ],
)
def test_adherence_bonus(trainingType, rpe, expected):
    assert adherenceBonus(trainingType, rpe, partialBonus=1.2) == expected


@pytest.mark.parametrize("rpe", [0, 1, 2, 11])
def test_adherence_bonus_rejects_rpe(rpe):
    with pytest.raises(ValueError):
        adherenceBonus(TrainingType.EXPLORATORY_LONG_RUN, rpe, partialBonus=1.2)


def test_adherence_bonus_rejects_tick_item():
    with pytest.raises(ValueError):
        adherenceBonus(TrainingType.YOGA, 4, partialBonus=1.2)


def test_earned_willpower():
    assert earnedWillpower(12.0, TrainingType.EXPLORATORY_LONG_RUN, 4, partialBonus=1.2) == pytest.approx(180.0)
    assert earnedWillpower(6.0, TrainingType.FUNDAMENTAL_RUN, 8, partialBonus=1.2) == pytest.approx(60.0)
