"""
Reading a training plan from a local JSON file.

Plans are personal data: they live in a local file, outside the repositories,
and ``kishin plan import`` stores them in the game database. The format::

    {
      "name": "Example Plan",
      "goal_type": null,
      "target_fat_ratio": null,
      "target_muscle_mass_kg": null,
      "weeks": [
        {
          "phase": "BASE",
          "trainings": [
            {"type": "EXPLORATORY_LONG_RUN",
             "segments": [{"type": "EASY", "distance_km": 10, "rpe": [3, 5]}]},
            {"type": "FUNDAMENTAL_RUN",
             "segments": [{"type": "EASY", "duration_min": 30, "rpe": [3, 5]}]},
            {"type": "CROSS_TRAINING"}, {"type": "LEG_DAY"},
            {"type": "YOGA"}, {"type": "YOGA"}, {"type": "YOGA"}
          ]
        }
      ]
    }

Week numbers are the order of ``weeks``; positions are the order of
``trainings``. A segment has exactly one of ``distance_km`` and
``duration_min``, and optionally ``rpe`` (``[min, max]``) and ``pace_min_km``.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from kishin_trails.training import Plan, PlanWeek, Segment, Training, planProblems
from kishin_trails.training_types import SegmentType, TrainingType, WeekPhase


class PlanFileError(ValueError):
    """A plan file that cannot be read, with one message per problem."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


class SegmentIn(BaseModel):
    """One segment in the file."""

    model_config = ConfigDict(extra="forbid")

    type: SegmentType
    distance_km: float | None = Field(default=None, gt=0)
    duration_min: float | None = Field(default=None, gt=0)
    rpe: tuple[int, int] | None = None
    pace_min_km: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _check(self) -> SegmentIn:
        if (self.distance_km is None) == (self.duration_min is None):
            raise ValueError("a segment needs exactly one of distance_km and duration_min")
        if self.rpe is not None:
            low, high = self.rpe
            if not 1 <= low <= high <= 10:
                raise ValueError("rpe must be [min, max] with 1 <= min <= max <= 10")
        return self


class TrainingIn(BaseModel):
    """One training in the file."""

    model_config = ConfigDict(extra="forbid")

    type: TrainingType
    segments: list[SegmentIn] = []


class WeekIn(BaseModel):
    """One week in the file."""

    model_config = ConfigDict(extra="forbid")

    phase: WeekPhase
    trainings: list[TrainingIn]


class PlanIn(BaseModel):
    """The whole file."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    goal_type: str | None = None
    target_fat_ratio: float | None = None
    target_muscle_mass_kg: float | None = None
    weeks: list[WeekIn] = Field(min_length=1)


def _segment(position: int, segment: SegmentIn) -> Segment:
    low, high = segment.rpe if segment.rpe is not None else (None, None)
    return Segment(
        position=position,
        segment_type=segment.type,
        duration_sec=round(segment.duration_min * 60) if segment.duration_min is not None else None,
        target_distance_km=segment.distance_km,
        target_rpe_min=low,
        target_rpe_max=high,
        target_pace_min_km=segment.pace_min_km,
    )


def buildPlan(data: object, ownerId: int) -> Plan:
    """Builds an unsaved Plan from decoded JSON.

    Raises:
        PlanFileError: when the data does not follow the format or breaks a rule of ``planProblems``.
    """
    try:
        planIn = PlanIn.model_validate(data)
    except ValidationError as error:
        raise PlanFileError(
            [f"{'.'.join(str(part) for part in item['loc']) or '(file)'}: {item['msg']}" for item in error.errors()]
        ) from error

    plan = Plan(
        name=planIn.name,
        goal_type=planIn.goal_type,
        owner_id=ownerId,
        target_fat_ratio=planIn.target_fat_ratio,
        target_muscle_mass_kg=planIn.target_muscle_mass_kg,
    )
    for weekNumber, week in enumerate(planIn.weeks, start=1):
        plan.weeks.append(PlanWeek(week_number=weekNumber, phase=week.phase))
        for position, training in enumerate(week.trainings, start=1):
            plan.trainings.append(
                Training(
                    week_number=weekNumber,
                    position=position,
                    training_type=training.type,
                    segments=[_segment(index, segment) for index, segment in enumerate(training.segments, start=1)],
                )
            )

    problems = planProblems(plan)
    if problems:
        raise PlanFileError(problems)
    return plan


def readPlanFile(path: Path, ownerId: int) -> Plan:
    """Reads and checks a plan file.

    Raises:
        PlanFileError: when the file cannot be read, is not JSON, or is not a valid plan.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise PlanFileError([f"cannot read {path}: {error.strerror}"]) from error
    except json.JSONDecodeError as error:
        raise PlanFileError([f"{path} is not JSON: {error.msg} at line {error.lineno}"]) from error
    return buildPlan(data, ownerId)
