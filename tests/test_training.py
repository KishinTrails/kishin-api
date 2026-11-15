"""
Tests for the training plan models in kishin_trails.training.
"""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from kishin_trails.training import (
    ACTIVE_PLAN_ID,
    ActivePlan,
    Plan,
    PlanWeek,
    Segment,
    SegmentType,
    Training,
    TrainingType,
    WeekPhase,
    planProblems,
)


def _easy(position: int = 1, **fields) -> Segment:
    return Segment(position=position, segment_type=SegmentType.EASY, target_rpe_min=3, target_rpe_max=5, **fields)


def _week(weekNumber: int, longRunKm: float) -> list[Training]:
    """The seven trainings of one week, in the order of the weekly contract."""
    trainings = [
        Training(
            week_number=weekNumber,
            position=1,
            training_type=TrainingType.EXPLORATORY_LONG_RUN,
            segments=[_easy(target_distance_km=longRunKm)],
        ),
        Training(
            week_number=weekNumber,
            position=2,
            training_type=TrainingType.FUNDAMENTAL_RUN,
            segments=[_easy(duration_sec=1800)],
        ),
        Training(week_number=weekNumber, position=3, training_type=TrainingType.CROSS_TRAINING),
        Training(week_number=weekNumber, position=4, training_type=TrainingType.LEG_DAY),
    ]
    trainings += [
        Training(week_number=weekNumber, position=position, training_type=TrainingType.YOGA)
        for position in (5, 6, 7)
    ]
    return trainings


@pytest.fixture
def plan(db_session) -> Plan:
    examplePlan = Plan(
        name="Example Plan",
        target_fat_ratio=20.0,
        target_muscle_mass_kg=40.0,
        weeks=[PlanWeek(week_number=1, phase=WeekPhase.BASE)],
        trainings=_week(1, 10.0),
    )
    db_session.add(examplePlan)
    db_session.commit()
    return examplePlan


def test_plan_round_trip(db_session, plan):
    db_session.expire_all()
    loaded = db_session.get(Plan, plan.id)

    assert loaded.name == "Example Plan"
    assert loaded.goal_type is None
    assert [week.phase for week in loaded.weeks] == [WeekPhase.BASE]
    assert [training.position for training in loaded.trainings] == [1, 2, 3, 4, 5, 6, 7]
    assert loaded.trainings[0].training_type is TrainingType.EXPLORATORY_LONG_RUN
    assert loaded.trainings[0].segments[0].segment_type is SegmentType.EASY


def test_trainings_ordered_by_week_then_position(db_session, plan):
    plan.weeks.append(PlanWeek(week_number=2, phase=WeekPhase.BASE))
    plan.trainings.extend(reversed(_week(2, 11.0)))
    db_session.commit()
    db_session.expire_all()

    loaded = db_session.get(Plan, plan.id)
    assert [(training.week_number, training.position) for training in loaded.trainings
            ] == [(week, position) for week in (1, 2) for position in range(1, 8)]


def test_totals():
    training = Training(
        week_number=1,
        position=1,
        training_type=TrainingType.EXPLORATORY_LONG_RUN,
        segments=[
            _easy(1, target_distance_km=5.0),
            _easy(2, duration_sec=600),
            _easy(3, target_distance_km=2.5),
            _easy(4, duration_sec=300),
        ],
    )
    assert training.total_distance_km == 7.5
    assert training.total_duration_sec == 900


def test_totals_without_segments():
    training = Training(week_number=1, position=3, training_type=TrainingType.LEG_DAY)
    assert training.total_distance_km == 0
    assert training.total_duration_sec == 0


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {
            "duration_sec": 600, "target_distance_km": 2.0
        },
        {
            "duration_sec": 0
        },
        {
            "target_distance_km": -1.0
        },
        {
            "duration_sec": 600, "target_rpe_min": 0
        },
        {
            "duration_sec": 600, "target_rpe_max": 11
        },
        {
            "duration_sec": 600, "target_rpe_min": 6, "target_rpe_max": 5
        },
    ],
    ids=["neither", "both", "zero-duration", "negative-distance", "rpe-min-0", "rpe-max-11", "rpe-min-above-max"],
)
def test_segment_check_constraints(db_session, plan, fields):
    training = plan.trainings[0]
    fields.setdefault("target_rpe_min", None)
    fields.setdefault("target_rpe_max", None)
    training.segments.append(Segment(position=2, segment_type=SegmentType.TEMPO, **fields))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_segment_rpe_bounds_accepted(db_session, plan):
    plan.trainings[0].segments.append(
        Segment(position=2, segment_type=SegmentType.TEMPO, duration_sec=600, target_rpe_min=1, target_rpe_max=10)
    )
    db_session.flush()


def test_duplicate_training_position(db_session, plan):
    plan.trainings.append(Training(week_number=1, position=7, training_type=TrainingType.YOGA))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_duplicate_plan_week(db_session, plan):
    plan.weeks.append(PlanWeek(week_number=1, phase=WeekPhase.RECOVERY))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_duplicate_segment_position(db_session, plan):
    plan.trainings[0].segments.append(_easy(1, duration_sec=600))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_week_number_starts_at_one(db_session, plan):
    plan.weeks.append(PlanWeek(week_number=0, phase=WeekPhase.BASE))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_plan_deletes_children(db_session, plan):
    db_session.delete(plan)
    db_session.commit()
    assert db_session.query(Training).count() == 0
    assert db_session.query(Segment).count() == 0
    assert db_session.query(PlanWeek).count() == 0


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 1, 5), 1),
        (date(2026, 1, 11), 1),
        (date(2026, 1, 12), 2),
        (date(2026, 3, 29), 12),
    ],
)
def test_current_week(today, expected):
    active = ActivePlan(plan_id=1, start_date=date(2026, 1, 5))
    assert active.currentWeek(today) == expected


def test_active_plan_round_trip(db_session, plan):
    db_session.add(ActivePlan(plan_id=plan.id, start_date=date(2026, 1, 5)))
    db_session.commit()
    db_session.expire_all()
    active = db_session.get(ActivePlan, ACTIVE_PLAN_ID)
    assert active.plan.name == "Example Plan"


def test_active_plan_holds_one_row(db_session, plan):
    db_session.add(ActivePlan(id=2, plan_id=plan.id, start_date=date(2026, 1, 5)))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_plan_problems_valid(plan):
    assert not planProblems(plan)


def test_plan_problems_missing_plan_week(plan):
    plan.trainings.extend(_week(2, 11.0))
    assert planProblems(plan) == ["week 2: no PlanWeek"]


def test_plan_problems_wrong_composition(plan):
    plan.trainings[-1].training_type = TrainingType.LEG_DAY
    assert planProblems(plan) == [
        "week 1: 2 LEG_DAY, expected 1",
        "week 1: 2 YOGA, expected 3",
    ]


def test_plan_problems_segments(plan):
    plan.trainings[0].segments.clear()
    plan.trainings[2].segments.append(_easy(duration_sec=1200))
    assert planProblems(plan) == [
        "week 1 position 1 (EXPLORATORY_LONG_RUN): a run has no segments",
        "week 1 position 3 (CROSS_TRAINING): a tick item has segments",
    ]
