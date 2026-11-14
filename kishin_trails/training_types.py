"""
Enums of the training plan models, kept apart from ``training.py`` so that code
using them does not register the training tables on ``Base.metadata``.
"""

import enum


class SegmentType(enum.Enum):
    """Nature of the effort of a segment."""

    EASY = "EASY"
    TEMPO = "TEMPO"


class TrainingType(enum.Enum):
    """Category of a training."""

    EXPLORATORY_LONG_RUN = "EXPLORATORY_LONG_RUN"
    FUNDAMENTAL_RUN = "FUNDAMENTAL_RUN"
    CROSS_TRAINING = "CROSS_TRAINING"
    LEG_DAY = "LEG_DAY"
    YOGA = "YOGA"


class WeekPhase(enum.Enum):
    """Phase of a plan week."""

    BASE = "BASE"
    BUILD = "BUILD"
    PEAK = "PEAK"
    RECOVERY = "RECOVERY"


#: Trainings the player ticks. They have no segments, no Garmin activity and no RPE.
TICK_TYPES = frozenset({TrainingType.CROSS_TRAINING, TrainingType.LEG_DAY, TrainingType.YOGA})

#: Trainings of one week, by type.
WEEK_COMPOSITION = {
    TrainingType.EXPLORATORY_LONG_RUN: 1,
    TrainingType.FUNDAMENTAL_RUN: 1,
    TrainingType.CROSS_TRAINING: 1,
    TrainingType.LEG_DAY: 1,
    TrainingType.YOGA: 3,
}
