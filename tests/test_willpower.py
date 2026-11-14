"""
Tests for the Willpower formulas in kishin_trails.willpower.
"""

import pytest

from kishin_trails.willpower import (
    DECAY_PER_MISSED_DAY,
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


def test_target_multiplier_default_weight():
    assert targetMultiplier(1.0, 0.0) == pytest.approx(1.25)


def test_target_multiplier_rejects_weight():
    with pytest.raises(ValueError):
        targetMultiplier(0.0, 0.0, wFat=1.5)


def test_daily_multipliers_decay_and_restore():
    result = dailyMultipliers([1.2, None, None, 1.3], initial=1.0, decay=0.1)
    assert result == pytest.approx([1.2, 1.1, 1.0, 1.3])


def test_daily_multipliers_start_from_initial():
    assert dailyMultipliers([None], initial=1.0, decay=0.25) == [0.75]


def test_daily_multipliers_reach_zero():
    assert dailyMultipliers([None, None, None], initial=0.5, decay=0.2) == pytest.approx([0.3, 0.1, 0.0])


def test_daily_multipliers_clamped():
    assert dailyMultipliers([2.0, -1.0], initial=1.0, decay=0.0) == [1.5, 0.0]


def test_daily_multipliers_rejects_decay():
    with pytest.raises(ValueError):
        dailyMultipliers([None], initial=1.0, decay=-0.1)


def test_default_decay_halves_in_14_days():
    result = dailyMultipliers([None] * 28)
    assert result[13] == pytest.approx(0.5)
    assert result[27] == pytest.approx(0.0)


def test_default_decay_empties_full_multiplier_in_42_days():
    result = dailyMultipliers([None] * 42, initial=1.5)
    assert result[40] == pytest.approx(DECAY_PER_MISSED_DAY)
    assert result[41] == pytest.approx(0.0)


def test_earned_willpower():
    assert earnedWillpower(12.0) == pytest.approx(120.0)
    assert earnedWillpower(0.0) == 0.0
