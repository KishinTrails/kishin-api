"""
SQLAlchemy models for training plans.

A Segment is one effort block of a run. A Training is one item of a week: a run
made of segments, or an item the player ticks. A PlanWeek gives a week its phase.
A Plan is an ordered list of weeks and trainings. ActivePlan, a single row,
records which plan the player follows and since when. A TrainingCompletion records that a training
is done: a run with the Garmin activity and RPE that completed it, a tick item
alone.

``main.py`` and the ``kishin db init`` command import this module, so
``Base.metadata.create_all`` creates these tables. The enums are in
``training_types.py``.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kishin_trails.database import Base
from kishin_trails.training_types import (
    TICK_TYPES,
    WEEK_COMPOSITION,
    SegmentType,
    TrainingType,
    WeekPhase,
)


class Plan(Base):
    """An ordered collection of weeks and trainings.

    Attributes:
        id: Primary key.
        name: Human-readable name.
        goal_type: Label of the plan's goal. The allowed values are not decided.
        target_fat_ratio: Body fat percentage to reach by the end of the plan.
        target_muscle_mass_kg: Muscle mass in kg to reach by the end of the plan.
        weeks: One PlanWeek per week.
        trainings: Trainings of every week.
    """

    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    goal_type: Mapped[str | None] = mapped_column(String)
    target_fat_ratio: Mapped[float | None] = mapped_column(Float)
    target_muscle_mass_kg: Mapped[float | None] = mapped_column(Float)

    weeks: Mapped[list[PlanWeek]] = relationship(
        "PlanWeek",
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="PlanWeek.week_number",
    )
    trainings: Mapped[list[Training]] = relationship(
        "Training",
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by=lambda: [Training.week_number, Training.position],
    )


class PlanWeek(Base):
    """The phase of one week of a plan.

    Attributes:
        id: Primary key.
        plan_id: Parent plan.
        week_number: Week within the plan (1-indexed).
        phase: BASE, BUILD, PEAK or RECOVERY.
    """

    __tablename__ = "plan_weeks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("plans.id"), nullable=False, index=True)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[WeekPhase] = mapped_column(Enum(WeekPhase, native_enum=False), nullable=False)

    plan: Mapped[Plan] = relationship("Plan", back_populates="weeks")

    __table_args__ = (
        UniqueConstraint("plan_id", "week_number", name="uix_plan_week"),
        CheckConstraint("week_number >= 1", name="ck_plan_week_number"),
    )


class Training(Base):
    """One item of a week: a run made of segments, or a tick item without segments.

    Attributes:
        id: Primary key.
        plan_id: Parent plan.
        week_number: Week within the plan (1-indexed).
        position: Order within the week (1-indexed).
        training_type: Category of the item.
        segments: Ordered segments; empty for tick items.
    """

    __tablename__ = "trainings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("plans.id"), nullable=False, index=True)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    training_type: Mapped[TrainingType] = mapped_column(Enum(TrainingType, native_enum=False), nullable=False)

    plan: Mapped[Plan] = relationship("Plan", back_populates="trainings")
    segments: Mapped[list[Segment]] = relationship(
        "Segment",
        back_populates="training",
        cascade="all, delete-orphan",
        order_by="Segment.position",
    )
    completion: Mapped[TrainingCompletion | None] = relationship(
        "TrainingCompletion",
        back_populates="training",
        cascade="all, delete-orphan",
        uselist=False,
    )

    __table_args__ = (
        UniqueConstraint("plan_id", "week_number", "position", name="uix_training_week_position"),
        CheckConstraint("week_number >= 1", name="ck_training_week_number"),
        CheckConstraint("position >= 1", name="ck_training_position"),
    )

    @property
    def total_duration_sec(self) -> int:
        """Sum of ``duration_sec`` over the timed segments."""
        return sum(segment.duration_sec for segment in self.segments if segment.duration_sec is not None)

    @property
    def total_distance_km(self) -> float:
        """Sum of ``target_distance_km`` over the distance segments."""
        return sum(
            segment.target_distance_km for segment in self.segments if segment.target_distance_km is not None
        )


class Segment(Base):
    """One effort block of a run.

    Exactly one of ``duration_sec`` and ``target_distance_km`` is set.
    ``target_pace_min_km`` is shown to the player only; completion and Willpower
    do not use it.

    Attributes:
        id: Primary key.
        training_id: Parent training.
        position: Order within the training (1-indexed).
        segment_type: Nature of the effort.
        duration_sec: Duration in seconds, or None for a distance segment.
        target_distance_km: Distance in km, or None for a timed segment.
        target_rpe_min: Lower bound of the target RPE (1-10).
        target_rpe_max: Upper bound of the target RPE (1-10).
        target_pace_min_km: Target pace in min/km, for example 5.5 for 5:30/km.
    """

    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    training_id: Mapped[int] = mapped_column(Integer, ForeignKey("trainings.id"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    segment_type: Mapped[SegmentType] = mapped_column(Enum(SegmentType, native_enum=False), nullable=False)
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    target_distance_km: Mapped[float | None] = mapped_column(Float)
    target_rpe_min: Mapped[int | None] = mapped_column(Integer)
    target_rpe_max: Mapped[int | None] = mapped_column(Integer)
    target_pace_min_km: Mapped[float | None] = mapped_column(Float)

    training: Mapped[Training] = relationship("Training", back_populates="segments")

    __table_args__ = (
        UniqueConstraint("training_id", "position", name="uix_segment_position"),
        CheckConstraint("position >= 1", name="ck_segment_position"),
        CheckConstraint(
            "(duration_sec IS NULL) != (target_distance_km IS NULL)",
            name="ck_segment_duration_xor_distance",
        ),
        CheckConstraint("duration_sec IS NULL OR duration_sec > 0", name="ck_segment_duration"),
        CheckConstraint("target_distance_km IS NULL OR target_distance_km > 0", name="ck_segment_distance"),
        CheckConstraint(
            "target_rpe_min IS NULL OR target_rpe_min BETWEEN 1 AND 10",
            name="ck_segment_rpe_min",
        ),
        CheckConstraint(
            "target_rpe_max IS NULL OR target_rpe_max BETWEEN 1 AND 10",
            name="ck_segment_rpe_max",
        ),
        CheckConstraint(
            "target_rpe_min IS NULL OR target_rpe_max IS NULL OR target_rpe_min <= target_rpe_max",
            name="ck_segment_rpe_order",
        ),
    )


class TrainingCompletion(Base):
    """That a training is done.

    A run carries the Garmin activity that completed it and the RPE the player
    entered; a tick item carries neither. ``activity_id`` points into the
    health-sync database, so it has no foreign key.

    Attributes:
        id: Primary key.
        training_id: The training; completed at most once.
        completed_at: When the player marked it done (UTC).
        activity_id: GarminDB activity id, or None for a tick item. Completes at most one training.
        rpe: RPE entered by the player (1-10), or None for a tick item.
    """

    __tablename__ = "training_completions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    training_id: Mapped[int] = mapped_column(Integer, ForeignKey("trainings.id"), nullable=False, unique=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    activity_id: Mapped[str | None] = mapped_column(String, unique=True)
    rpe: Mapped[int | None] = mapped_column(Integer)

    training: Mapped[Training] = relationship("Training", back_populates="completion")

    __table_args__ = (CheckConstraint("rpe IS NULL OR rpe BETWEEN 1 AND 10", name="ck_completion_rpe"),)


#: Primary key of the only ActivePlan row.
ACTIVE_PLAN_ID = 1


class ActivePlan(Base):
    """The plan the player follows, and the Monday it started. The table holds at most one row.

    Attributes:
        id: Always ``ACTIVE_PLAN_ID`` (1); the check constraint keeps the table to one row.
        plan_id: The plan followed.
        start_date: The Monday the plan began.
    """

    __tablename__ = "active_plan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("plans.id"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)

    plan: Mapped[Plan] = relationship("Plan")

    __table_args__ = (CheckConstraint("id = 1", name="ck_active_plan_single_row"),)

    def currentWeek(self, today: date) -> int:
        """Week of the plan that contains ``today`` (1-indexed)."""
        return (today - self.start_date).days // 7 + 1


def planProblems(plan: Plan) -> list[str]:
    """Lists the rules of a plan that row constraints cannot check.

    - Each week holds the trainings of ``WEEK_COMPOSITION``.
    - Tick items have no segments; runs have at least one.
    - Each week used by a training has a PlanWeek.

    Returns:
        One message per broken rule; an empty list when the plan is valid.
    """
    problems: list[str] = []

    weeksWithPhase = {week.week_number for week in plan.weeks}
    trainingsByWeek: dict[int, list[Training]] = {}
    for training in plan.trainings:
        trainingsByWeek.setdefault(training.week_number, []).append(training)

    for weekNumber in sorted(trainingsByWeek):
        trainings = trainingsByWeek[weekNumber]

        if weekNumber not in weeksWithPhase:
            problems.append(f"week {weekNumber}: no PlanWeek")

        counts = Counter(training.training_type for training in trainings)
        for trainingType, expected in WEEK_COMPOSITION.items():
            if counts[trainingType] != expected:
                problems.append(
                    f"week {weekNumber}: {counts[trainingType]} {trainingType.value}, expected {expected}"
                )

        for training in trainings:
            label = f"week {weekNumber} position {training.position} ({training.training_type.value})"
            if training.training_type in TICK_TYPES and training.segments:
                problems.append(f"{label}: a tick item has segments")
            if training.training_type not in TICK_TYPES and not training.segments:
                problems.append(f"{label}: a run has no segments")

    return problems
