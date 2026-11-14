"""
Made-up training plans for the tests, in the plan file format of
kishin_trails/plan_file.py.
"""

from __future__ import annotations

import copy

TICKS = [{"type": "CROSS_TRAINING"}, {"type": "LEG_DAY"}, {"type": "YOGA"}, {"type": "YOGA"}, {"type": "YOGA"}]


def week(phase: str, longRunKm: float) -> dict:
    """One week: a long run of ``longRunKm``, a 30-minute run and the five tick items."""
    return {
        "phase": phase,
        "trainings": [
            {"type": "EXPLORATORY_LONG_RUN", "segments": [{"type": "EASY", "distance_km": longRunKm, "rpe": [3, 5]}]},
            {"type": "FUNDAMENTAL_RUN", "segments": [{"type": "EASY", "duration_min": 30, "rpe": [3, 5]}]},
            *copy.deepcopy(TICKS),
        ],
    }


def examplePlan() -> dict:
    """A two-week plan: long runs of 13 and 8 km."""
    return {
        "name": "Example Plan",
        "goal_type": None,
        "target_fat_ratio": 20.0,
        "target_muscle_mass_kg": None,
        "weeks": [week("BASE", 13), week("RECOVERY", 8)],
    }
